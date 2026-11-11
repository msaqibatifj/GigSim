import pytest
from mcp.shared.memory import create_connected_server_and_client_session as connect
from mcp_servers.portfolio.server import mcp

@pytest.mark.asyncio
async def test_tools_and_annotations():
    async with connect(mcp._mcp_server) as c:
        tools = {t.name: t for t in (await c.list_tools()).tools}
        assert set(tools) == {"search_evidence", "get_case_study", "list_skills"}
        assert all(t.annotations.readOnlyHint for t in tools.values())

@pytest.mark.asyncio
async def test_search_finds_gold_and_empty_for_unrelated():
    async with connect(mcp._mcp_server) as c:
        r = await c.call_tool("search_evidence", {"requirement": "hybrid search RAG over PDFs"})
        assert "c1" in r.content[0].text
        r = await c.call_tool("search_evidence", {"requirement": "kubernetes operators golang"})
        assert not r.content or "c1" not in r.content[0].text

@pytest.mark.asyncio
async def test_bad_input_rejected():
    async with connect(mcp._mcp_server) as c:
        r = await c.call_tool("search_evidence", {"requirement": "x", "k": 99})
        assert r.isError

@pytest.mark.asyncio
async def test_resources_and_prompts():
    async with connect(mcp._mcp_server) as c:
        assert (await c.list_resource_templates()).resourceTemplates
        assert len((await c.list_prompts()).prompts) == 2
