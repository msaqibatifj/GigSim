"""SSE bridge to LangGraph streams. The worker writes every stream_mode='updates' chunk to the events table;
this endpoint tails it, so streams survive API restarts and work across processes (API != worker)."""
import asyncio, json
from sse_starlette.sse import EventSourceResponse
from apps.api.db import q

DONE = {"submitted", "skipped", "watching", "rejected", "needs_attention", "dead_letter", "sent", "done", "skipped_by_user"}


def sse(run_id: str, poll_s: float = 0.4):
    async def gen():
        seq, idle = 0, 0
        while True:
            rows = q("SELECT seq, data FROM events WHERE run_id=:r AND seq>:s ORDER BY seq", r=run_id, s=seq)
            for e in rows:
                seq = e["seq"]
                yield {"id": str(seq), "event": json.loads(e["data"])["kind"], "data": e["data"]}
            status = q("SELECT status FROM runs WHERE id=:r", r=run_id)[0]["status"]
            if status in DONE or status == "awaiting_approval":
                yield {"event": "end", "data": json.dumps({"status": status})}
                return
            idle = 0 if rows else idle + 1
            if idle > 1500:   # ~10 min with nothing new: let the client reconnect
                return
            await asyncio.sleep(poll_s)
    return EventSourceResponse(gen(), ping=15)
