import httpx
import pytest
import respx

from autodev import attachments
from autodev.models import Status, Ticket
from autodev.trackers.notion import NotionTracker, _file_ref
from autodev.config import TrackerConfig


@pytest.fixture(autouse=True)
def root(tmp_path, monkeypatch):
    monkeypatch.setattr(attachments, "ROOT", tmp_path / "attachments")


class Tracker:
    def __init__(self, refs):
        self.refs = refs

    async def attachments(self, ticket_id):
        return self.refs


def ticket():
    return Ticket(id="abc-123", title="Bug", status=Status.NEW, attachments=["shot.png"])


def test_names_are_plain_and_unique():
    taken: set[str] = set()
    assert attachments.safe_name("../../etc/passwd", taken) == "passwd"
    assert attachments.safe_name("shot.png", taken) == "shot.png"
    assert attachments.safe_name("shot.png", taken) == "shot-2.png"
    assert attachments.safe_name("???", taken) == "___"


@pytest.mark.asyncio
@respx.mock
async def test_files_are_saved_and_described_to_the_agent():
    respx.get("https://s3.example/shot.png").mock(return_value=httpx.Response(200, content=b"\x89PNG" + b"0" * 2048))
    t = ticket()
    await attachments.attach(Tracker([
        {"name": "shot.png", "url": "https://s3.example/shot.png", "external": False},
        {"name": "log", "url": "https://elsewhere.example/log", "external": True},
    ]), t, "shop")
    assert [f["name"] for f in t.files] == ["shot.png"]
    saved = attachments.folder("shop", t.id) / "shot.png"
    assert saved.stat().st_size == 2052 and t.files[0]["path"] == str(saved) and t.files[0]["type"] == "image/png"
    assert any("a link, not downloaded" in n for n in t.file_notes)
    text = attachments.prompt_section(t)
    assert str(saved) in text and "copy it into the repository" in text
    assert attachments.folders(t) == [str(saved.parent)]


@pytest.mark.asyncio
@respx.mock
async def test_too_big_files_and_failures_are_reported_not_fatal():
    respx.get("https://s3.example/big").mock(return_value=httpx.Response(200, content=b"0" * 100, headers={"content-length": str(attachments.MAX_FILE_BYTES + 1)}))
    respx.get("https://s3.example/gone").mock(return_value=httpx.Response(403))
    t = ticket()
    await attachments.attach(Tracker([
        {"name": "big.bin", "url": "https://s3.example/big", "external": False},
        {"name": "gone.txt", "url": "https://s3.example/gone", "external": False},
    ]), t, "shop")
    assert t.files == [] and len(t.file_notes) == 2
    assert not list(attachments.folder("shop", t.id).iterdir())


@pytest.mark.asyncio
async def test_a_tracker_without_files_or_with_an_error_changes_nothing():
    t = ticket()
    await attachments.attach(object(), t, "shop")
    assert t.files == [] and t.file_notes == [] and attachments.prompt_section(t) == "Attachments: shot.png"

    class Broken:
        async def attachments(self, _):
            raise RuntimeError("boom")

    await attachments.attach(Broken(), t, "shop")
    assert "could not be read" in t.file_notes[0]


def test_notion_file_objects_become_references():
    hosted = {"type": "file", "name": "a.png", "file": {"url": "https://s3/a.png"}}
    assert _file_ref("a.png", hosted) == {"name": "a.png", "url": "https://s3/a.png", "external": False}
    link = {"type": "external", "external": {"url": "https://x.example/dir/doc.pdf"}}
    assert _file_ref("", link) == {"name": "doc.pdf", "url": "https://x.example/dir/doc.pdf", "external": True}
    assert _file_ref("n", {"type": "file", "file": {}}) is None


@pytest.mark.asyncio
@respx.mock
async def test_the_notion_tracker_reads_the_column_and_the_body_blocks():
    cfg = TrackerConfig(type="notion", database_id="d", data_source_id="s", status_map={s: s.value for s in Status})
    respx.get("https://api.notion.com/v1/pages/t1").mock(return_value=httpx.Response(200, json={"properties": {"Attachments": {"files": [
        {"type": "file", "name": "col.png", "file": {"url": "https://s3/col.png"}}]}}}))
    respx.get("https://api.notion.com/v1/blocks/t1/children").mock(return_value=httpx.Response(200, json={"results": [
        {"type": "paragraph", "paragraph": {"rich_text": []}},
        {"type": "image", "image": {"type": "file", "file": {"url": "https://s3/body.png?sig=1"}}},
        {"type": "pdf", "pdf": {"type": "external", "external": {"url": "https://x.example/spec.pdf"}}},
    ]}))
    tracker = NotionTracker(cfg, "tok")
    refs = await tracker.attachments("t1")
    await tracker.aclose()
    assert [(r["name"], r["external"]) for r in refs] == [("col.png", False), ("body.png", False), ("spec.pdf", True)]


# ---- what the dashboard shows -----------------------------------------------------------------
from tests.test_server import client, env  # noqa: E402,F401


@respx.mock
def test_the_dashboard_lists_and_serves_a_tickets_files(client, env):
    c, db, tracker, app = env
    refs = [
        {"name": "shot.png", "url": "https://s3.example/shot.png", "external": False},
        {"name": "page.html", "url": "https://s3.example/page.html", "external": False},
        {"name": "spec", "url": "https://x.example/spec", "external": True},
    ]

    async def listing(_id):
        return refs

    tracker.attachments = listing
    respx.get("https://s3.example/shot.png").mock(return_value=httpx.Response(200, content=b"\x89PNG-data"))
    respx.get("https://s3.example/page.html").mock(return_value=httpx.Response(200, content=b"<script>alert(1)</script>"))
    out = c.get("/api/tickets/t1/attachments").json()["attachments"]
    assert [(a["name"], a["inline"], a["external"]) for a in out] == [("shot.png", True, False), ("page.html", False, False), ("spec", False, True)]
    assert out[2]["url"] == "https://x.example/spec" and out[0]["url"] is None

    png = c.get("/api/tickets/t1/attachments/shot.png")
    assert png.status_code == 200 and png.content == b"\x89PNG-data" and png.headers["content-disposition"].startswith("inline")
    page = c.get("/api/tickets/t1/attachments/page.html")
    assert page.headers["content-disposition"].startswith("attachment")  # uploaded HTML is never rendered by the dashboard
    assert c.get("/api/tickets/t1/attachments/nope.png").status_code == 404
    assert c.get("/api/tickets/t1/attachments/..%2F..%2Fetc%2Fpasswd").status_code == 404


def test_files_need_a_session(env):
    c, *_ = env
    assert c.get("/api/tickets/t1/attachments").status_code == 401
    assert c.get("/api/tickets/t1/attachments/a.png").status_code == 401
