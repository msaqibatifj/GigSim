# Submission checklist and demo script (owner: you)

## Before the deadline (12 Nov 2026, 11:59 PM PKT)
- [ ] `gh repo create gigbid --public --source=. --push`, last commit before the deadline
- [ ] Deploy publicly; set `REVIEWER_EMAIL` / `REVIEWER_PASSWORD` in the host env; keep it live until grades
- [ ] Valid LangSmith key in `.env`; then ask Claude to record 4 traces and add 3+ links to README
- [ ] Judge labels: `python -m evals.runners.judge_calibration label`, then score
- [ ] Inspector screenshots in `docs/images/`: `npx @modelcontextprotocol/inspector python -m mcp_servers.<portfolio|marketplace|workspace>.server`; screenshot the tool list and one call per server
- [ ] Fill README TODOs (lines 5-6, 79) and `report.html` TODOs (repo, live URL, section 6), reprint PDF
- [ ] Publish write-up (`docs/WRITEUP.md`) and Portfolio MCP server (README has run commands; add the final repo URL)
- [ ] Classroom: deployed URL, reviewer login (private comment), repo, PDF, video, MCP link, write-up link

## 3-minute demo video (shot list)
1. 0:00 Sign in as the reviewer persona, show the inbox ranked by fit with risk badges (20 s)
2. 0:20 Open a recommended job: JobSpec, requirement-to-evidence matrix, price rationale (30 s)
3. 0:50 Run the agents; show the live run viewer streaming node by node (20 s)
4. 1:10 Proposal studio: hover a claim to show its evidence, read Critic/Compliance comments, edit, check the dry_run cost, approve (40 s)
5. 1:50 A scam job: show it flagged and skipped with the reason (20 s)
6. 2:10 A planted-injection job: show the instruction ignored (20 s)
7. 2:30 Messages: client reply, suggested response and interview slots, approve (20 s)
8. 2:50 Pipeline board updated; close with the README results table (10 s)

## 30 s GIF: steps 2 + 4 only, saved as `docs/images/demo.gif`.
