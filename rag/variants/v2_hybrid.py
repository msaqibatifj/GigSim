"""V2: BM25 + dense fused with reciprocal rank fusion."""
from rag.variants.base import Pipeline
def make(idx): return Pipeline(idx, "whole", "hybrid", name="v2_hybrid")
