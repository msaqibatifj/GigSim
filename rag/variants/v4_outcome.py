"""V4 (optional): outcome-aware ranking, boosts proposals that won replies/hires."""
from rag.variants.base import Pipeline
def make(idx): return Pipeline(idx, "whole", "hybrid", rerank=True, outcome_boost=0.2, name="v4_outcome")
