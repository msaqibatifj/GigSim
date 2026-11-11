import pytest
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command
from agent.graphs.bid_graph import build
from agent.mcp_client import Tools
from data import personas_util



@pytest.fixture(autouse=True)
def _offline(monkeypatch):
    monkeypatch.setenv("MODEL_PROFILE", "offline")


async def run(job_id, persona="ayesha_ml", resume=None, graph=None, thread="t-" + "x"):
    async with Tools(persona=persona) as tools:
        g = graph or build(MemorySaver())
        cfg = {"configurable": {"thread_id": thread + job_id, "tools": tools}}
        out = await g.ainvoke({"job_id": job_id, "user": personas_util.profile(persona)}, cfg)
        if resume is not None:
            out = await g.ainvoke(Command(resume=resume), cfg)
        return out, tools


async def test_good_job_reaches_approval_then_submits_once():
    out, tools = await run("a01")
    assert "__interrupt__" in out
    payload = out["__interrupt__"][0].value
    assert payload["dry_run"]["dry_run"] and payload["evidence"] and payload["verification"]["unsupported_after"] == 0
    out, _ = await run("a01", resume={"action": "approve"})
    assert out["status"] == "submitted" and out["result"]["submit"]["ok"]


async def test_scam_and_injection_are_skipped_without_approval():
    for job in ("a12", "b13", "s11"):
        out, _ = await run(job, persona={"a12": "ayesha_ml", "b13": "bilal_web", "s11": "sara_data"}[job])
        assert out["status"] == "skipped" and "__interrupt__" not in out, job


async def test_reject_never_sends():
    out, _ = await run("a01", resume={"action": "reject", "reason": "tone"})
    assert out["status"] == "rejected" and "result" not in out
    from mcp_servers.marketplace import server
    assert server.M.get_connects_balance() == 100


async def test_edit_goes_back_through_compliance():
    out, _ = await run("a01", resume={"action": "edit", "text": "Email me at x@y.com, guaranteed results. I build RAG."})
    assert "__interrupt__" in out  # re-interrupts after compliance re-check
    assert "x@y.com" not in out["__interrupt__"][0].value["draft"]["cover_letter"]


async def test_clean_edit_is_sent_without_a_second_prompt():
    out, _ = await run("a01", resume={"action": "edit", "text": "I built hybrid search over scanned PDFs for a legal client. What is your timeline?"})
    assert "__interrupt__" not in out and out["status"] == "submitted"   # compliance changed nothing: the user's approval stands


async def test_edits_feed_style_memory_and_reach_writer():
    from langgraph.store.memory import InMemoryStore
    from agent.memory.store import style_rules
    store = InMemoryStore()
    async with Tools() as tools:
        g = build(MemorySaver())
        for n in range(2):
            c = {"configurable": {"thread_id": f"e{n}", "tools": tools, "store": store, "user_id": "u1"}}
            out = await g.ainvoke({"job_id": "a01", "user": personas_util.profile("ayesha_ml")}, c)
            first = out["__interrupt__"][0].value["draft"]["cover_letter"]
            await g.ainvoke(Command(resume={"action": "edit", "text": first.split(". ", 1)[1]}), c)
    assert any("generic first sentence" in r for r in style_rules(store, "u1"))
