"""The single marketplace interface. Graph code imports only this; adapters are chosen by config."""
import os
from typing import Protocol
from pydantic import BaseModel, Field

class Job(BaseModel):
    id: str
    title: str
    description: str
    budget_usd: float | None = None
    client_id: str
    posted_at: str
    category: str | None = None          # ml_nlp | web | data (market-stats key)
    connects_cost: int | None = None     # per-job cost when the marketplace states one
    source: str = "synthetic"            # "kaggle:<owner/slug>" for real postings

class ClientHistory(BaseModel):
    client_id: str
    total_spent_usd: float
    hire_rate: float = Field(ge=0, le=1)
    payment_verified: bool
    reviews: list[str] = []
    source: str = "synthetic"

class MarketStats(BaseModel):
    category: str
    fixed_budget_usd: dict[str, float]
    hourly_rate_usd: dict[str, float]
    sources: list[str] = []

class Message(BaseModel):
    id: str
    thread_id: str
    sender: str  # "client" | "freelancer"
    text: str

class WriteResult(BaseModel):
    ok: bool
    dry_run: bool
    would_send: dict
    connects_cost: int
    id: str | None = None
    replayed: bool = False  # True when an idempotency key was seen before

class Marketplace(Protocol):
    def search_jobs(self, query: str = "", limit: int = 20, category: str | None = None) -> list[Job]: ...
    def get_job(self, job_id: str) -> Job: ...
    def get_client_history(self, client_id: str) -> ClientHistory: ...
    def get_connects_balance(self) -> int: ...
    def get_market_stats(self, category: str) -> MarketStats: ...
    def list_messages(self, thread_id: str) -> list[Message]: ...
    def list_threads(self) -> list[str]: ...
    def proposal_events(self) -> list[dict]: ...
    def create_proposal_draft(self, job_id: str, text: str, *, idem_key: str, dry_run: bool = False) -> WriteResult: ...
    def submit_proposal(self, draft_id: str, *, idem_key: str, dry_run: bool = False) -> WriteResult: ...
    def send_message(self, thread_id: str, text: str, *, idem_key: str, dry_run: bool = False) -> WriteResult: ...

def get_marketplace() -> Marketplace:
    name = os.getenv("MARKETPLACE_ADAPTER", "gigsim")
    if name == "gigsim":
        from mcp_servers.marketplace.adapters.gigsim import MockGigSim
        return MockGigSim()
    if name == "upwork":
        from mcp_servers.marketplace.adapters.upwork_live import UpworkLive
        return UpworkLive()
    raise ValueError(f"unknown MARKETPLACE_ADAPTER {name!r}")
