"""Client threads. Suggested replies come from the conversation graph; sending needs approval (/api/approvals)."""
from fastapi import APIRouter, Request
from apps.api.auth.users import UserDep
from apps.api.deps import get_run, latest_runs, run_out, ui_tools
from apps.api.dispatch import enqueue
from apps.api.schemas import Message, RunOut, Thread, ThreadDetail
from worker.tasks import new_run

r = APIRouter(prefix="/api/messages", tags=["messages"])


@r.get("", response_model=list[Thread])
async def threads(request: Request, user: dict = UserDep):
    runs = latest_runs(user, "conversation")
    out = []
    async with ui_tools(user, request.state.trace) as t:
        for tid in await t.call("ui", "list_threads", many=True):
            msgs = [m for m in await t.call("ui", "list_messages", {"thread_id": tid}, many=True) if isinstance(m, dict)]
            out.append(Thread(thread_id=tid, last=Message(**msgs[-1]) if msgs else None, run=run_out(runs[tid]) if tid in runs else None))
    return out


@r.get("/{thread_id}", response_model=ThreadDetail)
async def thread(thread_id: str, request: Request, user: dict = UserDep):
    async with ui_tools(user, request.state.trace) as t:
        msgs = [Message(**m) for m in await t.call("ui", "list_messages", {"thread_id": thread_id}, many=True) if isinstance(m, dict)]
    run = latest_runs(user, "conversation").get(thread_id)
    return ThreadDetail(thread_id=thread_id, messages=msgs, run=run_out(run) if run else None)


@r.post("/{thread_id}/draft", response_model=RunOut)
async def draft_reply(thread_id: str, user: dict = UserDep):
    """Client Liaison reads the newest client message, classifies intent and drafts a reply (worker)."""
    run = latest_runs(user, "conversation").get(thread_id)
    if run and run["status"] in ("queued", "running", "awaiting_approval", "resuming"):
        return run_out(run)
    rid = new_run(user["id"], "conversation", thread_id)
    await enqueue("start_run", rid, key=f"start:{rid}")
    return run_out(get_run(user, rid))
