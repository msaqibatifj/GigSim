"""One entry point for every LLM call. Model comes from config; prompt comes from agent/prompts/<node>.md.
Per-run usage (tokens, USD, seconds per node) is collected through a context variable and enforced against the
thread token budget (agent/config.yaml limits.max_tokens)."""
import contextvars, itertools, json, os, string, time
import httpx
from pydantic import BaseModel
from agent.config import ROOT, cfg, model_for
from agent.safety import UNTRUSTED_KEYS, neutralise

BASES = {"groq": "https://api.groq.com/openai/v1", "openrouter": "https://openrouter.ai/api/v1",
         "together": "https://api.together.xyz/v1"}
LEDGER: dict = {}   # process-wide usage per node (eval runners read this)
RUN_USAGE: contextvars.ContextVar[dict | None] = contextvars.ContextVar("run_usage", default=None)  # per graph run


_key_i = itertools.count()


def api_key(provider: str, bump: bool = False) -> str:
    """Round-robin over <PROVIDER>_API_KEYS (comma-separated, one per account) so free-tier per-account rate limits add up.
    bump=True skips to the next key (used after a 429)."""
    return (_keys(provider) or [""])[next(_key_i) % max(len(_keys(provider)), 1)]


def _keys(provider: str) -> list[str]:
    raw = os.getenv(f"{provider.upper()}_API_KEYS", "").split(",") + [os.getenv(f"{provider.upper()}_API_KEY", "")]
    return list(dict.fromkeys(k.strip() for k in raw if k.strip()))


class BudgetExceeded(RuntimeError):
    """Thread token budget used up: the run moves to the visible 'needs_attention' state."""


def render(node: str, data: dict) -> str:
    tpl = string.Template((ROOT / "agent" / "prompts" / f"{node}.md").read_text(encoding="utf-8"))
    vals = {}
    for k, v in data.items():
        s = v if isinstance(v, str) else json.dumps(v, default=str, indent=1)
        vals[k] = neutralise(s) if k in UNTRUSTED_KEYS else s   # untrusted text cannot close its delimiter
    return tpl.safe_substitute(vals)


def usd(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    p = cfg().get("prices_usd_per_mtok", {}).get(model, [0, 0])
    return (prompt_tokens * p[0] + completion_tokens * p[1]) / 1e6


def _account(node, model, usage, seconds):
    cost = usd(model, *usage)
    for led in (LEDGER, RUN_USAGE.get()):
        if led is None:
            continue
        L = led.setdefault(node, {"calls": 0, "prompt_tokens": 0, "completion_tokens": 0, "seconds": 0.0, "usd": 0.0})
        L["calls"] += 1; L["prompt_tokens"] += usage[0]; L["completion_tokens"] += usage[1]
        L["seconds"] += seconds; L["usd"] += cost


def _check_budget():
    run = RUN_USAGE.get()
    if run is not None:
        used = sum(v["prompt_tokens"] + v["completion_tokens"] for v in run.values())
        if used > cfg()["limits"]["max_tokens"]:
            raise BudgetExceeded(f"token budget {cfg()['limits']['max_tokens']} exceeded ({used})")


def structured(node: str, schema: type[BaseModel], data: dict, retries: int = 3) -> BaseModel:
    _check_budget()
    m = model_for(node)
    t0 = time.perf_counter()
    if m["provider"] == "fake":
        from agent import llm_fake
        out, usage = schema.model_validate(llm_fake.respond(node, data)), (0, 0)
    else:
        try:
            out, usage = _traced(node, m, render(node, data), schema, retries)
        except Exception:
            fb = cfg()["profiles"][os.getenv("MODEL_PROFILE", "open")].get("fallback")  # cheap nodes fall back to a second model
            if not fb or cfg()["nodes"][node] != "small":
                raise
            m = fb
            out, usage = _traced(node, fb, render(node, data), schema, retries)
    _account(node, m["model"], usage, time.perf_counter() - t0)
    return out


def _traced(node, m, prompt, schema, retries):
    """LangSmith span with token usage and cost when tracing is on (PII masked by the client, apps/api/tracing.py)."""
    if os.getenv("LANGSMITH_TRACING", "").lower() != "true":
        return _remote(m, prompt, schema, retries)
    from langsmith import traceable

    @traceable(run_type="llm", name=node, metadata={"ls_provider": m["provider"], "ls_model_name": m["model"]})
    def call(messages):
        out, (pt, ct) = _remote(m, prompt, schema, retries)
        return {"choices": [{"message": {"role": "assistant", "content": out.model_dump_json()}}],
                "usage_metadata": {"input_tokens": pt, "output_tokens": ct, "total_tokens": pt + ct,
                                   "total_cost": usd(m["model"], pt, ct)}, "_out": out, "_usage": [pt, ct]}
    r = call([{"role": "user", "content": prompt}])
    return r["_out"], tuple(r["_usage"])


def _remote(m, prompt, schema, retries):
    p = m["provider"]
    base = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434") + "/v1" if p == "ollama" else BASES[p]
    body = {"model": m["model"], "response_format": {"type": "json_object"}, "temperature": 0,
            "messages": [{"role": "user", "content": prompt + "\n\nRespond with JSON only."}]}
    if m.get("reasoning_effort"):
        body["reasoning_effort"] = m["reasoning_effort"]
    for i in range(retries + 5):   # extra attempts are only spent on 429s (free-tier tokens/minute)
        try:
            r = httpx.post(f"{base}/chat/completions", json=body, headers={"Authorization": f"Bearer {api_key(p)}"}, timeout=90)
            if r.status_code == 429 and i < retries + 4:
                n_keys = max(len(_keys(p)), 1)
                if n_keys == 1 or i % n_keys == n_keys - 1:   # every key tried this round: wait; otherwise just try the next key
                    time.sleep(min(float(r.headers.get("retry-after", 2 ** i)), 60))
                continue
            if r.status_code in (429, 500, 502, 503):
                raise httpx.HTTPError(f"{r.status_code}")
            r.raise_for_status()
            j = r.json()
            u = j.get("usage", {})
            return schema.model_validate_json(j["choices"][0]["message"]["content"]), (u.get("prompt_tokens", 0), u.get("completion_tokens", 0))
        except (httpx.HTTPError, ValueError):
            if i >= retries - 1:
                raise
            time.sleep(2 ** i)  # bounded backoff


async def astructured(node: str, schema: type[BaseModel], data: dict, retries: int = 3) -> BaseModel:
    """Async nodes use this so parallel branches (analyst | risk | matcher) really overlap their LLM calls."""
    import asyncio
    return await asyncio.to_thread(structured, node, schema, data, retries)
