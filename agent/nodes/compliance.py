"""Compliance Guard: deterministic policy-pack enforcement (rules live in data/policy_pack/policy.yaml)."""
import re
from agent.config import policy
from agent.handoffs import ComplianceVerdict

CONTACT = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+|\+?\d[\d\s().-]{7,}\d|\b(whatsapp|telegram|skype)\b", re.I)
GUARANTEE = re.compile(r"[^.!?]*\b(guarantee[sd]?|100%)[^.!?]*[.!?]?", re.I)


async def compliance(state, config):
    p, d = policy(), state["draft"]
    text, violations = d.cover_letter, []
    if p["forbid"]["contact_details"] and CONTACT.search(text):
        text, violations = CONTACT.sub("", text), violations + ["contact details removed"]
    if p["forbid"]["guarantees"] and GUARANTEE.search(text):
        text, violations = GUARANTEE.sub("", text), violations + ["guarantee removed"]
    for rule in p.get("forbid_patterns", []):   # new marketplace rules are config: name, regex, action (remove | block)
        rx = re.compile(rule["regex"], re.I)
        if rx.search(text):
            if rule.get("action", "remove") == "block":
                violations.append(f"blocked: {rule['name']}")
                return {"compliance": ComplianceVerdict(allowed=False, violations=violations), "draft": d.model_copy(update={"cover_letter": text}), "steps": 1}
            text, violations = rx.sub("", text), violations + [f"{rule['name']} removed"]
    text = re.sub(r"\s+", " ", text).strip()
    over = len(text.split()) > p["limits"]["cover_letter_max_words"]
    if over:
        violations.append("over word limit")   # cannot be fixed by deletion alone -> block
    v = ComplianceVerdict(allowed=not over, violations=violations)
    return {"compliance": v, "draft": d.model_copy(update={"cover_letter": text}), "steps": 1}
