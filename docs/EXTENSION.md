# EXTENSION: X2 Proposal experiments

**What:** an A/B harness that writes proposals for the same jobs under two strategies (same Writer model, evidence and claim verification; only the style rules differ), scores them in GigSim, and tests the difference.

- Strategy A *intro-first*: introduce yourself, then relevant work.
- Strategy B *deliverable-first*: open with the job's exact deliverable, cite one measurable result from the evidence, close with one scoped question.

**How it is measured:** `evals/runners/ab_experiment.py` runs every bid-worthy dev job (30) through both strategies and computes the per-job difference in GigSim reply probability. Significance is a paired sign-flip permutation test (20,000 resamples). Result: `evals/results/ab_experiment.json`.

**How it connects to the product:** the style rules are the same `style` input that style memory fills, so a winning strategy can be promoted into a user's style rules through the normal promotion path (never silently).

**Limits:** GigSim's client model is synthetic (`outcome()` in `adapters/gigsim.py`). A significant result means "this strategy scores higher under that model", which is partly the model's own assumptions (specific opening, length). With real replies you would need far more than 30 jobs per arm. Treat the number as a test of the pipeline, not a finding about clients.
