from dataclasses import dataclass
from rag.ingest.loaders import Item


@dataclass
class Chunk:
    id: str
    item_id: str
    text: str
    item: Item


def chunk_items(items: list[Item], words: int = 45, overlap: int = 10) -> list[Chunk]:
    """Fixed-size word windows (V0 baseline chunking). Every chunk keeps its item's metadata."""
    out = []
    for it in items:
        w = it.text.split()
        step = max(words - overlap, 1)
        for n, s in enumerate(range(0, max(len(w) - overlap, 1), step)):
            out.append(Chunk(f"{it.id}#{n}", it.id, " ".join(w[s:s + words]), it))
    return out
