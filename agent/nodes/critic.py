from agent.handoffs import Critique
from agent.llm import astructured
from agent.nodes.common import job_text, max_words


async def critic(state, config):
    c = await astructured("critic", Critique, {"job": job_text(state["job"]), "job_obj": state["job"], "max_words": max_words(),
                                        "draft": state["draft"].cover_letter, "evidence": [f"{e['id']}: {e['text']}" for e in state.get("evidence", [])],
                                        "claims": [(c.text, c.label, c.evidence_ids) for c in state["draft"].claims], "draft_obj": state["draft"].model_dump()})
    return {"critiques": [c], "steps": 1}
