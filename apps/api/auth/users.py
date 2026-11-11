"""Users, sessions (opaque cookie tokens) and the encrypted OAuth token store."""
import base64, hashlib, hmac, json, os, secrets, time
from cryptography.fernet import Fernet
from fastapi import Cookie, Depends, HTTPException
from apps.api.db import q


def hash_pw(pw: str, salt: bytes | None = None) -> str:
    salt = salt or secrets.token_bytes(16)
    return base64.b64encode(salt).decode() + "$" + base64.b64encode(hashlib.scrypt(pw.encode(), salt=salt, n=2**14, r=8, p=1)).decode()


def check_pw(pw: str, stored: str) -> bool:
    salt = base64.b64decode(stored.split("$")[0])
    return hmac.compare_digest(hash_pw(pw, salt), stored)


def create_user(email: str, pw: str, persona: str, user_id: str | None = None) -> str:
    uid = user_id or secrets.token_hex(6)
    q("INSERT INTO users(id,email,pw_hash,persona,settings) VALUES (:i,:e,:p,:s,:st)", i=uid, e=email.lower(), p=hash_pw(pw), s=persona,
      st=json.dumps({"autonomy": "ask_always", "connects_budget_weekly": 60}))
    return uid


def login(email: str, pw: str) -> str | None:
    u = q("SELECT * FROM users WHERE email=:e", e=email.lower())
    if not u or not check_pw(pw, u[0]["pw_hash"]):
        return None
    tok = secrets.token_urlsafe(32)
    q("INSERT INTO sessions(token,user_id,created) VALUES (:t,:u,:c)", t=tok, u=u[0]["id"], c=time.time())
    return tok


def current_user(session: str | None = Cookie(default=None)) -> dict:
    rows = q("SELECT u.* FROM sessions s JOIN users u ON u.id=s.user_id WHERE s.token=:t", t=session or "")
    if not rows:
        raise HTTPException(401, "not signed in")
    return rows[0]


# --- OAuth token store: Fernet-encrypted at rest, never logged, never returned by the API ---
def _fernet() -> Fernet:
    key = os.environ.get("TOKEN_ENC_KEY")
    if not key:
        raise RuntimeError("TOKEN_ENC_KEY is not set")
    return Fernet(key.encode())


def save_token(user_id: str, provider: str, token: dict):
    enc = _fernet().encrypt(json.dumps(token).encode()).decode()
    q("DELETE FROM accounts WHERE user_id=:u", u=user_id)
    q("INSERT INTO accounts(user_id,provider,token_enc) VALUES (:u,:p,:t)", u=user_id, p=provider, t=enc)


def load_token(user_id: str) -> dict | None:
    r = q("SELECT token_enc FROM accounts WHERE user_id=:u", u=user_id)
    return json.loads(_fernet().decrypt(r[0]["token_enc"].encode())) if r else None


UserDep = Depends(current_user)
