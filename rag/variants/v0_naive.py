"""V0 baseline: fixed chunks, top-k cosine on the whole job post."""
from rag.variants.base import Pipeline
def make(idx): return Pipeline(idx, "whole", "dense", name="v0_naive")
