import time
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from autodev import engine as engine_mod
from autodev import knowledge
from autodev.agents import fix as fix_agent
from autodev.agents import learn, triage
from autodev.agents.learn import LearnResult, Proposal
from autodev.config import load_project
from autodev.db import Database
from autodev.engine import Engine
from autodev.jobs import RunSummary, run_tracked
from autodev.knowledge import Entry
from autodev.models import Comment, Status, Ticket
from autodev.server.app import create_app
from tests.test_engine import Tracker as EngineTracker
from tests.test_server import PASSWORD, FakeTracker, seed_run

BASE = load_project(Path(__file__).parent.parent / "projects" / "demo.yaml")


@pytest.fixture
def cfg(tmp_path):
    c = BASE.model_copy(deep=True)
    c.knowledge_path = str(tmp_path / "demo.knowledge.md")
    c.local_path = str(tmp_path / "checkout")
    (tmp_path / "checkout" / "apps" / "backend").mkdir(parents=True)
    (tmp_path / "checkout" / "apps" / "backend" / "export.py").write_text("")
    return c


def ticket(**kw):
    kw.setdefault("area", "Export PDF")
    return Ticket(id="t1", title="The download button does nothing", status=Status.CLOSED, body="x" * 60, **kw)


def entry(text, category="where", **kw):
    return Entry(id=kw.pop("id", knowledge.new_id()), category=category, text=text, **kw)


# ---- the file ---------------------------------------------------------------------------------
def test_the_file_round_trips_and_hand_written_bullets_are_entries():
    text = """# Playbook

intro

## where
- Export lives in export.py. <!-- {"id":"k1","source":"t9","title":"a --> b","date":"2026-10-01","area":"Export PDF","paths":["a/export.py"]} -->
- written by hand

## gotcha
- Watch the order.

## unknown
- ignored
"""
    preamble, entries = knowledge.parse(text)
    assert preamble.endswith("intro")
    assert [(e.category, e.text) for e in entries] == [("where", "Export lives in export.py."), ("where", "written by hand"), ("gotcha", "Watch the order.")]
    first = entries[0]
    assert (first.id, first.source_id, first.source_title, first.area, first.paths) == ("k1", "t9", "a --> b", "Export PDF", ["a/export.py"])
    assert entries[1].id.startswith("k") and entries[1].id == knowledge.parse(text)[1][1].id  # stable id for hand-written bullets
    again = knowledge.parse(knowledge.render(preamble, entries))
    assert again == (preamble, entries)


def test_adding_and_deleting_entries_rewrites_the_file(cfg):
    added = knowledge.add_entry(cfg, entry("Use export.py", area="Export PDF", paths=["apps/backend/export.py"]))
    knowledge.add_entry(cfg, entry("Run make up first", "command"))
    _, entries = knowledge.load(cfg)
    assert [e.text for e in entries] == ["Use export.py", "Run make up first"] and entries[0].date
    assert knowledge.delete_entry(cfg, added.id) and not knowledge.delete_entry(cfg, added.id)
    assert [e.text for e in knowledge.load(cfg)[1]] == ["Run make up first"]


def test_entries_with_secrets_or_a_bad_category_are_refused(cfg):
    with pytest.raises(ValueError):
        knowledge.add_entry(cfg, entry("the api_key = abcd1234efgh is used"))
    with pytest.raises(ValueError):
        knowledge.add_entry(cfg, entry("fine", category="rumour"))


# ---- selection and the size cap ---------------------------------------------------------------
def test_selection_prefers_paths_then_area_then_recent_and_respects_the_cap():
    entries = [
        entry("old other", id="a", date="2026-01-01", area="Billing"),
        entry("new other", id="b", date="2026-09-01", area="Billing"),
        entry("area match", id="c", date="2026-02-01", area="Export PDF"),
        entry("path match", id="d", date="2026-01-01", paths=["apps/backend/"]),
    ]
    assert [e.id for e in knowledge.select(entries, "export pdf", ["apps/backend/export.py"], 6000)] == ["d", "c", "b", "a"]
    one_line = len(entries[3].prompt_line()) + 1
    assert [e.id for e in knowledge.select(entries, "Export PDF", ["apps/backend/export.py"], one_line)] == ["d"]
    assert knowledge.select(entries, None, [], 5) == []


def test_playbook_text_is_capped_and_disabled_when_off(cfg):
    for i in range(30):
        knowledge.add_entry(cfg, entry(f"Fact number {i} " + "x" * 80))
    cfg.knowledge.max_chars = 500
    pb = knowledge.playbook_for(cfg, ticket())
    assert 0 < len(pb.text) <= 500 and len(pb.ids) == len(pb.text.splitlines())
    cfg.knowledge.enabled = False
    assert knowledge.playbook_for(cfg, ticket()) == knowledge.Playbook() and knowledge.section(knowledge.Playbook()) == ""


def test_paths_mentioned_in_the_ticket_select_entries(cfg):
    knowledge.add_entry(cfg, entry("about export", id="kx", paths=["apps/backend/export.py"]))
    for i in range(3):
        knowledge.add_entry(cfg, entry(f"filler {i} " + "y" * 200, id=f"f{i}", date="2026-12-01"))
    cfg.knowledge.max_chars = 120
    t = ticket(area=None).model_copy(update={"body": "see apps/backend/export.py line 4"})
    assert knowledge.playbook_for(cfg, t).ids == ["kx"]


# ---- injection into the prompts ---------------------------------------------------------------
class FakeSession:
    def __init__(self, output):
        self.output, self.options, self.prompt = output, None, None

    async def __call__(self, prompt, options, on_message, stage="agent"):
        self.prompt, self.options = prompt, options
        return SimpleNamespace(is_error=False, structured_output=self.output, total_cost_usd=0.1, num_turns=3, subtype="", errors=None, result="")


async def test_triage_receives_the_playbook_and_cites_only_injected_entries(cfg, monkeypatch):
    knowledge.add_entry(cfg, entry("Export lives in export.py", id="k1", area="Export PDF"))
    session = FakeSession({"verdict": "ready", "confidence": "high", "risk": "Low", "analysis": "a", "playbook_cited": ["k1", "k404"]})
    monkeypatch.setattr(triage, "run_session", session)
    result, info = await triage._run(cfg, ticket(), "claude-haiku-5-5")
    prompt = session.options.system_prompt
    assert "# Project playbook" in prompt and "- [k1] (where) Export lives in export.py" in prompt
    assert "Check it BEFORE you ask a question" in prompt and "UNTRUSTED" in prompt
    assert (info.injected, info.cited, result.playbook_cited) == (["k1"], ["k1"], ["k1"])
    assert "Export lives in export.py" not in session.prompt


async def test_triage_without_a_playbook_has_no_section(cfg, monkeypatch):
    session = FakeSession({"verdict": "ready", "confidence": "high", "risk": "Low", "analysis": "a"})
    monkeypatch.setattr(triage, "run_session", session)
    _, info = await triage._run(cfg, ticket(), "claude-haiku-5-5")
    assert "# Project playbook" not in session.options.system_prompt and info.injected == []


def test_the_triage_comment_names_the_entries_it_used():
    from autodev.pipeline import format_comment

    r = triage.TriageResult(verdict="ready", confidence="high", risk="Low", analysis="a", playbook_cited=["k1"])
    assert "Playbook entries used: k1" in format_comment(r, "Low", [])


async def test_fix_agent_system_prompt_carries_the_playbook(cfg, tmp_path, monkeypatch):
    knowledge.add_entry(cfg, entry("Run backend tests with make test", "command", id="k2"))
    pb = knowledge.playbook_for(cfg, ticket())
    ws = SimpleNamespace(path=tmp_path, history=lambda: "")
    assert "- [k2] (command) Run backend tests with make test" in fix_agent.system_prompt(ws, playbook=pb)
    assert "# Project playbook" not in fix_agent.system_prompt(ws)
    session = FakeSession({"outcome": "fixed", "summary": "s"})
    monkeypatch.setattr(fix_agent, "run_session", session)
    await fix_agent.run_fix(cfg, ticket(), ws, [], playbook=pb)
    assert "[k2]" in session.options.system_prompt


# ---- usage and metrics ------------------------------------------------------------------------
async def test_a_tracked_run_records_which_entries_were_injected_and_cited(tmp_path):
    db = Database(tmp_path / "u.db")

    async def work(report):
        return None

    summary = RunSummary(outcome="analyzed", cost_usd=0.2, extra={"turns": 7, "playbook": {"injected": ["k1", "k2"], "cited": ["k2"]}})
    await run_tracked(db, project="demo", ticket=ticket(), kind="triage", work=work, summarize=lambda _: summary, daily_cap_usd=10)
    run = db.one("SELECT turns, area FROM runs")
    assert (run["turns"], run["area"]) == (7, "Export PDF")
    stats = knowledge.usage_stats(db, "demo")
    assert stats["k1"]["uses"] == 1 and stats["k1"]["cited"] == 0 and stats["k2"]["cited"] == 1 and stats["k2"]["last_used"]


def test_metrics_per_area(tmp_path):
    db = Database(tmp_path / "m.db")
    seed_run(db, ticket_id="a", area="Autofill", kind="triage", outcome="needs_info", cost_usd=0.1, turns=5)
    seed_run(db, ticket_id="a", area="Autofill", kind="triage", outcome="analyzed", cost_usd=0.1, turns=6)
    run1 = seed_run(db, ticket_id="a", area="Autofill", kind="fix", outcome="review", cost_usd=1.0, turns=20)
    seed_run(db, ticket_id="a", area="Autofill", kind="fix", outcome="review", cost_usd=0.8, turns=10)
    seed_run(db, ticket_id="b", area="Autofill", kind="fix", outcome="review", cost_usd=0.6, turns=4)
    seed_run(db, ticket_id="c", area=None, kind="triage", outcome="analyzed", cost_usd=0.05, turns=3)
    seed_run(db, ticket_id="a", area="Autofill", kind="learn", outcome="proposed", cost_usd=0.9, turns=9)
    db.execute("INSERT INTO approvals(run_id, kind, title, status, created_at) VALUES(?, 'checkpoint', 'x', 'denied', 1)", (run1,))
    db.execute("INSERT INTO approvals(run_id, kind, title, status, created_at) VALUES(?, 'checkpoint', 'x', 'allowed', 1)", (run1,))
    by_area = {m["area"]: m for m in knowledge.metrics(db, "demo")}
    a = by_area["Autofill"]
    assert (a["tickets"], a["questions"], a["retries"], a["rejections"]) == (2, 1, 1, 1)
    assert a["avg_cost"] == pytest.approx((0.1 + 0.1 + 1.0 + 0.8 + 0.6) / 2) and a["avg_turns"] == pytest.approx((5 + 6 + 20 + 10 + 4) / 2)
    assert by_area["(no area)"]["tickets"] == 1


# ---- the retrospective ------------------------------------------------------------------------
def test_sanitize_drops_unsupported_secret_and_duplicate_proposals_and_caps_them():
    ok = lambda text, **kw: Proposal(category="where", text=text, evidence=kw.pop("evidence", "a person said so"), **kw)  # noqa: E731
    result = LearnResult(proposals=[
        ok("Export lives in export.py", paths=["apps/backend/export.py", "/etc/passwd", "../x"]),
        ok("export lives in   export.py"),
        ok("no evidence here", evidence=""),
        ok("the token = sk-abcdefghijklmnopqrstuv is used"),
        *[ok(f"fact {i}") for i in range(10)],
    ])
    items = learn.sanitize(result, "Export PDF")
    assert len(items) == learn.MAX_PROPOSALS
    assert items[0]["paths"] == ["apps/backend/export.py"] and items[1]["text"] == "fact 0"


def test_evidence_includes_comments_rejections_and_the_diff_but_marks_ticket_text_untrusted():
    t = ticket()
    text = learn.evidence_text(
        t, [Comment(author="Christian", text="Only the SCIA SUE counts"), Comment(author="autodev", is_bot=True, text="Triage: ready")],
        [{"id": 1, "kind": "fix", "status": "done", "outcome": "review", "model": "m", "cost_usd": 1.0, "turns": 12},
         {"id": 2, "kind": "fix", "status": "done", "outcome": "review", "model": "m", "cost_usd": 1.0, "turns": 9}],
        [{"kind": "checkpoint", "title": "open the PR?", "status": "denied", "note": "use the existing helper"}],
        " a.py | 2 +-",
    )
    assert "[person: Christian] Only the SCIA SUE counts" in text and "[autodev analysis] Triage: ready" in text
    assert "1 retries" in text and "denied: open the PR? -- note: use the existing helper" in text and "a.py | 2 +-" in text
    assert "UNTRUSTED" in learn.SYSTEM_PROMPT


def test_diff_stat_reads_the_branch_and_copes_without_one(cfg):
    assert "no branch" in learn.diff_stat(cfg, None)
    assert "no longer available" in learn.diff_stat(cfg, "autodev/gone")


async def run_engine_learn(tmp_path, cfg, monkeypatch, proposals):
    async def fake_run_learn(cfg_, evidence, current, report=None):
        fake_run_learn.seen = (evidence, current)
        return LearnResult(proposals=proposals), 0.07, 4, "claude-haiku-5-5"

    monkeypatch.setattr(learn, "run_learn", fake_run_learn)
    from autodev.agents.learn import learn_ticket

    monkeypatch.setattr(engine_mod, "learn_ticket", learn_ticket)
    db = Database(tmp_path / "l.db")
    t = ticket(branch="autodev/gone")
    tracker = EngineTracker([t])
    engine = Engine(cfg, "demo", db, tracker)
    await engine.start("t1", "learn")
    await engine.wait_idle()
    return engine, db, fake_run_learn


async def test_the_retrospective_is_a_tracked_run_that_only_stores_proposals(tmp_path, cfg, monkeypatch):
    knowledge.add_entry(cfg, entry("Already known fact", id="k1"))
    props = [
        Proposal(category="domain", text="Both SCIA signatures are required", area="Export PDF", paths=["apps/backend/export.py"], evidence="Christian said so"),
        Proposal(category="where", text="already known fact", evidence="x"),
    ]
    engine, db, fake = await run_engine_learn(tmp_path, cfg, monkeypatch, props)
    run = db.one("SELECT * FROM runs WHERE kind = 'learn'")
    assert (run["status"], run["outcome"], run["turns"], run["model"], run["cost_usd"]) == ("done", "proposed", 4, "claude-haiku-5-5", 0.07)
    rows = knowledge.list_proposals(db, "demo")
    assert [r["text"] for r in rows] == ["Both SCIA signatures are required"]
    assert rows[0]["source_ticket_id"] == "t1" and rows[0]["run_id"] == run["id"] and rows[0]["paths"] == ["apps/backend/export.py"]
    assert [e.text for e in knowledge.load(cfg)[1]] == ["Already known fact"]  # nothing written without a human
    assert "[k1]" in fake.seen[1] and "Both" not in fake.seen[1]


async def test_the_default_retrospective_model_is_the_cheapest_triage_model(cfg):
    assert learn.learn_model(cfg) == "claude-haiku-5-5"
    cfg.knowledge.model = "claude-sonnet-5-5"
    assert learn.learn_model(cfg) == "claude-sonnet-5-5"


async def test_closing_queues_one_retrospective_and_respects_the_switches(tmp_path, cfg, no_real_retrospective):
    db = Database(tmp_path / "q.db")
    t = ticket()
    e = Engine(cfg, "demo", db, EngineTracker([t]))
    cfg.knowledge.auto_propose_on_close = False
    e.after_close(t)
    await e.wait_idle()
    assert no_real_retrospective == []
    cfg.knowledge.auto_propose_on_close = True
    cfg.knowledge.enabled = False
    e.after_close(t)
    await e.wait_idle()
    assert no_real_retrospective == []
    cfg.knowledge.enabled = True
    e.after_close(t)
    e.after_close(t)
    await e.wait_idle()
    assert no_real_retrospective == ["t1"]
    e.after_close(t)  # already learned from
    await e.wait_idle()
    assert no_real_retrospective == ["t1"]


async def test_a_retrospective_waits_while_an_agent_is_busy(tmp_path, cfg, no_real_retrospective):
    db = Database(tmp_path / "w.db")
    t = ticket()
    e = Engine(cfg, "demo", db, EngineTracker([t]))
    seed_run(db, status="running", project="demo", ticket_id="other")
    e.after_close(t)
    await e.wait_idle()
    assert no_real_retrospective == []
    db.execute("UPDATE runs SET status = 'done'")
    e.drain_learn()
    await e.wait_idle()
    assert no_real_retrospective == ["t1"]


async def test_learning_needs_a_closed_or_reviewed_ticket(tmp_path, cfg):
    from autodev.engine import Refused

    e = Engine(cfg, "demo", Database(tmp_path / "r.db"), EngineTracker([ticket().model_copy(update={"status": Status.NEW})]))
    with pytest.raises(Refused):
        await e.start("t1", "learn")


# ---- the API ----------------------------------------------------------------------------------
@pytest.fixture
def api(tmp_path, cfg):
    db = Database(tmp_path / "s.db")
    tracker = FakeTracker()
    app = create_app(cfg, "demo", db, tracker, static_dir=None)
    c = TestClient(app)
    c.post("/api/auth/setup", json={"password": PASSWORD, "code": app.state.auth.setup_code})
    return c, db, cfg


def propose(db, cfg, *items):
    return knowledge.propose(db, cfg, "demo", ticket(), None, list(items))


def test_proposals_are_listed_with_missing_paths_flagged(api):
    c, db, cfg = api
    propose(db, cfg, {"category": "where", "text": "Export in export.py", "area": "Export PDF", "paths": ["apps/backend/export.py", "apps/backend/nope.py"], "evidence": "diff"})
    data = c.get("/api/knowledge").json()
    assert data["enabled"] and data["file"] == "demo.knowledge.md" and data["max_chars"] == 6000
    (p,) = data["proposals"]
    assert p["missing_paths"] == ["apps/backend/nope.py"] and p["source_title"] == "The download button does nothing" and p["evidence"] == "diff"


def test_accepting_writes_the_entry_and_closes_the_proposal(api):
    c, db, cfg = api
    propose(db, cfg, {"category": "domain", "text": "Both signatures are required", "area": "Export PDF", "paths": [], "evidence": "e"})
    lid = c.get("/api/knowledge").json()["proposals"][0]["id"]
    r = c.post(f"/api/learnings/{lid}/accept")
    assert r.status_code == 200
    data = c.get("/api/knowledge").json()
    assert data["proposals"] == [] and [e["text"] for e in data["entries"]] == ["Both signatures are required"]
    entry = data["entries"][0]
    assert (entry["source_id"], entry["area"], entry["category"], entry["uses"]) == ("t1", "Export PDF", "domain", 0)
    assert "Both signatures are required" in Path(cfg.knowledge_path).read_text()
    assert c.post(f"/api/learnings/{lid}/accept").status_code == 422  # already accepted
    assert c.post("/api/learnings/999/accept").status_code == 404


def test_edit_and_accept_stores_the_edited_entry(api):
    c, db, cfg = api
    propose(db, cfg, {"category": "where", "text": "original", "paths": ["a.py"], "evidence": "e"})
    lid = c.get("/api/knowledge").json()["proposals"][0]["id"]
    r = c.post(f"/api/learnings/{lid}/accept", json={"text": "edited text", "category": "gotcha", "area": "Billing", "paths": ["apps/backend/export.py"]})
    assert r.status_code == 200
    (e,) = c.get("/api/knowledge").json()["entries"]
    assert (e["text"], e["category"], e["area"], e["paths"]) == ("edited text", "gotcha", "Billing", ["apps/backend/export.py"])
    propose(db, cfg, {"category": "where", "text": "other", "evidence": "e"})
    lid = c.get("/api/knowledge").json()["proposals"][0]["id"]
    assert c.post(f"/api/learnings/{lid}/accept", json={"text": "  "}).status_code == 422


def test_rejecting_keeps_the_playbook_untouched_and_lets_nothing_be_decided_twice(api):
    c, db, cfg = api
    propose(db, cfg, {"category": "where", "text": "meh", "evidence": "e"})
    lid = c.get("/api/knowledge").json()["proposals"][0]["id"]
    assert c.post(f"/api/learnings/{lid}/reject").status_code == 200
    data = c.get("/api/knowledge").json()
    assert data["proposals"] == [] and data["entries"] == []
    assert c.post(f"/api/learnings/{lid}/reject").status_code == 422
    assert c.post(f"/api/learnings/{lid}/accept").status_code == 422
    assert not Path(cfg.knowledge_path).exists()
    propose(db, cfg, {"category": "where", "text": "meh", "evidence": "e"})  # a rejected text may be proposed again later
    assert len(c.get("/api/knowledge").json()["proposals"]) == 1


def test_entries_show_usage_and_can_be_deleted(api):
    c, db, cfg = api
    knowledge.add_entry(cfg, entry("Fact", id="k1", paths=["gone.py"]))
    run_id = seed_run(db)
    knowledge.record_usage(db, "demo", run_id, ["k1"], ["k1"])
    knowledge.record_usage(db, "demo", run_id, ["k1"], [])
    (e,) = c.get("/api/knowledge").json()["entries"]
    assert (e["uses"], e["cited"], e["missing_paths"]) == (2, 1, ["gone.py"]) and e["last_used"]
    assert c.delete("/api/knowledge/entries/k1").status_code == 200
    assert c.get("/api/knowledge").json()["entries"] == []
    assert c.delete("/api/knowledge/entries/k1").status_code == 404


def test_the_playbook_is_scoped_to_its_project(api):
    c, db, cfg = api
    propose(db, cfg, {"category": "where", "text": "mine", "evidence": "e"})
    assert knowledge.list_proposals(db, "other") == []


def test_learn_can_be_started_from_the_api(api, no_real_retrospective):
    c, _, _ = api
    r = c.post("/api/tickets/t3/start", json={"kind": "learn"})
    assert r.status_code == 409 and "closed" in r.json()["detail"]  # t3 is New


def test_the_api_requires_a_session(tmp_path, cfg):
    app = create_app(cfg, "demo", Database(tmp_path / "x.db"), FakeTracker(), static_dir=None)
    c = TestClient(app)
    assert c.get("/api/knowledge").status_code == 401
    assert c.post("/api/learnings/1/accept").status_code == 401
    assert c.delete("/api/knowledge/entries/k").status_code == 401


def test_merging_from_the_dashboard_queues_a_retrospective(api, monkeypatch, no_real_retrospective):
    from autodev import github

    c, db, cfg = api
    cfg.pr.slug = "o/r"
    app_tracker = c.app.state.engine.tracker
    app_tracker.tickets[0].pr_url = "https://gh/pull/1"

    async def list_pulls(cfg_, prefix, limit=30):
        return [{"url": "https://gh/pull/1", "number": 1, "state": "open", "branch": "autodev/x", "draft": False, "checks": None, "mergeable": True}]

    async def merge_pull(cfg_, number, method="squash"):
        return "sha"

    async def delete_remote_branch(cfg_, branch):
        return True

    monkeypatch.setattr(github, "list_pulls", list_pulls)
    monkeypatch.setattr(github, "merge_pull", merge_pull)
    monkeypatch.setattr(github, "delete_remote_branch", delete_remote_branch)
    app_tracker.tickets[0].risk = "Low"
    r = c.post("/api/prs/1/merge", json={"confirm": True})
    assert r.status_code == 200, r.text
    time.sleep(0.2)
    assert no_real_retrospective == ["t1"]
