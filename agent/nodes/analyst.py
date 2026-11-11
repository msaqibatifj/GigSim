from agent.handoffs import JobSpec
from agent.llm import astructured
from agent.nodes.common import job_text


async def analyst(state, config):
    job = state["job"]
    spec = await astructured("analyst", JobSpec, {"job": job_text(job), "job_obj": job})
    spec = spec.model_copy(update={"job_id": job["id"]})   # never trust the model for an id we already know
    return {"spec": spec, "steps": 1}
