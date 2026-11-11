"""Record the demo traces in LangSmith, tagged so they are easy to find:
  critic-loop   first candidate job whose Critic sends the draft back at least once
  crash-resume  run to the approval gate, 'crash' (close everything), reopen, approve -> submitted
Run: python -m scripts.localenv scripts.record_traces   (needs LANGSMITH_* in .env; spends a few thousand Groq tokens)"""
import asyncio, json, pathlib, tempfile
import mcp_servers.portfolio.server  # noqa: F401  (load onnxruntime first on Windows)
from langgraph.checkpoint.memory import MemorySaver
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.types import Command
from agent.graphs.bid_graph import build
from agent.mcp_client import Tools
from agent.tracing import traced
from data import personas_util
from mcp_servers.marketplace import server
from mcp_servers.marketplace.adapters.gigsim import MockGigSim

DEV = {j["id"]: j for j in json.loads((pathlib.Path(__file__).resolve().parents[1] / "evals/datasets/dev_jobs.json").read_text())}
CANDIDATES = ["a02", "b01", "b02", "s01", "s02", "a11", "b11", "s11", "a13"]


def cfg(tools, thread, tags):
    return {"configurable": {"thread_id": thread, "tools": tools}, "tags": tags, "run_name": tags[0]}


async def critic_loop():
    for jid in CANDIDATES:
        j = DEV[jid]
        async with Tools(persona=j["persona"], user=f"trace-{j['persona']}") as t:
            with traced():
                out = await build(MemorySaver()).ainvoke({"job_id": jid, "user": personas_util.profile(j["persona"])}, cfg(t, f"cl-{jid}", ["critic-loop", jid]))
        loops = len(out.get("critiques", [])) - 1
        print(f"critic-loop candidate {jid}: loops={loops}")
        if loops >= 1:
            return jid
    print("no critic loop found among candidates")


async def crash_resume(jid="a01"):
    j = DEV[jid]
    db = str(pathlib.Path(tempfile.mkdtemp()) / "ckpt.sqlite")
    th = f"crash-{jid}"
    async with AsyncSqliteSaver.from_conn_string(db) as cp, Tools(persona=j["persona"], user="trace-crash") as t:
        with traced():
            out = await build(cp).ainvoke({"job_id": jid, "user": personas_util.profile(j["persona"])}, cfg(t, th, ["crash-resume-before", jid]))
        assert "__interrupt__" in out
    server.M = MockGigSim()  # fresh process: marketplace state reloaded from disk
    async with AsyncSqliteSaver.from_conn_string(db) as cp, Tools(persona=j["persona"], user="trace-crash") as t:
        with traced():
            out = await build(cp).ainvoke(Command(resume={"action": "approve"}), cfg(t, th, ["crash-resume-after-approve", jid]))
    print("crash-resume status:", out.get("status"))


async def forced_critic_loop(jid="a01", limit=40):
    """Only the Critic sees a tighter length limit than the Writer (policy says 250), so a normal first draft gets sent back.
    Demonstrates the bounded loop (max 2) when organic runs never trigger it. Tagged so the trace says so."""
    from agent.nodes import critic as critic_mod
    critic_mod.max_words = lambda: limit
    j = DEV[jid]
    async with Tools(persona=j["persona"], user="trace-forced") as t:
        with traced():
            out = await build(MemorySaver()).ainvoke({"job_id": jid, "user": personas_util.profile(j["persona"])}, cfg(t, f"forced-{jid}", [f"critic-loop-forced-{limit}w", jid]))
    print("forced critic loops:", len(out.get("critiques", [])) - 1)


if __name__ == "__main__":
    import sys
    async def main():
        if "--forced" in sys.argv:
            return await forced_critic_loop()
        await critic_loop()
        await crash_resume()
    asyncio.run(main())
