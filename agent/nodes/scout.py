from agent.nodes.common import tools


async def scout(state, config):
    """Hands one job into the bid graph. (Scheduled discovery + dedupe lives in worker/.)"""
    job = await tools(config).call("scout", "get_job", {"job_id": state["job_id"]})
    return {"job": job, "steps": 1}
