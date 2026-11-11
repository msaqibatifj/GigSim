"""Signature extension X2: proposal experiments. A/B two proposal strategies on the same jobs, scored by GigSim.
  A "intro-first": open by introducing the freelancer, then relevant work.
  B "deliverable-first": open with the job's exact deliverable, cite one measurable result, close with one scoped question.
Both use the same Writer model, evidence and verification; only the style rules differ (passed through the Writer's `style` input).
Test: paired sign-flip permutation test on the per-job GigSim reply probability difference (exact up to 20000 resamples),
plus the observed simulated reply counts. CAVEAT printed into the result: GigSim's client model is synthetic (outcome() in
adapters/gigsim.py), so this shows the experiment pipeline and agreement with that model, not real client behaviour.
Run: python -m scripts.localenv evals.runners.ab_experiment  -> evals/results/ab_experiment.json"""
import asyncio, json, pathlib, random, statistics
import mcp_servers.portfolio.server  # noqa: F401
from agent.handoffs import ProposalDraft
from agent.llm import astructured
from agent.nodes.common import job_text, max_words
from mcp_servers.marketplace.adapters.gigsim import MockGigSim, outcome
from mcp_servers.portfolio import tools as ptools
from rag.verify import verify

ROOT = pathlib.Path(__file__).resolve().parents[2]
STYLES = {"A_intro_first": ["Open with one sentence introducing yourself and your background.", "Then describe relevant past work."],
          "B_deliverable_first": ["Open with the job's exact deliverable in the first sentence.", "Cite one measurable result from the evidence.",
                                  "Close with one specific question about scope."]}


def perm_test(diffs, n=20000, seed=3):
    rng, obs = random.Random(seed), abs(statistics.mean(diffs))
    hits = sum(abs(statistics.mean(d * rng.choice((-1, 1)) for d in diffs)) >= obs - 1e-12 for _ in range(n))
    return round((hits + 1) / (n + 1), 4)


async def one(job, mk, sem):
    async with sem:
        ev = [{"id": h["id"], "title": h["title"], "text": h["snippet"]} for h in ptools.search_evidence(job["title"] + ". " + job["description"], 4, persona_name=job["persona"])]
        res = {}
        for name, style in STYLES.items():
            d = await astructured("writer", ProposalDraft, {"job": job_text(job), "job_obj": job, "max_words": max_words(), "style": style,
                                                            "evidence": [f"{e['id']}: {e['text']}" for e in ev], "evidence_obj": ev, "feedback": []})
            d, _ = await asyncio.to_thread(verify, d, ev)
            jm = mk.get_job(job["id"])
            o = outcome(jm, mk.clients.get(jm.client_id), d.cover_letter, None)
            res[name] = {"p_reply": o["p_reply"], "replied": "replied" in o["stages"], "words": len(d.cover_letter.split())}
        return {"job": job["id"], "persona": job["persona"], **res}


async def main():
    jobs = [j for j in json.loads((ROOT / "evals" / "datasets" / "dev_jobs.json").read_text()) if j["gold_action"] == "bid"]
    mk, sem = MockGigSim(), asyncio.Semaphore(3)
    rows = await asyncio.gather(*[one(j, mk, sem) for j in jobs])
    a, b = "A_intro_first", "B_deliverable_first"
    diffs = [r[b]["p_reply"] - r[a]["p_reply"] for r in rows]
    out = {"n_jobs": len(rows), "mean_p_reply": {k: round(statistics.mean(r[k]["p_reply"] for r in rows), 3) for k in (a, b)},
           "sim_replies": {k: sum(r[k]["replied"] for r in rows) for k in (a, b)}, "mean_diff_B_minus_A": round(statistics.mean(diffs), 3),
           "permutation_p_value": perm_test(diffs), "words_mean": {k: round(statistics.mean(r[k]["words"] for r in rows), 1) for k in (a, b)},
           "caveat": "GigSim client behaviour is a synthetic model; this demonstrates the experiment pipeline, not real-world effect.", "rows": rows}
    (ROOT / "evals" / "results" / "ab_experiment.json").write_text(json.dumps(out, indent=1))
    print({k: v for k, v in out.items() if k != "rows"})


def test_perm_test():
    assert perm_test([0.2] * 12) < 0.01
    assert perm_test([0.1, -0.1] * 6) > 0.5


if __name__ == "__main__":
    asyncio.run(main())
