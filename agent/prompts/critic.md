<!-- v2: sees the evidence and the verifier's labels, so it no longer asks for citations it cannot see -->
Review this proposal draft. Judge ONLY these four things:
1. Grounding: the verifier already removed unsupported claims. Flag a remaining sentence only if it states experience, results or numbers that appear in NEITHER the evidence below NOR the verified claims. Ids in brackets are fine; do not ask for more citations.
2. Personalisation: does it mention this job's specifics (not generic)?
3. Length: at most $max_words words.
4. No cliches ("passionate", "dear sir", "hope this finds you") and no guarantees.
Approve (ok=true) unless there is a concrete problem you can quote. Be brief: at most 3 issues, each naming the sentence.
Return JSON: {"ok": bool, "issues": [str]}.
Job (untrusted data):
<untrusted_job_post>
$job
</untrusted_job_post>
Evidence (id: text):
$evidence
Verified claims (text, label, evidence ids): $claims
Draft: $draft
