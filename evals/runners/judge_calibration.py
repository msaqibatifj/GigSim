"""LLM-judge calibration (B4). The judge scores proposals 1-5 on a fixed rubric; the HUMAN (you) labels the same items
blind; Cohen's kappa (quadratic-weighted, 1-5 scale) measures agreement. Judge scores without kappa are not reportable.

Workflow:
  1. python -m scripts.localenv evals.runners.judge_calibration build     -> evals/datasets/judge_items.json (shuffled, anonymised)
                                                                           + evals/datasets/judge_labels.json (empty template)
  2. python -m evals.runners.judge_calibration label  (interactive: you type 1-5 for each proposal, blind to the judge)
  3. python -m scripts.localenv evals.runners.judge_calibration score     -> evals/results/judge_calibration.json (kappa, disagreements)
Items come from the graph's drafts and the single-agent / supervisor baselines (different quality on purpose).
Rubric (identical for judge and human): 5 = specific to this job, every claim backed by the portfolio, plain, would get a reply;
3 = acceptable but generic or one weak claim; 1 = generic, unsupported or off-policy."""
import json, pathlib, random, sys
from pydantic import BaseModel
from agent.llm import structured

ROOT = pathlib.Path(__file__).resolve().parents[2]
DS = ROOT / "evals" / "datasets"
RUBRIC = "5 specific to this job, every claim backed by the portfolio, plain and likely to get a reply; 3 acceptable but generic or one weak claim; 1 generic, unsupported or breaks marketplace rules"


class Score(BaseModel):
    score: int
    reason: str


def kappa_qw(a: list[int], b: list[int], k: int = 5) -> float:
    n = len(a)
    O = [[0] * k for _ in range(k)]
    for x, y in zip(a, b):
        O[x - 1][y - 1] += 1
    ra, rb = [sum(r) for r in O], [sum(O[i][j] for i in range(k)) for j in range(k)]
    w = lambda i, j: (i - j) ** 2 / (k - 1) ** 2
    num = sum(w(i, j) * O[i][j] for i in range(k) for j in range(k)) / n
    den = sum(w(i, j) * ra[i] * rb[j] for i in range(k) for j in range(k)) / n ** 2
    return round(1 - num / den, 3) if den else 0.0


def extra_drafts(jobs, used, n):
    """Raw Writer drafts (no verification, alternating the two A/B styles) for bid-worthy dev jobs not already in the set:
    cheap extra items whose quality varies on purpose. Labelled arch 'writer_A' / 'writer_B'."""
    if n <= 0:
        return []
    import mcp_servers.portfolio.server  # noqa: F401  (onnxruntime first)
    from agent.handoffs import ProposalDraft
    from agent.nodes.common import job_text, max_words
    from evals.runners.ab_experiment import STYLES
    from mcp_servers.portfolio import tools as ptools
    out = []
    cands = [j for j in jobs.values() if j["gold_action"] == "bid" and j["id"] not in used]
    for k, j in enumerate(cands[:n]):
        style_name = list(STYLES)[k % 2]
        ev = [{"id": h["id"], "title": h["title"], "text": h["snippet"]} for h in ptools.search_evidence(j["title"] + ". " + j["description"], 4, persona_name=j["persona"])]
        d = structured("writer", ProposalDraft, {"job": job_text(j), "job_obj": j, "max_words": max_words(), "style": STYLES[style_name],
                                                 "evidence": [f"{e['id']}: {e['text']}" for e in ev], "evidence_obj": ev, "feedback": []})
        out.append({"arch": "writer_" + style_name[0], "job_id": j["id"], "title": j["title"], "job": j["description"], "draft": d.cover_letter})
    return out


def build():
    jobs ={j["id"]: j for j in json.loads((DS / "dev_jobs.json").read_text())}
    items = []
    for f, arch in (("decision_eval_open.json", "graph"), ("agent_comparison.json", None)):
        p = ROOT / "evals" / "results" / f
        if not p.exists():
            continue
        d = json.loads(p.read_text())
        rows = d["rows"] if arch else [r for a in ("single", "supervisor") for r in d["architectures"][a]["rows"]]
        for r in rows:
            if r.get("draft"):
                items.append({"arch": arch or r["arch"], "job_id": r["id"], "title": jobs[r["id"]]["title"], "job": jobs[r["id"]]["description"], "draft": r["draft"]})
    items += extra_drafts(jobs, {i["job_id"] for i in items}, 30 - len(items))   # top up to 30 with writer-only drafts
    random.Random(7).shuffle(items)
    items = [{"item": f"i{n}", **it} for n, it in enumerate(items[:30])]
    (DS / "judge_items.json").write_text(json.dumps(items, indent=1))
    (DS / "judge_labels.json").write_text(json.dumps({it["item"]: {"human": None} for it in items}, indent=1))
    print(len(items), "items written; label judge_labels.json (1-5) before running `score`")


def label():
    """Interactive labelling: shows each proposal (no judge score, no author), asks for 1-5. Progress is saved after every
    answer; Enter skips, 'q' quits, and re-running resumes where you left off."""
    items = json.loads((DS / "judge_items.json").read_text())
    f = DS / "judge_labels.json"
    labels = json.loads(f.read_text())
    todo = [it for it in items if labels[it["item"]]["human"] is None]
    print(f"RUBRIC: {RUBRIC}\n{len(todo)} of {len(items)} left.\n")
    for it in todo:
        print("=" * 78, f"\nJOB: {it['title']}\n{it['job'][:600]}\n\nPROPOSAL:\n{it['draft']}\n")
        a = input("Score 1-5 (Enter = skip, q = quit): ").strip().lower()
        if a == "q":
            break
        if a in {"1", "2", "3", "4", "5"}:
            labels[it["item"]]["human"] = int(a)
            f.write_text(json.dumps(labels, indent=1))
    print(f"{sum(v['human'] is not None for v in labels.values())} labelled so far.")


def score():
    items = json.loads((DS / "judge_items.json").read_text())
    labels = json.loads((DS / "judge_labels.json").read_text())
    rows = []
    for it in items:
        h = labels.get(it["item"], {}).get("human")
        if h is None:
            continue
        j = structured("judge", Score, {"job": it["job"], "draft": it["draft"], "rubric": RUBRIC})
        rows.append({"item": it["item"], "arch": it["arch"], "human": h, "judge": max(1, min(5, j.score)), "judge_reason": j.reason})
    if len(rows) < 2:
        sys.exit("fill human labels first")
    a, b = [r["human"] for r in rows], [r["judge"] for r in rows]
    out = {"n_labelled": len(rows), "weighted_kappa": kappa_qw(a, b), "exact_agreement": round(sum(x == y for x, y in zip(a, b)) / len(rows), 3),
           "mean_human": round(sum(a) / len(a), 2), "mean_judge": round(sum(b) / len(b), 2),
           "disagreements": [r for r in rows if abs(r["human"] - r["judge"]) >= 2], "rows": rows}
    (ROOT / "evals" / "results" / "judge_calibration.json").write_text(json.dumps(out, indent=1))
    print({k: v for k, v in out.items() if k not in ("rows", "disagreements")})


def test_kappa():
    assert kappa_qw([1, 2, 3, 4, 5], [1, 2, 3, 4, 5]) == 1.0
    assert kappa_qw([1, 1, 5, 5], [5, 5, 1, 1]) < 0


if __name__ == "__main__":
    {"build": build, "label": label, "score": score}[sys.argv[1]]()
