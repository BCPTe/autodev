from typing import Protocol

from autodev.models import Risk, Status, Ticket


class Tracker(Protocol):
    async def fetch_ready(self) -> list[Ticket]:
        """Tickets in status NEW that a human marked as authorized."""

    async def fetch_by_status(self, status: Status, *, authorized_only: bool = True) -> list[Ticket]: ...

    async def bot_comments(self, ticket_id: str) -> list[str]:
        """Comments written by the integration itself (e.g. the triage analysis)."""

    async def set_status(self, ticket_id: str, status: Status) -> None: ...

    async def comment(self, ticket_id: str, text: str, *, as_human: bool = False) -> None: ...

    async def update(
        self,
        ticket_id: str,
        *,
        risk: Risk | None = None,
        pr_url: str | None = None,
        branch: str | None = None,
        attempts: int | None = None,
        cost_usd: float | None = None,
        agent_note: str | None = None,
        verification: str | None = None,
        authorized: bool | None = None,
        model: str | None = None,
    ) -> None: ...
