.PHONY: dev test eval smoke-eval seed demo lint data graph web
PY ?= python
dev:        ; docker compose -f infra/docker-compose.yml --env-file .env up --build
test:       ; $(PY) -m pytest -q
lint:       ; $(PY) -m ruff check .
data:       ; $(PY) -m data.build_market
seed:       ; $(PY) -m rag.ingest
graph:      ; $(PY) -m agent.graphs.bid_graph > docs/images/bid_graph.mmd && $(PY) -m agent.graphs.conversation_graph > docs/images/conversation_graph.mmd
demo:       ; $(PY) -m scripts.localenv evals.runners.decision_eval --jobs a01,a12,b13 --tag demo
web:        ; cd apps/web && npm ci && npm run gen:api && npm run build
# full evaluation: retrieval + decisions/proposals/GigSim outcomes + injection + tool granularity (needs GROQ_API_KEY)
eval:
	$(PY) -m scripts.localenv evals.runners.rag_eval --pool all
	$(PY) -m scripts.localenv evals.runners.decision_eval
	$(PY) -m scripts.localenv evals.runners.injection_eval
	$(PY) -m scripts.localenv evals.runners.tool_granularity
	$(PY) -m evals.runners.check_thresholds evals/results/decision_eval_open.json
# CI: 30-job smoke eval with failure thresholds
smoke-eval:
	$(PY) -m scripts.localenv evals.runners.decision_eval --tag smoke
	$(PY) -m evals.runners.check_thresholds evals/results/decision_eval_$${MODEL_PROFILE:-open}_smoke.json
