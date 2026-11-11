"""Agent run viewer: run list, events, live stream, checkpoint history and replay."""
import json
from fastapi import APIRouter, HTTPException
from apps.api.auth.users import UserDep
from apps.api.db import q
from apps.api.deps import get_run, run_out
from apps.api.dispatch import enqueue
from apps.api.schemas import Event, RunOut
from apps.api.streaming import sse

r = APIRouter(prefix="/api/runs", tags=["runs"])


@r.get("", response_model=list[RunOut])
def runs(user: dict = UserDep):
    return [run_out(x) for x in q("SELECT * FROM runs WHERE user_id=:u ORDER BY created DESC LIMIT 200", u=user["id"])]


@r.get("/{run_id}", response_model=RunOut)
def one(run_id: str, user: dict = UserDep):
    run = get_run(user, run_id)
    if not run:
        raise HTTPException(404, "run not found")
    return run_out(run)


@r.get("/{run_id}/events", response_model=list[Event])
def events(run_id: str, after: int = 0, user: dict = UserDep):
    if not get_run(user, run_id):
        raise HTTPException(404, "run not found")
    return [Event(seq=e["seq"], data=json.loads(e["data"])) for e in
            q("SELECT seq, data FROM events WHERE run_id=:r AND seq>:a ORDER BY seq", r=run_id, a=after)]


@r.get("/{run_id}/stream")
async def stream(run_id: str, user: dict = UserDep):
    """Server-sent events: every node update as the worker produces it (LangGraph stream_mode='updates')."""
    if not get_run(user, run_id):
        raise HTTPException(404, "run not found")
    return sse(run_id)


@r.get("/{run_id}/history", response_model=list[dict])
async def history(run_id: str, user: dict = UserDep):
    """Checkpoint history of the run's thread: any of these can be replayed."""
    from worker.tasks import checkpointer
    from agent.graphs import bid_graph, conversation_graph
    run = get_run(user, run_id)
    if not run:
        raise HTTPException(404, "run not found")
    g = (bid_graph if run["kind"] == "bid" else conversation_graph).build
    out = []
    async with checkpointer() as cp:
        async for s in g(cp).aget_state_history({"configurable": {"thread_id": run["thread_id"]}}):
            out.append({"checkpoint_id": s.config["configurable"]["checkpoint_id"], "next": list(s.next),
                        "step": s.metadata.get("step"), "created_at": s.created_at})
    return out


@r.post("/{run_id}/replay/{checkpoint_id}", response_model=RunOut)
async def replay(run_id: str, checkpoint_id: str, user: dict = UserDep):
    """Fork a new run that continues from an earlier checkpoint of this thread (debugging a wrong decision)."""
    src = get_run(user, run_id)
    if not src:
        raise HTTPException(404, "run not found")
    from worker.tasks import new_run
    rid = new_run(user["id"], src["kind"], src["ref"])
    q("UPDATE runs SET thread_id=:t, summary=:s WHERE id=:i", t=src["thread_id"], i=rid,
      s=json.dumps({"replay_of": run_id, "checkpoint_id": checkpoint_id}))
    await enqueue("replay_run", rid, checkpoint_id, key=f"replay:{rid}")
    return run_out(get_run(user, rid))


@r.post("/{run_id}/retry", response_model=RunOut)
async def retry(run_id: str, user: dict = UserDep):
    """Re-queue a run that errored or waited out a marketplace outage; it continues from its checkpoint."""
    run = get_run(user, run_id)
    if not run or run["status"] not in ("error", "queued_degraded", "queued", "resuming"):
        raise HTTPException(409, "run is not retryable")
    if run["status"] == "resuming":
        answer = json.loads(q("SELECT data FROM events WHERE run_id=:r AND data LIKE '%\"approval\"%' ORDER BY seq DESC LIMIT 1", r=run_id)[0]["data"])["answer"]
        await enqueue("resume_run", run_id, answer, key=f"resume:{run_id}:{run['attempts']}")
    else:
        await enqueue("start_run", run_id, key=f"start:{run_id}:{run['attempts']}")
    return run_out(get_run(user, run_id))
