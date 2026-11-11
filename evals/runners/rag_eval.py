"""Retrieval evaluation: Recall@5, MRR, nDCG@10 per variant, overall and per persona.
Run: python -m evals.runners.rag_eval [--variants v0_naive,v3_rerank]   -> evals/results/rag_eval.json"""
import argparse, json, math, pathlib, statistics, time
from agent.config import profile
from rag.index.store import Index
from rag.retriever import VARIANTS, get_retriever

RES = pathlib.Path(__file__).resolve().parents[1] / "results"
DEV = pathlib.Path(__file__).resolve().parents[1] / "datasets" / "dev_jobs.json"


def metrics(ranked: list[str], gold: list[str]):
    rec = len(set(ranked[:5]) & set(gold)) / len(gold)
    rr = next((1 / (i + 1) for i, x in enumerate(ranked) if x in gold), 0.0)
    dcg = sum(1 / math.log2(i + 2) for i, x in enumerate(ranked[:10]) if x in gold)
    idcg = sum(1 / math.log2(i + 2) for i in range(min(len(gold), 10)))
    return rec, rr, dcg / idcg


def pooled_index():
    """Stress setting: every persona's items in one index (no persona filter), ids prefixed. Gold ids are prefixed to match."""
    import dataclasses
    from rag.ingest.loaders import load_persona
    items = [dataclasses.replace(i, id=f"{p}/{i.id}") for p in ("ayesha_ml", "bilal_web", "sara_data") for i in load_persona(p)]
    return Index("pooled", items)


def run(variants, jobs=None, per_job=False, pool="persona"):
    jobs = jobs or [j for j in json.loads(DEV.read_text()) if j["gold_evidence"]]
    if pool == "all":
        shared = pooled_index()
        jobs = [{**j, "gold_evidence": [f"{j['persona']}/{g}" for g in j["gold_evidence"]]} for j in jobs]
        idx = {p: shared for p in {j["persona"] for j in jobs}}
    else:
        idx = {p: Index(p) for p in {j["persona"] for j in jobs}}
    out = {}
    for v in variants:
        rows, lat = [], []
        for j in jobs:
            r = get_retriever(idx[j["persona"]], v)
            t = time.perf_counter()
            ranked = [h.item_id for h in r.search(j, k=10)]
            lat.append(time.perf_counter() - t)
            rows.append({"job": j["id"], "persona": j["persona"], "n_req": len(j["gold_evidence"]), "ranked": ranked, **dict(zip(("recall5", "mrr", "ndcg10"), metrics(ranked, j["gold_evidence"])))})
        agg = lambda rs: {m: round(statistics.mean(x[m] for x in rs), 3) for m in ("recall5", "mrr", "ndcg10")}
        out[v] = {"overall": agg(rows), "by_persona": {p: agg([x for x in rows if x["persona"] == p]) for p in idx},
                  "by_job_type": {"single_evidence": agg([x for x in rows if x["n_req"] == 1]), "multi_evidence": agg([x for x in rows if x["n_req"] > 1])},
                  "latency_s": {"p50": round(statistics.median(lat), 3), "p95": round(sorted(lat)[int(0.95 * (len(lat) - 1))], 3)}}
        if per_job:
            out[v]["rows"] = rows
        print(v, out[v]["overall"], out[v]["latency_s"])
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--variants", default=",".join(VARIANTS))
    ap.add_argument("--pool", default="persona", choices=["persona", "all"], help="all = pooled-distractor stress test")
    a = ap.parse_args()
    res = {"llm_profile": profile(), "n_jobs": sum(1 for j in json.loads(DEV.read_text()) if j["gold_evidence"]),
           "note": "decomposition uses the matcher node; under MODEL_PROFILE=offline that is a rule-based splitter, not an LLM",
           "pool": a.pool, "variants": run(a.variants.split(","), per_job=True, pool=a.pool)}
    RES.mkdir(exist_ok=True)
    (RES / f"rag_eval_{a.pool}.json").write_text(json.dumps(res, indent=1))
