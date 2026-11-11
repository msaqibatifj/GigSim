import operator
from typing import Annotated, TypedDict
from agent.handoffs import (BidDecision, ComplianceVerdict, Critique, FitReport, JobSpec, PriceQuote, ProposalDraft, RiskReport)


def _merge(a: dict, b: dict) -> dict:  # reducer for parallel branches
    return {**(a or {}), **(b or {})}


class BidState(TypedDict, total=False):
    # input
    job_id: str
    user: dict              # persona profile: name, floor, rate, skills
    # state: what this job needs right now (execution trace and long-term memory live elsewhere)
    job: dict
    spec: JobSpec
    risk: RiskReport
    fit: FitReport
    evidence: list[dict]
    analyses: Annotated[dict, _merge]
    decision: BidDecision
    price: PriceQuote
    draft: ProposalDraft
    verification: dict      # unsupported-claim counts before/after verification
    critiques: Annotated[list[Critique], operator.add]
    compliance: ComplianceVerdict
    approval: dict          # set from interrupt() resume: {action: approve|edit|reject, ...}
    result: dict            # marketplace write results
    steps: Annotated[int, operator.add]
    status: str             # running | skipped | watching | rejected | needs_attention | submitted
