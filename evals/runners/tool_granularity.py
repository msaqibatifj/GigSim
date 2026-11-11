"""R&D question A: tool granularity. 40 tasks with known correct calls, three tool designs, one model call per task.
  fine   : many fine-grained tools (our tools + near-duplicate splits, terse descriptions)
  coarse : 4 coarse tools taking an `action` + `args`
  best   : our real MCP tool set with rewritten, disambiguating descriptions
Metrics: tool-selection accuracy, argument accuracy (key args equal), prompt tokens per task.
Run: python -m scripts.localenv evals.runners.tool_granularity   -> evals/results/tool_granularity.json"""
import json, pathlib, time
import httpx
from agent.config import model_for, profile
from agent.llm import api_key

ROOT = pathlib.Path(__file__).resolve().parents[2]


def T(name, desc, props=None, req=None):
    return {"type": "function", "function": {"name": name, "description": desc,
            "parameters": {"type": "object", "properties": props or {}, "required": req or []}}}


S, I = {"type": "string"}, {"type": "integer"}
BEST = [
    T("search_jobs", "Find open marketplace jobs matching keywords, optionally in one category (ml_nlp, web, data). Use to discover jobs, not to read one job.", {"query": S, "category": S, "limit": I}),
    T("get_job", "Read ONE job post by its id (title, description, budget).", {"job_id": S}, ["job_id"]),
    T("get_client_history", "A client's track record: total spend, hire rate, payment verification, reviews. Use for client quality or scam checks.", {"client_id": S}, ["client_id"]),
    T("get_connects_balance", "How many Connects (bidding credits) the freelancer has left."),
    T("get_market_stats", "Typical budgets and hourly rates for a category (ml_nlp, web, data). Use for pricing questions.", {"category": S}, ["category"]),
    T("list_threads", "List the ids of the freelancer's client conversations."),
    T("list_messages", "Read the messages in ONE client conversation by thread id.", {"thread_id": S}, ["thread_id"]),
    T("create_proposal_draft", "Save a proposal for a job as a DRAFT (nothing is submitted). Needs job_id, text, idempotency_key.", {"job_id": S, "text": S, "idempotency_key": S}, ["job_id", "text", "idempotency_key"]),
    T("submit_proposal", "Submit an existing proposal draft by draft_id; spends Connects. Only after human approval.", {"draft_id": S, "idempotency_key": S}, ["draft_id", "idempotency_key"]),
    T("send_message", "Send a message in a client thread. Only after human approval.", {"thread_id": S, "text": S, "idempotency_key": S}, ["thread_id", "text", "idempotency_key"]),
    T("search_evidence", "Search the freelancer's OWN portfolio (case studies, past proposals) for proof of one requirement.", {"requirement": S, "k": I}, ["requirement"]),
    T("get_case_study", "Read one portfolio case study in full by id (e.g. c3).", {"id": S}, ["id"]),
    T("list_skills", "The skills the freelancer can truthfully claim."),
    T("free_slots", "Free calendar slots for an interview in the next N days.", {"days": I}),
    T("create_tentative_hold", "Put a tentative interview hold on the calendar at an ISO start time.", {"start": S, "title": S}, ["start", "title"]),
    T("create_email_draft", "Save (not send) an email draft for a thread.", {"to_thread": S, "body": S}, ["to_thread", "body"]),
]
TERSE = {"search_jobs": "Search jobs.", "get_job": "Get job.", "get_client_history": "Client history.", "get_connects_balance": "Connects.",
         "get_market_stats": "Market stats.", "list_threads": "Threads.", "list_messages": "Messages.", "create_proposal_draft": "Create draft.",
         "submit_proposal": "Submit proposal.", "send_message": "Send message.", "search_evidence": "Search evidence.", "get_case_study": "Case study.",
         "list_skills": "Skills.", "free_slots": "Free slots.", "create_tentative_hold": "Create hold.", "create_email_draft": "Email draft."}
FINE = [T(t["function"]["name"], TERSE[t["function"]["name"]], t["function"]["parameters"]["properties"], t["function"]["parameters"]["required"]) for t in BEST] + [
    T("get_job_budget", "Job budget.", {"job_id": S}, ["job_id"]), T("get_job_skills", "Job skills.", {"job_id": S}, ["job_id"]),
    T("get_client_reviews", "Client reviews.", {"client_id": S}, ["client_id"]), T("get_client_spend", "Client spend.", {"client_id": S}, ["client_id"]),
    T("get_hourly_rates", "Hourly rates.", {"category": S}, ["category"]), T("get_last_message", "Last message.", {"thread_id": S}, ["thread_id"]),
    T("search_proposals", "Search proposals.", {"requirement": S}, ["requirement"]), T("update_proposal_draft", "Update draft.", {"draft_id": S, "text": S}, ["draft_id", "text"]),
]
GROUP = {"search_jobs": "marketplace_read", "get_job": "marketplace_read", "get_client_history": "marketplace_read", "get_connects_balance": "marketplace_read",
         "get_market_stats": "marketplace_read", "list_threads": "marketplace_read", "list_messages": "marketplace_read",
         "create_proposal_draft": "marketplace_write", "submit_proposal": "marketplace_write", "send_message": "marketplace_write",
         "search_evidence": "portfolio", "get_case_study": "portfolio", "list_skills": "portfolio",
         "free_slots": "workspace", "create_tentative_hold": "workspace", "create_email_draft": "workspace"}
COARSE = [T(g, f"{g.replace('_', ' ')} operations. action is one of: {', '.join(k for k, v in GROUP.items() if v == g)}; args holds that action's arguments.",
            {"action": S, "args": {"type": "object"}}, ["action"]) for g in dict.fromkeys(GROUP.values())]

# (task, expected tool, key args that must match)
TASKS = [
    ("Find me new RAG chatbot jobs.", "search_jobs", {}), ("Any open React jobs in the web category?", "search_jobs", {"category": "web"}),
    ("Show me data jobs about dashboards.", "search_jobs", {"category": "data"}), ("Look for NLP work posted recently.", "search_jobs", {}),
    ("Open job a07 so I can read it.", "get_job", {"job_id": "a07"}), ("What's the budget on job b03?", "get_job", {"job_id": "b03"}),
    ("Which skills does job s05 need?", "get_job", {"job_id": "s05"}), ("Read the full post for job k1a2b3c4d.", "get_job", {"job_id": "k1a2b3c4d"}),
    ("Is client c_a12 trustworthy?", "get_client_history", {"client_id": "c_a12"}), ("How much has client c_b02 spent before?", "get_client_history", {"client_id": "c_b02"}),
    ("What do other freelancers say about client c_s04?", "get_client_history", {"client_id": "c_s04"}), ("Is client c_a03's payment verified?", "get_client_history", {"client_id": "c_a03"}),
    ("How many Connects do I have left?", "get_connects_balance", {}), ("Can I afford to bid this week? Check my credits.", "get_connects_balance", {}),
    ("What do ML/NLP fixed-price jobs usually pay?", "get_market_stats", {"category": "ml_nlp"}), ("Typical hourly rate for web developers?", "get_market_stats", {"category": "web"}),
    ("Is $800 a normal budget for a data dashboard job?", "get_market_stats", {"category": "data"}), ("Which client conversations do I have?", "list_threads", {}),
    ("Show me my inbox of client chats.", "list_threads", {}), ("What did the client say in thread t1?", "list_messages", {"thread_id": "t1"}),
    ("Read the conversation t-sub-d3.", "list_messages", {"thread_id": "t-sub-d3"}), ("Did the client in thread t2 reply about the start date?", "list_messages", {"thread_id": "t2"}),
    ("Save this text as a draft proposal for job a01: 'I built a hybrid search bot.' Use key k-a01-0001.", "create_proposal_draft", {"job_id": "a01"}),
    ("Draft (don't submit) a proposal to job b04 saying 'Next.js expert here', key k-b04-0001.", "create_proposal_draft", {"job_id": "b04"}),
    ("The user approved draft d7. Submit it with key k-sub-d7-01.", "submit_proposal", {"draft_id": "d7"}), ("Approved: send proposal draft d2 now, key k-sub-d2-01.", "submit_proposal", {"draft_id": "d2"}),
    ("Approved: reply 'Monday works' in thread t1, key k-t1-msg-01.", "send_message", {"thread_id": "t1"}), ("User approved: tell thread t5 'Thanks, rate is $40/h', key k-t5-msg-01.", "send_message", {"thread_id": "t5"}),
    ("Do I have proof of PDF extraction experience?", "search_evidence", {}), ("Find portfolio evidence for Airflow pipelines.", "search_evidence", {}),
    ("Have I done Playwright testing before? Check my work.", "search_evidence", {}), ("Which of my past projects used FastAPI?", "search_evidence", {}),
    ("Open my case study c3.", "get_case_study", {"id": "c3"}), ("Show the full write-up of case study c10.", "get_case_study", {"id": "c10"}),
    ("What skills can I honestly claim?", "list_skills", {}), ("List my skills.", "list_skills", {}),
    ("When am I free for an interview this week?", "free_slots", {}), ("Find interview times in the next 2 days.", "free_slots", {"days": 2}),
    ("Hold 2026-11-14T10:00 on my calendar for the client interview.", "create_tentative_hold", {"start": "2026-11-14T10:00"}),
    ("Write an email draft to thread t3 confirming the call.", "create_email_draft", {"to_thread": "t3"}),
]


def call(model, tools, task):
    body = {"model": model["model"], "temperature": 0, "tool_choice": "required", "tools": tools,
            "messages": [{"role": "system", "content": "You are GigBid's tool router. Call exactly one tool for the user's request."},
                         {"role": "user", "content": task}]}
    if model.get("reasoning_effort"):
        body["reasoning_effort"] = model["reasoning_effort"]
    for i in range(8):
        r = httpx.post("https://api.groq.com/openai/v1/chat/completions", json=body, headers={"Authorization": f"Bearer {api_key('groq')}"}, timeout=60)
        if r.status_code == 429:
            time.sleep(min(float(r.headers.get("retry-after", 2 ** i)), 60)); continue
        if r.status_code >= 400:   # e.g. model produced an invalid tool call: counts as a miss
            return None, {}, 0
        j = r.json()
        tc = (j["choices"][0]["message"].get("tool_calls") or [None])[0]
        if not tc:
            return None, {}, j["usage"]["prompt_tokens"]
        try:
            args = json.loads(tc["function"]["arguments"] or "{}")
        except ValueError:
            args = {}
        return tc["function"]["name"], args, j["usage"]["prompt_tokens"]
    return None, {}, 0


def score(design, name, args, want, want_args):
    if design == "coarse":
        ok = name == GROUP[want] and (args.get("action") == want)
        args = args.get("args") or {}
    else:
        ok = name == want
    arg_ok = ok and all(str(args.get(a, "")).lower().startswith(str(v).lower()) for a, v in want_args.items())
    return ok, arg_ok


def main():
    model = model_for("scout")   # router-class model
    out = {"profile": profile(), "model": model["model"], "n_tasks": len(TASKS), "designs": {}}
    for design, tools in (("fine", FINE), ("coarse", COARSE), ("best", BEST)):
        rows = []
        for task, want, want_args in TASKS:
            name, args, ptok = call(model, tools, task)
            ok, arg_ok = score(design, name, args, want, want_args)
            rows.append({"task": task, "want": want, "got": name, "args": args, "tool_ok": ok, "args_ok": arg_ok, "prompt_tokens": ptok})
        n = len(rows)
        out["designs"][design] = {"n_tools": len(tools), "tool_accuracy": round(sum(r["tool_ok"] for r in rows) / n, 3),
                                  "arg_accuracy": round(sum(r["args_ok"] for r in rows) / n, 3),
                                  "prompt_tokens_per_task": round(sum(r["prompt_tokens"] for r in rows) / n, 1), "rows": rows}
        print(design, {k: v for k, v in out["designs"][design].items() if k != "rows"})
    (ROOT / "evals" / "results" / "tool_granularity.json").write_text(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
