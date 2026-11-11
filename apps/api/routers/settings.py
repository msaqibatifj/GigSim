"""Memory viewer: see and delete learned style rules and outcome stats."""
from fastapi import APIRouter
from apps.api.auth.users import UserDep
from apps.api.schemas import MemoryItem
from agent.memory.store import delete_item, get_store

r = APIRouter(prefix="/api/memory", tags=["settings"])


@r.get("", response_model=list[MemoryItem])
def memory(user: dict = UserDep):
    s = get_store()
    return [MemoryItem(kind=k, key=i.key, value=i.value) for k in ("style", "outcome") for i in s.search((user["id"], k))]


@r.delete("/{kind}/{key}")
def forget(kind: str, key: str, user: dict = UserDep):
    if kind not in ("style", "outcome"):
        return {"ok": False}
    delete_item(get_store(), user["id"], kind, key)   # also clears candidates so it cannot silently re-promote
    return {"ok": True}
