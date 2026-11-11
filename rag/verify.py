"""Claim verification: label each claim against evidence, drop unsupported ones BEFORE the Critic sees the draft."""
import re
from agent.handoffs import Claim, ProposalDraft
from agent.llm import structured
from pydantic import BaseModel


class Claims(BaseModel):
    claims: list[Claim]


def label(draft: ProposalDraft, evidence: list[dict]) -> list[Claim]:
    return structured("verifier", Claims, {"draft": draft.cover_letter, "draft_obj": draft.model_dump(),
                                          "evidence": [f"{e['id']}: {e['text']}" for e in evidence], "evidence_obj": evidence}).claims


def verify(draft: ProposalDraft, evidence: list[dict]) -> tuple[ProposalDraft, dict]:
    claims = label(draft, evidence)
    bad = {c.text for c in claims if c.label == "unsupported"}
    kept = [s for s in re.split(r"(?<=[.!?])\s+", draft.cover_letter) if s not in bad]
    fixed = draft.model_copy(update={"cover_letter": " ".join(kept), "claims": [c for c in claims if c.label != "unsupported"]})
    # re-verify only a draft we actually changed (optimisation: halves verifier tokens on clean drafts)
    after = sum(c.label == "unsupported" for c in label(fixed, evidence)) if bad else 0
    return fixed, {"unsupported_before": len(bad), "unsupported_after": after, "claims": len(claims), "partial": sum(c.label == "partial" for c in claims)}
