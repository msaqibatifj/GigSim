"""Does the retrieval score tell a real fit from a non-fit? For every dev job, take the cross-encoder score of the single best
evidence item for the whole post (shipped variant v3) and compare jobs that should be bid with jobs that should be skipped.
No LLM calls. Run: python -m evals.runners.score_gap  -> evals/results/score_gap.json"""
import json, pathlib, statistics
import mcp_servers.portfolio.server  # noqa: F401  (onnxruntime first)
from mcp_servers.portfolio import tools as ptools

ROOT = pathlib.Path(__file__).resolve().parents[2]


def main():
    jobs = json.loads((ROOT / "evals" / "datasets" / "dev_jobs.json").read_text())
    rows = []
    for j in jobs:
        hit = ptools.search_evidence(j["title"] + ". " + j["description"], 1, persona_name=j["persona"])
        rows.append({"id": j["id"], "persona": j["persona"], "kind": j["kind"], "gold": j["gold_action"], "best_score": hit[0]["score"] if hit else None})
    from agent.config import cfg
    floor = cfg()["rag"]["min_support_score"]["v3_rerank"]
    by = lambda pred: [r["best_score"] for r in rows if pred(r) and r["best_score"] is not None]
    legit_bid, legit_skip, hostile = by(lambda r: r["kind"] == "legit" and r["gold"] == "bid"), by(lambda r: r["kind"] == "legit" and r["gold"] == "skip"), by(lambda r: r["kind"] != "legit")
    stat = lambda xs: {"n": len(xs), "min": round(min(xs), 2), "median": round(statistics.median(xs), 2), "max": round(max(xs), 2)} if xs else None
    out = {"variant": "v3_rerank", "floor": floor, "legit_should_bid": stat(legit_bid), "legit_should_skip": stat(legit_skip), "scam_or_injection": stat(hostile),
           "bid_jobs_below_floor": sum(s < floor for s in legit_bid), "skip_jobs_above_floor": sum(s >= floor for s in legit_skip),
           "gap": round(min(legit_bid) - max(legit_skip), 2) if legit_bid and legit_skip else None, "rows": rows,
           "note": "Scores are cross-encoder logits (higher = more relevant). The floor was chosen by looking at this separation, on these same jobs."}
    (ROOT / "evals" / "results" / "score_gap.json").write_text(json.dumps(out, indent=1))
    print({k: v for k, v in out.items() if k not in ("rows", "note")})


if __name__ == "__main__":
    main()
