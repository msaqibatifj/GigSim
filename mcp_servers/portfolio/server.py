"""Portfolio MCP server (read-only). Run: python -m mcp_servers.portfolio.server [--http]"""
import sys
from typing import Annotated, Literal
from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations
from pydantic import BaseModel, Field
from mcp_servers.portfolio import tools

mcp = FastMCP("portfolio")
RO = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)

class Evidence(BaseModel):
    id: str
    type: str
    title: str
    snippet: str
    source: str
    outcome: str | None = None
    score: float

class CaseStudy(BaseModel):
    id: str
    type: str
    title: str
    text: str
    source: str
    skills: list[str] = []
    date: str | None = None
    industry: str | None = None

@mcp.tool(annotations=RO)
def search_evidence(
    requirement: Annotated[str, Field(min_length=3, max_length=500, description="One job requirement, e.g. 'hybrid search RAG over PDFs'")],
    k: Annotated[int, Field(ge=1, le=20)] = 5,
    type: Literal["case_study", "proposal"] | None = None,
    outcome: Literal["won", "hired", "replied", "no_reply", "rejected"] | None = None,
) -> list[Evidence]:
    """Find portfolio items that support a requirement. Returns type, source, outcome. Empty list = no evidence; do not claim it."""
    return tools.search_evidence(requirement, k, type, outcome)

@mcp.tool(annotations=RO)
def get_case_study(id: Annotated[str, Field(min_length=1, max_length=40)]) -> CaseStudy:
    """Full text of one case study by id."""
    r = tools.get_case_study(id)
    if r is None:
        raise ValueError(f"no case study {id!r}")
    return CaseStudy(**{k: (str(v) if k == "date" and v is not None else v) for k, v in r.items() if k in CaseStudy.model_fields})

@mcp.tool(annotations=RO)
def list_skills() -> list[str]:
    """Skills the freelancer can truthfully claim."""
    return tools.list_skills()

@mcp.resource("portfolio://case/{id}")
def case_resource(id: str) -> str:
    r = tools.get_case_study(id)
    return r["text"] if r else f"not found: {id}"

@mcp.resource("portfolio://proposal/{id}")
def proposal_resource(id: str) -> str:
    r = tools.get_proposal(id)
    return r["text"] if r else f"not found: {id}"

@mcp.prompt()
def answer_screening_question(question: str) -> str:
    """Answer a client's screening question using only my portfolio."""
    return (f"Answer this screening question using ONLY evidence from my portfolio. "
            f"First call search_evidence for each part of the question, cite item ids in [brackets], "
            f"and say plainly if I lack experience.\n\nQuestion: {question}")

@mcp.prompt()
def write_cover_letter(job_description: str) -> str:
    """Draft a short cover letter for a job, grounded in my portfolio."""
    return ("Draft a cover letter under 200 words. For each requirement in the job, call search_evidence; "
            "only claim experience you find, cite ids, no guarantees, no contact details.\n\nJob:\n" + job_description)

if __name__ == "__main__":
    mcp.run(transport="streamable-http" if "--http" in sys.argv else "stdio")
