"""Local GigSim (the course's simulator was not provided; see gigsim/README.md and docs/DATA_CARD.md).
Jobs: synthetic labelled jobs (data/mock_market/jobs.json) + real Kaggle postings (real_jobs.json).
Per-user account state (Connects, drafts, idempotency keys, threads, submissions) is persisted to one JSON
file with atomic writes, so "crash, restart, submitted exactly once" is demonstrable.

Client behaviour after a submission is SIMULATED (synthetic): outcome() turns proposal quality signals into
viewed / replied / interview / hired / lost, deterministically per (job, text), unfolding over wall-clock time."""
import hashlib, json, os, pathlib, re, time
import yaml
from agent.marketplace_port import ClientHistory, Job, MarketStats, Message, WriteResult

ROOT = pathlib.Path(__file__).resolve().parents[3]
DATA = ROOT / "data" / "mock_market"
STATE = pathlib.Path(os.getenv("MOCK_GIGSIM_STATE", "data/processed/mock_gigsim.json"))
STAGE_DELAY_S = float(os.getenv("GIGSIM_STAGE_DELAY_S", "60"))   # time between simulated client events
CLICHE = re.compile(r"\b(passionate|dear sir|hope this finds you|i am the best|guarantee)\b", re.I)


def _user() -> str:
    from mcp_servers.marketplace.guard import who   # the authenticated caller owns the account
    return who()


def _policy() -> dict:
    return yaml.safe_load((ROOT / "data" / "policy_pack" / "policy.yaml").read_text())


def _draw(*parts) -> float:
    return int(hashlib.sha256("|".join(map(str, parts)).encode()).hexdigest()[:8], 16) / 0xFFFFFFFF


def outcome(job: Job, client: ClientHistory | None, text: str, bid_usd: float | None) -> dict:
    """Simulated client response. Signals: requirement-word overlap, specific opening, length, price vs budget,
    client quality. Returns {"p_reply", "stages"}; stages is the full path the card will travel."""
    w = lambda s: set(re.findall(r"[a-z]{4,}", s.lower()))
    jw, tw = w(job.title + " " + job.description), w(text)
    overlap = len(jw & tw) / max(len(jw), 1)
    first = re.split(r"(?<=[.!?])\s", text.strip())[0] if text.strip() else ""
    specific = len(w(first) & w(job.title)) >= 1
    n = len(text.split())
    p = 0.10 + 0.6 * min(overlap, 0.5) + (0.10 if specific else -0.05) + (0.05 if 60 <= n <= 220 else -0.05)
    p -= 0.15 if CLICHE.search(text) else 0
    if bid_usd and job.budget_usd:
        p -= 0.2 if bid_usd > 1.3 * job.budget_usd else 0
    if client:
        p += 0.1 * client.hire_rate - (0.05 if not client.payment_verified else 0)
    p = max(0.02, min(0.9, p))
    d = _draw(job.id, text)
    if d >= p:
        return {"p_reply": round(p, 3), "stages": ["submitted", "viewed", "lost"] if d < p + 0.4 else ["submitted", "lost"]}
    hired = _draw(job.id, text, "hire") < 0.4
    return {"p_reply": round(p, 3), "stages": ["submitted", "viewed", "replied", "interview"] + (["hired"] if hired else ["lost"])}


class MockGigSim:
    def __init__(self, connects: int = 100):
        # every record carries its source ("synthetic" or "kaggle:<owner/slug>")
        self.jobs = [Job(**j) for f in ("jobs.json", "real_jobs.json") if (DATA / f).exists() for j in json.loads((DATA / f).read_text())]
        self.clients = {c["client_id"]: ClientHistory(**c) for f in ("clients.json", "real_clients.json") if (DATA / f).exists()
                        for c in json.loads((DATA / f).read_text())}
        self.stats = json.loads((ROOT / "data" / "market" / "market_stats.json").read_text())
        self.start_connects = connects
        self.all = json.loads(STATE.read_text()) if STATE.exists() else {}

    @property
    def s(self) -> dict:
        return self.all.setdefault(_user(), {"connects": self.start_connects, "seen": {}, "drafts": {}, "subs": {}, "msgs": {
            "t1": [Message(id="m1", thread_id="t1", sender="client", text="Hi! Saw your profile. Can you start Monday, and what would you charge for a small fix?").model_dump()]}})

    def _save(self):
        STATE.parent.mkdir(parents=True, exist_ok=True)
        tmp = STATE.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.all))
        tmp.replace(STATE)  # atomic: a crash never leaves half a file

    # --- reads ---
    def search_jobs(self, query="", limit=20, category=None):
        q = query.lower()
        return [j for j in self.jobs if q in (j.title + j.description).lower() and (not category or j.category == category)][:limit]

    def get_job(self, job_id):
        j = next((j for j in self.jobs if j.id == job_id), None)
        if j is None:
            raise KeyError(f"no job {job_id}")
        return j

    def get_client_history(self, client_id):
        return self.clients[client_id]

    def get_connects_balance(self):
        return self.s["connects"]

    def get_market_stats(self, category):
        return MarketStats(category=category, **self.stats[category])

    def list_messages(self, thread_id):
        self._advance()
        return [Message(**m) for m in self.s["msgs"].get(thread_id, [])]

    def list_threads(self) -> list[str]:
        self._advance()
        return list(self.s["msgs"])

    def proposal_events(self) -> list[dict]:
        """Current stage of every submission (drives the pipeline board)."""
        self._advance()
        return [{"submission_id": k, **{x: v[x] for x in ("job_id", "stage", "thread_id", "p_reply")}} for k, v in self.s["subs"].items()]

    def _advance(self):
        """Move each submission along its simulated path; a 'replied' stage posts a client message."""
        now, changed = time.time(), False
        for sid, sub in self.s["subs"].items():
            idx = min(int((now - sub["at"]) / STAGE_DELAY_S), len(sub["stages"]) - 1)
            if sub["stages"][idx] != sub["stage"]:
                sub["stage"], changed = sub["stages"][idx], True
                if sub["stage"] == "replied" and sub["thread_id"] not in self.s["msgs"]:
                    job = self.get_job(sub["job_id"])
                    self.s["msgs"][sub["thread_id"]] = [Message(id="m1", thread_id=sub["thread_id"], sender="client",
                        text=f"Thanks for your proposal on '{job.title}'. Could we do a short call this week to discuss?").model_dump()]
        if changed:
            self._save()

    # --- writes (idempotent by key; dry_run has no side effects) ---
    def _write(self, key, dry_run, payload, cost, apply):
        if key in self.s["seen"]:
            return WriteResult(**self.s["seen"][key]).model_copy(update={"replayed": True})
        if dry_run:
            return WriteResult(ok=True, dry_run=True, would_send=payload, connects_cost=cost)
        if cost > self.s["connects"]:
            return WriteResult(ok=False, dry_run=False, would_send=payload, connects_cost=cost)
        self.s["connects"] -= cost
        res = WriteResult(ok=True, dry_run=False, would_send=payload, connects_cost=cost, id=apply())
        self.s["seen"][key] = res.model_dump()
        self._save()  # state and key land together in one atomic write
        return res

    def connects_cost(self, job_id) -> int:
        """Per-job cost when the posting states one (real data), else the policy-pack default."""
        job = next((j for j in self.jobs if j.id == job_id), None)
        return (job.connects_cost if job and job.connects_cost else None) or _policy()["limits"]["connects_per_bid"]

    def create_proposal_draft(self, job_id, text, *, idem_key, dry_run=False, bid_usd=None):
        def apply():
            did = f"d{len(self.s['drafts']) + 1}"
            self.s["drafts"][did] = {"job_id": job_id, "text": text, "bid_usd": bid_usd}
            return did
        return self._write(idem_key, dry_run, {"job_id": job_id, "text": text, "bid_usd": bid_usd,
                                               "connects_cost_on_submit": self.connects_cost(job_id)}, 0, apply)

    def submit_proposal(self, draft_id, *, idem_key, dry_run=False):
        if draft_id not in self.s["drafts"]:
            raise KeyError(draft_id)
        d = self.s["drafts"][draft_id]

        def apply():
            sid = f"sub-{draft_id}"
            job = self.get_job(d["job_id"])
            o = outcome(job, self.clients.get(job.client_id), d["text"], d.get("bid_usd"))
            self.s["subs"][sid] = {"job_id": d["job_id"], "at": time.time(), "stage": "submitted", "thread_id": f"t-{sid}", **o}
            return sid
        return self._write(idem_key, dry_run, {"draft_id": draft_id}, self.connects_cost(d["job_id"]), apply)

    def send_message(self, thread_id, text, *, idem_key, dry_run=False):
        def apply():
            msgs = self.s["msgs"].setdefault(thread_id, [])
            m = Message(id=f"m{len(msgs) + 1}", thread_id=thread_id, sender="freelancer", text=text)
            msgs.append(m.model_dump())
            return m.id
        return self._write(idem_key, dry_run, {"thread_id": thread_id, "text": text}, 0, apply)


def test_outcome_is_deterministic_and_rewards_relevance():
    j = Job(id="z", title="React dashboard", description="Build a react dashboard with charts and auth", client_id="c", posted_at="x", budget_usd=500)
    good = "Your react dashboard with charts and auth is close to one I shipped last month. I would start with the auth flow and charts."
    bad = "Dear sir, I am passionate about all kinds of work and can do anything you need."
    assert outcome(j, None, good, 500) == outcome(j, None, good, 500)
    assert outcome(j, None, good, 500)["p_reply"] > outcome(j, None, bad, 500)["p_reply"]
