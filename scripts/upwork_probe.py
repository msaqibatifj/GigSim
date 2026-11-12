"""First thing to run once you have Upwork access: lists the real tools on the official Upwork MCP server and shows which
port methods in agent/config.yaml `upwork.tools` do not match, so fixing the mapping is a config edit.
Read-only (list_tools only). Token: UPWORK_ACCESS_TOKEN env var, or the signed-in user's stored token via --user <id>.
Run: python -m scripts.localenv scripts.upwork_probe [--user USER_ID]"""
import asyncio, os, sys
from agent.config import cfg
from mcp_servers.marketplace.adapters.upwork_live import URL, _token


async def main():
    user = sys.argv[sys.argv.index("--user") + 1] if "--user" in sys.argv else None
    token = os.getenv("UPWORK_ACCESS_TOKEN") or (_token(user) if user else None)
    if not token:
        sys.exit("Set UPWORK_ACCESS_TOKEN or pass --user <id> (after Settings > Connect Upwork).")
    from langchain_mcp_adapters.client import MultiServerMCPClient
    client = MultiServerMCPClient({"upwork": {"transport": "streamable_http", "url": URL, "headers": {"Authorization": f"Bearer {token}"}}})
    names = sorted(t.name for t in await client.get_tools())
    print(f"{len(names)} tools on {URL}:\n  " + "\n  ".join(names))
    bad = {k: v for k, v in cfg()["upwork"]["tools"].items() if v not in names}
    print("\nMapping OK" if not bad else "\nFix in agent/config.yaml upwork.tools (port method -> missing name):\n  " + "\n  ".join(f"{k}: {v}" for k, v in bad.items()))


if __name__ == "__main__":
    asyncio.run(main())
