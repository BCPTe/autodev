import pytest
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
            "Title": {"title": [{"plain_text": "Export PDF vuoto"}]},
            "Status": {"status": {"name": "New"}},
            "Type": sel("Bug"),
            "Area": sel("Export PDF"),
            "Priority": sel("Alta"),
            "Environment": sel("Staging"),
            "Page URL": {"url": "https://staging.example.com/orders/1"},
            "Reported by": {"rich_text": [{"plain_text": "Mario"}]},
            "Authorized": {"checkbox": authorized},
            "Attempts": {"number": None},
            "Cost (USD)": {"number": 0.25},
            "Attachments": {"files": [{"name": "shot.png"}]},
        },
    }


def test_project_config_loads():
    cfg = load_project(ROOT / "projects" / "demo.yaml")
    assert cfg.base_branch == "staging"
    assert cfg.tracker.status_map[Status.NEW] == "New"


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
    assert cfg.tracker.prop("title") == "Title"
    cfg.tracker.properties = {"title": "Name"}
    assert cfg.tracker.prop("title") == "Name"
    assert cfg.tracker.prop("status") == "Status"


@respx.mock
async def test_comment_typed_in_the_dashboard_counts_as_human_for_the_agents():
    cfg = load_project(ROOT / "projects" / "demo.yaml")
    posted = respx.post(f"{API}/comments").mock(return_value=httpx.Response(200, json={}))
    respx.get(f"{API}/comments").mock(
        return_value=httpx.Response(
            200,
            json={"results": [
                {"display_name": {"type": "integration", "resolved_name": "autodev"}, "rich_text": [{"plain_text": "Triage: ready"}]},
                {"display_name": {"type": "integration", "resolved_name": "autodev"}, "rich_text": [{"plain_text": "[dashboard] Solo la SCIA SUE"}]},
            ]},
        )
    )
    tracker = NotionTracker(cfg.tracker, token="x")
    await tracker.comment("page-1", "Solo la SCIA SUE", as_human=True)
    assert b"[dashboard] Solo la SCIA SUE" in posted.calls.last.request.content
    assert await tracker.bot_comments("page-1") == ["Triage: ready"]
    assert await tracker._comments("page-1", bot=False) == ["Solo la SCIA SUE"]
    await tracker.aclose()


@respx.mock
async def test_authorized_and_model_are_written_to_their_columns():
    cfg = load_project(ROOT / "projects" / "demo.yaml")
    patch = respx.patch(f"{API}/pages/page-1").mock(return_value=httpx.Response(200, json={}))
    tracker = NotionTracker(cfg.tracker, token="x")
    await tracker.update("page-1", authorized=True, model="Opus")
    body = patch.calls.last.request.content
    assert b'"Authorized":{"checkbox":true}' in body.replace(b" ", b"")
    assert b'"Model":{"select":{"name":"Opus"}}' in body.replace(b" ", b"")
    await tracker.aclose()


@respx.mock
async def test_a_status_label_missing_from_the_project_file_is_an_error_not_an_empty_board():
    cfg = load_project(ROOT / "projects" / "demo.yaml")
    page = _page()
    page["properties"]["Status"] = {"status": {"name": "Nuovo"}}
    respx.post(f"{API}/data_sources/{cfg.tracker.data_source_id}/query").mock(
        return_value=httpx.Response(200, json={"results": [page], "has_more": False})
    )
    tracker = NotionTracker(cfg.tracker, token="x")
    with pytest.raises(RuntimeError, match="status_map"):
        await tracker.list_all()
    await tracker.aclose()
