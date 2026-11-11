"""V3: hybrid retrieval then cross-encoder reranking."""
from rag.variants.base import Pipeline
def make(idx): return Pipeline(idx, "whole", "hybrid", rerank=True, name="v3_rerank")
