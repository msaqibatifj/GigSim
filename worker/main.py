"""arq worker: `python -m arq worker.main.WorkerSettings`. Scouting and every graph run execute here, never in a web request.
Schedules: a cron tick every 15 min runs each saved search whose own interval has elapsed (docs/RUNBOOK.md)."""
import mcp_servers.portfolio.server  # noqa: F401  load onnxruntime first: on Windows it crashes if first loaded after threads start
import json, os, time
from arq import Retry, cron
from arq.connections import RedisSettings
from apps.api.db import q
from agent.mcp_client import MarketplaceDown
from worker import tasks

LIVE_MIN_HOURS = 6   # live Upwork mode never scouts more often than this, whatever the user sets


async def start_run(ctx, run_id):
    try:
        await tasks.start_run(ctx, run_id)
    except MarketplaceDown:
        raise Retry(defer=tasks.DEGRADED_RETRY_S)   # degraded mode: retry until the marketplace is back


async def resume_run(ctx, run_id, answer):
    try:
        await tasks.resume_run(ctx, run_id, answer)
    except MarketplaceDown:
        q("UPDATE runs SET status='resuming' WHERE id=:i", i=run_id)   # approval is kept; resume when back
        raise Retry(defer=tasks.DEGRADED_RETRY_S)


async def scout_user(ctx, user_id):
    for rid in await tasks.scout_user(ctx, user_id):
        await ctx["redis"].enqueue_job("start_run", rid, _job_id=f"start:{rid}")   # job id = dedupe key


def due(settings: dict, now: float) -> bool:
    hours = max(float(settings.get("scout_every_hours", 4)), LIVE_MIN_HOURS if os.getenv("MARKETPLACE_ADAPTER") == "upwork" else 1)
    return now - float(settings.get("last_scout", 0)) >= hours * 3600


async def scout_due(ctx):
    now = time.time()
    for u in q("SELECT id, settings FROM users"):
        s = json.loads(u["settings"] or "{}")
        if s.get("paused") or not due(s, now):
            continue
        s["last_scout"] = now
        q("UPDATE users SET settings=:s WHERE id=:i", s=json.dumps(s), i=u["id"])
        await ctx["redis"].enqueue_job("scout_user", u["id"], _job_id=f"scout:{u['id']}:{int(now // 900)}")


async def replay_run(ctx, run_id, checkpoint_id):
    await tasks.replay_run(ctx, run_id, checkpoint_id)


class WorkerSettings:
    functions = [start_run, resume_run, scout_user, replay_run]
    cron_jobs = [cron(scout_due, minute={0, 15, 30, 45}, run_at_startup=True)]
    redis_settings = RedisSettings.from_dsn(os.getenv("REDIS_URL", "redis://localhost:6379/0"))
    max_tries = 20
    job_timeout = 600
    max_jobs = 4


def test_due_respects_live_minimum(monkeypatch=None):
    assert due({"scout_every_hours": 1, "last_scout": 0}, 3600)
    assert not due({"scout_every_hours": 4, "last_scout": 0}, 3600)
