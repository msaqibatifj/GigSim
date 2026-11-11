# My retrieval never said "no": how every job looked like a fit

*Draft of the technical write-up (publish on LinkedIn, Medium or a personal blog). Numbers come from `evals/results/*.json` in the GigBid repo; file names are in brackets.*

I built GigBid, an agent that reads freelance job posts, decides whether to bid, and drafts a proposal in which every claim has to link to the freelancer's own portfolio. A human approves before anything is sent. The graph has the usual shape: three agents analyse the job in parallel (what it asks for, whether it looks like a scam, whether the portfolio covers it), then pricing, writing, claim verification, a critic, and a compliance check.

The most surprising result of the whole project was not about agents. It was that my first evaluation run bid on jobs the freelancer had no business bidding on, and that the bug was in a place I had never thought to look.

## Three jobs that should have been skipped

My dev set has jobs labelled "bid" and "skip". In the first run on a compact set of 14 jobs, bid/skip accuracy was 75% (over the 12 jobs that completed; the other two crashed on an unrelated bug). The misses were all the same kind. A machine-learning freelancer got a bid drafted for a React storefront redesign. A web developer got one for training a vision model. A data analyst got one for a Unity multiplayer game. Each came with a price and a cover letter that cited portfolio items. The cover letters were fluent and, after claim verification, nothing in them was unsupported. They were just about work the freelancer had never done.

(Those first-run numbers are from the console output of that run; the results file was overwritten by the later fixed runs, which `docs/FAILURES.md` says explicitly.)

## Why: "covered" was vacuous

The Fit Matcher splits a job into requirements, searches the portfolio for each one, and scores fit as the share of requirements that have evidence. The part I got wrong is what "have evidence" meant: the search returned something. Vector search always returns its top-k. A cross-encoder reranker orders the candidates, but it never says "none of these are relevant". So a React storefront requirement happily matched the nearest ML case study, the requirement counted as covered, and fit looked fine.

A lot of RAG code has this shape, because retrieval metrics reward ranking and not abstaining. My retrieval evaluation was good: Recall@5 of 0.95 and nDCG@10 of 0.91 for the shipped variant [rag_eval_all.json]. Those numbers measure whether the right item is near the top when there is a right item. They say nothing about what happens when there isn't one, and that is exactly the case a bidding assistant has to handle.

## What the scores actually look like

The reranker returns a raw score for each item, and the scores are not all alike. I took the best whole-post score for each of the 42 dev jobs [score_gap.json]:

| Group | n | min | median | max |
|---|---|---|---|---|
| should bid | 30 | -6.77 | 0.14 | 5.72 |
| legit, should skip | 5 | -10.83 | -10.28 | -7.63 |
| scam or injection | 7 | -9.98 | -7.72 | -6.09 |

There is a real separation, but it is narrow: the worst job that should be bid scores -6.77 and the best job that should be skipped scores -7.63, a gap of 0.86 logits. I added a hard evidence floor, a requirement counts as supported only if its best item scores at least -8.0, and the three low-fit jobs in my compact set went to a fit of 0.0 and were skipped. Scam and injection posts score high because they are written like real jobs, so they are caught by the risk checks, not by this floor.

## The fix broke something else, and I tuned it on the wrong data

With the floor in place, two good jobs were now skipped. The reason is again in the definition: fit is the share of *decomposed* requirements that are covered, and the number of requirements depends on how many the model chose to list. One job had a made-up fifth requirement, so a genuinely well-matched job scored 0.25. Since the floor now guarantees that anything counted as covered is real support, I lowered the bid threshold from 0.5 to 0.2. The compact set went to 14 of 14 correct.

That number is not trustworthy, and the reason is the point of this section. The compact set had only 3 of the 5 low-fit jobs in my dev set. I then ran the two it left out. Both were wrongly bid [decision_eval_open_extra_lowfit.json]: one has a whole-post score of -7.63, just above the floor, and the other has a whole-post score of -10.09 but one decomposed requirement still matched, giving a fit of exactly 0.2, the threshold I had just chosen.

There is a threshold near -7.2 on the whole-post score that would separate all 35 legitimate dev jobs. I did not apply it, because I would be choosing it using the same data I would then report on, with a margin of 0.4. Five low-fit jobs cannot tell a real threshold from a lucky one. The honest status is that the floor fixes the failure in kind but not in degree, and the system needs more labelled low-fit jobs before I would trust it on a real feed.

## What the ablation said about everything else

I wrote four hypotheses before running the ablation (they are in the runner's docstring) and then removed components from the best pipeline one at a time [ablation.json]. Nothing about this pipeline was what I had assumed:

- **The reranker is the component that matters.** Removing it cost 0.204 nDCG@10. Removing hybrid BM25+dense fusion cost exactly 0.000, with identical numbers in every column, probably because on a portfolio this small the reranker sees nearly the same top candidates either way.
- **Requirement decomposition hurt.** Removing it *raised* nDCG@10 by 0.058, and in the pooled setting where all three personas share an index, decomposition alone collapsed nDCG@10 from 0.885 to 0.611. Short sub-queries are ambiguous, and each one pulls in its own distractors from other people's portfolios. I expected decomposition to help on jobs with several requirements. It did not.

So the shipped retrieval is the plain reranker. The elaborate options, a corrective-RAG loop and a decompose-hybrid-rerank stack, were slower (a p95 of 89 seconds for the corrective loop) and no better.

## Smaller findings that held up

**A critic that cannot see the evidence will always object.** In the first run the Critic sent drafts back a mean of 1.78 times per proposal (the maximum is 2) across 9 proposals, mostly because it kept asking for citations it had no way to check. Giving it the evidence and the verifier's labels brought the mean to zero and cut p95 latency from about 90 s to 28 s. The risk is the opposite one: a critic that now approves everything. I have not measured that.

**Tool descriptions mattered more than tool count.** On 40 tasks with known correct calls, a set of 16 tools with rewritten, disambiguating descriptions got 100% tool and argument accuracy, against 70% for 24 fine-grained tools with terse descriptions and 85% (tool) and 67.5% (arguments) for 4 coarse tools [tool_granularity.json]. The best set also used more prompt tokens than the coarse one (697 vs 301 per task). The tasks were written by me alongside the descriptions, so this is an upper bound.

**A single ReAct agent tied my multi-agent graph on accuracy.** On the same 14 jobs both got 14 of 14 right, and the single agent used fewer tokens (1,379 against 2,172 per job). The graph was about 7 times faster at p95 (28 s against 186 s) because its three analysis branches run in parallel, and it is the only one with an approval gate, a deterministic compliance check and verified claims. A prebuilt supervisor skipped 5 of the 6 jobs that should be bid [agent_comparison.json]. If I only cared about accuracy on this set, I would ship the single agent.

**Injected instructions were mostly a Writer problem.** With planted instructions in six job posts, the defences cut attack success from 0.67 to 0.0 [injection_eval.json]. Before the defences, the planted word reached a draft in half the cases, so the Writer was following instructions inside the job post. Scrubbing the offending sentences before any drafting step fixed it. A regex-based detector will miss paraphrased or non-English injections; the human approval gate is what is left behind it.

## What I would do differently

I would have built the abstention test first. A retrieval evaluation should include queries that have no right answer and measure how often the system still returns something it treats as support. I would also have labelled far more low-fit jobs before touching a threshold, and kept a split I never tuned on. I got this lesson by accident, from two jobs I almost did not run.

The caveats on everything above: 14 jobs, one run each, thresholds tuned in-sample, and a simulated client whose reply behaviour I wrote myself, so any "reply rate" in the repo measures agreement with my own model and not real clients. The code, the data card and every result file are in the repository.
