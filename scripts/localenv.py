"""Local runs outside docker: take API keys from .env but keep local stores (no docker hostnames).
Usage: python -m scripts.localenv <module> [args]  e.g.  python -m scripts.localenv evals.runners.decision_eval"""
import os, runpy, sys
import dotenv

KEYS = ("GROQ_API_KEY", "GROQ_API_KEYS", "OPENROUTER_API_KEY", "LANGSMITH_API_KEY", "LANGSMITH_TRACING", "LANGSMITH_PROJECT", "LANGSMITH_ENDPOINT", "LANGSMITH_WORKSPACE_ID",
        "MODEL_PROFILE", "GITHUB_TOKEN", "TOKEN_ENC_KEY", "ANTHROPIC_API_KEY")
for k, v in dotenv.dotenv_values(".env").items():
    if k in KEYS and v and k not in os.environ:
        os.environ[k] = v
os.environ.pop("DATABASE_URL", None); os.environ.pop("REDIS_URL", None)
if __name__ == "__main__":
    mod = sys.argv[1]
    sys.argv = sys.argv[1:]
    runpy.run_module(mod, run_name="__main__")
