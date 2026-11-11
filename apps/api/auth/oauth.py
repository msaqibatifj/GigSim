"""OAuth 2.1 (authorization code + PKCE) for the official Upwork MCP server, following the MCP authorization spec:
protected-resource metadata (RFC 9728) -> authorization-server metadata (RFC 8414) -> optional dynamic client
registration (RFC 7591) -> code exchange. Tokens are stored Fernet-encrypted per user (auth/users.py), never logged.
shortcut: not exercised against a live Upwork account (none available); verify end-to-end before relying on it."""
import base64, hashlib, os, secrets, time
from urllib.parse import urlencode
import httpx
from apps.api.auth.users import save_token

MCP_URL = os.getenv("UPWORK_MCP_URL", "https://mcp.upwork.com/mcp")
_pending: dict[str, dict] = {}   # state -> {user, verifier, ...}; shortcut: in-memory, a restart mid-login means "connect again"


def _redirect_uri() -> str:
    return os.getenv("PUBLIC_URL", "http://localhost:8000").rstrip("/") + "/api/auth/upwork/callback"


async def _metadata(c: httpx.AsyncClient) -> dict:
    origin = MCP_URL.split("/mcp")[0]
    pr = (await c.get(f"{origin}/.well-known/oauth-protected-resource")).json()
    issuer = pr["authorization_servers"][0].rstrip("/")
    return (await c.get(f"{issuer}/.well-known/oauth-authorization-server")).json()


async def _client_id(c: httpx.AsyncClient, meta: dict) -> tuple[str, str | None]:
    if os.getenv("UPWORK_CLIENT_ID"):
        return os.environ["UPWORK_CLIENT_ID"], os.getenv("UPWORK_CLIENT_SECRET")
    if not meta.get("registration_endpoint"):
        raise RuntimeError("Upwork requires a registered client: set UPWORK_CLIENT_ID / UPWORK_CLIENT_SECRET")
    reg = (await c.post(meta["registration_endpoint"], json={
        "client_name": "GigBid", "redirect_uris": [_redirect_uri()], "grant_types": ["authorization_code", "refresh_token"],
        "response_types": ["code"], "token_endpoint_auth_method": "none"})).json()
    return reg["client_id"], reg.get("client_secret")


async def start(user_id: str) -> str:
    """Returns the URL to send the browser to."""
    async with httpx.AsyncClient(timeout=15) as c:
        meta = await _metadata(c)
        cid, secret = await _client_id(c, meta)
    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    state = secrets.token_urlsafe(24)
    _pending[state] = {"user": user_id, "verifier": verifier, "cid": cid, "secret": secret, "token_url": meta["token_endpoint"], "t": time.time()}
    return meta["authorization_endpoint"] + "?" + urlencode({
        "response_type": "code", "client_id": cid, "redirect_uri": _redirect_uri(), "state": state,
        "code_challenge": challenge, "code_challenge_method": "S256", "resource": MCP_URL})


async def finish(state: str, code: str) -> str:
    p = _pending.pop(state, None)
    if not p or time.time() - p["t"] > 600:
        raise ValueError("unknown or expired OAuth state")
    data = {"grant_type": "authorization_code", "code": code, "redirect_uri": _redirect_uri(), "client_id": p["cid"],
            "code_verifier": p["verifier"], "resource": MCP_URL}
    if p["secret"]:
        data["client_secret"] = p["secret"]
    async with httpx.AsyncClient(timeout=15) as c:
        r = await c.post(p["token_url"], data=data)
        r.raise_for_status()
        tok = r.json()
    tok["obtained_at"] = time.time()
    tok["client_id"], tok["token_url"] = p["cid"], p["token_url"]
    save_token(p["user"], "upwork", tok)
    return p["user"]
