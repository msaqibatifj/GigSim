import os, tempfile
# test processes never touch the dev databases (set before any app module creates its engine)
_TMP = tempfile.mkdtemp(prefix="gigbid-test-")
os.environ.setdefault("APP_DATABASE_URL", f"sqlite:///{_TMP}/app.sqlite")
os.environ.setdefault("MEMORY_DB", f"{_TMP}/memory.sqlite")
os.environ.setdefault("CHECKPOINT_DB", f"{_TMP}/ckpt.sqlite")
os.environ.setdefault("AUDIT_LOG", f"{_TMP}/audit.jsonl")
os.environ.pop("DATABASE_URL", None)
os.environ.pop("REDIS_URL", None)
import mcp_servers.portfolio.server  # noqa: F401  load onnxruntime first: on Windows it crashes if first loaded after threads start
import pytest
from mcp_servers.marketplace.adapters import gigsim

@pytest.fixture(autouse=True)
def _isolated_mock_state(tmp_path, monkeypatch):
    monkeypatch.setattr(gigsim, "STATE", tmp_path / "mock_gigsim.json")
    from mcp_servers.marketplace import guard
    monkeypatch.setattr(guard.limiter, 'burst', 1000)
    guard.limiter.b.clear()
    try:
        from mcp_servers.marketplace import server
        monkeypatch.setattr(server, "M", gigsim.MockGigSim())
    except ImportError:
        pass
