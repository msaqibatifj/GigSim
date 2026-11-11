from typing import Literal
from pydantic import BaseModel, Field

class JobSpec(BaseModel):
    job_id: str | None = None   # filled by the analyst node from the job itself; models often omit or null it
    deliverables: list[str]
    skills: list[str]
    budget_usd: float | None = None
    timeline_days: int | None = None
    screening_questions: list[str] = []
    hidden_needs: list[str] = []

class RiskReport(BaseModel):
    client_score: float = Field(ge=0, le=1)
    flags: list[Literal["scam", "free_work", "off_platform", "injection"]] = []
    reasons: list[str] = []

class Evidence(BaseModel):
    requirement: str
    item_id: str | None = None   # None = no support found
    source: str | None = None

class FitReport(BaseModel):
    score: float = Field(ge=0, le=1)
    evidence: list[Evidence]
    reasons: list[str] = []

class BidDecision(BaseModel):
    action: Literal["skip", "watch", "bid"]
    reasons: list[str]

class PriceQuote(BaseModel):
    amount_usd: float = Field(gt=0)
    connects: int = Field(ge=0)
    rationale: str
    worth_connects: bool = True

class Claim(BaseModel):
    text: str
    label: Literal["supported", "partial", "unsupported"]
    evidence_ids: list[str] = []

class ProposalDraft(BaseModel):
    cover_letter: str
    screening_answers: dict[str, str] = {}
    claims: list[Claim] = []

class Critique(BaseModel):
    ok: bool
    issues: list[str] = []

class ComplianceVerdict(BaseModel):
    allowed: bool
    violations: list[str] = []


class ClientIntent(BaseModel):
    intent: Literal["question", "negotiation", "interview_request", "scam_signal"]
    reasons: list[str] = []


class ReplyDraft(BaseModel):
    text: str
    slots: list[str] = []   # proposed interview slots (ISO start times), only for interview requests
