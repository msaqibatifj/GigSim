"""V8: corrective RAG as a small LangGraph loop.
retrieve (hybrid+rerank on whole post) -> grade each requirement against what was retrieved
-> if some requirements are uncovered, retrieve again for just those (once) -> merge."""
from typing import TypedDict
from langgraph.graph import END, START, StateGraph
from agent.config import cfg
from rag.index.store import reranker
from rag.variants.base import Pipeline, decompose


class S(TypedDict, total=False):
    job: dict
    k: int
    hits: list
    uncovered: list
    attempts: int


class Corrective:
    def __init__(self, idx):
        self.base = Pipeline(idx, "whole", "hybrid", rerank=True)
        self.name = "v8_corrective"
        g = StateGraph(S)
        g.add_node("retrieve", self.retrieve)
        g.add_node("grade", self.grade)
        g.add_node("correct", self.correct)
        g.add_edge(START, "retrieve")
        g.add_edge("retrieve", "grade")
        g.add_conditional_edges("grade", lambda s: "correct" if s["uncovered"] and s["attempts"] < 1 else END, ["correct", END])
        g.add_edge("correct", "grade")
        self.graph = g.compile()

    def retrieve(self, s):
        return {"hits": self.base.search(s["job"], k=s["k"]), "attempts": 0}

    def grade(self, s):
        top = [h.text for h in s["hits"][:5]]
        tau = cfg()["rag"]["corrective_threshold"]
        unc = []
        for r in decompose(s["job"]):
            if top and max(reranker().rerank(r, top)) < tau:
                unc.append(r)
        return {"uncovered": unc}

    def correct(self, s):
        extra = self.base.search(s["job"], k=s["k"], queries=s["uncovered"])
        seen = {h.item_id for h in s["hits"]}
        merged = s["hits"][:3] + [h for h in extra if h.item_id not in seen][:3] + s["hits"][3:]
        return {"hits": merged[: s["k"]], "attempts": s["attempts"] + 1}

    def search(self, job, k=10, queries=None):
        return self.graph.invoke({"job": job, "k": k})["hits"]


def make(idx):
    return Corrective(idx)
