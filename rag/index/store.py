"""Per-persona index: Qdrant (vector store; in-memory locally, server via QDRANT_URL) + BM25 over the same chunks.
Incremental re-index: add_items() embeds only new items."""
import os, re
import numpy as np
from fastembed import TextEmbedding
from fastembed.rerank.cross_encoder import TextCrossEncoder
from qdrant_client import QdrantClient, models
from rank_bm25 import BM25Okapi
from agent.config import cfg, profile
from rag.ingest.chunking import Chunk, chunk_items
from rag.ingest.loaders import load_persona

_models = {}


def _embedder():
    n = cfg()["profiles"][profile()]["embed"]["model"]
    return _models.setdefault(("e", n), TextEmbedding(n))


def reranker():
    n = cfg()["profiles"][profile()]["rerank"]["model"]
    return _models.setdefault(("r", n), TextCrossEncoder(n))


def tok(s: str) -> list[str]:
    return re.findall(r"[a-z0-9+#]+", s.lower())


class Index:
    def __init__(self, persona: str, items=None):
        self.persona, self.chunks, self.items = persona, [], {}
        self.q = QdrantClient(url=os.environ["QDRANT_URL"]) if os.getenv("QDRANT_URL") else QdrantClient(":memory:")
        self.col = f"portfolio_{persona}"
        self.q.recreate_collection(self.col, vectors_config=models.VectorParams(size=len(next(iter(_embedder().embed(["x"])))), distance=models.Distance.COSINE))
        self.add_items(items if items is not None else load_persona(persona))

    def add_items(self, items):
        new = chunk_items(items, cfg()["rag"]["chunk_words"], cfg()["rag"]["chunk_overlap"])
        vecs = list(_embedder().embed([c.text for c in new]))
        base = len(self.chunks)
        self.q.upsert(self.col, points=[models.PointStruct(id=base + i, vector=v.tolist(), payload={"chunk": c.id}) for i, (c, v) in enumerate(zip(new, vecs))])
        self.chunks += new
        self.items.update({i.id: i for i in items})
        self.bm25 = BM25Okapi([tok(c.text + " " + c.item.title) for c in self.chunks])

    def dense(self, query: str, n: int = 20) -> list[tuple[Chunk, float]]:
        v = next(iter(_embedder().query_embed([query])))
        hits = self.q.query_points(self.col, query=v.tolist(), limit=n).points
        return [(self.chunks[h.id], h.score) for h in hits]

    def sparse(self, query: str, n: int = 20) -> list[tuple[Chunk, float]]:
        s = self.bm25.get_scores(tok(query))
        return [(self.chunks[i], float(s[i])) for i in np.argsort(-s)[:n] if s[i] > 0]
