"""MCP access for agents. Agents get only the tools on their allowlist; they never import adapters.
mode "inproc": servers run in this process over an in-memory MCP session (tests, evals; fast).
mode "stdio":  each server is a subprocess via MultiServerMCPClient (docker/prod uses streamable HTTP instead)."""
import contextlib, json, os, sys
from langchain_mcp_adapters.tools import load_mcp_tools

# agent -> allowed tool names (spec section 5, "MCP Access")
ALLOW = {
    "scout": {"search_jobs", "get_job"},
    "risk": {"get_client_history", "get_job"},
    "matcher": {"search_evidence", "list_skills"},
    "pricing": {"get_client_history", "get_market_stats", "get_connects_balance"},
    "writer": {"search_evidence", "get_case_study"},
    "critic": {"search_evidence", "get_case_study"},
    "liaison": {"list_threads", "list_messages", "send_message", "free_slots", "create_tentative_hold", "create_email_draft"},
    "ui": {"search_jobs", "get_job", "get_client_history", "get_connects_balance", "list_threads", "list_messages", "get_proposal_events"},  # API read-only views
    "executor": {"get_job", "create_proposal_draft", "submit_proposal", "send_message"},  # runs only after human approval
}
SERVERS = {"portfolio": "mcp_servers.portfolio.server", "marketplace": "mcp_servers.marketplace.server", "workspace": "mcp_servers.workspace.server"}
import asyncio, weakref
_LOCKS = weakref.WeakKeyDictionary()  # per event loop (a module-level Lock binds to the first loop), then per server


def _lock(server: str):
    """In-process servers read the caller's identity from env vars that belong to ONE server each, so serialise per
    server: a slow portfolio rerank must not block fast marketplace reads."""
    return _LOCKS.setdefault(asyncio.get_running_loop(), {}).setdefault(server, asyncio.Lock())


class _NoLock:   # remote servers get identity from request headers: nothing to serialise
    async def __aenter__(self): return self
    async def __aexit__(self, *a): return False


TIMEOUT_S = 20
RETRIES = 4


def _parse(blocks, many):
    items = []
    for b in blocks if isinstance(blocks, list) else [{"text": blocks}]:
        t = b.get("text", "") if isinstance(b, dict) else str(b)
        try:
            items.append(json.loads(t))
        except ValueError:
            items.append(t)
    return items if many or len(items) != 1 else items[0]


class Tools:
    """Usage: async with Tools(persona="ayesha_ml") as t: await t.call("scout", "search_jobs", {...})"""

    def __init__(self, persona="ayesha_ml", mode=None, user="dev", trace="-", servers=None):
        self.user, self.trace, self.servers = user, trace, servers   # servers: subset to connect (API views need only the marketplace)
        self.persona, self.mode, self._tools = persona, mode or os.getenv("MCP_MODE", "inproc"), {}
        self._srv, self._remote = {}, set()   # tool name -> server name; servers reached over HTTP
        self._stack = contextlib.AsyncExitStack()

    async def __aenter__(self):
        await self._stack.__aenter__()
        os.environ["PORTFOLIO_PERSONA"] = self.persona
        for name, module in SERVERS.items():
            if self.servers and name not in self.servers:
                continue
            url = os.getenv(f"{name.upper()}_MCP_URL")
            if url:  # remote server over Streamable HTTP; a fresh session per call, so a restarted server is picked up
                conn = {"transport": "streamable_http", "url": url, "timeout": TIMEOUT_S,
                        "headers": {"Authorization": f"Bearer {os.getenv(f'{name.upper()}_MCP_TOKEN', '')}",
                                    "X-GigBid-User": self.user, "X-Trace-Id": self.trace}}
                try:
                    for t in await load_mcp_tools(None, connection=conn):
                        self._tools[t.name], self._srv[t.name] = t, name
                    self._remote.add(name)
                except Exception as e:
                    if name == "marketplace":
                        raise MarketplaceDown(f"marketplace MCP server unreachable at {url}: {type(e).__name__}") from e
                    raise
                continue
            if self.mode == "inproc":
                import importlib
                from mcp.shared.memory import create_connected_server_and_client_session as connect
                srv = importlib.import_module(module).mcp
                session = await self._stack.enter_async_context(connect(srv._mcp_server))
            else:
                from mcp import StdioServerParameters, stdio_client, ClientSession
                p = StdioServerParameters(command=sys.executable, args=["-m", module], env={**os.environ})
                r, w = await self._stack.enter_async_context(stdio_client(p))
                session = await self._stack.enter_async_context(ClientSession(r, w))
                await session.initialize()
            for t in await load_mcp_tools(session):
                self._tools[t.name], self._srv[t.name] = t, name
        return self

    async def __aexit__(self, *a):
        return await self._stack.__aexit__(*a)

    async def call(self, agent, name, args=None, many=False):
        import asyncio
        if name not in ALLOW[agent]:
            raise PermissionError(f"{agent} may not call {name}")
        for attempt in range(RETRIES):
            srv = self._srv[name]
            async with (_NoLock() if srv in self._remote else _lock(srv)):   # serialise so concurrent runs can't mix users
                if srv == "portfolio":
                    os.environ["PORTFOLIO_PERSONA"] = self.persona
                elif srv == "marketplace":
                    os.environ.update(MARKETPLACE_USER=self.user, GIGBID_TRACE=self.trace)
                try:
                    out = await asyncio.wait_for(self._tools[name].ainvoke(args or {}), TIMEOUT_S)
                except (OSError, asyncio.TimeoutError, ExceptionGroup) as e:   # transport failure, not a tool error
                    if name in MARKETPLACE_TOOLS and attempt == RETRIES - 1:
                        raise MarketplaceDown(f"{name}: {type(e).__name__}") from e
                    await asyncio.sleep(0.5 * 2 ** attempt)
                    continue
            res = _parse(out, many)
            err = res if isinstance(res, str) and res.startswith("Error executing tool") else None
            if err is None:
                return res
            if "rate limit" in err and attempt < RETRIES - 1:
                await asyncio.sleep(0.5 * 2 ** attempt)  # bounded exponential backoff
                continue
            raise ToolError(err)


class ToolError(RuntimeError): ...


class MarketplaceDown(RuntimeError):
    """The marketplace server is unreachable: runs go to queued_degraded and the UI shows a banner."""


MARKETPLACE_TOOLS = {"search_jobs", "get_job", "get_client_history", "get_connects_balance", "get_market_stats", "list_threads",
                     "list_messages", "get_proposal_events", "create_proposal_draft", "submit_proposal", "send_message"}
