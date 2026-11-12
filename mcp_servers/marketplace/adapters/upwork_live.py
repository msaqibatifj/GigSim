"""Live Upwork adapter (A4): the official Upwork MCP server at https://mcp.upwork.com/mcp over Streamable HTTP via
MultiServerMCPClient, with the signed-in user's OAuth token (stored encrypted, apps/api/auth). Mapped onto the same
marketplace port as GigSim, so the graph cannot tell which marketplace it is using.

Platform rules enforced here (R9, A4):
- drafts only: create_proposal_draft makes an Upwork draft; submit_proposal NEVER spends Connects from GigBid,
  it returns "confirm on Upwork" (the user submits there); send_message saves a message draft
- no browser automation, no cookies, no page scraping: only the official MCP tools
- reads are rate-limited by the marketplace server's limiter and scheduled conservatively (docs/RUNBOOK.md)

Tool names on the Upwork server are mapped in agent/config.yaml `upwork.tools` so a renamed upstream tool is a config
edit. shortcut: mapping not verified against a live account (none available); check names with `list_tools` first."""
import asyncio, json, os, time
from agent.config import cfg
from agent.marketplace_port import ClientHistory, Job, MarketStats, Message, WriteResult

URL = os.getenv("UPWORK_MCP_URL", "https://mcp.upwork.com/mcp")


def _token(user: str) -> str:
    from apps.api.auth.users import load_token
    tok = load_token(user)
    if not tok:
        raise PermissionError("Upwork is not connected for this user (Settings > Connect Upwork)")
    if tok.get("expires_in") and time.time() > tok["obtained_at"] + tok["expires_in"] - 60:
        tok = _refresh(user, tok)
    return tok["access_token"]


def _refresh(user: str, tok: dict) -> dict:
    """Silent refresh_token grant; any failure means the user must reconnect (never loop or retry blindly)."""
    import httpx
    from apps.api.auth.users import save_token
    if not tok.get("refresh_token"):
        raise PermissionError("Upwork token expired: reconnect in Settings")
    data = {"grant_type": "refresh_token", "refresh_token": tok["refresh_token"], "client_id": tok["client_id"], "resource": URL}
    if os.getenv("UPWORK_CLIENT_SECRET"):
        data["client_secret"] = os.environ["UPWORK_CLIENT_SECRET"]
    try:
        r = httpx.post(tok["token_url"], data=data, timeout=15)
        r.raise_for_status()
    except httpx.HTTPError:
        raise PermissionError("Upwork token expired and refresh failed: reconnect in Settings") from None
    new = {**tok, **r.json(), "obtained_at": time.time()}   # keeps the old refresh_token if the server does not rotate it
    save_token(user, "upwork", new)
    return new


def _run(coro):
    """Port methods are sync (FastMCP runs them in a worker thread), the MCP client is async."""
    return asyncio.run(coro)


class UpworkLive:
    def __init__(self):
        self.map = cfg().get("upwork", {}).get("tools", {})
        self._seen: dict[str, WriteResult] = {}

    async def _call(self, port_name: str, args: dict):
        from langchain_mcp_adapters.client import MultiServerMCPClient
        from mcp_servers.marketplace.guard import who
        client = MultiServerMCPClient({"upwork": {"transport": "streamable_http", "url": URL,
                                                  "headers": {"Authorization": f"Bearer {_token(who())}"}}})
        tools = {t.name: t for t in await client.get_tools()}
        name = self.map.get(port_name, port_name)
        if name not in tools:
            raise NotImplementedError(f"Upwork MCP has no tool {name!r} for {port_name}; available: {sorted(tools)[:20]}")
        out = await tools[name].ainvoke(args)
        try:
            return json.loads(out if isinstance(out, str) else out[0]["text"])
        except (ValueError, TypeError, KeyError, IndexError):
            return out

    @staticmethod
    def _job(d: dict) -> Job:
        b = d.get("budget")
        return Job(id=str(d.get("id") or d.get("ciphertext")), title=d.get("title", ""), description=d.get("description", ""),
                   budget_usd=b.get("amount") if isinstance(b, dict) else b,
                   client_id=str((d.get("client") or {}).get("id", d.get("client_id", "unknown"))),
                   posted_at=str(d.get("createdDateTime") or d.get("posted_at", "")), connects_cost=d.get("connectPrice"), source="upwork:live")

    def search_jobs(self, query="", limit=20, category=None):
        res = _run(self._call("search_jobs", {"query": query, "limit": limit}))
        return [self._job(j) for j in (res.get("jobs", []) if isinstance(res, dict) else res)][:limit]

    def get_job(self, job_id):
        return self._job(_run(self._call("get_job", {"job_id": job_id})))

    def get_client_history(self, client_id):
        d = _run(self._call("get_client_history", {"client_id": client_id}))
        return ClientHistory(client_id=client_id, total_spent_usd=float(d.get("totalSpent", 0) or 0), hire_rate=float(d.get("hireRate", 0) or 0),
                             payment_verified=bool(d.get("paymentVerified")), reviews=[r.get("comment", "") for r in d.get("reviews", [])][:5], source="upwork:live")

    def get_connects_balance(self):
        return int(_run(self._call("get_connects_balance", {})).get("balance", 0))

    def get_market_stats(self, category):
        from mcp_servers.marketplace.adapters.gigsim import ROOT   # market stats come from the public datasets in both modes
        return MarketStats(category=category, **json.loads((ROOT / "data" / "market" / "market_stats.json").read_text())[category])

    def list_threads(self):
        return [str(t.get("id")) for t in _run(self._call("list_threads", {}))]

    def list_messages(self, thread_id):
        return [Message(id=str(m.get("id")), thread_id=thread_id, sender="freelancer" if m.get("fromMe") else "client", text=m.get("text", ""))
                for m in _run(self._call("list_messages", {"thread_id": thread_id}))]

    def proposal_events(self):
        return []   # shortcut: live pipeline stages come from the user confirming on Upwork; no polling of proposal pages

    def _write(self, key, dry_run, payload, fn):
        if key in self._seen:
            return self._seen[key].model_copy(update={"replayed": True})
        if dry_run:
            return WriteResult(ok=True, dry_run=True, would_send=payload, connects_cost=0)
        res = WriteResult(ok=True, dry_run=False, would_send=payload, connects_cost=0, id=str(fn()))
        self._seen[key] = res
        return res

    def create_proposal_draft(self, job_id, text, *, idem_key, dry_run=False, bid_usd=None):
        payload = {"job_id": job_id, "cover_letter": text, "bid_usd": bid_usd}
        return self._write(idem_key, dry_run, payload, lambda: (_run(self._call("create_proposal_draft", payload)) or {}).get("id", "draft"))

    def submit_proposal(self, draft_id, *, idem_key, dry_run=False):
        # never submit or spend Connects from GigBid in live mode: the user confirms the draft on Upwork
        return WriteResult(ok=True, dry_run=dry_run, would_send={"draft_id": draft_id, "action": "confirm_on_upwork"}, connects_cost=0, id=draft_id)

    def send_message(self, thread_id, text, *, idem_key, dry_run=False):
        payload = {"thread_id": thread_id, "text": text, "draft": True}
        return self._write(idem_key, dry_run, payload, lambda: (_run(self._call("create_message_draft", payload)) or {}).get("id", "draft"))


def test_expired_token_is_refreshed_and_saved(monkeypatch):
    import httpx
    import apps.api.auth.users as users
    old = {"access_token": "old", "refresh_token": "r1", "expires_in": 10, "obtained_at": 0, "client_id": "c", "token_url": "https://x/token"}
    saved = {}
    monkeypatch.setattr(users, "load_token", lambda u: old)
    monkeypatch.setattr(users, "save_token", lambda u, p, t: saved.update(t))
    monkeypatch.setattr(httpx, "post", lambda *a, **k: httpx.Response(200, json={"access_token": "new", "expires_in": 3600}, request=httpx.Request("POST", a[0])))
    assert _token("u1") == "new" and saved["refresh_token"] == "r1"


def test_live_never_spends_connects():
    u = UpworkLive.__new__(UpworkLive)
    r = u.submit_proposal("d1", idem_key="k" * 8)
    assert r.connects_cost == 0 and r.would_send["action"] == "confirm_on_upwork"
