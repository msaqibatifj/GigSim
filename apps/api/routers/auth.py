"""Sign-in and onboarding: users, sessions, persona, settings, marketplace connection, portfolio upload."""
import json, os, re, shutil
from fastapi import APIRouter, HTTPException, Response, UploadFile
from fastapi.responses import RedirectResponse
from apps.api.auth import oauth
from apps.api.auth.users import UserDep, create_user, login, load_token
from apps.api.db import q
from apps.api.deps import settings_of
from apps.api.schemas import LoginIn, Me, Persona, Settings, SignupIn
from data import personas_util
from rag.ingest.loaders import PERSONAS

r = APIRouter(prefix="/api/auth", tags=["auth"])
BASE_PERSONAS = ("ayesha_ml", "bilal_web", "sara_data")
SECURE = os.getenv("COOKIE_SECURE", "false").lower() == "true"


def _me(u: dict) -> Me:
    try:
        up = bool(load_token(u["id"]))
    except RuntimeError:   # TOKEN_ENC_KEY unset: no live accounts possible
        up = False
    return Me(id=u["id"], email=u["email"], persona=u["persona"], settings=settings_of(u), upwork_connected=up)


def _cookie(resp: Response, tok: str):
    resp.set_cookie("session", tok, httponly=True, samesite="lax", secure=SECURE, max_age=14 * 86400)


@r.get("/personas", response_model=list[Persona])
def personas():
    out = []
    for p in BASE_PERSONAS:
        d = personas_util.profile(p)
        out.append(Persona(id=p, name=d["name"], title=d["title"], skills=d["skills"], category=d["category"]))
    return out


@r.post("/signup", response_model=Me)
def signup(body: SignupIn, resp: Response):
    if body.persona not in BASE_PERSONAS:
        raise HTTPException(422, "unknown persona")
    if q("SELECT 1 FROM users WHERE email=:e", e=body.email.lower()):
        raise HTTPException(409, "email already registered")
    create_user(body.email, body.password, body.persona)
    _cookie(resp, login(body.email, body.password))
    return _me(q("SELECT * FROM users WHERE email=:e", e=body.email.lower())[0])


@r.post("/login", response_model=Me)
def do_login(body: LoginIn, resp: Response):
    tok = login(body.email, body.password)
    if not tok:
        raise HTTPException(401, "wrong email or password")
    _cookie(resp, tok)
    return _me(q("SELECT * FROM users WHERE email=:e", e=body.email.lower())[0])


@r.post("/logout")
def logout(resp: Response, user: dict = UserDep):
    q("DELETE FROM sessions WHERE user_id=:u", u=user["id"])
    resp.delete_cookie("session")
    return {"ok": True}


@r.get("/me", response_model=Me)
def me(user: dict = UserDep):
    return _me(user)


@r.put("/settings", response_model=Me)
def put_settings(body: Settings, user: dict = UserDep):
    cur = json.loads(user["settings"] or "{}")
    q("UPDATE users SET settings=:s WHERE id=:i", s=json.dumps({**cur, **body.model_dump()}), i=user["id"])
    return _me(q("SELECT * FROM users WHERE id=:i", i=user["id"])[0])


@r.put("/persona/{persona}", response_model=Me)
def set_persona(persona: str, user: dict = UserDep):
    if persona not in BASE_PERSONAS:
        raise HTTPException(422, "unknown persona")
    q("UPDATE users SET persona=:p WHERE id=:i", p=persona, i=user["id"])
    return _me(q("SELECT * FROM users WHERE id=:i", i=user["id"])[0])


@r.post("/connect/gigsim", response_model=Me)
def connect_gigsim(user: dict = UserDep):
    s = settings_of(user).model_copy(update={"marketplace": "gigsim"})
    return put_settings(s, user)


@r.get("/upwork/start")
async def upwork_start(user: dict = UserDep):
    try:
        return {"url": await oauth.start(user["id"])}
    except Exception as e:
        raise HTTPException(503, f"Upwork OAuth unavailable: {e}")


@r.get("/upwork/callback")
async def upwork_callback(state: str, code: str):
    try:
        await oauth.finish(state, code)
    except Exception:
        raise HTTPException(400, "Upwork sign-in failed; try connecting again")
    return RedirectResponse("/settings?connected=upwork")


@r.post("/portfolio", response_model=Me)
async def upload_portfolio(file: UploadFile, user: dict = UserDep):
    """Add a case study (.md with front matter, or plain .md/.txt) or a PDF CV. The Portfolio index embeds it on next search."""
    name = re.sub(r"[^\w.-]", "_", file.filename or "upload")
    data = await file.read()
    if len(data) > 5_000_000 or not name.lower().endswith((".md", ".txt", ".pdf")):
        raise HTTPException(422, "upload a .md, .txt or .pdf under 5 MB")
    persona = user["persona"]
    if not persona.startswith("u_"):   # copy-on-write: personas are shared, a user's own portfolio is private
        persona = f"u_{user['id']}"
        if not (PERSONAS / persona).exists():
            shutil.copytree(PERSONAS / user["persona"], PERSONAS / persona)
        q("UPDATE users SET persona=:p WHERE id=:i", p=persona, i=user["id"])
    folder = PERSONAS / persona / "case_studies"
    if name.lower().endswith(".pdf"):
        (PERSONAS / persona / name).write_bytes(data)
    else:
        text = data.decode("utf-8", errors="replace")
        if not text.startswith("---\n"):
            n = len(list(folder.glob("*.md"))) + 1
            text = f"---\nid: u{n}\ntype: case_study\nskills: []\n---\n" + (text if text.lstrip().startswith("#") else f"# {name}\n\n{text}")
        (folder / (name if name.endswith(".md") else name + ".md")).write_text(text, encoding="utf-8")
    return _me(q("SELECT * FROM users WHERE id=:i", i=user["id"])[0])
