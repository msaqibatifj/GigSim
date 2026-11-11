"""Workspace MCP server: calendar slots + email drafts. Local mock; agents only ever see these tools,
so swapping in Google Calendar/Gmail later changes nothing upstream."""
import sys
from datetime import datetime, timedelta
from typing import Annotated
from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations
from pydantic import BaseModel, Field

mcp = FastMCP("workspace")
_holds: dict[str, dict] = {}
_drafts: dict[str, dict] = {}


class Hold(BaseModel):
    start: str
    title: str
    status: str


class EmailDraft(BaseModel):
    thread: str
    body: str
    status: str


class Slot(BaseModel):
    start: str
    end: str


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=True))
def free_slots(days: Annotated[int, Field(ge=1, le=14)] = 3, minutes: Annotated[int, Field(ge=15, le=120)] = 30) -> list[Slot]:
    """Free interview slots (weekdays 10:00-16:00 local), excluding existing holds."""
    out, d = [], datetime.now().replace(minute=0, second=0, microsecond=0) + timedelta(days=1)
    while len(out) < 3 * days:
        if d.weekday() < 5:
            for h in (10, 13, 15):
                s = d.replace(hour=h)
                if s.isoformat() not in _holds:
                    out.append(Slot(start=s.isoformat(), end=(s + timedelta(minutes=minutes)).isoformat()))
        d += timedelta(days=1)
    return out[: 3 * days]


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=True))
def create_tentative_hold(start: Annotated[str, Field(pattern=r"^\d{4}-\d\d-\d\dT")], title: Annotated[str, Field(min_length=1, max_length=120)]) -> Hold:
    """Place a tentative calendar hold. Same start = same hold (idempotent)."""
    _holds[start] = {"start": start, "title": title, "status": "tentative"}
    return Hold(**_holds[start])


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=True))
def create_email_draft(to_thread: Annotated[str, Field(min_length=1, max_length=40)], body: Annotated[str, Field(min_length=1, max_length=5000)]) -> EmailDraft:
    """Save an email draft (never sends). One draft per thread; re-calling replaces it."""
    _drafts[to_thread] = {"thread": to_thread, "body": body, "status": "draft"}
    return EmailDraft(**_drafts[to_thread])


if __name__ == "__main__":
    mcp.run(transport="streamable-http" if "--http" in sys.argv else "stdio")
