"""Long agent runs and scheduled scouting. Executed by the arq worker (worker/main.py), never inside a web request.
Local dev without Redis: apps/api falls back to an in-process asyncio task calling the same functions.

Exactly-once rules:
- one graph thread per run; restarting a run continues from its checkpoint instead of starting over
- marketplace writes carry idempotency keys derived from the thread id (agent/graphs/bid_graph.py execute)"""
import contextlib, json, os, secrets, time, uuid
from langgraph.types import Command
from apps.api.db import q
from agent.config import cfg
from agent.llm import RUN_USAGE, BudgetExceeded
from agent.mcp_client import MarketplaceDown, Tools
from agent.tracing import traced

DEGRADED_RETRY_S = 30


def _json(o):
    return o.model_dump() if hasattr(o, "model_dump") else str(o)


def _serde():
    """Checkpoints hold our Pydantic hand-offs; allow exactly those types to deserialize (nothing else)."""
    import inspect
    from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
    from agent import handoffs
    allowed = [("agent.handoffs", n) for n, c in vars(handoffs).items() if inspect.isclass(c) and c.__module__ == "agent.handoffs"]
    return JsonPlusSerializer(allowed_msgpack_modules=allowed)


@contextlib.asynccontextmanager
async def checkpointer():
    """Postgres in docker/prod (DATABASE_URL=postgresql://...), sqlite file locally."""
    url = os.getenv("DATABASE_URL", "")
    if url.startswith("postgres"):
        from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
        async with AsyncPostgresSaver.from_conn_string(url, serde=_serde()) as cp:
            await cp.setup()
            yield cp
    else:
        from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
        os.makedirs("data/processed", exist_ok=True)
        async with AsyncSqliteSaver.from_conn_string(os.getenv("CHECKPOINT_DB", "data/processed/checkpoints.sqlite")) as cp:
            cp.serde = _serde()
            yield cp


def emit(run_id: str, kind: str, data: dict):
    seq = q("SELECT COALESCE(MAX(seq),0)+1 AS n FROM events WHERE run_id=:r", r=run_id)[0]["n"]
    q("INSERT INTO events(run_id,seq,data) VALUES (:r,:s,:d)", r=run_id, s=seq,
      d=json.dumps({"kind": kind, "ts": time.time(), **data}, default=_json))


def set_run(run_id: str, **kw):
    if "summary" in kw:
        cur = json.loads(q("SELECT summary FROM runs WHERE id=:i", i=run_id)[0]["summary"] or "{}")
        kw["summary"] = json.dumps({**cur, **kw["summary"]}, default=_json)
    sets = ",".join(f"{k}=:{k}" for k in kw)
    q(f"UPDATE runs SET {sets} WHERE id=:id", id=run_id, **kw)


def new_run(user_id: str, kind: str, ref: str) -> str:
    rid = uuid.uuid4().hex[:12]
    q("INSERT INTO runs(id,user_id,kind,ref,thread_id,status,trace_id,attempts,created,summary) "
      "VALUES (:i,:u,:k,:r,:t,'queued',:tr,0,:c,'{}')",
      i=rid, u=user_id, k=kind, r=ref, t=f"{kind}-{user_id}-{ref}-{rid}", tr=secrets.token_hex(8), c=time.time())
    return rid


def _summarise(update: dict) -> dict:
    """The few fields the inbox/pipeline need, pulled from a node update (full state stays in the checkpoint)."""
    s = {}
    for k, f in (("decision", "decision"), ("fit", "fit"), ("risk", "risk"), ("price", "price"), ("spec", "spec"),
                 ("compliance", "compliance"), ("verification", "verification"), ("result", "result"), ("intent", "intent")):
        if k in update:
            s[f] = update[k]
    if "status" in update:
        s["final"] = update["status"]
    if isinstance(update.get("job"), dict):
        s["job_category"], s["job_title"] = update["job"].get("category"), update["job"]["title"]
    return s


async def _drive(run: dict, graph_inp, user: dict, checkpoint_id: str | None = None):
    from agent.memory.store import get_store, style_rules
    from agent.graphs import bid_graph, conversation_graph
    builder = bid_graph.build if run["kind"] == "bid" else conversation_graph.build
    store = get_store()
    cfg_ = {"configurable": {"thread_id": run["thread_id"], "user_id": user["id"], "store": store,
                             "style": style_rules(store, user["id"])},
            "run_name": f"{run['kind']}:{run['ref']}", "metadata": {"run_id": run["id"], "trace_id": run["trace_id"], "user": user["id"]},
            "tags": [run["kind"]], "run_id": uuid.uuid4()}
    if checkpoint_id:   # replay: continue from an earlier checkpoint (forks the thread)
        cfg_["configurable"]["checkpoint_id"] = checkpoint_id   # LangSmith root run id -> trace link
    set_run(run["id"], status="running", attempts=(run["attempts"] or 0) + 1)
    emit(run["id"], "status", {"status": "running"})
    prev = json.loads(q("SELECT summary FROM runs WHERE id=:i", i=run["id"])[0]["summary"] or "{}")
    usage, t0 = prev.get("usage") or {}, time.perf_counter()
    token = RUN_USAGE.set(usage)
    try:
        async with checkpointer() as cp, Tools(persona=user["persona"], user=user["id"], trace=run["trace_id"]) as tools:
            with traced():
                cfg_["configurable"]["tools"] = tools
                g = builder(cp)
                snap = await g.aget_state(cfg_)
                if graph_inp is not None and not isinstance(graph_inp, Command) and snap.values:
                    graph_inp = None   # worker restart: continue the existing thread, never re-analyse from scratch
                if isinstance(graph_inp, Command) and not getattr(snap, "interrupts", ()):
                    graph_inp = None   # approval already consumed before a crash: continue to execute, don't resume twice
                payload = None
                # never break out of astream early: that cancels LangGraph's pending checkpoint writes
                async for chunk in g.astream(graph_inp, cfg_, stream_mode="updates"):
                    for node, upd in chunk.items():
                        if node == "__interrupt__":
                            payload = upd[0].value
                        elif not node.startswith("__"):
                            upd = upd or {}
                            set_run(run["id"], summary=_summarise(upd))
                            emit(run["id"], "node", {"node": node, "update": upd})
                if payload is not None:
                    set_run(run["id"], status="awaiting_approval", summary={"approval": payload})
                    emit(run["id"], "interrupt", {"node": "approval", "payload": payload})
                    return
                final = (await g.aget_state(cfg_)).values.get("status", "done")
                set_run(run["id"], status=final, summary={"approval": None})
                emit(run["id"], "status", {"status": final})
    except BudgetExceeded as e:   # step/token budget: visible "needs attention" state, never silently dropped
        set_run(run["id"], status="needs_attention", summary={"error": str(e)})
        emit(run["id"], "status", {"status": "needs_attention", "error": str(e)})
    except MarketplaceDown as e:   # degraded mode: queue and recover, the checkpoint keeps finished nodes
        set_run(run["id"], status="queued_degraded")
        emit(run["id"], "status", {"status": "queued_degraded", "error": str(e)})
        raise
    except Exception as e:
        dead = (run["attempts"] or 0) + 1 >= 3
        set_run(run["id"], status="dead_letter" if dead else "error", summary={"error": f"{type(e).__name__}: {e}"[:500]})
        emit(run["id"], "status", {"status": "dead_letter" if dead else "error", "error": str(e)[:500]})
        if not dead:
            raise
    finally:
        RUN_USAGE.reset(token)
        secs = round(prev.get("seconds", 0) + time.perf_counter() - t0, 2)
        set_run(run["id"], summary={"usage": usage, "seconds": secs, "trace_url": _trace_url(cfg_["run_id"]) or prev.get("trace_url")})


def _trace_url(run_uuid) -> str | None:
    if os.getenv("LANGSMITH_TRACING", "").lower() != "true":
        return None
    try:
        from langsmith import Client
        c = Client()
        return c.get_run_url(run=c.read_run(run_uuid))
    except Exception:
        return None   # trace not flushed yet / tracing off: the UI just hides the link


def _load(run_id: str):
    run = q("SELECT * FROM runs WHERE id=:i", i=run_id)[0]
    user = q("SELECT * FROM users WHERE id=:u", u=run["user_id"])[0]
    return run, user


async def start_run(ctx, run_id: str):
    run, user = _load(run_id)
    if run["status"] not in ("queued", "queued_degraded", "error"):
        return  # already running/finished: a duplicate enqueue is a no-op
    if run["kind"] == "bid":
        from data import personas_util
        prof = personas_util.profile(user["persona"])
        settings = json.loads(user["settings"] or "{}")
        prof.update({k: settings[k] for k in ("rate", "floor") if k in settings})
        inp = {"job_id": run["ref"], "user": prof}
    else:
        inp = {"thread_id": run["ref"]}
    await _drive(run, inp, user)


async def resume_run(ctx, run_id: str, answer: dict):
    run, user = _load(run_id)
    if run["status"] != "awaiting_approval" and run["status"] != "resuming":
        return  # approval already consumed: never resumes twice
    emit(run_id, "approval", {"answer": answer})
    await _drive(run, Command(resume=answer), user)


async def replay_run(ctx, run_id: str, checkpoint_id: str):
    run, user = _load(run_id)
    await _drive(run, None, user, checkpoint_id=checkpoint_id)


async def scout_user(ctx, user_id: str):
    """One saved-search pass for one user: search (via the Scout's MCP allowlist), dedupe, queue new jobs."""
    user = q("SELECT * FROM users WHERE id=:u", u=user_id)[0]
    from data import personas_util
    cat = personas_util.profile(user["persona"]).get("category")
    searches = json.loads(user["settings"] or "{}").get("saved_searches") or [{"query": "", "category": cat}]
    seen = {r["ref"] for r in q("SELECT ref FROM runs WHERE user_id=:u AND kind='bid'", u=user_id)}
    queued = []
    batch = int(os.getenv("GIGBID_SCOUT_BATCH") or cfg()["limits"].get("scout_batch", 10))   # new jobs queued per pass: bounded work, polite to the marketplace
    async with Tools(persona=user["persona"], user=user_id, trace="scout-" + secrets.token_hex(4), servers=("marketplace",)) as t:
        for s in searches:
            for job in await t.call("scout", "search_jobs", {"query": s.get("query", ""), "limit": 30,
                                                                 **({"category": s["category"]} if s.get("category") else {})}, many=True):
                if len(queued) >= batch:
                    return queued
                if isinstance(job, dict) and job["id"] not in seen:
                    seen.add(job["id"])
                    queued.append(new_run(user_id, "bid", job["id"]))
    return queued
