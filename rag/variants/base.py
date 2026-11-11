"""One configurable retrieval pipeline; each vN_*.py is a named preset of it (V8 is a LangGraph loop).
Stages: query transform (whole post | decompose into requirements) -> retrieve (dense | hybrid RRF)
        -> optional cross-encoder rerank -> optional outcome-aware boost -> item-level results."""
from dataclasses import dataclass
from collections import defaultdict
from pydantic import BaseModel
from agent.config import cfg
from agent.llm import structured
from rag.index.store import Index, reranker

GOOD = {"hired", "replied"}


@dataclass
class Hit:
    item_id: str
    score: float
    text: str
    type: str
    outcome: str | None


class Requirements(BaseModel):
    requirements: list[str]


def job_query(job: dict) -> str:
    return f"{job['title']}. {job['description']}"


def rrf(lists, k=60):
    """Reciprocal rank fusion over ranked lists of keys -> {key: score}."""
    s = defaultdict(float)
    for lst in lists:
        for r, key in enumerate(lst):
            s[key] += 1.0 / (k + r + 1)
    return s


def decompose(job: dict) -> list[str]:
    reqs = structured("matcher", Requirements, {"job": job_query(job), "job_obj": job}).requirements
    return reqs or [job_query(job)]


class Pipeline:
    def __init__(self, index: Index, query="whole", retrieve="dense", rerank=False, outcome_boost=0.0, name=""):
        self.idx, self.query, self.retrieve, self.rerank, self.boost, self.name = index, query, retrieve, rerank, outcome_boost, name

    def _chunks(self, q):  # ranked chunk list for one query
        n = cfg()["rag"]["candidates"]
        dense = [c for c, _ in self.idx.dense(q, n)]
        if self.retrieve == "dense":
            return dense
        sparse = [c for c, _ in self.idx.sparse(q, n)]
        fused = rrf([[c.id for c in dense], [c.id for c in sparse]])
        by_id = {c.id: c for c in dense + sparse}
        return [by_id[i] for i, _ in sorted(fused.items(), key=lambda x: -x[1])][:n]

    def search(self, job: dict, k: int = 10, queries: list[str] | None = None) -> list[Hit]:
        queries = queries or (decompose(job) if self.query == "decompose" else [job_query(job)])
        item_score, item_chunk = defaultdict(float), {}
        for q in queries:
            ranked = self._chunks(q)
            if self.rerank and ranked:
                scores = list(reranker().rerank(q, [c.text for c in ranked]))
                pairs = sorted(zip(ranked, scores), key=lambda x: -x[1])
                for c, s in pairs:           # item score = best (query, chunk) rerank score
                    if s > item_score.get(c.item_id, float("-inf")) or c.item_id not in item_score:
                        item_score[c.item_id], item_chunk[c.item_id] = s, c
            else:
                seen = set()
                for r, c in enumerate(ranked):  # RRF contribution per query, best chunk per item
                    if c.item_id not in seen:
                        seen.add(c.item_id)
                        item_score[c.item_id] += 1.0 / (60 + r + 1)
                        item_chunk.setdefault(c.item_id, c)
        if self.boost:  # additive so it also works for negative cross-encoder scores
            for i in item_score:
                it = self.idx.items[i]
                if it.type == "proposal" and it.outcome in GOOD:
                    item_score[i] += self.boost * abs(item_score[i])
        top = sorted(item_score.items(), key=lambda x: -x[1])[:k]
        return [Hit(i, s, item_chunk[i].text, self.idx.items[i].type, self.idx.items[i].outcome) for i, s in top]
