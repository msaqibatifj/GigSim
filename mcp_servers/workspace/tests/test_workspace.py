import pytest
from mcp.shared.memory import create_connected_server_and_client_session as connect
from mcp_servers.workspace.server import mcp


@pytest.mark.asyncio
async def test_tools_and_annotations():
    async with connect(mcp._mcp_server) as c:
        tools = {t.name: t for t in (await c.list_tools()).tools}
        assert set(tools) == {"free_slots", "create_tentative_hold", "create_email_draft"}
        assert tools["free_slots"].annotations.readOnlyHint
        assert not tools["create_email_draft"].annotations.destructiveHint


@pytest.mark.asyncio
async def test_hold_removes_slot_and_is_idempotent():
    async with connect(mcp._mcp_server) as c:
        slots = (await c.call_tool("free_slots", {"days": 1})).structuredContent["result"]
        start = slots[0]["start"]
        for _ in range(2):
            r = await c.call_tool("create_tentative_hold", {"start": start, "title": "Interview"})
            assert not r.isError
        after = (await c.call_tool("free_slots", {"days": 1})).structuredContent["result"]
        assert start not in [s["start"] for s in after]


@pytest.mark.asyncio
async def test_bad_input_rejected():
    async with connect(mcp._mcp_server) as c:
        assert (await c.call_tool("free_slots", {"days": 99})).isError
        assert (await c.call_tool("create_email_draft", {"to_thread": "t1", "body": ""})).isError
