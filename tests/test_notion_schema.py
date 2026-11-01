import json

import httpx
import pytest
import respx

from autodev.config import DEFAULT_PROPERTIES
from autodev.trackers import notion_schema as ns

PAGE = "0123456789abcdef0123456789abcdef"


def mock_views(ds_id: str, existing: tuple[str, ...] = ("Default view",)) -> dict:
    """The Notion endpoints `arrange_views` talks to; returns what was written to them."""
    names = {f"v{i}": n for i, n in enumerate(existing)}
    seen = {"patched": [], "created": [], "deleted": []}
    props = {n: {"id": f"id-{n}"} for n in ns.schema()}
    respx.get(f"https://api.notion.com/v1/data_sources/{ds_id}").mock(return_value=httpx.Response(200, json={"properties": props, "parent": {"type": "database_id", "database_id": "db1"}}))
    respx.get("https://api.notion.com/v1/views").mock(return_value=httpx.Response(200, json={"results": [{"id": i} for i in names]}))
    for i, n in names.items():
        respx.get(f"https://api.notion.com/v1/views/{i}").mock(return_value=httpx.Response(200, json={"name": n}))
        respx.patch(f"https://api.notion.com/v1/views/{i}").mock(side_effect=lambda req: (seen["patched"].append(json.loads(req.content)), httpx.Response(200, json={}))[1])
        respx.delete(f"https://api.notion.com/v1/views/{i}").mock(side_effect=lambda req, i=i: (seen["deleted"].append(names[i]), httpx.Response(200, json={}))[1])
    respx.post("https://api.notion.com/v1/views").mock(side_effect=lambda req: (seen["created"].append(json.loads(req.content)), httpx.Response(200, json={}))[1])
    return seen


def test_the_schema_has_every_column_the_code_reads_with_the_right_types():
    s = ns.schema(areas=["Web"], models=["Haiku", "Sonnet"])
    assert set(s) == set(ns.column_names().values())
    assert "title" in s[DEFAULT_PROPERTIES["title"]]
    assert "status" in s[DEFAULT_PROPERTIES["status"]]
    assert [o["name"] for o in s["Area"]["select"]["options"]] == ["Web"]
    assert all(o["color"] for o in s["autodev · Risk"]["select"]["options"])
    assert all(0 < len(c["description"]) <= 280 for c in s.values())
    assert [o["name"] for o in s["Model"]["select"]["options"]] == ["Auto", "Haiku", "Sonnet"]
    labels = [o["name"] for o in s["Status"]["status"]["options"]]
    assert labels == list(ns.status_map().values())


@pytest.mark.asyncio
@respx.mock
async def test_create_database_sends_the_schema_and_returns_both_ids():
    route = respx.post("https://api.notion.com/v1/databases").mock(return_value=httpx.Response(200, json={
        "id": "aaaaaaaa-0000-0000-0000-000000000001", "url": "https://notion.so/x",
        "data_sources": [{"id": "bbbbbbbb-0000-0000-0000-000000000002", "name": "t"}],
    }))
    views = mock_views("bbbbbbbb-0000-0000-0000-000000000002")
    out = await ns.create_database("tok", PAGE, "shop tickets")
    sent = json.loads(route.calls[0].request.content)
    assert "fill in the columns" in sent["description"][0]["text"]["content"]
    assert views["patched"], "the default view is renamed and narrowed to the columns a person fills in"
    assert "autodev · …" in sent["description"][0]["text"]["content"]
    assert sent["parent"] == {"type": "page_id", "page_id": PAGE}
    assert set(sent["initial_data_source"]["properties"]) == set(ns.column_names().values())
    assert route.calls[0].request.headers["Notion-Version"] == "2025-09-03"
    assert out == {"database_id": "aaaaaaaa000000000000000000000001", "data_source_id": "bbbbbbbb000000000000000000000002", "url": "https://notion.so/x"}


@pytest.mark.asyncio
@respx.mock
async def test_an_existing_database_gets_only_the_missing_columns():
    respx.get("https://api.notion.com/v1/data_sources/ds1").mock(return_value=httpx.Response(200, json={"properties": {"Title": {}, "Status": {}, "autodev · Risk": {}}}))
    patch = respx.patch("https://api.notion.com/v1/data_sources/ds1").mock(return_value=httpx.Response(200, json={}))
    missing = await ns.missing_properties("tok", "ds1")
    assert "Title" not in missing and "autodev · PR" in missing
    await ns.add_properties("tok", "ds1", missing)
    assert set(json.loads(patch.calls[0].request.content)["properties"]) == set(missing)


@pytest.mark.asyncio
@respx.mock
async def test_refresh_adds_descriptions_and_colors_but_never_replaces_the_users_options():
    respx.get("https://api.notion.com/v1/data_sources/ds1").mock(return_value=httpx.Response(200, json={"properties": {"Title": {}, "Status": {}, "autodev · Risk": {}, "Area": {}, "Gone": {}}}))
    patch = respx.patch("https://api.notion.com/v1/data_sources/ds1").mock(return_value=httpx.Response(200, json={}))
    await ns.refresh_properties("tok", "ds1")
    sent = json.loads(patch.calls[0].request.content)["properties"]
    assert set(sent) == {"Title", "Status", "autodev · Risk", "Area"}
    assert sent["autodev · Risk"]["select"]["options"][0]["color"] and sent["autodev · Risk"]["description"]
    assert sent["Status"]["status"] == {} and sent["Status"]["description"]   # its options are the user's workflow: not touched
    assert sent["Area"]["select"] == {} and sent["Area"]["description"]       # the user's own areas stay as they are


@pytest.mark.asyncio
@respx.mock
async def test_one_view_with_only_the_columns_a_person_fills_in():
    seen = mock_views("ds1")
    await ns.arrange_views("tok", "ds1")
    renamed, = seen["patched"]
    assert renamed["name"] == "Tickets" and seen["created"] == [] and seen["deleted"] == []
    visible = {p["property_id"] for p in renamed["configuration"]["properties"] if p["visible"]}
    assert visible == {f"id-{n}" for n in ns.user_columns()}
    assert not any(name in visible for name in ("id-autodev · Risk", "id-autodev · Cost (USD)", "id-autodev · Branch"))


@pytest.mark.asyncio
@respx.mock
async def test_arranging_the_views_twice_does_not_duplicate_and_drops_the_old_extra_view():
    seen = mock_views("ds1", existing=(ns.TICKETS_VIEW, ns.LEGACY_VIEW))
    await ns.arrange_views("tok", "ds1")
    assert seen["created"] == [] and seen["deleted"] == [ns.LEGACY_VIEW] and len(seen["patched"]) == 1


@pytest.mark.asyncio
@respx.mock
async def test_a_database_without_any_view_gets_one():
    seen = mock_views("ds1", existing=())
    await ns.arrange_views("tok", "ds1")
    assert [v["name"] for v in seen["created"]] == ["Tickets"] and seen["patched"] == []


@pytest.mark.asyncio
@respx.mock
async def test_old_databases_get_the_prefixed_names_on_the_columns_autodev_owns():
    respx.get("https://api.notion.com/v1/data_sources/ds1").mock(return_value=httpx.Response(200, json={"properties": {"Title": {}, "Risk": {}, "Branch": {}, "autodev · PR": {}, "PR": {}}}))
    patch = respx.patch("https://api.notion.com/v1/data_sources/ds1").mock(return_value=httpx.Response(200, json={}))
    renamed = await ns.rename_legacy("tok", "ds1")
    assert renamed == ["autodev · Branch", "autodev · Risk"]       # PR already has its new name: left alone
    assert json.loads(patch.calls[0].request.content)["properties"] == {"Risk": {"name": "autodev · Risk"}, "Branch": {"name": "autodev · Branch"}}


def test_the_project_file_maps_the_renamed_columns():
    from autodev import onboarding
    from autodev.config import ProjectConfig

    cfg = ProjectConfig.model_validate(onboarding.project_dict(
        name="x", repo="r", base_branch="main", local_path="/p", database_id="d", data_source_id="s"))
    assert cfg.tracker.prop("risk") == "autodev · Risk" and cfg.tracker.prop("title") == "Title"
    assert set(ns.column_names().values()) >= {cfg.tracker.prop(k) for k in ns.BOT_KEYS}
