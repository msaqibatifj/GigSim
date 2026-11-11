"""Loaders -> Items with metadata. Items are portfolio units (case study / proposal / review / CV page / README)."""
import json, pathlib, re
import yaml
from dataclasses import dataclass, field

PERSONAS = pathlib.Path(__file__).resolve().parents[2] / "data" / "personas"


@dataclass
class Item:
    id: str
    type: str          # case_study | proposal | review | cv | readme
    title: str
    text: str
    persona: str
    skills: list = field(default_factory=list)
    date: str | None = None
    outcome: str | None = None      # for proposals: hired|replied|no_reply|rejected
    industry: str | None = None

    @property
    def meta(self):
        return {k: v for k, v in self.__dict__.items() if k != "text"}


def load_markdown(path: pathlib.Path, persona: str) -> Item:
    _, fm, body = path.read_text(encoding="utf-8").split("---\n", 2)
    m = yaml.safe_load(fm)
    title = body.strip().splitlines()[0].lstrip("# ")
    return Item(id=str(m["id"]), type=m["type"], title=title, text=body.strip(), persona=persona,
                skills=m.get("skills", []) if isinstance(m.get("skills"), list) else [],
                date=str(m.get("date")) if m.get("date") else None, outcome=m.get("outcome"))


def load_pdf(path: pathlib.Path, persona: str) -> list[Item]:
    """CV loader: one Item per page."""
    from pypdf import PdfReader
    return [Item(id=f"{path.stem}-p{i}", type="cv", title=f"{path.stem} page {i + 1}", text=(pg.extract_text() or "").strip(), persona=persona)
            for i, pg in enumerate(PdfReader(str(path)).pages)]


def load_readme(path: pathlib.Path, persona: str) -> Item:
    """Repo README (fetched via the GitHub MCP server during ingestion, or from disk)."""
    t = path.read_text(encoding="utf-8")
    return Item(id=f"readme-{path.parent.name}", type="readme", title=path.parent.name, text=t, persona=persona,
                skills=re.findall(r"\b(python|typescript|react|fastapi|postgres|docker)\b", t.lower()))


def load_persona(persona: str) -> list[Item]:
    root, items = PERSONAS / persona, []
    for f in sorted(root.glob("*/*.md")):
        items.append(load_markdown(f, persona))
    for f in sorted(root.glob("*.pdf")):
        items += load_pdf(f, persona)
    return items


def profile(persona: str) -> dict:
    return json.loads((PERSONAS / persona / "profile.json").read_text())
