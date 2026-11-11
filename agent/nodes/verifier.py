import asyncio
from rag.verify import verify


async def verifier(state, config):
    """Claim verification (B3): label every claim, drop unsupported ones before the Critic sees the draft."""
    draft, stats = await asyncio.to_thread(verify, state["draft"], state.get("evidence", []))
    return {"draft": draft, "verification": stats, "steps": 1}
