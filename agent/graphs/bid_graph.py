"""Bid graph (one thread per job). Hand-written StateGraph.
scout -> [analyst | risk | matcher] in parallel (Send) -> decide -> pricing -> writer -> verifier -> critic (<=2 send-backs)
      -> compliance -> approval (interrupt) -> execute (idempotent)."""
from langgraph.graph import END, START, StateGraph
from langgraph.types import RetryPolicy, Send, interrupt
from agent.config import cfg
from agent.handoffs import BidDecision
from agent.nodes.analyst import analyst
from agent.nodes.common import thresholds, tools
from agent.nodes.compliance import compliance
from agent.nodes.critic import critic
from agent.nodes.matcher import matcher
from agent.nodes.pricing import pricing
from agent.nodes.risk import risk
from agent.nodes.scout import scout
from agent.nodes.verifier import verifier
from agent.nodes.writer import writer
from agent.state import BidState

RETRY = RetryPolicy(max_attempts=3, initial_interval=0.5)  # per-node retries (tool errors, rate limits)


def fan_out(state):
    return [Send(n, state) for n in ("analyst", "risk", "matcher")]


async def decide(state, config):
    th, r, f = thresholds(), state["risk"], state["fit"]
    if len(r.flags) > th["max_risk_flags"]:
        d = BidDecision(action="skip", reasons=[f"risk flags: {', '.join(r.flags)}"] + r.reasons)
    elif f.score >= th["bid_min_fit"]:
        d = BidDecision(action="bid", reasons=f.reasons)
    elif f.score >= th["watch_min_fit"]:
        d = BidDecision(action="watch", reasons=["partial fit"] + f.reasons)
    else:
        d = BidDecision(action="skip", reasons=["low fit"] + f.reasons)
    return {"decision": d, "steps": 1}


def after_decide(state):
    return "pricing" if state["decision"].action == "bid" else "finish"


def after_pricing(state):
    return "writer" if state["price"].worth_connects else "finish"


def after_critic(state):
    if state.get("steps", 0) > cfg()["limits"]["max_steps"]:
        return "needs_attention"
    c = state["critiques"]
    sent_back = len(c) - 1
    return "writer" if (not c[-1].ok and sent_back < cfg()["limits"]["critic_max_loops"]) else "compliance"


def after_compliance(state):
    if not state["compliance"].allowed:
        return "needs_attention"
    if (state.get("approval") or {}).get("action") == "edit" and not state["compliance"].violations:
        return "execute"   # the user just approved exactly this text and compliance changed nothing: no second prompt
    return "approval"      # first draft, or compliance altered the user's edit: they must see what will really be sent


async def finish(state, config):
    d, p = state["decision"], state.get("price")
    status = "skipped" if d.action == "skip" or (p and not p.worth_connects) else "watching"
    return {"status": status}


async def needs_attention(state, config):
    return {"status": "needs_attention"}


async def approval(state, config):
    """Human gate. Everything before interrupt() must be idempotent: the node re-runs on resume."""
    t = tools(config)
    preview = await t.call("executor", "create_proposal_draft", {
        "job_id": state["job"]["id"], "text": state["draft"].cover_letter,
        "idempotency_key": f"{config['configurable']['thread_id']}:preview", "dry_run": True,
        "bid_usd": state["price"].amount_usd})
    answer = interrupt({
        "draft": state["draft"].model_dump(), "evidence": state.get("evidence", []), "risk": state["risk"].model_dump(),
        "price": state["price"].model_dump(), "critiques": [c.model_dump() for c in state["critiques"]],
        "compliance": state["compliance"].model_dump(), "dry_run": preview, "verification": state.get("verification")})
    upd = {"approval": answer, "steps": 1}
    if answer["action"] == "edit":
        st = config["configurable"].get("store")
        if st:  # edits reach style memory only through the promotion rule (agent/memory)
            from agent.memory.store import record_edit
            record_edit(st, config["configurable"]["user_id"], state["draft"].cover_letter, answer["text"])
        upd["draft"] = state["draft"].model_copy(update={"cover_letter": answer["text"]})
    return upd


def after_approval(state):
    return {"approve": "execute", "edit": "compliance", "reject": "rejected"}[state["approval"]["action"]]


async def rejected(state, config):
    return {"status": "rejected"}


async def execute(state, config):
    """Runs only after human approval. Keys derive from the thread id, so a crash + replay cannot double-send."""
    t, tid = tools(config), config["configurable"]["thread_id"]
    d = await t.call("executor", "create_proposal_draft", {"job_id": state["job"]["id"], "text": state["draft"].cover_letter,
                                                       "idempotency_key": f"{tid}:draft", "bid_usd": state["price"].amount_usd})
    s = await t.call("executor", "submit_proposal", {"draft_id": d["id"], "idempotency_key": f"{tid}:submit"})
    return {"result": {"draft": d, "submit": s}, "status": "submitted" if s["ok"] else "needs_attention"}


def build(checkpointer=None):
    g = StateGraph(BidState)
    for name, fn in [("scout", scout), ("analyst", analyst), ("risk", risk), ("matcher", matcher), ("decide", decide),
                     ("pricing", pricing), ("writer", writer), ("verifier", verifier), ("critic", critic),
                     ("compliance", compliance), ("approval", approval), ("execute", execute)]:
        g.add_node(name, fn, retry_policy=RETRY if name in {"scout", "risk", "matcher", "pricing", "execute"} else None)
    for name, fn in [("finish", finish), ("needs_attention", needs_attention), ("rejected", rejected)]:
        g.add_node(name, fn)
    g.add_edge(START, "scout")
    g.add_conditional_edges("scout", fan_out, ["analyst", "risk", "matcher"])
    g.add_edge(["analyst", "risk", "matcher"], "decide")  # join: waits for all three branches
    g.add_conditional_edges("decide", after_decide, ["pricing", "finish"])
    g.add_conditional_edges("pricing", after_pricing, ["writer", "finish"])
    g.add_edge("writer", "verifier")
    g.add_edge("verifier", "critic")
    g.add_conditional_edges("critic", after_critic, ["writer", "compliance", "needs_attention"])
    g.add_conditional_edges("compliance", after_compliance, ["approval", "needs_attention", "execute"])
    g.add_conditional_edges("approval", after_approval, ["execute", "compliance", "rejected"])
    for n in ("execute", "finish", "needs_attention", "rejected"):
        g.add_edge(n, END)
    return g.compile(checkpointer=checkpointer)


if __name__ == "__main__":  # `make graph`: render from code
    print(build().get_graph().draw_mermaid())
