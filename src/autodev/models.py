from enum import StrEnum

from pydantic import BaseModel, Field


class Status(StrEnum):
    NEW = "new"
    NEEDS_INFO = "needs_info"
    ANALYZED = "analyzed"
    IN_PROGRESS = "in_progress"
    REVIEW = "review"
    ESCALATED = "escalated"
    CLOSED = "closed"


class Risk(StrEnum):
    LOW = "Low"
    MEDIUM = "Medium"
    HIGH = "High"


class Ticket(BaseModel):
    id: str
    title: str
    status: Status
    kind: str | None = None
    area: str | None = None
    priority: str | None = None
    environment: str | None = None
    page_url: str | None = None
    reported_by: str | None = None
    authorized: bool = False
    attempts: int = 0
    cost_usd: float = 0.0
    model: str | None = None
    body: str = ""
    attachments: list[str] = Field(default_factory=list)
    # filled by `attachments.attach` just before an agent runs: files saved on disk, and why others were not
    files: list[dict] = Field(default_factory=list)
    file_notes: list[str] = Field(default_factory=list)
    comments: list[str] = Field(default_factory=list)
    url: str | None = None
    risk: str | None = None
    branch: str | None = None
    pr_url: str | None = None
    agent_note: str | None = None
    verification: str | None = None
    created_at: str | None = None
    updated_at: str | None = None


class Comment(BaseModel):
    author: str
    is_bot: bool = False
    text: str
    created_at: str | None = None
