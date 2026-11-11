"""App tables (SQLAlchemy Core; sqlite locally, Postgres via DATABASE_URL). Every query is tenant-scoped by user_id."""
import os, pathlib
from sqlalchemy import Column, Float, Integer, MetaData, String, Table, Text, create_engine, text

URL = os.getenv("APP_DATABASE_URL") or os.getenv("DATABASE_URL") or "sqlite:///data/processed/app.sqlite"
if URL.startswith("sqlite:///"):
    pathlib.Path(URL.removeprefix("sqlite:///")).parent.mkdir(parents=True, exist_ok=True)
engine = create_engine(URL, future=True, connect_args={"check_same_thread": False} if URL.startswith("sqlite") else {})
md = MetaData()

users = Table("users", md, Column("id", String, primary_key=True), Column("email", String, unique=True), Column("pw_hash", String),
               Column("persona", String), Column("settings", Text, default="{}"))
sessions = Table("sessions", md, Column("token", String, primary_key=True), Column("user_id", String), Column("created", Float))
runs = Table("runs", md, Column("id", String, primary_key=True), Column("user_id", String, index=True), Column("kind", String),  # bid | conversation
              Column("ref", String),  # job id or thread id
              Column("thread_id", String), Column("status", String), Column("trace_id", String), Column("attempts", Integer, default=0),
              Column("created", Float), Column("summary", Text, default="{}"))
events = Table("events", md, Column("run_id", String, index=True), Column("seq", Integer), Column("data", Text))
accounts = Table("accounts", md, Column("user_id", String, primary_key=True), Column("provider", String), Column("token_enc", Text))
md.create_all(engine)


def q(sql: str, **p):
    with engine.begin() as c:
        r = c.execute(text(sql), p)
        return [dict(x._mapping) for x in r] if r.returns_rows else []


def x(sql: str, **p) -> int:
    """Execute a write and return the affected row count (used for compare-and-set transitions)."""
    with engine.begin() as c:
        return c.execute(text(sql), p).rowcount
