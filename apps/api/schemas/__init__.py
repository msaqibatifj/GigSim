"""Request/response models. The web client's types are generated from these (apps/web/src/lib/api)."""
from typing import Annotated, Any, Literal
from pydantic import BaseModel, Field

EmailStr = Annotated[str, Field(pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$", max_length=200)]


class Persona(BaseModel):
    id: str
    name: str
    title: str
    skills: list[str]
    category: str


class SavedSearch(BaseModel):
    query: str = Field("", max_length=200)
    category: Literal["ml_nlp", "web", "data"] | None = None


class Settings(BaseModel):
    rate: float | None = Field(None, gt=0, le=1000)
    floor: float | None = Field(None, gt=0, le=1000)
    connects_budget_weekly: int = Field(60, ge=0, le=1000)
    autonomy: Literal["ask_always", "auto_skip_low_fit"] = "ask_always"   # never auto-send
    saved_searches: list[SavedSearch] = []
    scout_every_hours: float = Field(4, ge=1, le=168)
    marketplace: Literal["gigsim", "upwork"] | None = None
    onboarded: bool = False


class Me(BaseModel):
    id: str
    email: str
    persona: str
    settings: Settings
    upwork_connected: bool = False


class SignupIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=200)
    persona: str = Field(pattern=r"^[a-z_]+$")


class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=200)


class Job(BaseModel):
    id: str
    title: str
    description: str
    budget_usd: float | None = None
    client_id: str
    posted_at: str
    category: str | None = None
    connects_cost: int | None = None
    source: str = "synthetic"


class InboxItem(BaseModel):
    job: Job
    run_id: str | None = None
    status: str = "new"
    action: str | None = None           # bid | watch | skip
    fit: float | None = None
    risk_flags: list[str] = []
    client_score: float | None = None
    price_usd: float | None = None
    connects: int | None = None
    reasons: list[str] = []


class RunOut(BaseModel):
    id: str
    kind: str
    ref: str
    status: str
    trace_id: str
    created: float
    summary: dict[str, Any]


class Event(BaseModel):
    seq: int
    data: dict[str, Any]


class JobDetail(BaseModel):
    job: Job
    client: dict[str, Any] | None = None
    run: RunOut | None = None
    state: dict[str, Any] = {}          # spec, risk, fit, evidence, decision, price, draft, critiques, compliance


class ApprovalIn(BaseModel):
    action: Literal["approve", "edit", "reject"]
    text: str | None = Field(None, max_length=5000)
    reason: str | None = Field(None, max_length=500)


class Pending(BaseModel):
    run: RunOut
    payload: dict[str, Any]


class RegenerateIn(BaseModel):
    text: str = Field(min_length=1, max_length=5000)
    paragraph: int = Field(ge=0, le=20)


class RegenerateOut(BaseModel):
    text: str


class PipelineCard(BaseModel):
    run_id: str
    job_id: str
    title: str
    stage: Literal["drafted", "submitted", "viewed", "replied", "interview", "hired", "lost"]
    price_usd: float | None = None
    thread_id: str | None = None


class Message(BaseModel):
    id: str
    thread_id: str
    sender: str
    text: str


class Thread(BaseModel):
    thread_id: str
    last: Message | None = None
    run: RunOut | None = None


class ThreadDetail(BaseModel):
    thread_id: str
    messages: list[Message]
    run: RunOut | None = None


class MemoryItem(BaseModel):
    kind: Literal["style", "outcome"]
    key: str
    value: dict[str, Any]


class Health(BaseModel):
    api: str = "ok"
    marketplace: Literal["up", "down"]
    marketplace_adapter: str
    model_profile: str
    detail: str | None = None


class Analytics(BaseModel):
    by_category: dict[str, dict[str, float]]
    connects_spent: int
    outcomes: dict[str, int]
    per_proposal: dict[str, float]      # mean / p95 latency_s, mean usd, tokens
    per_job: dict[str, float]
    rejection_reasons: list[tuple[str, int]]
    skip_reasons: list[tuple[str, int]]
    runs_by_status: dict[str, int]
