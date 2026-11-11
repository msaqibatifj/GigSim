"""Conversation graph (one thread per client conversation): read -> classify -> draft -> approve (interrupt) -> send."""
import operator
from typing import Annotated, TypedDict
from langgraph.graph import END, START, StateGraph
from langgraph.types import RetryPolicy, interrupt
from agent.handoffs import ClientIntent, ReplyDraft
from agent.llm import astructured
from agent.nodes.common import tools

RETRY = RetryPolicy(max_attempts=3, initial_interval=0.5)


class ConvState(TypedDict, total=False):
    thread_id: str
    message: dict
    intent: ClientIntent
    reply: ReplyDraft
    approval: dict
    result: dict
    steps: Annotated[int, operator.add]
    status: str


async def read(state, config):
    msgs = await tools(config).call("liaison", "list_messages", {"thread_id": state["thread_id"]}, many=True)
    client = [m for m in msgs if isinstance(m, dict) and m["sender"] == "client"]
    return {"message": client[-1], "steps": 1}


async def classify(state, config):
    m = state["message"]
    return {"intent": await astructured("liaison_intent", ClientIntent, {"message": m["text"], "message_obj": m}), "steps": 1}


def after_classify(state):
    return "flag" if state["intent"].intent == "scam_signal" else "draft"


async def flag(state, config):
    return {"status": "needs_attention"}  # surfaced in the UI; never auto-replied


async def draft(state, config):
    t, i = tools(config), state["intent"].intent
    slots = []
    if i == "interview_request":
        slots = [s["start"] for s in await t.call("liaison", "free_slots", {"days": 2}, many=True)]
    r = await astructured("liaison", ReplyDraft, {"intent": i, "message": state["message"]["text"], "message_obj": state["message"], "slots": slots})
    return {"reply": r, "steps": 1}


async def approval(state, config):
    a = interrupt({"message": state["message"], "intent": state["intent"].model_dump(), "reply": state["reply"].model_dump()})
    upd = {"approval": a}
    if a["action"] == "edit":
        upd["reply"] = state["reply"].model_copy(update={"text": a["text"]})
    return upd


def after_approval(state):
    return "send" if state["approval"]["action"] in ("approve", "edit") else "rejected"


async def send(state, config):
    t, tid = tools(config), config["configurable"]["thread_id"]
    key = f"reply:{tid}:{state['message']['id']}"   # one reply per client message, even on replay
    r = await t.call("liaison", "send_message", {"thread_id": state["thread_id"], "text": state["reply"].text, "idempotency_key": key})
    holds = [await t.call("liaison", "create_tentative_hold", {"start": s, "title": "Client interview"}) for s in state["reply"].slots[:1]]
    return {"result": {"sent": r, "holds": holds}, "status": "sent"}


async def rejected(state, config):
    return {"status": "rejected"}


def build(checkpointer=None):
    g = StateGraph(ConvState)
    for n, f in [("read", read), ("classify", classify), ("draft", draft), ("approval", approval), ("send", send)]:
        g.add_node(n, f, retry_policy=RETRY if n in ("read", "send") else None)
    g.add_node("flag", flag)
    g.add_node("rejected", rejected)
    g.add_edge(START, "read")
    g.add_edge("read", "classify")
    g.add_conditional_edges("classify", after_classify, ["flag", "draft"])
    g.add_edge("draft", "approval")
    g.add_conditional_edges("approval", after_approval, ["send", "rejected"])
    for n in ("send", "flag", "rejected"):
        g.add_edge(n, END)
    return g.compile(checkpointer=checkpointer)


if __name__ == "__main__":
    print(build().get_graph().draw_mermaid())
