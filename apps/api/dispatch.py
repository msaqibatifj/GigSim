"""Hand work to the worker. With REDIS_URL: arq queue (job id = dedupe key). Without (local dev, tests): in-process task."""
import asyncio, os
from worker import tasks

_pool = None
_background: set = set()


_sems: dict = {}


def _slots():
    return _sems.setdefault(asyncio.get_running_loop(), asyncio.Semaphore(int(os.getenv("LOCAL_WORKER_SLOTS", "3"))))


async def _arq():
    global _pool
    if _pool is None:
        from arq import create_pool
        from arq.connections import RedisSettings
        _pool = await create_pool(RedisSettings.from_dsn(os.environ["REDIS_URL"]))
    return _pool


async def enqueue(fn: str, *args, key: str):
    if os.getenv("REDIS_URL"):
        await (await _arq()).enqueue_job(fn, *args, _job_id=key)
        return
    async def local():   # shortcut: no retry-on-degraded loop in local mode; the UI "retry" button re-enqueues
        try:
            if fn == "scout_user":
                for rid in await tasks.scout_user({}, *args):
                    await enqueue("start_run", rid, key=f"start:{rid}")
            else:
                async with _slots():   # same bound as the arq worker's max_jobs: never 30 graph runs at once
                    await getattr(tasks, fn)({}, *args)
        except Exception:
            pass   # status and error are already recorded on the run by worker.tasks
    t = asyncio.create_task(local())
    _background.add(t)
    t.add_done_callback(_background.discard)
