"""Shared helpers for nodes."""
from agent.config import cfg, policy
from agent.safety import scrub


def tools(config):
    return config["configurable"]["tools"]  # agent.mcp_client.Tools; not checkpointed


def job_text(job: dict, raw: bool = False) -> str:
    """Prompt text for a job. Drafting nodes get the scrubbed text; only the Risk node passes raw=True."""
    desc = job["description"] if raw else scrub(job["description"])
    return f"Title: {job['title']}\n{desc}\nBudget: {job.get('budget_usd')}"


def max_words() -> int:
    return policy()["limits"]["cover_letter_max_words"]


def thresholds() -> dict:
    return cfg()["thresholds"]
