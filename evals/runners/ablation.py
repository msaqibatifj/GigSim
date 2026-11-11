"""R&D question B: ablate the best retrieval pipeline one component at a time (pooled-distractor setting, dev set).

HYPOTHESIS (written before the first run, 2026-11-11):
  H1. The cross-encoder reranker is the component that matters most: removing it lowers nDCG@10 by more than removing
      hybrid fusion or requirement decomposition.
  H2. Decomposition helps multi-evidence jobs (several gold items) and is neutral or slightly harmful on single-evidence jobs.
  H3. Hybrid BM25+dense adds little over dense alone on these short, keyword-rich portfolio items.
  H4. Better retrieval will NOT raise the simulated GigSim reply rate much, because outcome() depends on proposal wording
      and price more than on which evidence item ranks first (checked in the report, section 4).

Best pipeline = decompose + hybrid + rerank (v5). Arms: full, -rerank, -hybrid, -decompose.
Run: python -m scripts.localenv evals.runners.ablation  -> evals/results/ablation.json"""
import json, pathlib, statistics
from evals.runners.rag_eval import DEV, metrics, pooled_index
from rag.variants.base import Pipeline, decompose

ROOT = pathlib.Path(__file__).resolve().parents[2]
ARMS = {"full": dict(query="decompose", retrieve="hybrid", rerank=True),
        "-rerank": dict(query="decompose", retrieve="hybrid", rerank=False),
        "-hybrid": dict(query="decompose", retrieve="dense", rerank=True),
        "-decompose": dict(query="whole", retrieve="hybrid", rerank=True)}


def main():
    jobs = [j for j in json.loads(DEV.read_text()) if j["gold_evidence"]]
    idx = pooled_index()
    gold = {j["id"]: [f"{j['persona']}/{g}" for g in j["gold_evidence"]] for j in jobs}
    reqs = {j["id"]: decompose(j) for j in jobs}   # one decomposition per job, shared by all arms (isolates the other components)
    out = {"setting": "pooled distractors (all 3 personas in one index)", "n_jobs": len(jobs), "arms": {}}
    for name, kw in ARMS.items():
        pipe = Pipeline(idx, **kw, name=name)
        rows = []
        for j in jobs:
            ranked = [h.item_id for h in pipe.search(j, k=10, queries=reqs[j["id"]] if kw["query"] == "decompose" else None)]
            rows.append({"persona": j["persona"], "multi": len(gold[j["id"]]) > 1, **dict(zip(("recall5", "mrr", "ndcg10"), metrics(ranked, gold[j["id"]])))})
        agg = lambda rs: {m: round(statistics.mean(r[m] for r in rs), 3) for m in ("recall5", "mrr", "ndcg10")} if rs else None
        out["arms"][name] = {"overall": agg(rows), "single_evidence": agg([r for r in rows if not r["multi"]]), "multi_evidence": agg([r for r in rows if r["multi"]]),
                             "by_persona": {p: agg([r for r in rows if r["persona"] == p]) for p in sorted({r["persona"] for r in rows})}}
        print(name, out["arms"][name]["overall"])
    full = out["arms"]["full"]["overall"]["ndcg10"]
    out["ndcg10_drop_when_removed"] = {n: round(full - a["overall"]["ndcg10"], 3) for n, a in out["arms"].items() if n != "full"}
    (ROOT / "evals" / "results" / "ablation.json").write_text(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
