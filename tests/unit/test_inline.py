"""Runs the small assert-based self-checks that live next to the code they check."""
from agent.safety import test_guardrails  # noqa: F401
from data.build_market import test_clean_masks_pii  # noqa: F401
from data.ingest_kaggle import test_ingest  # noqa: F401
from mcp_servers.marketplace.adapters.gigsim import test_outcome_is_deterministic_and_rewards_relevance  # noqa: F401
from worker.main import test_due_respects_live_minimum  # noqa: F401
from mcp_servers.marketplace.adapters.upwork_live import test_live_never_spends_connects, test_expired_token_is_refreshed_and_saved  # noqa: F401
from evals.runners.judge_calibration import test_kappa  # noqa: F401
from evals.runners.ab_experiment import test_perm_test  # noqa: F401


async def test_policy_rule_is_config_only(monkeypatch):
    """A new marketplace rule added to the policy pack takes effect with no code change."""
    import agent.config as c
    from agent.handoffs import ProposalDraft
    from agent.nodes.compliance import compliance
    pol = {**c.policy(), "forbid_patterns": [{"name": "no rate quotes", "regex": r"\$\s?\d+", "action": "remove"}, {"name": "no crypto", "regex": "crypto", "action": "block"}]}
    monkeypatch.setattr("agent.nodes.compliance.policy", lambda: pol)
    r = await compliance({"draft": ProposalDraft(cover_letter="I charge $50 for this React work.")}, {})
    assert "$50" not in r["draft"].cover_letter and "no rate quotes removed" in r["compliance"].violations
    r = await compliance({"draft": ProposalDraft(cover_letter="Happy to take crypto payment.")}, {})
    assert not r["compliance"].allowed
