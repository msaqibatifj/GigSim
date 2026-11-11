"""Decision + proposal + outcome evaluation on the dev set (one graph run per job, stopped at the approval gate).
Metrics: bid/skip F1, scam precision/recall, price inside fair band, unsupported claims per proposal (before/after
verification), critic loops, compliance violations caught, simulated GigSim reply rate (fixed job set, deterministic
client model), p50/p95 latency, tokens and USD per job and per proposal.

Run: python -m scripts.localenv evals.runners.decision_eval [--profile open] [--limit N] [--variant v3_rerank] [--tag x]
Writes evals/results/decision_eval_<profile>[_<tag>].json. Every README/report number cites one of these files."""
import argparse, asyncio, json, os, pathlib, statistics, time
import mcp_servers.portfolio.server  # noqa: F401  (load onnxruntime first on Windows)
from langgraph.checkpoint.memory import MemorySaver
from agent.graphs.bid_graph import build
from agent.llm import RUN_USAGE
from agent.mcp_client import Tools
from data import personas_util
from mcp_servers.marketplace.adapters.gigsim import MockGigSim, outcome

ROOT = pathlib.Path(__file__).resolve().parents[2]
DEV = ROOT / "evals" / "datasets" / "dev_jobs.json"
RES = ROOT / "evals" / "results"


def p95(xs):
    xs = sorted(xs)
    return round(xs[int(0.95 * (len(xs) - 1))], 3) if xs else None


def f1(rows, pos):
    tp = sum(r["pred"] == pos and r["gold"] == pos for r in rows)
    fp = sum(r["pred"] == pos and r["gold"] != pos for r in rows)
    fn = sum(r["pred"] != pos and r["gold"] == pos for r in rows)
    p, r = tp / (tp + fp) if tp + fp else 0.0, tp / (tp + fn) if tp + fn else 0.0
    return round(2 * p * r / (p + r), 3) if p + r else 0.0, round(p, 3), round(r, 3)


async def one(job, sem, market):
    async with sem:
        usage = {}
        tok = RUN_USAGE.set(usage)
        t0 = time.perf_counter()
        err, out = None, {}
        try:
            async with Tools(persona=job["persona"], user=f"eval-{job['persona']}") as t:
                cfg = {"configurable": {"thread_id": f"eval-{job['id']}", "tools": t, "style": []}}
                out = await build(MemorySaver()).ainvoke({"job_id": job["id"], "user": personas_util.profile(job["persona"])}, cfg)
        except Exception as e:   # recorded, never hidden: counts as a failed job in the report
            err = f"{type(e).__name__}: {e}"[:300]
        finally:
            RUN_USAGE.reset(tok)
        secs = time.perf_counter() - t0
    d, risk, price, draft = out.get("decision"), out.get("risk"), out.get("price"), out.get("draft")
    pred = "bid" if out.get("__interrupt__") or (d and d.action == "bid" and price and price.worth_connects) else "skip"
    row = {"id": job["id"], "persona": job["persona"], "kind": job["kind"], "gold": job["gold_action"], "pred": pred,
           "decision": d.action if d else None, "status": out.get("status") or ("awaiting_approval" if out.get("__interrupt__") else None),
           "flags": risk.flags if risk else [], "fit": out["fit"].score if out.get("fit") else None, "error": err,
           "seconds": round(secs, 2), "usage": usage,
           "usd": round(sum(v["usd"] for v in usage.values()), 6), "tokens": sum(v["prompt_tokens"] + v["completion_tokens"] for v in usage.values())}
    if price:
        lo, hi = job["fair_price_band"]
        row.update(price=price.amount_usd, in_band=lo <= price.amount_usd <= hi)
    if draft:
        jm = market.get_job(job["id"])
        o = outcome(jm, market.clients.get(jm.client_id), draft.cover_letter, price.amount_usd if price else None)
        row.update(draft=draft.cover_letter, claims=[c.model_dump() for c in draft.claims], verification=out.get("verification"),
                   critic_loops=len(out.get("critiques", [])) - 1, critic_issues=[i for c in out.get("critiques", []) for i in c.issues],
                   compliance=out["compliance"].model_dump() if out.get("compliance") else None,
                   words=len(draft.cover_letter.split()), sim_p_reply=o["p_reply"], sim_replied="replied" in o["stages"],
                   sim_hired="hired" in o["stages"])
    return row


def summarise(rows):
    ok = [r for r in rows if not r["error"]]
    props = [r for r in ok if r.get("draft")]
    scam_like = {"scam", "injection"}
    caught = [r for r in ok if set(r["flags"]) & {"scam", "free_work", "off_platform", "injection"}]
    tp = sum(r["kind"] in scam_like for r in caught)
    scam_n = sum(r["kind"] in scam_like for r in ok)
    mean = lambda xs: round(statistics.mean(xs), 4) if xs else None
    bid_f1, bid_p, bid_r = f1(ok, "bid")
    return {
        "n_jobs": len(rows), "n_errors": len(rows) - len(ok),
        "bid_skip": {"f1_bid": bid_f1, "precision_bid": bid_p, "recall_bid": bid_r, "f1_skip": f1(ok, "skip")[0],
                     "accuracy": round(sum(r["pred"] == r["gold"] for r in ok) / len(ok), 3) if ok else None},
        "scam_detection": {"precision": round(tp / len(caught), 3) if caught else None, "recall": round(tp / scam_n, 3) if scam_n else None,
                           "n_scam_or_injection": scam_n},
        "price_in_fair_band": mean([float(r["in_band"]) for r in ok if "in_band" in r and r["gold"] == "bid"]),
        "proposals": {"n": len(props),
                      "unsupported_claims_before": mean([r["verification"]["unsupported_before"] for r in props if r.get("verification")]),
                      "unsupported_claims_after": mean([r["verification"]["unsupported_after"] for r in props if r.get("verification")]),
                      "critic_loops_mean": mean([r["critic_loops"] for r in props]),
                      "compliance_violations_caught": sum(len((r["compliance"] or {}).get("violations", [])) for r in props),
                      "compliance_blocked": sum(not (r["compliance"] or {}).get("allowed", True) for r in props),
                      "words_mean": mean([r["words"] for r in props])},
        "gigsim": {"sim_reply_rate": mean([float(r["sim_replied"]) for r in props]), "sim_hire_rate": mean([float(r["sim_hired"]) for r in props]),
                   "mean_p_reply": mean([r["sim_p_reply"] for r in props])},
        "cost_latency": {"per_job": {"p50_s": round(statistics.median([r["seconds"] for r in ok]), 2) if ok else None, "p95_s": p95([r["seconds"] for r in ok]),
                                     "usd_mean": mean([r["usd"] for r in ok]), "tokens_mean": mean([r["tokens"] for r in ok])},
                         "per_proposal": {"p50_s": round(statistics.median([r["seconds"] for r in props]), 2) if props else None, "p95_s": p95([r["seconds"] for r in props]),
                                          "usd_mean": mean([r["usd"] for r in props]), "tokens_mean": mean([r["tokens"] for r in props])}},
        "by_persona": {p: {"accuracy": round(sum(r["pred"] == r["gold"] for r in g) / len(g), 3),
                           "sim_reply_rate": mean([float(r["sim_replied"]) for r in g if r.get("draft")])}
                       for p in sorted({r["persona"] for r in ok}) for g in [[r for r in ok if r["persona"] == p]]},
        "by_kind": {k: {"n": len(g), "accuracy": round(sum(r["pred"] == r["gold"] for r in g) / len(g), 3)}
                    for k in sorted({r["kind"] for r in ok}) for g in [[r for r in ok if r["kind"] == k]]},
    }


async def main(a):
    if a.variant:
        from agent.config import cfg
        cfg()["rag"]["variant"] = a.variant
    jobs = json.loads(DEV.read_text())
    if not a.all and not a.jobs:   # default: compact stratified set (each persona: 2 bid, 1 low-fit, 1 scam; + 2 injections)
        a.jobs = (DEV.parent / "compact_ids.txt").read_text().strip()
    if a.jobs:
        jobs = [j for j in jobs if j["id"] in a.jobs.split(",")]
    jobs = jobs[: a.limit] if a.limit else jobs
    os.environ.setdefault("MOCK_GIGSIM_STATE", str(ROOT / "data" / "processed" / "eval_gigsim.json"))
    market, sem = MockGigSim(), asyncio.Semaphore(a.concurrency)
    t0 = time.time()
    rows = await asyncio.gather(*[one(j, sem, market) for j in jobs])
    from agent.config import cfg, profile
    res = {"profile": profile(), "models": {k: v for k, v in cfg()["profiles"][profile()].items() if k in ("small", "strong", "fallback")},
           "rag_variant": cfg()["rag"]["variant"], "dataset": str(DEV.relative_to(ROOT)), "wall_s": round(time.time() - t0, 1),
           "note": "GigSim client behaviour is a synthetic model (mcp_servers/marketplace/adapters/gigsim.py outcome()).",
           "summary": summarise(rows), "rows": rows}
    RES.mkdir(exist_ok=True)
    out = RES / f"decision_eval_{profile()}{'_' + a.tag if a.tag else ''}.json"
    out.write_text(json.dumps(res, indent=1, default=str))
    print(json.dumps(res["summary"], indent=1))
    print("->", out)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int)
    ap.add_argument("--all", action="store_true", help="all 42 dev jobs instead of the compact set")
    ap.add_argument("--jobs")
    ap.add_argument("--variant")
    ap.add_argument("--tag", default="")
    ap.add_argument("--concurrency", type=int, default=3)   # = number of Groq accounts
    asyncio.run(main(ap.parse_args()))
