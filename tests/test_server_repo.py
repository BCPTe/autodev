import pytest
from fastapi.testclient import TestClient

from autodev import github
from autodev.db import Database
from autodev.models import Status, Ticket
from autodev.server.app import create_app
from tests.fixture_repo import make_project
from tests.test_engine import Tracker
from tests.test_repo_ops import agent_branch, git

PASSWORD = "una-password-lunga-1"


def pr(number, *, state="open", draft=False, verdict="passing", mergeable=True, branch="autodev/fix-a"):
    return {
        "number": number, "title": f"fix {number}", "url": f"https://github.com/o/r/pull/{number}", "branch": branch,
        "state": state, "draft": draft, "body": "", "updated_at": "2026-10-21T10:00:00Z", "author": "bot",
        "checks": {"verdict": verdict, "total": 1, "failed": 0, "pending": 0} if state == "open" else None, "mergeable": mergeable,
    }


@pytest.fixture
def env(tmp_path, monkeypatch):
    cfg = make_project(tmp_path)
    cfg.pr.slug = "o/r"
    git(cfg.local_path, "fetch", "-q")
    db = Database(tmp_path / "s.db")
    tracker = Tracker([Ticket(id="t1", title="Bug", status=Status.REVIEW, pr_url="https://github.com/o/r/pull/1", risk="Low")])
    app = create_app(cfg, "shop", db, tracker, static_dir=None)
    c = TestClient(app)
    c.post("/api/auth/setup", json={"password": PASSWORD, "code": app.state.auth.setup_code})
    state = {"prs": [pr(1)], "merged": [], "deleted": []}

    async def list_pulls(cfg, prefix, limit=30):
        return state["prs"]

    async def merge_pull(cfg, number, method="squash"):
        state["merged"].append((number, method))
        return "sha"

    async def delete_remote_branch(cfg, branch):
        state["deleted"].append(branch)
        return True

    monkeypatch.setattr(github, "list_pulls", list_pulls)
    monkeypatch.setattr(github, "merge_pull", merge_pull)
    monkeypatch.setattr(github, "delete_remote_branch", delete_remote_branch)
    return c, cfg, db, tracker, state, app


def test_prs_are_listed_with_their_ticket(env):
    c, *_ = env
    prs = c.get("/api/prs").json()["prs"]
    assert prs[0]["number"] == 1 and prs[0]["ticket"]["id"] == "t1" and prs[0]["ticket"]["risk"] == "Low"


def test_merge_needs_explicit_confirmation_and_closes_the_ticket(env):
    c, _, db, tracker, state, _ = env
    assert c.post("/api/prs/1/merge", json={}).status_code == 422
    assert state["merged"] == []
    assert c.post("/api/prs/1/merge", json={"confirm": True}).status_code == 200
    assert state["merged"] == [(1, "squash")] and state["deleted"] == ["autodev/fix-a"]
    assert tracker.tickets["t1"].status == Status.CLOSED
    assert db.one("SELECT action FROM actions WHERE action = 'merge'")


@pytest.mark.parametrize("change,code", [
    ({"state": "closed"}, 409), ({"draft": True}, 409), ({"verdict": "failing"}, 409),
    ({"verdict": "pending"}, 409), ({"mergeable": False}, 409),
])
def test_merge_is_refused_when_the_pull_request_is_not_ready(env, change, code):
    c, *_, state, _ = env
    state["prs"] = [pr(1, **change)]
    assert c.post("/api/prs/1/merge", json={"confirm": True}).status_code == code
    assert state["merged"] == []


def test_high_risk_changes_are_never_merged_from_the_dashboard(env):
    c, _, _, tracker, state, _ = env
    tracker.tickets["t1"].risk = "High"
    r = c.post("/api/prs/1/merge", json={"confirm": True})
    assert r.status_code == 403 and state["merged"] == []


def test_branch_checkout_and_cleanup_go_through_the_guards(env):
    c, cfg, db, *_ = env
    agent_branch(cfg, "autodev/done", "a = 1\n", merge=True)
    agent_branch(cfg, "autodev/open", "b = 2\n")
    assert c.post("/api/repo/checkout", json={"branch": "autodev/open"}).status_code == 200
    assert c.get("/api/repo").json()["branch"] == "autodev/open"
    assert c.post("/api/repo/checkout", json={"branch": "main"}).status_code == 200
    assert c.post("/api/repo/cleanup", json={"names": ["autodev/open"]}).status_code == 409
    done = c.post("/api/repo/cleanup", json={"remote": True}).json()
    assert done == {"deleted": ["autodev/done"], "remote_deleted": ["autodev/done"]}


def test_repo_changes_are_refused_while_an_agent_works(env):
    c, cfg, db, *_ = env
    db.execute("INSERT INTO runs(project, ticket_id, ticket_title, kind, status, started_at) VALUES('shop','x','x','fix','running',strftime('%s','now'))")
    assert c.post("/api/repo/checkout", json={"branch": "main"}).status_code == 409
    assert c.post("/api/repo/cleanup", json={}).status_code == 409
    assert c.post("/api/repo/checks", json={}).status_code == 409


async def test_checks_run_as_a_tracked_job(tmp_path):
    cfg = make_project(tmp_path)
    (__import__("pathlib").Path(cfg.local_path) / "tests" / "test_ok.py").write_text("def test_ok():\n    assert True\n")
    db = Database(tmp_path / "c.db")
    from autodev.engine import Engine

    engine = Engine(cfg, "shop", db, Tracker([]))
    await engine.start_checks()
    await engine.wait_idle()
    run = db.one("SELECT kind, status, outcome FROM runs")
    assert run == {"kind": "checks", "status": "done", "outcome": "passed"}
    assert "PASS  tests" in db.one("SELECT text FROM events WHERE type = 'result'")["text"]
