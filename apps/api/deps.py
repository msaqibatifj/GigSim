"""Helpers shared by routers. Every query is scoped by the signed-in user's id (tenant)."""
import contextlib, json
from apps.api.db import q
from apps.api.schemas import RunOut, Settings
from agent.mcp_client import Tools


def settings_of(user: dict) -> Settings:
    return Settings(**json.loads(user["settings"] or "{}"))


def run_out(r: dict) -> RunOut:
    return RunOut(id=r["id"], kind=r["kind"], ref=r["ref"], status=r["status"], trace_id=r["trace_id"], created=r["created"],
                  summary=json.loads(r["summary"] or "{}"))


def get_run(user: dict, run_id: str) -> dict | None:
    r = q("SELECT * FROM runs WHERE id=:i AND user_id=:u", i=run_id, u=user["id"])
    return r[0] if r else None


def latest_runs(user: dict, kind: str) -> dict[str, dict]:
    """ref -> newest run of that kind for this user."""
    out = {}
    for r in q("SELECT * FROM runs WHERE user_id=:u AND kind=:k ORDER BY created", u=user["id"], k=kind):
        out[r["ref"]] = r
    return out


@contextlib.asynccontextmanager
async def ui_tools(user: dict, trace: str = "-"):
    """Read-only marketplace access for API views, through the same MCP servers (allowlist 'ui')."""
    async with Tools(persona=user["persona"], user=user["id"], trace=trace, servers=("marketplace",)) as t:
        yield t


async def graph_state(run: dict) -> dict:
    """Latest checkpointed values of a run's thread (job detail, studio)."""
    from worker.tasks import checkpointer
    from agent.graphs import bid_graph, conversation_graph
    build = bid_graph.build if run["kind"] == "bid" else conversation_graph.build
    async with checkpointer() as cp:
        snap = await build(cp).aget_state({"configurable": {"thread_id": run["thread_id"]}})
    return {k: (v.model_dump() if hasattr(v, "model_dump") else [x.model_dump() if hasattr(x, "model_dump") else x for x in v]
                if isinstance(v, list) else v) for k, v in (snap.values or {}).items() if k != "user"}
