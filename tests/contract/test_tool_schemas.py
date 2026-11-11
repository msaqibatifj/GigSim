"""Fails when any MCP tool signature changes unintentionally. Intentional change: UPDATE_SNAPSHOTS=1 pytest tests/contract"""
import json, os, pathlib
import pytest
from mcp.shared.memory import create_connected_server_and_client_session as connect
from mcp_servers.marketplace.server import mcp as marketplace
from mcp_servers.portfolio.server import mcp as portfolio
from mcp_servers.workspace.server import mcp as workspace

SNAP = pathlib.Path(__file__).parent / "snapshots"


@pytest.mark.parametrize("name,srv", [("portfolio", portfolio), ("marketplace", marketplace), ("workspace", workspace)])
async def test_schema_snapshot(name, srv):
    async with connect(srv._mcp_server) as c:
        cur = {t.name: {"in": t.inputSchema, "out": t.outputSchema, "ann": t.annotations.model_dump(exclude_none=True) if t.annotations else None}
               for t in (await c.list_tools()).tools}
    f = SNAP / f"{name}.json"
    if os.getenv("UPDATE_SNAPSHOTS") or not f.exists():
        SNAP.mkdir(exist_ok=True)
        f.write_text(json.dumps(cur, indent=1, sort_keys=True))
    assert json.loads(f.read_text()) == json.loads(json.dumps(cur, sort_keys=True))
