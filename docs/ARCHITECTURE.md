# ARCHITECTURE

```
browser (React/TS) --REST+SSE--> FastAPI --enqueue--> Redis/arq --> worker --> LangGraph (bid | conversation)
                                    |                                              |  MCP client (per-agent allowlists)
                                    +-- Postgres: users, runs, events, checkpoints, memory    v
                                                                   portfolio MCP | marketplace MCP (GigSim | Upwork live) | workspace MCP
                                                                   (rag: Qdrant + BM25 + reranker)   (audit log, idempotency, rate limit)
```
Graphs are drawn from code: `make graph` writes `docs/images/*.mmd`.

**Bid graph** (`agent/graphs/bid_graph.py`, one thread per job): `scout` -> `Send` to **analyst | risk | matcher** in parallel (reducer `_merge` for parallel writes) -> `decide` (skip/watch/bid from thresholds in config) -> `pricing` -> `writer` -> `verifier` (claim split; unsupported claims removed *before* the critic) -> `critic` (send back to writer at most twice) -> `compliance` (policy pack; can block with a reason) -> `approval` (`interrupt()`) -> `execute` (idempotent). Step and token budgets move a thread to `needs_attention`; failed nodes retry with a `RetryPolicy`; cheap nodes fall back to a second model.

**Conversation graph**: `read` -> `classify` (question / negotiation / interview request / scam signal; scam is flagged, never auto-replied) -> `draft` (slots from the Workspace server) -> `approval` (`interrupt()`) -> `send` (key per client message).

**Three kinds of memory, kept apart**

| | Lives in | Written by |
|---|---|---|
| State (this job right now) | LangGraph state, checkpointed in Postgres | nodes |
| Execution trace (tool, args, result) | `events` table, marketplace audit log, LangSmith | worker / MCP guard |
| Long-term memory | LangGraph store: `(user,'style')`, `(user,'outcome')` | only `agent/memory/promotion_rules.py` (S1: pattern seen in 2 separate edits; O1: 3 outcomes in a category). Raw tool output and draft text are never stored. Users can view and delete items. |

**Why each agent exists:** Scout (cheap, scheduled, dedupes). Job Analyst (structured `JobSpec`, no tools, so injected text cannot reach a tool). Risk Assessor (client history plus a deterministic injection detector OR-ed with the LLM). Fit Matcher (requirement -> evidence; the only source of claims). Pricing (market stats from real contracts data, user floor, Connects). Writer and Critic (strongest model). Compliance Guard (deterministic policy pack, no LLM, so it cannot be talked out of a rule). Client Liaison (reads replies, drafts, offers slots).

**Marketplace port** (`agent/marketplace_port.py`): one interface, two adapters chosen by `MARKETPLACE_ADAPTER`. Switching to live changes the adapter and the OAuth token source; graphs, prompts, tools and UI are untouched.

**Durability:** run row and checkpoint survive restarts. `awaiting_approval -> resuming` is a compare-and-set, so a double click cannot resume twice. Writes carry idempotency keys derived from the thread id, so a crash between the marketplace write and the checkpoint replays to the stored result (`tests/integration/test_durability.py`).
