from langgraph.store.memory import InMemoryStore
from agent.memory import store as M

def test_style_promotes_only_after_two_edits_and_can_be_deleted():
    s = InMemoryStore()
    before = "I am passionate about AI. I built a RAG system. Happy to help."
    after = "I built a RAG system. Happy to help."
    assert M.record_edit(s, "u", before, after) == []            # one edit: candidate only
    assert M.style_rules(s, "u") == []
    assert "cut_first_sentence" in M.record_edit(s, "u", before, after)
    assert any("passionate" in r for r in M.style_rules(s, "u"))
    M.delete_item(s, "u", "style", "avoid:passionate")
    assert not any("passionate" in r for r in M.style_rules(s, "u"))

def test_outcome_needs_three_observations_and_stores_no_raw_text():
    s = InMemoryStore()
    assert not M.record_outcome(s, "u", "rag", "replied") and not M.record_outcome(s, "u", "rag", "no_reply")
    assert M.record_outcome(s, "u", "rag", "hired")
    assert M.outcome_stats(s, "u")["rag"]["rate"] == 0.67
