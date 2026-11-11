"""V1: one retrieval per requirement, then merge (RRF over requirements)."""
from rag.variants.base import Pipeline
def make(idx): return Pipeline(idx, "decompose", "dense", name="v1_decompose")
