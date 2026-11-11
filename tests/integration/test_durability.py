"""Kill the API while a proposal awaits approval -> restart -> approve -> submitted exactly once."""
import pytest
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.types import Command
from agent.graphs.bid_graph import build, execute
from agent.mcp_client import Tools
from data import personas_util
from mcp_servers.marketplace import server
from mcp_servers.marketplace.adapters.gigsim import MockGigSim


@pytest.fixture(autouse=True)
def _offline(monkeypatch):
    monkeypatch.setenv("MODEL_PROFILE", "offline")


async def test_pending_approval_survives_restart_and_submits_once(tmp_path):
    db = str(tmp_path / "ckpt.sqlite")
    cfg = lambda tools: {"configurable": {"thread_id": "job-a01", "tools": tools}}
    # process 1: run to the approval gate, then "crash" (everything closed)
    async with AsyncSqliteSaver.from_conn_string(db) as cp, Tools() as tools:
        out = await build(cp).ainvoke({"job_id": "a01", "user": personas_util.profile("ayesha_ml")}, cfg(tools))
        assert "__interrupt__" in out
    server.M = MockGigSim()  # process 2: fresh marketplace object, state reloaded from disk
    async with AsyncSqliteSaver.from_conn_string(db) as cp, Tools() as tools:
        g = build(cp)
        snap = await g.aget_state(cfg(tools))
        assert snap.next == ("approval",)  # pending approval is still there
        out = await g.ainvoke(Command(resume={"action": "approve"}), cfg(tools))
        assert out["status"] == "submitted"
        # worker dies after the marketplace write but before the checkpoint: execute runs AGAIN
        again = await execute(out, cfg(tools))
        assert again["result"]["submit"]["replayed"] is True
    assert MockGigSim().get_connects_balance() == 94  # charged once (6 Connects)


async def test_replay_from_checkpoint_history(tmp_path):
    async with AsyncSqliteSaver.from_conn_string(str(tmp_path / "c.sqlite")) as cp, Tools() as tools:
        g, c = build(cp), {"configurable": {"thread_id": "r1", "tools": tools}}
        await g.ainvoke({"job_id": "a01", "user": personas_util.profile("ayesha_ml")}, c)
        hist = [s async for s in g.aget_state_history(c)]
        assert len(hist) > 5 and any(s.next == ("writer",) for s in hist)
