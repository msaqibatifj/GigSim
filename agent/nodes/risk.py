from agent.handoffs import RiskReport
from agent.llm import astructured
from agent.nodes.common import job_text, tools
from agent.safety import injection_signals


async def risk(state, config):
    job = state["job"]
    client = await tools(config).call("risk", "get_client_history", {"client_id": job["client_id"]})
    client = {k: v for k, v in client.items() if k != "source"}   # provenance is for us, not a risk signal
    r = await astructured("risk", RiskReport, {"job": job_text(job, raw=True), "job_obj": job, "client": client, "client_obj": client})
    hits = injection_signals(job_text(job, raw=True))   # deterministic layer: does not depend on the model noticing
    if hits and "injection" not in r.flags:
        r = r.model_copy(update={"flags": [*r.flags, "injection"], "reasons": [*r.reasons, f"injected instruction: {hits[0]!r}"]})
    return {"risk": r, "steps": 1}
