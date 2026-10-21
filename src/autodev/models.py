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
    LOW = "Basso"
    MEDIUM = "Medio"
    HIGH = "Alto"


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
    comments: list[str] = Field(default_factory=list)
