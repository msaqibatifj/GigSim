"""Fit Matcher: decompose the job into requirements, retrieve evidence for each (variant V1 = decomposition)."""
from pydantic import BaseModel
from agent.config import cfg
from agent.handoffs import Evidence, FitReport
from agent.llm import astructured
from agent.nodes.common import job_text, tools


class Requirements(BaseModel):
    requirements: list[str]


async def matcher(state, config):
    job, t = state["job"], tools(config)
    reqs = (await astructured("matcher", Requirements, {"job": job_text(job), "job_obj": job})).requirements
    ev, items, covered = [], {}, 0
    for r in reqs:
        hits = await t.call("matcher", "search_evidence", {"requirement": r[:500] if len(r) >= 3 else r + "   ", "k": 3}, many=True)
        floor = cfg()["rag"].get("min_support_score", {}).get(cfg()["rag"]["variant"])
        hits = [h for h in hits if isinstance(h, dict) and (floor is None or h["score"] >= floor)]
        if hits:
            covered += 1
            ev.append(Evidence(requirement=r, item_id=hits[0]["id"], source=hits[0]["source"]))
            for h in hits:
                items.setdefault(h["id"], {"id": h["id"], "type": h["type"], "title": h["title"], "text": h["snippet"], "outcome": h.get("outcome")})
        else:
            ev.append(Evidence(requirement=r))
    fit = FitReport(score=round(covered / max(len(reqs), 1), 2), evidence=ev,
                    reasons=[f"{covered}/{len(reqs)} requirements have portfolio evidence"])
    return {"fit": fit, "evidence": list(items.values()), "steps": 1}
