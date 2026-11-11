# ADR 1: One marketplace port, two adapters
Agents depend on `agent/marketplace_port.py` only. GigSim and live Upwork are adapters behind the Marketplace MCP server, chosen by `MARKETPLACE_ADAPTER`. Cost: the port is the lowest common denominator (live mode cannot submit, so `submit_proposal` returns "confirm on Upwork"). Benefit: switching modes is a config change.

# ADR 2: Human approval with interrupt() and idempotent writes
Approval is a LangGraph `interrupt()` persisted in the checkpoint, not a prompt instruction. The node before it re-runs on resume, so it only does a dry run. All writes carry keys derived from the thread id, and the API moves `awaiting_approval -> resuming` with a compare-and-set. A crash, restart or double click cannot double-submit.

# ADR 3: The RAG variant is a config value chosen by evaluation
`agent/config.yaml rag.variant` selects `rag/variants/vN_*.py`. The shipped variant is the one in `evals/results/rag_eval_*.json` with the best Recall@5 and nDCG at acceptable latency, not the most elaborate one. The decision paragraph is in the report, section 4.

# ADR 4: Deterministic guards next to LLM checks
Compliance Guard and the injection detector are regex and policy code that runs regardless of model output. A model told by a job post to "ignore your rules" can also be told to approve itself. Known limit: regexes miss paraphrased or non-English injections; prompt-level delimiting and the human approval gate are the second and third layers.
