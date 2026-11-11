"""Job inbox and job detail. Analysis itself runs in the worker; these routes only queue and read."""
import json
from fastapi import APIRouter, HTTPException, Request
from apps.api.auth.users import UserDep
from apps.api.db import q
from apps.api.deps import get_run, graph_state, latest_runs, run_out, ui_tools
from apps.api.dispatch import enqueue
from apps.api.schemas import InboxItem, Job, JobDetail, RunOut
from agent.mcp_client import ToolError
from worker.tasks import new_run

r = APIRouter(prefix="/api/jobs", tags=["jobs"])


def _item(job: dict, run: dict | None) -> InboxItem:
    if not run:
        return InboxItem(job=Job(**job))
    s = json.loads(run["summary"] or "{}")
    d, fit, risk, price = s.get("decision") or {}, s.get("fit") or {}, s.get("risk") or {}, s.get("price") or {}
    return InboxItem(job=Job(**job), run_id=run["id"], status=run["status"], action=d.get("action"), fit=fit.get("score"),
                     risk_flags=risk.get("flags", []), client_score=risk.get("client_score"), price_usd=price.get("amount_usd"),
                     connects=price.get("connects") or job.get("connects_cost"), reasons=d.get("reasons", [])[:3])


@r.get("", response_model=list[InboxItem])
async def inbox(request: Request, user: dict = UserDep):
    """Jobs the Scout queued for this user, ranked: bid first, then by fit."""
    runs = latest_runs(user, "bid")
    if not runs:
        return []
    async with ui_tools(user, request.state.trace) as t:
        jobs = {}
        for ref in runs:
            try:
                jobs[ref] = await t.call("ui", "get_job", {"job_id": ref})
            except ToolError:
                continue
    items = [_item(jobs[ref], run) for ref, run in runs.items() if ref in jobs]
    rank = {"bid": 0, "watch": 1, None: 2, "skip": 3}
    return sorted(items, key=lambda i: (rank.get(i.action, 2), -(i.fit or 0)))


@r.post("/scout", response_model=dict)
async def scout_now(user: dict = UserDep):
    """Run the user's saved searches now (normally on schedule)."""
    await enqueue("scout_user", user["id"], key=f"scout-now:{user['id']}")
    return {"queued": True}


@r.get("/{job_id}", response_model=JobDetail)
async def detail(job_id: str, request: Request, user: dict = UserDep):
    async with ui_tools(user, request.state.trace) as t:
        try:
            job = await t.call("ui", "get_job", {"job_id": job_id})
        except ToolError:
            raise HTTPException(404, "job not found")
        client = await t.call("ui", "get_client_history", {"client_id": job["client_id"]})
    run = latest_runs(user, "bid").get(job_id)
    return JobDetail(job=Job(**job), client=client, run=run_out(run) if run else None, state=await graph_state(run) if run else {})


@r.post("/{job_id}/analyse", response_model=RunOut)
async def analyse(job_id: str, user: dict = UserDep):
    run = latest_runs(user, "bid").get(job_id)
    if run and run["status"] in ("queued", "running", "awaiting_approval", "resuming"):
        return run_out(run)   # already in flight: never analyse twice
    rid = new_run(user["id"], "bid", job_id)
    await enqueue("start_run", rid, key=f"start:{rid}")
    return run_out(get_run(user, rid))


@r.post("/{job_id}/skip", response_model=RunOut)
def skip(job_id: str, user: dict = UserDep):
    run = latest_runs(user, "bid").get(job_id)
    if not run:
        raise HTTPException(404, "job not in inbox")
    q("UPDATE runs SET status='skipped_by_user' WHERE id=:i AND user_id=:u", i=run["id"], u=user["id"])
    return run_out(get_run(user, run["id"]))
