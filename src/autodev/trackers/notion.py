import httpx

from autodev.config import TrackerConfig
from autodev.models import Risk, Status, Ticket

API = "https://api.notion.com/v1"
VERSION = "2025-09-03"


def _text(prop: dict, key: str) -> str | None:
    parts = prop.get(key) or []
    return "".join(p.get("plain_text", "") for p in parts) or None


def _select(prop: dict) -> str | None:
    sel = prop.get("select")
    return sel["name"] if sel else None


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
        status_name = p["Stato"]["status"]["name"]
        return Ticket(
            id=page["id"],
            title=_text(p["Titolo"], "title") or "",
            status=self._to_status[status_name],
            kind=_select(p["Tipo"]),
            area=_select(p["Area"]),
            priority=_select(p["Priorità"]),
            environment=_select(p["Ambiente"]),
            page_url=p["URL pagina"]["url"],
            reported_by=_text(p["Segnalato da"], "rich_text"),
            authorized=p["Autorizzato"]["checkbox"],
            attempts=int(p["Tentativi"]["number"] or 0),
            cost_usd=float(p["Costo (USD)"]["number"] or 0.0),
            model=_select(p.get("Modello") or {}),
            attachments=[f["name"] for f in p["Allegati"]["files"]],
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
        conditions: list[dict] = [{"property": "Stato", "status": {"equals": self._cfg.status_map[status]}}]
        if authorized_only:
            conditions.append({"property": "Autorizzato", "checkbox": {"equals": True}})
        r = await self._client.post(
            f"/data_sources/{self._cfg.data_source_id}/query", json={"filter": {"and": conditions}}
        )
        r.raise_for_status()
        tickets = [self._parse(page) for page in r.json()["results"]]
        for t in tickets:
            t.body = await self._body(t.id)
            t.comments = await self._comments(t.id, bot=False)
        return tickets

    async def fetch_ready(self) -> list[Ticket]:
        return await self.fetch_by_status(Status.NEW)

    async def _comments(self, ticket_id: str, *, bot: bool) -> list[str]:
        r = await self._client.get("/comments", params={"block_id": ticket_id, "page_size": 100})
        r.raise_for_status()
        return [
            _text(c, "rich_text") or ""
            for c in r.json()["results"]
            if ((c.get("created_by") or {}).get("type") == "bot") == bot
        ]

    async def bot_comments(self, ticket_id: str) -> list[str]:
        return await self._comments(ticket_id, bot=True)

    async def _patch(self, ticket_id: str, properties: dict) -> None:
        r = await self._client.patch(f"/pages/{ticket_id}", json={"properties": properties})
        r.raise_for_status()

    async def set_status(self, ticket_id: str, status: Status) -> None:
        await self._patch(ticket_id, {"Stato": {"status": {"name": self._cfg.status_map[status]}}})

    async def comment(self, ticket_id: str, text: str) -> None:
        r = await self._client.post(
            "/comments",
            json={"parent": {"page_id": ticket_id}, "rich_text": _rich(text)["rich_text"]},
        )
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
    ) -> None:
        props: dict = {}
        if risk is not None:
            props["Rischio"] = {"select": {"name": risk.value}}
        if pr_url is not None:
            props["PR"] = {"url": pr_url}
        if branch is not None:
            props["Branch"] = _rich(branch)
        if attempts is not None:
            props["Tentativi"] = {"number": attempts}
        if cost_usd is not None:
            props["Costo (USD)"] = {"number": cost_usd}
        if agent_note is not None:
            props["Note agente"] = _rich(agent_note)
        if verification is not None:
            props["Esito verifica"] = {"select": {"name": verification}}
        if props:
            await self._patch(ticket_id, props)

    async def verify(self) -> list[str]:
        r = await self._client.get(f"/data_sources/{self._cfg.data_source_id}")
        r.raise_for_status()
        return sorted(r.json()["properties"])

    async def aclose(self) -> None:
        await self._client.aclose()
