"""GigBid API. Run: uvicorn apps.api.main:app --reload
Serves /api/* and, when apps/web/dist exists, the built web app (one public URL)."""
import mcp_servers.portfolio.server  # noqa: F401  load onnxruntime first: on Windows it crashes if first loaded after threads start
import json, logging, os, pathlib, secrets
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from apps.api.routers import analytics, approvals, auth, jobs, messages, proposals, runs, settings
from apps.api.schemas import Health
from agent.config import profile
from agent.safety import mask

WEB = pathlib.Path(__file__).resolve().parents[1] / "web" / "dist"


_make_record = logging.getLogRecordFactory()


def _masked_record(*a, **k):
    """Emails, phones and payment details never reach the logs (E4). Masks at record creation, for every logger,
    keeping the args tuple's shape (uvicorn's access formatter unpacks exactly five values)."""
    r = _make_record(*a, **k)
    if isinstance(r.msg, str):
        r.msg = mask(r.msg)
    if isinstance(r.args, tuple):
        r.args = tuple(mask(x) if isinstance(x, str) else x for x in r.args)
    return r


logging.setLogRecordFactory(_masked_record)


def seed_reviewer():
    """Reviewer login comes from env only (never the repo); preloaded with a persona and a scouted inbox."""
    email, pw = os.getenv("REVIEWER_EMAIL"), os.getenv("REVIEWER_PASSWORD")
    if not email or not pw:
        return None
    from apps.api.auth.users import create_user
    from apps.api.db import q
    if q("SELECT 1 FROM users WHERE email=:e", e=email.lower()):
        return None
    uid = create_user(email, pw, os.getenv("REVIEWER_PERSONA") or "ayesha_ml")
    q("UPDATE users SET settings=:s WHERE id=:i", i=uid, s=json.dumps({"autonomy": "ask_always", "connects_budget_weekly": 60,
                                                                       "marketplace": "gigsim", "onboarded": True, "scout_every_hours": 4}))
    return uid


@asynccontextmanager
async def lifespan(app):
    uid = seed_reviewer()
    if uid:
        from apps.api.dispatch import enqueue
        await enqueue("scout_user", uid, key=f"seed-scout:{uid}")
    yield


app = FastAPI(title="GigBid API", version="1.0.0", lifespan=lifespan)


@app.middleware("http")
async def trace_id(request: Request, call_next):
    """One trace id per UI request: API -> graph run -> every MCP server -> audit log."""
    tid = request.headers.get("x-trace-id") or secrets.token_hex(8)
    request.state.trace = tid
    resp = await call_next(request)
    resp.headers["x-trace-id"] = tid
    return resp


for m in (auth, jobs, runs, approvals, proposals, messages, analytics, settings):
    app.include_router(m.r)


@app.get("/api/health", response_model=Health, tags=["health"])
async def health():
    """Drives the 'marketplace unavailable' banner."""
    from agent.mcp_client import Tools
    adapter = os.getenv("MARKETPLACE_ADAPTER", "gigsim")
    try:
        async with Tools(persona="ayesha_ml", user="healthcheck", trace="health") as t:
            await t.call("ui", "get_connects_balance")
        return Health(marketplace="up", marketplace_adapter=adapter, model_profile=profile())
    except Exception as e:
        return Health(marketplace="down", marketplace_adapter=adapter, model_profile=profile(), detail=type(e).__name__)


if WEB.exists():
    app.mount("/assets", StaticFiles(directory=WEB / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        f = WEB / path
        return FileResponse(f if path and f.is_file() else WEB / "index.html")
