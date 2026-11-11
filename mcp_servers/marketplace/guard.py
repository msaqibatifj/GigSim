"""Cross-cutting: per-user rate limit, append-only audit log, bearer auth. Kept out of tool code."""
import contextvars, json, os, pathlib, time, threading

current_user = contextvars.ContextVar("user", default=None)   # set per HTTP request by BearerAuth
current_trace = contextvars.ContextVar("trace", default=None)


def who() -> str:  # stdio/in-process fall back to env, set per call by the MCP client
    return current_user.get() or os.getenv("MARKETPLACE_USER", "dev")


def trace_id() -> str:
    return current_trace.get() or os.getenv("GIGBID_TRACE", "-")
AUDIT = pathlib.Path(os.getenv("AUDIT_LOG", "data/processed/audit.jsonl"))


class RateLimited(Exception): ...


class Limiter:  # token bucket per user; defaults stay well under a typical simulator limit
    def __init__(self, rate_per_s=2.0, burst=5):
        self.rate, self.burst, self.b, self.lock = rate_per_s, burst, {}, threading.Lock()

    def check(self, user):
        with self.lock:
            now = time.monotonic()
            tokens, t = self.b.get(user, (self.burst, now))
            tokens = min(self.burst, tokens + (now - t) * self.rate)
            if tokens < 1:
                self.b[user] = (tokens, now)
                raise RateLimited(f"rate limit for {user}; retry shortly")
            self.b[user] = (tokens - 1, now)


limiter = Limiter()


def audit(tool, args, result):
    AUDIT.parent.mkdir(parents=True, exist_ok=True)
    with AUDIT.open("a", encoding="utf-8") as f:  # append-only
        f.write(json.dumps({"ts": time.time(), "user": who(), "tool": tool, "args": args,
                            "result": result, "trace_id": trace_id()}, default=str) + "\n")


def guarded(name):
    def deco(fn):
        def wrapper(**kw):
            limiter.check(who())
            try:
                res = fn(**kw)
            except Exception as e:
                audit(name, kw, {"error": str(e)})
                raise
            audit(name, kw, res.model_dump() if hasattr(res, "model_dump") else res)
            return res
        # keep the original signature so FastMCP builds the input schema from it
        wrapper.__name__, wrapper.__doc__, wrapper.__wrapped__ = fn.__name__, fn.__doc__, fn
        return wrapper
    return deco


class BearerAuth:  # ASGI middleware; MARKETPLACE_TOKENS="token1:alice,token2:bob,svc-token:*"
    """A token mapped to "*" is the GigBid service token: it acts for the user named in X-GigBid-User."""
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            tokens = dict(p.split(":", 1) for p in os.getenv("MARKETPLACE_TOKENS", "").split(",") if ":" in p)
            h = {k.decode().lower(): v.decode() for k, v in scope["headers"]}
            tok = h.get("authorization", "").removeprefix("Bearer ").strip()
            if tok not in tokens:
                await send({"type": "http.response.start", "status": 401, "headers": [(b"content-type", b"text/plain")]})
                await send({"type": "http.response.body", "body": b"unauthorized"})
                return
            current_user.set(h.get("x-gigbid-user", "dev") if tokens[tok] == "*" else tokens[tok])
            current_trace.set(h.get("x-trace-id", "-"))
        await self.app(scope, receive, send)
