"""Portfolio data layer (read-only). search_evidence is lexical for now; rag.retriever replaces it later."""
import os, pathlib
import yaml
# imported at module load: onnxruntime (via fastembed) crashes on Windows if first loaded from a worker thread
from rag.index.store import Index
from rag.ingest.loaders import load_persona
from rag.retriever import get_retriever

ROOT = pathlib.Path(__file__).resolve().parents[2] / "data" / "personas"

def persona() -> str:
    return os.getenv("PORTFOLIO_PERSONA", "ayesha_ml")

def _items(p: str | None = None) -> list[dict]:
    out = []
    for f in sorted((ROOT / (p or persona())).glob("*/*.md")):
        _, fm, body = f.read_text(encoding="utf-8").split("---\n", 2)
        meta = yaml.safe_load(fm)
        title = body.strip().splitlines()[0].lstrip("# ")
        out.append({**meta, "title": title, "text": body.strip(), "source": f"portfolio://{'case' if meta['type']=='case_study' else 'proposal'}/{meta['id']}"})
    return out

_INDEX: dict = {}


def _index(p: str | None = None):
    """One index per persona, built once; items added on disk since (UI uploads) are embedded incrementally."""
    p = p or persona()
    items = load_persona(p)
    if p not in _INDEX:
        _INDEX[p] = Index(p, items)
    else:
        new = [i for i in items if i.id not in _INDEX[p].items]
        if new:
            _INDEX[p].add_items(new)
    return _INDEX[p]


def search_evidence(requirement: str, k: int = 5, type: str | None = None, outcome: str | None = None, persona_name: str | None = None) -> list[dict]:
    """Retrieval goes through the variant chosen by evaluation (agent/config.yaml rag.variant, R6).
    persona_name is for in-process callers (eval runners) that run several personas concurrently; the MCP tool uses the env."""
    idx = _index(persona_name)
    hits = get_retriever(idx).search({"title": "", "description": requirement}, k=max(k * 3, 10), queries=[requirement])
    out = []
    for h in hits:
        it = idx.items[h.item_id]
        if (type and it.type != type) or (outcome and it.outcome != outcome):
            continue
        out.append({"id": it.id, "type": it.type, "title": it.title, "snippet": h.text[:300],
                    "source": f"portfolio://{'proposal' if it.type == 'proposal' else 'case'}/{it.id}", "outcome": it.outcome,
                    "score": round(float(h.score), 4)})
    return out[:k]


def get_case_study(id: str) -> dict | None:
    return next((i for i in _items() if i["id"] == id and i["type"] == "case_study"), None)

def get_proposal(id: str) -> dict | None:
    return next((i for i in _items() if i["id"] == id and i["type"] == "proposal"), None)

def list_skills() -> list[str]:
    import json
    return json.loads((ROOT / persona() / "profile.json").read_text())["skills"]
