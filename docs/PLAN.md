# 2-day plan (due 12 Nov 11:59 PM PKT)
GigSim/personas/policy pack were not provided -> build a small local mock (jobs, clients, replies) + 3 synthetic personas + short policy pack ourselves; say so in DATA_CARD.md.

## Day 1 (core = Parts A, C, B-minimum)
1. Mock marketplace + marketplace_port.py (gigsim adapter only)
2. Portfolio MCP server (3 tools, resources, prompts) + Marketplace MCP (read/write, idempotency, dry_run, bearer, audit)
3. Workspace MCP as local mock
4. Bid graph: Send-parallel analyst/risk/matcher, writer, verifier, critic(<=2), compliance, interrupt(); Postgres checkpointer
5. RAG V0-V3 + V8, verify.py, small dev set, rag_eval.py
## Day 2 (D, E, deliverables)
6. FastAPI + SSE + approve/edit/reject; Next.js: inbox, studio, run viewer, pipeline (others minimal), 5 Playwright tests
7. Worker (arq) scout, docker compose, deploy, reviewer login
8. Evals -> evals/results/*.json; Râ€‹&D report (10pp), README table, 3-min video, write-up
## Cut first if short
Live Upwork OAuth (document as unverified), second 3rd-party server beyond GitHub, V4-V7/V9, X-extension (pick X2), conversation graph UI polish.
## Rule
Every README/report number must come from evals/results/*.json. Do not invent results.
