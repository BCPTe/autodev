from pathlib import Path

import httpx
import respx

from autodev.config import load_project
from autodev.models import Status
from autodev.trackers.notion import API, NotionTracker

ROOT = Path(__file__).parent.parent


def _page(authorized: bool = True) -> dict:
    def sel(name):
        return {"select": {"name": name}}

    return {
        "id": "page-1",
        "properties": {
            "Titolo": {"title": [{"plain_text": "Export PDF vuoto"}]},
            "Stato": {"status": {"name": "Nuovo"}},
            "Tipo": sel("Bug"),
            "Area": sel("Export PDF"),
            "Priorità": sel("Alta"),
            "Ambiente": sel("Staging"),
            "URL pagina": {"url": "https://staging.example.com/orders/1"},
            "Segnalato da": {"rich_text": [{"plain_text": "Mario"}]},
            "Autorizzato": {"checkbox": authorized},
            "Tentativi": {"number": None},
            "Costo (USD)": {"number": 0.25},
            "Allegati": {"files": [{"name": "shot.png"}]},
        },
    }


def test_project_config_loads():
    cfg = load_project(ROOT / "projects" / "demo.yaml")
    assert cfg.base_branch == "staging"
    assert cfg.tracker.status_map[Status.NEW] == "Nuovo"


@respx.mock
async def test_fetch_ready_parses_ticket_and_body():
    cfg = load_project(ROOT / "projects" / "demo.yaml")
    respx.post(f"{API}/data_sources/{cfg.tracker.data_source_id}/query").mock(
        return_value=httpx.Response(200, json={"results": [_page()]})
    )
    respx.get(f"{API}/blocks/page-1/children").mock(
        return_value=httpx.Response(
            200,
            json={
                "results": [
                    {"type": "paragraph", "paragraph": {"rich_text": [{"plain_text": "Il PDF esce vuoto"}]}}
                ]
            },
        )
    )
    respx.get(f"{API}/comments").mock(
        return_value=httpx.Response(
            200,
            json={
                "results": [
                    {"created_by": {"object": "user", "id": "b"}, "display_name": {"type": "integration", "resolved_name": "autodev"}, "rich_text": [{"plain_text": "Triage: needs_info"}]},
                    {"created_by": {"object": "user", "id": "p"}, "display_name": {"type": "user", "resolved_name": "Christian"}, "rich_text": [{"plain_text": "Solo la SCIA SUE"}]},
                ]
            },
        )
    )
    tracker = NotionTracker(cfg.tracker, token="x")
    tickets = await tracker.fetch_ready()
    await tracker.aclose()

    assert len(tickets) == 1
    t = tickets[0]
    assert (t.title, t.status, t.area, t.attempts) == ("Export PDF vuoto", Status.NEW, "Export PDF", 0)
    assert t.body == "Il PDF esce vuoto"
    assert t.attachments == ["shot.png"]
    assert t.comments == ["Solo la SCIA SUE"]
    assert t.cost_usd == 0.25


@respx.mock
async def test_bot_comments_are_recognised_by_display_name_and_returned_for_the_fix_agent():
    cfg = load_project(ROOT / "projects" / "demo.yaml")
    respx.get(f"{API}/comments").mock(
        return_value=httpx.Response(
            200,
            json={
                "results": [
                    {"created_by": {"object": "user", "id": "b"}, "display_name": {"type": "integration", "resolved_name": "autodev"},
                     "rich_text": [{"plain_text": "Triage: ready"}], "created_time": "2026-10-21T10:00:00Z"},
                    {"created_by": {"object": "user", "id": "p"}, "display_name": {"type": "user", "resolved_name": "Christian Gatto"},
                     "rich_text": [{"plain_text": "ok procedi"}], "created_time": "2026-10-21T10:05:00Z"},
                ]
            },
        )
    )
    tracker = NotionTracker(cfg.tracker, token="x")
    assert await tracker.bot_comments("page-1") == ["Triage: ready"]
    await tracker.aclose()


def test_tracker_column_names_can_be_overridden_per_project():
    cfg = load_project(ROOT / "projects" / "demo.yaml")
    assert cfg.tracker.prop("title") == "Titolo"
    cfg.tracker.properties = {"title": "Name"}
    assert cfg.tracker.prop("title") == "Name"
    assert cfg.tracker.prop("status") == "Stato"
