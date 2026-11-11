"""Explicit rules deciding what reaches long-term memory. Nothing else may write to the promoted namespaces.
Rule S1 (style): a pattern seen in >= STYLE_MIN_SUPPORT separate user edits becomes a style rule.
Rule O1 (outcome): a job category with >= OUTCOME_MIN_N outcomes gets promoted stats.
Raw tool output / draft text is never stored, only derived patterns and counters."""
import re

STYLE_MIN_SUPPORT = 2
OUTCOME_MIN_N = 3
GOOD = {"replied", "hired", "won"}

_RULE_TEXT = {"cut_first_sentence": "Never open with a generic first sentence; start with something specific to the job."}


def _sents(t):
    return [s for s in re.split(r"(?<=[.!?])\s+", t.strip()) if s]


def extract_patterns(before: str, after: str) -> list[str]:
    """Derive candidate style patterns from one user edit."""
    b, a, out = _sents(before), _sents(after), []
    if b and b[0] not in a:
        out.append("cut_first_sentence")
    removed = set(re.findall(r"[a-z']+", " ".join(b).lower())) - set(re.findall(r"[a-z']+", " ".join(a).lower()))
    out += [f"avoid:{w}" for w in sorted(removed) if w in {"passionate", "excited", "dear", "guarantee", "eager", "honored"}]
    if len(after.split()) < 0.7 * len(before.split()):
        out.append("shorter")
    return out


def rule_text(pattern: str) -> str:
    if pattern.startswith("avoid:"):
        return f'Never use the word "{pattern[6:]}".'
    return _RULE_TEXT.get(pattern, "Keep proposals noticeably shorter than the first draft.")


def should_promote_style(count: int) -> bool:
    return count >= STYLE_MIN_SUPPORT


def should_promote_outcome(n: int) -> bool:
    return n >= OUTCOME_MIN_N
