from agent.handoffs import ProposalDraft
from agent.llm import astructured
from agent.nodes.common import job_text, max_words


async def writer(state, config):
    job, ev = state["job"], state.get("evidence", [])
    fb = [i for c in state.get("critiques", [])[-1:] for i in c.issues]
    draft = await astructured("writer", ProposalDraft, {
        "job": job_text(job), "job_obj": job, "max_words": max_words(),
        "style": config["configurable"].get("style", []),   # promoted style memory (agent/memory)
        "evidence": [f"{e['id']}: {e['text']}" for e in ev], "evidence_obj": ev, "feedback": fb})
    return {"draft": draft, "steps": 1}
