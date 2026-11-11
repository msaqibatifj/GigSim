import json
import pytest
from mcp.shared.memory import create_connected_server_and_client_session as connect
from mcp_servers.marketplace import guard, server


@pytest.fixture(autouse=True)
def _tmp(tmp_path, monkeypatch):
    monkeypatch.setattr(guard, "AUDIT", tmp_path / "audit.jsonl")
    guard.limiter.b.clear()
    guard.limiter.burst = 50
    return tmp_path


def js(r):
    return json.loads(r.content[0].text)


async def test_exactly_once_and_audit(_tmp):
    async with connect(server.mcp._mcp_server) as c:
        d = js(await c.call_tool("create_proposal_draft", {"job_id": "a01", "text": "hello", "idempotency_key": "key-draft-1"}))
        a = {"draft_id": d["id"], "idempotency_key": "key-submit-1"}
        s1 = js(await c.call_tool("submit_proposal", a))
        s2 = js(await c.call_tool("submit_proposal", a))
        assert s1["ok"] and not s1["replayed"] and s2["replayed"]
    lines = (_tmp / "audit.jsonl").read_text().splitlines()
    assert len(lines) == 3 and json.loads(lines[0])["tool"] == "create_proposal_draft"


async def test_dry_run_and_validation():
    async with connect(server.mcp._mcp_server) as c:
        bad = await c.call_tool("submit_proposal", {"draft_id": "nope", "idempotency_key": "short"})
        assert bad.isError
        d = js(await c.call_tool("create_proposal_draft", {"job_id": "a01", "text": "x", "idempotency_key": "key-draft-2"}))
        p = js(await c.call_tool("submit_proposal", {"draft_id": d["id"], "idempotency_key": "key-dry-001", "dry_run": True}))
        assert p["dry_run"] and p["connects_cost"] > 0


async def test_annotations():
    async with connect(server.mcp._mcp_server) as c:
        t = {x.name: x.annotations for x in (await c.list_tools()).tools}
        assert t["search_jobs"].readOnlyHint
        assert t["submit_proposal"].destructiveHint and not t["submit_proposal"].readOnlyHint


def test_rate_limit():
    l = guard.Limiter(rate_per_s=0.001, burst=2)
    l.check("u")
    l.check("u")
    with pytest.raises(guard.RateLimited):
        l.check("u")
    l.check("other")  # per-user isolation


def test_bearer_rejects_without_token(monkeypatch):
    from starlette.testclient import TestClient
    monkeypatch.setenv("MARKETPLACE_TOKENS", "tok:alice")
    assert TestClient(server.http_app()).post("/mcp", json={}).status_code == 401
