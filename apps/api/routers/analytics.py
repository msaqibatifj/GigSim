"""Analytics: reply/hire rate by category, Connects vs outcomes, cost and latency per proposal, rejection reasons."""
import json, statistics
from collections import Counter, defaultdict
from fastapi import APIRouter
from apps.api.auth.users import UserDep
from apps.api.db import q
from apps.api.schemas import Analytics

r = APIRouter(prefix="/api/analytics", tags=["analytics"])


def _p95(xs):
    xs = sorted(xs)
    return xs[int(0.95 * (len(xs) - 1))] if xs else 0.0


@r.get("", response_model=Analytics)
def analytics(user: dict = UserDep):
    runs = q("SELECT * FROM runs WHERE user_id=:u AND kind='bid'", u=user["id"])
    by_cat, outcomes, rej, skips, status = defaultdict(lambda: Counter()), Counter(), Counter(), Counter(), Counter()
    connects, prop_lat, prop_usd, prop_tok, job_lat, job_usd = 0, [], [], [], [], []
    for r_ in runs:
        s = json.loads(r_["summary"] or "{}")
        status[r_["status"]] += 1
        usage = s.get("usage") or {}
        usd = sum(v.get("usd", 0) for v in usage.values())
        tok = sum(v.get("prompt_tokens", 0) + v.get("completion_tokens", 0) for v in usage.values())
        if s.get("seconds"):
            job_lat.append(s["seconds"]); job_usd.append(usd)
            if s.get("draft") or "writer" in usage or r_["status"] in ("awaiting_approval", "submitted", "rejected"):
                prop_lat.append(s["seconds"]); prop_usd.append(usd); prop_tok.append(tok)
        cat = (s.get("job_category") or "all")
        if r_["status"] == "submitted":
            connects += ((s.get("result") or {}).get("submit") or {}).get("connects_cost", 0)
            by_cat[cat]["submitted"] += 1
            o = s.get("outcome_recorded")
            if o:
                outcomes[o] += 1
                by_cat[cat]["replied"] += o == "replied"
            if s.get("hired"):
                outcomes["hired"] += 1
                by_cat[cat]["hired"] += 1
        if s.get("rejection_reason"):
            rej[s["rejection_reason"][:80]] += 1
        d = s.get("decision") or {}
        if d.get("action") == "skip":
            skips[(d.get("reasons") or ["?"])[0][:80]] += 1
    cats = {c: {"submitted": v["submitted"], "reply_rate": round(v["replied"] / v["submitted"], 3) if v["submitted"] else 0.0,
                "hire_rate": round(v["hired"] / v["submitted"], 3) if v["submitted"] else 0.0}
            for c, v in by_cat.items()}
    mean = lambda xs: round(statistics.mean(xs), 4) if xs else 0.0
    return Analytics(by_category=cats, connects_spent=connects, outcomes=dict(outcomes),
                     per_proposal={"n": len(prop_lat), "latency_mean_s": mean(prop_lat), "latency_p95_s": round(_p95(prop_lat), 2),
                                   "usd_mean": mean(prop_usd), "tokens_mean": mean(prop_tok)},
                     per_job={"n": len(job_lat), "latency_mean_s": mean(job_lat), "latency_p95_s": round(_p95(job_lat), 2), "usd_mean": mean(job_usd)},
                     rejection_reasons=rej.most_common(5), skip_reasons=skips.most_common(5), runs_by_status=dict(status))
