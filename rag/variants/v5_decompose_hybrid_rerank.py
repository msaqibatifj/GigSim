"""Combination: decompose + hybrid + rerank (the candidate 'best' pipeline for ablation)."""
from rag.variants.base import Pipeline
def make(idx): return Pipeline(idx, "decompose", "hybrid", rerank=True, name="v5_decompose_hybrid_rerank")
