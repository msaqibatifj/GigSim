from agent.config import policy
from agent.handoffs import PriceQuote
from agent.nodes.common import thresholds, tools


async def pricing(state, config):
    """Bid from the job budget, market stats (real Upwork data), the user's floor and the Connects cost.
    Rules come from config/policy, not code."""
    user, job, th, t = state["user"], state["job"], thresholds(), tools(config)
    connects = job.get("connects_cost") or policy()["limits"]["connects_per_bid"]
    balance = await t.call("pricing", "get_connects_balance")
    m = await t.call("pricing", "get_market_stats", {"category": job.get("category") or user.get("category", "web")})
    hours = th.get("assumed_hours", 10)
    floor_total = user["floor"] * hours
    budget = job.get("budget_usd") or m["fixed_budget_usd"]["50"]
    amount = max(round(budget * th["price_floor_margin"]), floor_total)
    worth = budget >= floor_total and balance >= connects
    fee = policy().get("fees", {}).get("platform_fee_pct", 0)
    why = (f"budget ${budget:g} x {th['price_floor_margin']} vs your floor ${floor_total:g} ({hours}h x ${user['floor']}); "
           f"market for {m['category']}: fixed p25/p50/p75 ${m['fixed_budget_usd']['25']:g}/${m['fixed_budget_usd']['50']:g}/${m['fixed_budget_usd']['75']:g}, "
           f"hourly p50 ${m['hourly_rate_usd']['50']:g}; you keep ${amount * (1 - fee / 100):.0f} after the {fee:g}% platform fee; {connects} Connects of {balance} left"
           + ("" if worth else "; not worth the Connects (budget below your floor or not enough Connects)"))
    return {"price": PriceQuote(amount_usd=amount, connects=connects, rationale=why, worth_connects=worth), "steps": 1}
