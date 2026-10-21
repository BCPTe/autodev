import json
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from autodev.config import load_project
from autodev.db import Database
from autodev.models import Comment, Status, Ticket
from autodev.server.app import create_app
from autodev.server.auth import MAX_FAILURES

CFG = load_project(Path(__file__).parent.parent / "projects" / "demo.yaml")
PASSWORD = "una-password-lunga-1"


class FakeTracker:
    def __init__(self):
        self.calls = 0
        self.tickets = [
            Ticket(id="t1", title="Bug uno", status=Status.ANALYZED, area="Autofill", risk="Medio", url="https://n/t1", cost_usd=0.5),
            Ticket(id="t2", title="Bug due", status=Status.IN_PROGRESS, model="Auto"),
            Ticket(id="t3", title="Bug tre", status=Status.NEW),
        ]

    async def list_all(self):
        self.calls += 1
        return self.tickets

    async def set_status(self, ticket_id, status):
        next(t for t in self.tickets if t.id == ticket_id).status = status

    async def update(self, ticket_id, **kw):
        t = next(t for t in self.tickets if t.id == ticket_id)
        for k, v in kw.items():
            setattr(t, k, v)

    async def comment(self, ticket_id, text, *, as_human=False):
        self.posted = getattr(self, "posted", []) + [(ticket_id, text, as_human)]

    async def detail(self, ticket_id):
        t = next(t for t in self.tickets if t.id == ticket_id)
        t = t.model_copy(update={"body": "descrizione"})
        return t, [Comment(author="autodev", is_bot=True, text="Triage: ready"), Comment(author="Christian", text="ok")]


@pytest.fixture
def env(tmp_path):
    db = Database(tmp_path / "s.db")
    tracker = FakeTracker()
    app = create_app(CFG, "demo", db, tracker, static_dir=None)
    return TestClient(app), db, tracker, app


@pytest.fixture
def client(env):
    c, db, tracker, app = env
    c.post("/api/auth/setup", json={"password": PASSWORD, "code": app.state.auth.setup_code})
    return c


def seed_run(db, **kw):
    cols = dict(project="demo", ticket_id="t1", ticket_title="Bug uno", kind="triage", status="done", started_at=__import__("time").time(), cost_usd=0.3, model="claude-haiku-5-5", outcome="analyzed")
    cols.update(kw)
    run_id = db.execute(
        f"INSERT INTO runs({','.join(cols)}) VALUES({','.join('?' * len(cols))})", tuple(cols.values())
    )
    return run_id


# ---- security -------------------------------------------------------------------------------
def test_everything_but_auth_requires_a_session(env):
    c, *_ = env
    for path in ["/api/overview", "/api/tickets", "/api/tickets/t1", "/api/runs", "/api/runs/1", "/api/costs", "/api/repo", "/api/config", "/api/control"]:
        assert c.get(path).status_code == 401, path
    for method, path in [("put", "/api/control"), ("post", "/api/control/stop-all"), ("post", "/api/runs/1/cancel"), ("post", "/api/tickets/t1/start"), ("patch", "/api/tickets/t1"), ("post", "/api/tickets/t1/comment")]:
        assert getattr(c, method)(path, json={}).status_code == 401, path


def test_first_run_setup_needs_the_one_time_code_and_a_long_password(env):
    c, _, _, app = env
    assert c.get("/api/auth/state").json() == {"setup_required": True, "authenticated": False}
    assert c.post("/api/auth/setup", json={"password": PASSWORD, "code": "wrong"}).status_code == 403
    assert c.post("/api/auth/setup", json={"password": "corta", "code": app.state.auth.setup_code}).status_code == 422
    assert c.post("/api/auth/setup", json={"password": PASSWORD, "code": app.state.auth.setup_code}).status_code == 200
    assert c.get("/api/auth/state").json() == {"setup_required": False, "authenticated": True}
    assert "samesite=strict" in c.post("/api/auth/login", json={"password": PASSWORD}).headers["set-cookie"].lower()


def test_setup_cannot_be_repeated_to_take_over_the_dashboard(client, env):
    _, _, _, app = env
    assert client.post("/api/auth/setup", json={"password": "un-altra-password-1", "code": "x"}).status_code == 403


def test_the_password_is_stored_hashed_never_in_clear(client, env):
    _, db, *_ = env
    stored = db.get_setting("password_hash")
    assert stored.startswith("scrypt$") and PASSWORD not in stored


def test_login_logout_and_session_cookie_flags(env):
    c, _, _, app = env
    c.post("/api/auth/setup", json={"password": PASSWORD, "code": app.state.auth.setup_code})
    c.post("/api/auth/logout")
    assert c.get("/api/overview").status_code == 401
    assert c.post("/api/auth/login", json={"password": "sbagliata"}).status_code == 401
    r = c.post("/api/auth/login", json={"password": PASSWORD})
    cookie = r.headers["set-cookie"].lower()
    assert r.status_code == 200 and "httponly" in cookie and "samesite=strict" in cookie
    assert c.get("/api/overview").status_code == 200


def test_repeated_wrong_passwords_are_throttled_even_for_the_right_one(env):
    c, _, _, app = env
    c.post("/api/auth/setup", json={"password": PASSWORD, "code": app.state.auth.setup_code})
    c.post("/api/auth/logout")
    for _ in range(MAX_FAILURES):
        assert c.post("/api/auth/login", json={"password": "no"}).status_code == 401
    blocked = c.post("/api/auth/login", json={"password": PASSWORD})
    assert blocked.status_code == 429 and int(blocked.headers["retry-after"]) > 0


def test_foreign_host_headers_and_cross_site_posts_are_refused(client):
    assert client.get("/api/auth/state", headers={"host": "evil.example.com"}).status_code == 400
    assert client.get("/api/auth/state", headers={"host": "localhost:8765"}).status_code == 200
    assert client.get("/api/auth/state", headers={"host": "[::1]:8765"}).status_code == 200
    r = client.post("/api/auth/logout", headers={"origin": "https://evil.example.com"})
    assert r.status_code == 403


def test_responses_carry_security_headers(client):
    h = client.get("/api/auth/state").headers
    assert h["x-frame-options"] == "DENY" and h["x-content-type-options"] == "nosniff"
    assert "default-src 'self'" in h["content-security-policy"]


# ---- data -----------------------------------------------------------------------------------
def test_overview_counts_tickets_and_builds_the_inbox(client, env):
    _, db, *_ = env
    seed_run(db, status="running", kind="fix", cost_usd=0)
    seed_run(db, status="failed", error="boom")
    o = client.get("/api/overview").json()
    assert o["counts"] == {"analyzed": 1, "in_progress": 1, "new": 1}
    assert [i["ticket"]["title"] for i in o["inbox"]] == ["Bug uno"]
    assert len(o["running"]) == 1 and len(o["recent_problems"]) == 1
    assert o["daily_cap"] == CFG.limits.daily_budget_usd and o["ticket_cap"] == 6.0


def test_tickets_are_cached_briefly_and_refresh_bypasses_the_cache(client, env):
    _, _, tracker, _ = env
    client.get("/api/tickets"); client.get("/api/tickets")
    assert tracker.calls == 1
    client.get("/api/tickets?refresh=true")
    assert tracker.calls == 2


def test_ticket_list_includes_the_last_run_of_each_ticket(client, env):
    _, db, *_ = env
    seed_run(db, ticket_id="t1", kind="triage")
    seed_run(db, ticket_id="t1", kind="fix", outcome="review")
    t1 = next(t for t in client.get("/api/tickets").json()["tickets"] if t["id"] == "t1")
    assert t1["last_run"]["kind"] == "fix" and "body" not in t1


def test_ticket_detail_has_comments_and_the_runs_on_it(client, env):
    _, db, *_ = env
    seed_run(db, ticket_id="t1")
    d = client.get("/api/tickets/t1").json()
    assert d["ticket"]["body"] == "descrizione" and [c["is_bot"] for c in d["comments"]] == [True, False]
    assert len(d["runs"]) == 1


def test_run_detail_returns_its_events_in_order(client, env):
    _, db, *_ = env
    rid = seed_run(db)
    for i, (t, text) in enumerate([("started", "via"), ("log", "legge x"), ("finished", "analyzed")]):
        db.execute("INSERT INTO events(run_id, ts, type, text, data) VALUES(?,?,?,?,?)", (rid, i, t, text, json.dumps({"cost_usd": 1}) if t == "finished" else None))
    d = client.get(f"/api/runs/{rid}").json()
    assert [e["type"] for e in d["events"]] == ["started", "log", "finished"]
    assert d["events"][2]["data"] == {"cost_usd": 1}
    assert client.get("/api/runs/999").status_code == 404


def test_the_event_stream_replays_history_then_ends_when_the_run_is_over(client, env):
    _, db, *_ = env
    rid = seed_run(db, status="done")
    for t, text in [("started", "via"), ("log", "legge x")]:
        db.execute("INSERT INTO events(run_id, ts, type, text) VALUES(?,?,?,?)", (rid, 1, t, text))
    with client.stream("GET", f"/api/runs/{rid}/stream") as r:
        body = "".join(r.iter_text())
    assert r.headers["content-type"].startswith("text/event-stream")
    assert body.count("event: event") == 2 and "legge x" in body and "event: end" in body


def test_the_event_stream_resumes_after_last_event_id(client, env):
    _, db, *_ = env
    rid = seed_run(db, status="done")
    ids = [db.execute("INSERT INTO events(run_id, ts, type, text) VALUES(?,?,?,?)", (rid, 1, "log", f"riga {i}")) for i in range(3)]
    with client.stream("GET", f"/api/runs/{rid}/stream", headers={"last-event-id": str(ids[0])}) as r:
        body = "".join(r.iter_text())
    assert "riga 0" not in body and "riga 1" in body and "riga 2" in body


def test_costs_aggregate_by_day_model_kind_and_ticket(client, env):
    _, db, *_ = env
    seed_run(db, cost_usd=0.5, model="claude-haiku-5-5", kind="triage")
    seed_run(db, cost_usd=2.0, model="claude-sonnet-5-5", kind="fix", ticket_id="t2", ticket_title="Bug due")
    c = client.get("/api/costs").json()
    assert c["today"] == pytest.approx(2.5) and c["total"] == pytest.approx(2.5)
    assert {m["model"]: m["cost"] for m in c["by_model"]} == {"claude-haiku-5-5": 0.5, "claude-sonnet-5-5": 2.0}
    assert c["by_ticket"][0]["title"] == "Bug due" and c["by_day"][-1]["runs"] == 2


def test_the_daily_cap_edited_in_settings_is_what_the_overview_shows(client, env):
    _, db, *_ = env
    db.set_setting("daily_budget_usd", "7.5")
    assert client.get("/api/overview").json()["daily_cap"] == 7.5


def test_config_is_exposed_without_secrets(client):
    c = client.get("/api/config").json()
    assert c["workspace_mode"] == "inplace" and c["model_choices"]["Opus"] == "claude-opus-5-5"
    assert "token" not in json.dumps(c).lower()


def test_repo_state_reads_the_checkout_without_changing_it(tmp_path):
    from tests.fixture_repo import make_project

    cfg = make_project(tmp_path)
    local = Path(cfg.local_path)
    subprocess.run(["git", "checkout", "-q", "-b", "autodev/x-1"], cwd=local, check=True)
    (local / "shop" / "new.py").write_text("X = 1\n")
    subprocess.run(["git", "add", "-A"], cwd=local, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "work"], cwd=local, check=True)
    (local / "notes.txt").write_text("wip\n")
    db = Database(tmp_path / "r.db")
    c = TestClient(create_app(cfg, "x", db, FakeTracker(), static_dir=None))
    c.post("/api/auth/setup", json={"password": PASSWORD, "code": c.app.state.auth.setup_code})
    r = c.get("/api/repo").json()
    assert r["branch"] == "autodev/x-1" and r["on_agent_branch"] and not r["clean"]
    assert any("notes.txt" in line for line in r["dirty"]) and r["ahead"] == 1
    assert r["branches"][0]["name"] == "autodev/x-1" and r["branches"][0]["ahead"] == 1 and not r["branches"][0]["merged"]
    assert (local / "notes.txt").exists()


def test_spa_fallback_serves_index_and_keeps_unknown_api_paths_404(tmp_path):
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<html>app</html>")
    (dist / "assets" / "a.js").write_text("console.log(1)")
    db = Database(tmp_path / "d.db")
    c = TestClient(create_app(CFG, "demo", db, FakeTracker(), static_dir=dist))
    assert c.get("/tickets/abc").text == "<html>app</html>"
    assert c.get("/assets/a.js").text == "console.log(1)"
    assert c.get("/api/nope").status_code in (401, 404)
    secret = tmp_path / "secret.txt"
    secret.write_text("TOP-SECRET")
    for attempt in ("/../secret.txt", "/%2e%2e/secret.txt", "/assets/../../secret.txt", "/..%2fsecret.txt"):
        assert "TOP-SECRET" not in c.get(attempt).text, attempt


# ---- controls -------------------------------------------------------------------------------
def test_mode_my_turn_and_daily_cap_can_be_changed_and_are_audited(client, env):
    _, db, *_ = env
    assert client.get("/api/control").json()["mode"] == "manual"
    state = client.put("/api/control", json={"mode": "supervised", "my_turn": True, "daily_budget_usd": 7.5}).json()
    assert (state["mode"], state["my_turn"], state["daily_cap"]) == ("supervised", True, 7.5)
    assert client.get("/api/overview").json()["control"]["mode"] == "supervised"
    assert {r["action"] for r in db.query("SELECT action FROM actions")} == {"mode", "my_turn", "daily_cap"}
    assert client.put("/api/control", json={"mode": "turbo"}).status_code == 422
    assert client.put("/api/control", json={"daily_budget_usd": 0}).status_code == 422


def test_ticket_fields_are_edited_in_the_tracker(client, env):
    _, db, tracker, _ = env
    r = client.patch("/api/tickets/t1", json={"status": "in_progress", "authorized": True, "model": "Opus", "attempts": 0})
    assert r.status_code == 200, r.text
    t = tracker.tickets[0]
    assert (t.status, t.authorized, t.model, t.attempts) == (Status.IN_PROGRESS, True, "Opus", 0)
    assert db.one("SELECT actor, action, ticket_id FROM actions") == {"actor": "user", "action": "edit", "ticket_id": "t1"}
    detail = client.get("/api/tickets/t1").json()
    assert detail["actions"][0]["action"] == "edit"


def test_invalid_ticket_edits_are_rejected_before_reaching_the_tracker(client, env):
    _, _, tracker, _ = env
    assert client.patch("/api/tickets/t1", json={}).status_code == 422
    assert client.patch("/api/tickets/t1", json={"model": "GPT"}).status_code == 422
    assert client.patch("/api/tickets/t1", json={"attempts": -1}).status_code == 422
    assert client.patch("/api/tickets/t1", json={"status": "bogus"}).status_code == 422
    assert tracker.tickets[0].model is None


def test_comment_is_posted_as_a_person_and_empty_ones_are_refused(client, env):
    _, _, tracker, _ = env
    assert client.post("/api/tickets/t1/comment", json={"text": "  "}).status_code == 422
    assert client.post("/api/tickets/t1/comment", json={"text": "  Solo la SCIA SUE  "}).status_code == 200
    assert tracker.posted == [("t1", "Solo la SCIA SUE", True)]


def test_start_is_refused_with_the_reason_when_the_mode_is_paused(client):
    client.put("/api/control", json={"mode": "paused"})
    r = client.post("/api/tickets/t3/start", json={"kind": "triage"})
    assert r.status_code == 409 and "pausa" in r.json()["detail"]
    assert client.post("/api/tickets/t3/start", json={"kind": "nope"}).status_code == 422


def test_cancel_marks_a_running_run_and_refuses_finished_ones(client, env):
    _, db, *_ = env
    running = seed_run(db, status="running", finished_at=None)
    done = seed_run(db)
    assert client.post(f"/api/runs/{running}/cancel", json={}).status_code == 200
    assert db.one("SELECT cancel_requested FROM runs WHERE id = ?", (running,))["cancel_requested"] == 1
    assert client.post(f"/api/runs/{done}/cancel", json={}).status_code == 409
    assert client.post("/api/runs/999/cancel", json={}).status_code == 404
    assert client.post("/api/control/stop-all", json={}).json() == {"stopped": 1}


# ---- interactive agents ---------------------------------------------------------------------
def test_talking_to_a_run_that_is_not_live_is_refused(client, env):
    _, db, *_ = env
    run_id = seed_run(db, status="running", finished_at=None)
    assert client.post(f"/api/runs/{run_id}/message", json={"text": "ciao"}).status_code == 409
    assert client.post(f"/api/runs/{run_id}/pause", json={}).status_code == 409
    assert client.get(f"/api/runs/{run_id}").json()["interactive"]["live"] is False


def test_pending_approvals_are_listed_and_decided_through_the_live_control(client, env):
    import asyncio

    from autodev.control import RunControl

    _, db, _, app = env
    run_id = seed_run(db, status="running", finished_at=None)
    control = RunControl(db, lambda: "manual")
    control.run_id = run_id
    app.state.engine.controls[run_id] = control

    async def scenario():
        waiting = asyncio.ensure_future(control.ask("permission", "esegue docker ps", {"tool": "Bash"}))
        await asyncio.sleep(0.05)
        return waiting

    loop = asyncio.new_event_loop()
    waiting = loop.run_until_complete(scenario())
    listed = client.get("/api/approvals").json()["approvals"]
    assert [(a["title"], a["ticket_id"]) for a in listed] == [("esegue docker ps", "t1")]
    assert client.get("/api/overview").json()["approvals"][0]["id"] == listed[0]["id"]
    assert client.get(f"/api/runs/{run_id}").json()["interactive"]["state"] == "approval"
    assert client.post(f"/api/approvals/{listed[0]['id']}", json={"decision": "maybe"}).status_code == 422
    # the future lives on the test loop: decide on it through the API, then let the loop deliver it
    assert client.post(f"/api/approvals/{listed[0]['id']}", json={"decision": "allow", "note": "ok"}).status_code == 200
    assert loop.run_until_complete(waiting) == (True, "ok", False)
    assert client.post(f"/api/approvals/{listed[0]['id']}", json={"decision": "deny"}).status_code == 409
    assert client.get("/api/approvals").json()["approvals"] == []
    loop.close()
