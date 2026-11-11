"""Long-term memory over a LangGraph store. Namespaces: (user,'style_candidates'), (user,'style'), (user,'outcome_candidates'), (user,'outcome').
Only this module writes them, and only via the promotion rules."""
import os, pathlib
from agent.memory import promotion_rules as R


def get_store():
    """Postgres when DATABASE_URL is set (docker/prod), else a local sqlite file (dev)."""
    if os.getenv("DATABASE_URL"):
        from langgraph.store.postgres import PostgresStore
        s = PostgresStore.from_conn_string(os.environ["DATABASE_URL"]).__enter__(); s.setup(); return s
    from langgraph.store.sqlite import SqliteStore
    path = pathlib.Path(os.getenv("MEMORY_DB", "data/processed/memory.sqlite")); path.parent.mkdir(parents=True, exist_ok=True)
    import sqlite3
    s = SqliteStore(sqlite3.connect(path, check_same_thread=False, isolation_level=None)); s.setup(); return s


def record_edit(store, user: str, before: str, after: str) -> list[str]:
    """Rule S1. Returns patterns newly promoted by this edit."""
    promoted = []
    for pat in R.extract_patterns(before, after):
        cur = store.get((user, "style_candidates"), pat)
        n = (cur.value["count"] if cur else 0) + 1
        store.put((user, "style_candidates"), pat, {"count": n})
        if R.should_promote_style(n) and not store.get((user, "style"), pat):
            store.put((user, "style"), pat, {"rule": R.rule_text(pat), "support": n})
            promoted.append(pat)
    return promoted


def style_rules(store, user: str) -> list[str]:
    return [i.value["rule"] for i in store.search((user, "style"))]


def record_outcome(store, user: str, category: str, outcome: str) -> bool:
    """Rule O1. Counters only; promoted when the category has enough observations."""
    cur = store.get((user, "outcome_candidates"), category)
    v = cur.value if cur else {"n": 0, "good": 0}
    v = {"n": v["n"] + 1, "good": v["good"] + (outcome in R.GOOD)}
    store.put((user, "outcome_candidates"), category, v)
    if R.should_promote_outcome(v["n"]):
        store.put((user, "outcome"), category, {**v, "rate": round(v["good"] / v["n"], 2)})
        return True
    return False


def outcome_stats(store, user: str) -> dict:
    return {i.key: i.value for i in store.search((user, "outcome"))}


def list_memory(store, user: str) -> list[dict]:
    """For the Settings > memory viewer."""
    return [{"kind": k, "key": i.key, **i.value} for k in ("style", "outcome") for i in store.search((user, k))]


def delete_item(store, user: str, kind: str, key: str):
    store.delete((user, kind), key)
    store.delete((user, kind + "_candidates"), key)  # otherwise it would re-promote on the next edit
