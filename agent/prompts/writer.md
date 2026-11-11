Write a cover letter (max $max_words words) for this job as the freelancer. Use ONLY the evidence below; never claim experience it does not support; no contact details, no guarantees, avoid cliches like "passionate". Open with something specific to this job, not a greeting formula.
Style rules learned from the freelancer's edits: $style
Return JSON: {"cover_letter": str, "screening_answers": {question: answer}, "claims": [{"text": str, "label": "supported", "evidence_ids": [ids]}]}.

<untrusted_job_post>
$job
</untrusted_job_post>
Evidence (id: text):
$evidence
Critic feedback to address (if any): $feedback
