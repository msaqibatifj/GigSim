"""Factory: the deployed variant is chosen by config (agent/config.yaml rag.variant), after evaluation (R6)."""
import importlib
from agent.config import cfg

VARIANTS = ["v0_naive", "v1_decompose", "v2_hybrid", "v3_rerank", "v4_outcome", "v5_decompose_hybrid_rerank", "v8_corrective"]


def get_retriever(index, variant: str | None = None):
    return importlib.import_module(f"rag.variants.{variant or cfg()['rag']['variant']}").make(index)
