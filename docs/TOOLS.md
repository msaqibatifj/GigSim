# TOOLS

Agents never touch GigSim, Upwork, a database or a file directly; every capability is an MCP tool. Per-agent allowlists live in `agent/mcp_client.py` (`ALLOW`). Schemas and annotations are snapshot-tested (`tests/contract`), so any signature change fails CI until the snapshot is deliberately updated.

| Tool | Server | R/W | Annotations (readOnly / destructive / idempotent) | Auth | Used by |
|---|---|---|---|---|---|
| `search_evidence(requirement, k, type, outcome)` | portfolio | R | T / F / T | none (local stdio) or bearer on HTTP | matcher, writer, critic |
| `get_case_study(id)` | portfolio | R | T / F / T | same | writer, critic |
| `list_skills()` | portfolio | R | T / F / T | same | matcher |
| resources `portfolio://case/{id}`, `portfolio://proposal/{id}`; prompts `answer_screening_question`, `write_cover_letter` | portfolio | R | | | Claude Desktop / Cursor |
| `search_jobs(query, limit, category)` | marketplace | R | T / F / T | bearer | scout, ui |
| `get_job(job_id)` | marketplace | R | T / F / T | bearer | scout, risk, ui |
| `get_client_history(client_id)` | marketplace | R | T / F / T | bearer | risk, ui |
| `get_connects_balance()` | marketplace | R | T / F / T | bearer | pricing, ui |
| `get_market_stats(category)` | marketplace | R | T / F / T | bearer | pricing |
| `list_threads()`, `list_messages(thread_id)` | marketplace | R | T / F / T | bearer | liaison, ui |
| `get_proposal_events()` | marketplace | R | T / F / T | bearer | ui (pipeline board) |
| `create_proposal_draft(job_id, text, idempotency_key, dry_run, bid_usd)` | marketplace | W | F / F / T | bearer | executor (after approval) |
| `submit_proposal(draft_id, idempotency_key, dry_run)` | marketplace | W | F / **T** / T | bearer | executor (after approval) |
| `send_message(thread_id, text, idempotency_key, dry_run)` | marketplace | W | F / F / T | bearer | executor, liaison (after approval) |
| `free_slots(days, minutes)` | workspace | R | T / F / T | none (local mock) | liaison |
| `create_tentative_hold(start, title)` | workspace | W | F / F / T | none | liaison |
| `create_email_draft(to_thread, body)` | workspace | W | F / F / T | none | liaison (draft only, never sends) |

**Marketplace guarantees** (`mcp_servers/marketplace/guard.py`): Pydantic input constraints (id patterns, text length, `limit` 1-100), declared output schemas, idempotency key on every write (same key returns the stored result with `replayed=true`, no second Connects charge), `dry_run` returns exactly what would be sent plus the Connects cost and has no side effect, bearer-token auth on the HTTP endpoint (`MARKETPLACE_TOKENS`; a `*` token is the GigBid service token acting for the user in `X-GigBid-User`), a per-user token-bucket rate limiter, and an append-only JSONL audit log (user, tool, arguments, result, trace id).

**Client discipline** (`agent/mcp_client.py`): per-agent name allowlist, 20 s timeout per call, 4 attempts with exponential backoff on rate limits and transport errors, `MarketplaceDown` when the server is unreachable (run goes to `queued_degraded`, the UI banner appears via `/api/health`, the worker retries every 30 s and continues from the checkpoint).

**Live mode** (`adapters/upwork_live.py`): same port, Upwork's tools mapped in `agent/config.yaml` under `upwork.tools`. `submit_proposal` never spends Connects from GigBid; the user confirms the draft on Upwork. Not exercised against a live account (none available).

## Third-party servers (A5) and why we trust them

| Server | Why |
|---|---|
| Official Upwork MCP `https://mcp.upwork.com/mcp` | First-party server from the marketplace itself; per-user OAuth 2.1 (PKCE), tokens encrypted at rest, draft-only writes. |
| GitHub MCP `@modelcontextprotocol/server-github` (pinned `2025.4.8`) | Maintained in the official `modelcontextprotocol/servers` repo; used read-only with a fine-grained token limited to public-repo read to ingest READMEs for the portfolio. Configured in `agent/config.yaml` (`third_party_mcp`); not run in CI (needs a token). |

## MCP Inspector evidence (A7)

Each server connected over stdio in MCP Inspector v2.13.0, tool list shown and one call made.

| Server | Call | Screenshot |
|---|---|---|
| Portfolio (3 tools) | `search_evidence` | [inspector_portfolio_search_evidence.png](images/inspector_portfolio_search_evidence.png) |
| Marketplace (11 tools) | `search_jobs` | [inspector_marketplace_search_jobs.png](images/inspector_marketplace_search_jobs.png) |
| Workspace (3 tools) | `free_slots` | [inspector_workspace_free_slots.png](images/inspector_workspace_free_slots.png) |
