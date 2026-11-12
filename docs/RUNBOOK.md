# RUNBOOK

**Run with Docker:** `cp .env.example .env` and fill `GROQ_API_KEY`, `TOKEN_ENC_KEY` (`python -c "from cryptography.fernet import Fernet;print(Fernet.generate_key().decode())"`), `REVIEWER_EMAIL`, `REVIEWER_PASSWORD`; then `make dev` (web+API, worker, three MCP servers, Postgres, Redis, Qdrant; add `--profile local-llm` for Ollama).
**Without Docker:** `python -m scripts.localenv uvicorn apps.api.main:app` (sqlite, in-process worker) and `cd apps/web && npm run dev`.

**Scheduling:** the worker cron ticks every 15 min; a user's saved searches run when their `scout_every_hours` (default 4, minimum 1) has elapsed. **Live Upwork mode never scouts more often than 6 h** (`worker/main.py LIVE_MIN_HOURS`, `agent/config.yaml upwork.min_scout_hours`): Upwork's automation rules forbid scraping-like polling, so reads are few, official-API only, and drafts are created only after approval. Job ids make enqueues idempotent (`scout:<user>:<15-min bucket>`, `start:<run>`), so a worker restart never double-analyses.

**Degraded mode (marketplace down):** `/api/health` reports `marketplace: down`, the UI shows a banner. Runs hit `MarketplaceDown`, go to `queued_degraded`, the worker retries every 30 s and continues from the checkpoint. An approved send that cannot reach the marketplace stays `resuming` with the approval stored. Code: `agent/mcp_client.py` (detect), `worker/tasks.py` (state), `worker/main.py` (retry).

**Crash during approval:** kill the API or worker, restart, the pending approval is still there; approve; the proposal is submitted once (idempotency key `<thread>:submit`).

**Budgets** (`agent/config.yaml budgets`): p95 latency per job 60 s, USD per job 0.02, per proposal 0.10. Measured values: `evals/results/decision_eval_*.json`.

**Change request (policy update):** edit `data/policy_pack/policy.yaml` (limits, fees, forbidden content, `connects_per_bid`). No code change: Compliance, Pricing and GigSim read the file at call time.

**Secrets:** environment only; `.env` is git-ignored; OAuth tokens are Fernet-encrypted, never returned by the API or logged; logs and traces mask emails, phones and card/IBAN numbers.

## Going live on Upwork (checklist, not yet run against a real account)
1. Get API/MCP access at upwork.com/ai/mcp; register the redirect URI `<PUBLIC_URL>/api/auth/upwork/callback`.
2. Set `UPWORK_CLIENT_ID`, `UPWORK_CLIENT_SECRET`, `PUBLIC_URL` in the environment (never in the repo).
3. Sign in, Settings > Connect Upwork (OAuth 2.1 + PKCE; the token is stored encrypted; expired tokens refresh silently).
4. `python -m scripts.localenv scripts.upwork_probe --user <your user id>` lists the real tool names and prints which entries of `agent/config.yaml` `upwork.tools` to fix.
5. Locally first: `MARKETPLACE_ADAPTER=upwork`, run one read-only search, then one proposal draft with `dry_run`. Only then switch the deployment.
6. Guarantees that do not change: drafts only, GigBid never spends Connects, reads at most every 6 h.
