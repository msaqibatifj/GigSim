"""Whole stack over HTTP (offline model profile): onboarding -> scout -> analysis in the background worker path ->
approval -> submitted exactly once. Also: double-approve is refused, reject needs a reason, pending approval survives."""
import asyncio, uuid
import httpx
import pytest
from apps.api.main import app


@pytest.fixture(autouse=True)
def _offline(monkeypatch):
    monkeypatch.setenv("MODEL_PROFILE", "offline")


async def wait_status(c, run_id, want, timeout=120):
    for _ in range(int(timeout / 0.25)):
        r = (await c.get(f"/api/runs/{run_id}")).json()
        if r["status"] in want:
            return r
        await asyncio.sleep(0.25)
    raise AssertionError(f"run {run_id} stuck in {r['status']}")


async def test_onboard_scout_approve_submit_once():
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        assert (await c.get("/api/jobs")).status_code == 401
        me = (await c.post("/api/auth/signup", json={"email": f"{uuid.uuid4().hex[:8]}@x.io", "password": "pw-123456", "persona": "ayesha_ml"})).json()
        assert me["persona"] == "ayesha_ml"
        assert (await c.put("/api/auth/settings", json={**me["settings"], "floor": 30, "onboarded": True})).json()["settings"]["onboarded"]
        run = (await c.post("/api/jobs/a01/analyse")).json()
        done = await wait_status(c, run["id"], {"awaiting_approval", "skipped", "error", "dead_letter"})
        assert done["status"] == "awaiting_approval", done["summary"].get("error")
        pend = (await c.get("/api/approvals")).json()
        assert pend and pend[0]["payload"]["dry_run"]["dry_run"] and pend[0]["payload"]["evidence"]
        detail = (await c.get("/api/jobs/a01")).json()
        assert detail["state"]["fit"]["evidence"] and detail["state"]["risk"]
        assert (await c.post(f"/api/approvals/{run['id']}", json={"action": "reject"})).status_code == 422
        assert (await c.post(f"/api/approvals/{run['id']}", json={"action": "approve"})).status_code == 200
        assert (await c.post(f"/api/approvals/{run['id']}", json={"action": "approve"})).status_code == 409   # no double submit
        done = await wait_status(c, run["id"], {"submitted", "error", "needs_attention"})
        assert done["status"] == "submitted"
        cards = (await c.get("/api/pipeline")).json()
        assert [x["stage"] for x in cards if x["run_id"] == run["id"]] == ["submitted"]
        ev = (await c.get(f"/api/runs/{run['id']}/events")).json()
        assert {"analyst", "risk", "matcher", "writer", "execute"} <= {e["data"].get("node") for e in ev}


async def test_scam_is_skipped_and_health():
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        await c.post("/api/auth/signup", json={"email": f"{uuid.uuid4().hex[:8]}@x.io", "password": "pw-123456", "persona": "ayesha_ml"})
        run = (await c.post("/api/jobs/a12/analyse")).json()
        assert (await wait_status(c, run["id"], {"skipped", "awaiting_approval", "error"}))["status"] == "skipped"
        assert (await c.get("/api/health")).json()["marketplace"] == "up"
