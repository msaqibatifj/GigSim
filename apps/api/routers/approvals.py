"""Human approval (R4). Resumes the interrupted LangGraph thread in the worker. Pending approvals live in the
checkpoint + runs table, so a page refresh or an API restart never loses one."""
import json
from fastapi import APIRouter, HTTPException
from apps.api.auth.users import UserDep
from apps.api.db import q, x
from apps.api.deps import get_run, run_out
from apps.api.dispatch import enqueue
from apps.api.schemas import ApprovalIn, Pending, RunOut

r = APIRouter(prefix="/api/approvals", tags=["approvals"])


@r.get("", response_model=list[Pending])
def pending(user: dict = UserDep):
    rows = q("SELECT * FROM runs WHERE user_id=:u AND status='awaiting_approval' ORDER BY created DESC", u=user["id"])
    return [Pending(run=run_out(r), payload=json.loads(r["summary"]).get("approval") or {}) for r in rows]


@r.post("/{run_id}", response_model=RunOut)
async def decide(run_id: str, body: ApprovalIn, user: dict = UserDep):
    if body.action == "edit" and not (body.text or "").strip():
        raise HTTPException(422, "edit needs the edited text")
    if body.action == "reject" and not (body.reason or "").strip():
        raise HTTPException(422, "reject needs a reason")
    # compare-and-set: exactly one request can move a run out of awaiting_approval
    if not x("UPDATE runs SET status='resuming' WHERE id=:i AND user_id=:u AND status='awaiting_approval'", i=run_id, u=user["id"]):
        raise HTTPException(409, "nothing awaiting approval on this run (already decided?)")
    if body.action == "reject":
        s = json.loads(get_run(user, run_id)["summary"] or "{}")
        q("UPDATE runs SET summary=:s WHERE id=:i", i=run_id, s=json.dumps({**s, "rejection_reason": body.reason}))
    await enqueue("resume_run", run_id, body.model_dump(exclude_none=True), key=f"resume:{run_id}")
    return run_out(get_run(user, run_id))
