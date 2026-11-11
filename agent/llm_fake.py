"""Deterministic rule-based stand-in for LLM nodes (MODEL_PROFILE=offline). For plumbing/tests only:
any number produced with it must not be reported as model quality."""
import re

VOCAB = ["python", "langchain", "rag", "pytorch", "fastapi", "postgres", "nlp", "typescript", "react", "nextjs", "node",
         "tailwind", "playwright", "sql", "airflow", "dbt", "bigquery", "tableau", "pandas", "classifier", "dashboard", "vector"]
CLICHE = re.compile(r"passionate|dear sir|hope this finds you", re.I)
BAIT = {"free_work": r"free sample|samples? free|for free|free test|do \d+ .*free", "off_platform": r"whatsapp|telegram|skype|gmail|@\w+\.\w+|\+\d[\d ]{8,}",
        "scam": r"bypass|login and rate limit|guarantee 5 stars", "injection": r"ignore (all |your )?(previous|prior)|disregard your|system:"}


def _text(job): return f"{job['title']}. {job['description']}"


def respond(node, d):
    job = d.get("job_obj", {})
    if node == "analyst":
        t = _text(job).lower()
        return {"job_id": job["id"], "deliverables": [job["title"]], "skills": [s for s in VOCAB if s in t],
                "budget_usd": job.get("budget_usd"), "screening_questions": [s.strip() + "?" for s in re.findall(r"([^.?!]*)\?", job["description"])]}
    if node == "risk":
        t, c = _text(job).lower(), d["client_obj"]
        flags = [f for f, rx in BAIT.items() if re.search(rx, t)]
        score = 0.2 + (0.3 if c["payment_verified"] else 0) + min(c["total_spent_usd"] / 10000, 0.3) + 0.2 * c["hire_rate"]
        return {"client_score": round(min(score, 1), 2), "flags": flags + (["scam"] if not c["payment_verified"] and c["total_spent_usd"] == 0 and "scam" not in flags else []),
                "reasons": [f"matched {f}" for f in flags]}
    if node == "matcher":
        parts = [p.strip() for p in re.split(r"[.,;\n]| and ", _text(job)) if len(p.strip()) > 3]
        return {"requirements": parts[:8]}
    if node == "writer":
        ev = d["evidence_obj"]  # list of {id,title,text}
        sents, claims = [], []
        for e in ev[:3]:
            body = re.sub(r"^#.*\n+", "", e["text"]).strip().split(". ")[0].rstrip(".")
            s = f"On a similar project, {e['title']}, I did this: {body}."
            sents.append(s); claims.append({"text": s, "label": "supported", "evidence_ids": [e["id"]]})
        opener = f"Your {job['title']} project maps directly to work I have already delivered."
        close = "Happy to walk through a short plan. What is your timeline?"
        if d.get("feedback"):
            pass  # a real model would revise; the rule writer is already compliant
        return {"cover_letter": " ".join([opener] + sents + [close]), "screening_answers": {}, "claims": claims}
    if node == "verifier":
        ev = {e["id"]: e["text"].lower() for e in d["evidence_obj"]}
        out = []
        for s in re.split(r"(?<=[.!?])\s+", d["draft_obj"]["cover_letter"]):
            if not re.search(r"\bI (built|have|did|delivered|led|shipped|worked|deployed)|years of|my experience|I've|I did", s):
                out.append({"text": s, "label": "supported", "evidence_ids": []}); continue
            toks = set(re.findall(r"[a-z0-9+]{4,}", s.lower())) - {"similar", "project", "this", "that", "with", "have", "built", "delivered"}
            best = max(((len(toks & set(re.findall(r"[a-z0-9+]{4,}", t))) / max(len(toks), 1), i) for i, t in ev.items()), default=(0, None))
            out.append({"text": s, "label": "supported" if best[0] >= .5 else "partial" if best[0] >= .25 else "unsupported",
                        "evidence_ids": [best[1]] if best[0] >= .25 else []})
        return {"claims": out}
    if node == "critic":
        txt, issues = d["draft_obj"]["cover_letter"], []
        if len(txt.split()) > d["max_words"]: issues.append(f"too long ({len(txt.split())} words)")
        if CLICHE.search(txt): issues.append("cliche opening/phrase")
        if not (set(re.findall(r"[a-z]{5,}", job["title"].lower())) & set(re.findall(r"[a-z]{5,}", txt.lower()))): issues.append("not personalised to the job")
        if not d["draft_obj"].get("claims"): issues.append("no cited evidence")
        return {"ok": not issues, "issues": issues}
    if node == "liaison_intent":
        m = d["message_obj"]["text"].lower()
        if re.search(BAIT["off_platform"] + "|" + BAIT["injection"] + r"|pay .*outside|gift card", m):
            return {"intent": "scam_signal", "reasons": ["off-platform or instruction-like text"]}
        if re.search(r"interview|call|meet|available|start monday|when can", m):
            return {"intent": "interview_request"}
        if re.search(r"rate|price|budget|discount|lower", m):
            return {"intent": "negotiation"}
        return {"intent": "question"}
    if node == "liaison":
        if d["intent"] == "interview_request":
            return {"text": "Thanks for reaching out. I can do a short call at one of these times: " + ", ".join(d["slots"][:3]) + ".", "slots": d["slots"][:3]}
        if d["intent"] == "negotiation":
            return {"text": "Thanks. I can work with your budget if we agree the scope below. Which deliverables are most important to you?"}
        return {"text": "Good question. I will answer it in detail once I confirm the specifics; could you share a bit more context?"}
    if node == "paragraph":
        para = d["paragraph"].strip()
        return {"text": re.sub(r"^(Hi|Hello|Dear)[^.!?]*[.!?]\s*", "", para) or para}
    raise KeyError(node)
