"""Proposal studio and pipeline board."""
import json
from fastapi import APIRouter, HTTPException, Request
from apps.api.auth.users import UserDep
from apps.api.db import q
from apps.api.deps import get_run, latest_runs, ui_tools
from apps.api.schemas import Pending, PipelineCard, RegenerateIn, RegenerateOut
from apps.api.deps import run_out
from agent.llm import astructured
from agent.memory.store import get_store, record_outcome, style_rules
from pydantic import BaseModel

r = APIRouter(tags=["proposals"])
TERMINAL = {"replied", "interview", "hired", "lost"}


class _Para(BaseModel):
    text: str


@r.get("/api/proposals/{run_id}", response_model=Pending)
def studio(run_id: str, user: dict = UserDep):
    run = get_run(user, run_id)
    if not run:
        raise HTTPException(404, "run not found")
    return Pending(run=run_out(run), payload=json.loads(run["summary"] or "{}").get("approval") or {})


@r.post("/api/proposals/{run_id}/regenerate", response_model=RegenerateOut)
async def regenerate(run_id: str, body: RegenerateIn, request: Request, user: dict = UserDep):
    """Rewrite one paragraph. The result is only a suggestion in the editor: sending it is an 'edit' approval,
    which goes back through the Compliance Guard."""
    run = get_run(user, run_id)
    if not run or run["status"] != "awaiting_approval":
        raise HTTPException(409, "no draft awaiting approval")
    paras = [p for p in body.text.split("\n\n")]
    if body.paragraph >= len(paras):
        raise HTTPException(422, "no such paragraph")
    async with ui_tools(user, request.state.trace) as t:
        job = await t.call("ui", "get_job", {"job_id": run["ref"]})
    new = await astructured("paragraph", _Para, {"draft": body.text, "paragraph": paras[body.paragraph], "job": f"{job['title']}\n{job['description']}",
                                                 "job_obj": job, "style": style_rules(get_store(), user["id"])})
    paras[body.paragraph] = new.text.strip()
    return RegenerateOut(text="\n\n".join(paras))


@r.get("/api/pipeline", response_model=list[PipelineCard])
async def pipeline(request: Request, user: dict = UserDep):
    """Kanban: drafted -> submitted -> viewed -> replied -> interview -> hired / lost, driven by marketplace events.
    Terminal outcomes reach outcome memory only through promotion rule O1 (agent/memory)."""
    runs = latest_runs(user, "bid")
    async with ui_tools(user, request.state.trace) as t:
        events = {e["submission_id"]: e for e in await t.call("ui", "get_proposal_events", many=True) if isinstance(e, dict)}
        jobs = {}
        for ref, run in runs.items():
            if run["status"] in ("awaiting_approval", "resuming", "submitted"):
                jobs[ref] = await t.call("ui", "get_job", {"job_id": ref})
    cards, store = [], None
    for ref, run in runs.items():
        s = json.loads(run["summary"] or "{}")
        price = (s.get("price") or {}).get("amount_usd")
        if run["status"] in ("awaiting_approval", "resuming"):
            cards.append(PipelineCard(run_id=run["id"], job_id=ref, title=jobs[ref]["title"], stage="drafted", price_usd=price))
            continue
        sub = ((s.get("result") or {}).get("submit") or {}).get("id")
        if run["status"] != "submitted" or sub not in events:
            continue
        e = events[sub]
        cards.append(PipelineCard(run_id=run["id"], job_id=ref, title=jobs[ref]["title"], stage=e["stage"], price_usd=price,
                                  thread_id=e["thread_id"] if e["stage"] in TERMINAL - {"lost"} else None))
        if e["stage"] in {"replied", "interview", "hired", "lost"} and not s.get("outcome_recorded"):
            store = store or get_store()   # one observation per proposal: got a reply (good) or lost without one
            outcome = "lost" if e["stage"] == "lost" else "replied"
            record_outcome(store, user["id"], jobs[ref].get("category") or "general", outcome)
            s["outcome_recorded"] = outcome
            q("UPDATE runs SET summary=:s WHERE id=:i", i=run["id"], s=json.dumps(s))
        if e["stage"] == "hired" and not s.get("hired"):
            q("UPDATE runs SET summary=:s WHERE id=:i", i=run["id"], s=json.dumps({**s, "hired": True}))
    return cards
