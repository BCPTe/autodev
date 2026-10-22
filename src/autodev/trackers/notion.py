import httpx

from autodev.config import TrackerConfig
from autodev.models import Comment, Risk, Status, Ticket

API = "https://api.notion.com/v1"
VERSION = "2025-09-03"


def _text(prop: dict, key: str) -> str | None:
    parts = prop.get(key) or []
    return "".join(p.get("plain_text", "") for p in parts) or None


def _select(prop: dict) -> str | None:
    sel = prop.get("select")
    return sel["name"] if sel else None


HUMAN_PREFIX = "[dashboard] "


def _raw_text(comment: dict) -> str:
    return _text(comment, "rich_text") or ""


def _from_dashboard(comment: dict) -> bool:
    """Comments typed in the dashboard are posted through the integration but written by a person."""
    return _raw_text(comment).startswith(HUMAN_PREFIX)


def _is_bot(comment: dict) -> bool:
    """Notion puts no `type` in a comment's created_by; the author kind is in display_name."""
    return (comment.get("display_name") or {}).get("type") == "integration" and not _from_dashboard(comment)


def _comment_text(comment: dict) -> str:
    text = _raw_text(comment)
    return text[len(HUMAN_PREFIX):] if text.startswith(HUMAN_PREFIX) else text


def _author(comment: dict) -> str:
    if _from_dashboard(comment):
        return "dashboard"
    return (comment.get("display_name") or {}).get("resolved_name") or ("autodev" if _is_bot(comment) else "persona")


def _rich(text: str) -> dict:
    chunks = [text[i : i + 2000] for i in range(0, len(text), 2000)] or [""]
    return {"rich_text": [{"type": "text", "text": {"content": c}} for c in chunks]}


class NotionTracker:
    def __init__(self, cfg: TrackerConfig, token: str, client: httpx.AsyncClient | None = None):
        self._cfg = cfg
        self._to_status = {label: status for status, label in cfg.status_map.items()}
        self._client = client or httpx.AsyncClient(
            base_url=API,
            headers={"Authorization": f"Bearer {token}", "Notion-Version": VERSION},
            timeout=30,
        )

    def _parse(self, page: dict) -> Ticket:
        p = page["properties"]
        c = self._cfg
        status_name = p[c.prop("status")]["status"]["name"]
        return Ticket(
            id=page["id"],
            title=_text(p[c.prop("title")], "title") or "",
            status=self._to_status[status_name],
            kind=_select(p[c.prop("kind")]),
            area=_select(p[c.prop("area")]),
            priority=_select(p[c.prop("priority")]),
            environment=_select(p[c.prop("environment")]),
            page_url=p[c.prop("page_url")]["url"],
            reported_by=_text(p[c.prop("reported_by")], "rich_text"),
            authorized=p[c.prop("authorized")]["checkbox"],
            attempts=int(p[c.prop("attempts")]["number"] or 0),
            cost_usd=float(p[c.prop("cost")]["number"] or 0.0),
            model=_select(p.get(c.prop("model")) or {}),
            url=page.get("url"),
            risk=_select(p.get(c.prop("risk")) or {}),
            branch=_text(p.get(c.prop("branch")) or {}, "rich_text"),
            pr_url=(p.get(c.prop("pr")) or {}).get("url"),
            agent_note=_text(p.get(c.prop("agent_note")) or {}, "rich_text"),
            verification=_select(p.get(c.prop("verification")) or {}),
            created_at=page.get("created_time"),
            updated_at=page.get("last_edited_time"),
            attachments=[f["name"] for f in p[c.prop("attachments")]["files"]],
        )

    async def _body(self, page_id: str) -> str:
        r = await self._client.get(f"/blocks/{page_id}/children", params={"page_size": 100})
        r.raise_for_status()
        lines = []
        for block in r.json()["results"]:
            content = block.get(block["type"], {})
            lines.append(_text(content, "rich_text") or "")
        return "\n".join(lines).strip()

    async def fetch_by_status(self, status: Status, *, authorized_only: bool = True) -> list[Ticket]:
        c = self._cfg
        conditions: list[dict] = [{"property": c.prop("status"), "status": {"equals": self._cfg.status_map[status]}}]
        if authorized_only:
            conditions.append({"property": c.prop("authorized"), "checkbox": {"equals": True}})
        r = await self._client.post(
            f"/data_sources/{self._cfg.data_source_id}/query", json={"filter": {"and": conditions}}
        )
        r.raise_for_status()
        tickets = [self._parse(page) for page in r.json()["results"]]
        for t in tickets:
            t.body = await self._body(t.id)
            t.comments = await self._comments(t.id, bot=False)
        return tickets

    async def list_all(self) -> list[Ticket]:
        """Every ticket with its properties (no body, no comments): enough for a board."""
        tickets: list[Ticket] = []
        cursor: str | None = None
        while True:
            payload: dict = {"page_size": 100}
            if cursor:
                payload["start_cursor"] = cursor
            r = await self._client.post(f"/data_sources/{self._cfg.data_source_id}/query", json=payload)
            r.raise_for_status()
            data = r.json()
            for page in data["results"]:
                try:
                    tickets.append(self._parse(page))
                except KeyError as e:
                    raise RuntimeError(
                        f"cannot read a Notion row: {e} is missing or is not in the project file "
                        "(check the column names in `tracker.properties` and the labels in `tracker.status_map`)"
                    ) from e
            if not data.get("has_more"):
                return tickets
            cursor = data["next_cursor"]

    async def detail(self, ticket_id: str) -> tuple[Ticket, list[Comment]]:
        r = await self._client.get(f"/pages/{ticket_id}")
        r.raise_for_status()
        ticket = self._parse(r.json())
        ticket.body = await self._body(ticket_id)
        c = await self._client.get("/comments", params={"block_id": ticket_id, "page_size": 100})
        c.raise_for_status()
        comments = [
            Comment(
                author=_author(x),
                is_bot=_is_bot(x),
                text=_comment_text(x),
                created_at=x.get("created_time"),
            )
            for x in c.json()["results"]
        ]
        ticket.comments = [c.text for c in comments if not c.is_bot]
        return ticket, comments

    async def fetch_ready(self) -> list[Ticket]:
        return await self.fetch_by_status(Status.NEW)

    async def _comments(self, ticket_id: str, *, bot: bool) -> list[str]:
        r = await self._client.get("/comments", params={"block_id": ticket_id, "page_size": 100})
        r.raise_for_status()
        return [
            _comment_text(c)
            for c in r.json()["results"]
            if _is_bot(c) == bot
        ]

    async def bot_comments(self, ticket_id: str) -> list[str]:
        return await self._comments(ticket_id, bot=True)

    async def _patch(self, ticket_id: str, properties: dict) -> None:
        r = await self._client.patch(f"/pages/{ticket_id}", json={"properties": properties})
        r.raise_for_status()

    async def set_status(self, ticket_id: str, status: Status) -> None:
        c = self._cfg
        await self._patch(ticket_id, {c.prop("status"): {"status": {"name": self._cfg.status_map[status]}}})

    async def comment(self, ticket_id: str, text: str, *, as_human: bool = False, author: str | None = None) -> None:
        """A comment typed by a person goes through the integration, so Notion would show it as written by
        the bot: it gets a custom display name (the person's), and a text marker as a fallback."""
        body = {"parent": {"page_id": ticket_id}, "rich_text": _rich(HUMAN_PREFIX + text if as_human else text)["rich_text"]}
        if as_human and author:
            named = {**body, "rich_text": _rich(text)["rich_text"], "display_name": {"type": "custom", "custom": {"name": author}}}
            r = await self._client.post("/comments", json=named)
            if r.status_code < 400:
                return
        r = await self._client.post("/comments", json=body)
        r.raise_for_status()

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
    ) -> None:
        props: dict = {}
        c = self._cfg
        if authorized is not None:
            props[c.prop("authorized")] = {"checkbox": authorized}
        if model is not None:
            props[c.prop("model")] = {"select": {"name": model}}
        if risk is not None:
            props[c.prop("risk")] = {"select": {"name": risk.value}}
        if pr_url is not None:
            props[c.prop("pr")] = {"url": pr_url}
        if branch is not None:
            props[c.prop("branch")] = _rich(branch)
        if attempts is not None:
            props[c.prop("attempts")] = {"number": attempts}
        if cost_usd is not None:
            props[c.prop("cost")] = {"number": cost_usd}
        if agent_note is not None:
            props[c.prop("agent_note")] = _rich(agent_note)
        if verification is not None:
            props[c.prop("verification")] = {"select": {"name": verification}}
        if props:
            await self._patch(ticket_id, props)

    async def verify(self) -> list[str]:
        r = await self._client.get(f"/data_sources/{self._cfg.data_source_id}")
        r.raise_for_status()
        return sorted(r.json()["properties"])

    async def aclose(self) -> None:
        await self._client.aclose()
