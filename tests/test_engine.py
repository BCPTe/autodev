import asyncio
from pathlib import Path

import pytest

from autodev import engine as engine_mod
from autodev.config import load_project
from autodev.db import Database
from autodev.engine import Engine, Refused
from autodev.models import Comment, Status, Ticket

CFG = load_project(Path(__file__).parent.parent / "tests" / "fixtures" / "demo.yaml")


class Tracker:
    def __init__(self, tickets):
        self.tickets = {t.id: t for t in tickets}
        self.comments = []

    async def list_all(self):
        return [t.model_copy() for t in self.tickets.values()]

    async def detail(self, ticket_id):
        return self.tickets[ticket_id].model_copy(update={"body": "x" * 100}), [Comment(author="a", text="c")]

    async def set_status(self, ticket_id, status):
        self.tickets[ticket_id].status = status

    async def update(self, ticket_id, **kw):
        for k, v in kw.items():
            setattr(self.tickets[ticket_id], {"agent_note": "agent_note", "cost_usd": "cost_usd"}.get(k, k), v)

    async def comment(self, ticket_id, text, *, as_human=False, author=None):
        self.comments.append((ticket_id, text, as_human))


def ticket(id, status, **kw):
    kw.setdefault("authorized", True)
    return Ticket(id=id, title=f"Ticket {id}", status=status, **kw)


@pytest.fixture
def fakes(monkeypatch):
    """Replace the agents: a job just records itself and moves the ticket along."""
    calls = []
    gate = asyncio.Event()
    gate.set()

    async def triage(cfg, tracker, t, report=None):
        calls.append(("triage", t.id))
        await gate.wait()
        await tracker.set_status(t.id, Status.ANALYZED)
        return Status.ANALYZED, [], "Triage: ready"

    class Outcome:
        status = Status.REVIEW
        cost_usd = 0.5
        models = ["claude-sonnet-5-5"]
        branch = "autodev/x"
        pr_url = None
        checks = []
        message = ""

    async def fix(cfg, tracker, t, report=None):
        calls.append(("fix", t.id))
        await gate.wait()
        await tracker.set_status(t.id, Status.REVIEW)
        return Outcome()

    monkeypatch.setattr(engine_mod, "triage_ticket", triage)
    monkeypatch.setattr(engine_mod, "fix_ticket", fix)
    return calls, gate


def make(tmp_path, tickets, **cfg_kw):
    db = Database(tmp_path / "e.db")
    cfg = CFG.model_copy(deep=True)
    for k, v in cfg_kw.items():
        setattr(cfg.autonomy, k, v)
    tracker = Tracker(tickets)
    return Engine(cfg, "demo", db, tracker), db, tracker


async def test_manual_mode_starts_nothing_by_itself(tmp_path, fakes):
    calls, _ = fakes
    e, db, _ = make(tmp_path, [ticket("a", Status.NEW)])
    assert e.mode == "manual"
    assert await e.tick() is None
    assert calls == []


async def test_start_runs_the_job_and_records_who_asked(tmp_path, fakes):
    calls, _ = fakes
    e, db, tracker = make(tmp_path, [ticket("a", Status.NEW)])
    await e.start("a", "triage")
    await e.wait_idle()
    assert calls == [("triage", "a")]
    assert tracker.tickets["a"].status == Status.ANALYZED
    assert db.one("SELECT status, outcome FROM runs") == {"status": "done", "outcome": "analyzed"}
    assert db.one("SELECT actor, action FROM actions") == {"actor": "user", "action": "start_triage"}


async def test_only_one_agent_runs_at_a_time(tmp_path, fakes):
    _, gate = fakes
    gate.clear()
    e, _, _ = make(tmp_path, [ticket("a", Status.NEW), ticket("b", Status.NEW)])
    await e.start("a", "triage")
    with pytest.raises(Refused, match="already working"):
        await e.start("b", "triage")
    gate.set()
    await e.wait_idle()


async def test_paused_and_my_turn_refuse_every_start(tmp_path, fakes):
    e, _, _ = make(tmp_path, [ticket("a", Status.NEW)])
    e.set_mode("paused")
    with pytest.raises(Refused, match="Paused"):
        await e.start("a", "triage")
    e.set_mode("manual")
    e.set_my_turn(True)
    with pytest.raises(Refused, match="is yours"):
        await e.start("a", "triage")
    e.set_my_turn(False)
    await e.start("a", "triage")
    await e.wait_idle()


async def test_fix_needs_the_ticket_to_be_approved_first(tmp_path, fakes):
    e, _, _ = make(tmp_path, [ticket("a", Status.ANALYZED)])
    with pytest.raises(Refused, match="approve it first"):
        await e.start("a", "fix")


async def test_daily_cap_blocks_starts(tmp_path, fakes):
    e, db, _ = make(tmp_path, [ticket("a", Status.NEW)])
    e.set_daily_cap(1.0)
    db.execute("INSERT INTO runs(project, ticket_id, ticket_title, kind, status, started_at, cost_usd) VALUES('demo','z','z','fix','done',?,1.5)", (__import__("time").time(),))
    with pytest.raises(Refused, match="daily cap"):
        await e.start("a", "triage")
    assert "daily cap" in e.state()["blocked"]


async def test_supervised_triages_and_fixes_only_what_is_authorized_and_approved(tmp_path, fakes):
    calls, _ = fakes
    e, db, tracker = make(tmp_path, [
        ticket("new-ok", Status.NEW),
        ticket("new-unauthorized", Status.NEW, authorized=False),
        ticket("analyzed", Status.ANALYZED, risk="Low"),
    ])
    e.set_mode("supervised")
    assert await e.tick() == "triage new-ok"
    await e.wait_idle()
    assert await e.tick() is None  # new-ok is cooling down; analyzed waits for a human
    assert calls == [("triage", "new-ok")]
    assert tracker.tickets["analyzed"].status == Status.ANALYZED


async def test_fix_goes_before_triage_when_both_are_waiting(tmp_path, fakes):
    e, _, _ = make(tmp_path, [ticket("n", Status.NEW), ticket("p", Status.IN_PROGRESS)])
    e.set_mode("supervised")
    assert await e.tick() == "fix p"
    await e.wait_idle()


async def test_auto_approves_low_and_medium_risk_but_not_high(tmp_path, fakes):
    e, db, tracker = make(tmp_path, [
        ticket("low", Status.ANALYZED, risk="Low"),
        ticket("high", Status.ANALYZED, risk="High"),
    ])
    e.set_mode("auto")
    assert await e.tick() == "fix low"
    await e.wait_idle()
    assert tracker.tickets["high"].status == Status.ANALYZED
    assert tracker.tickets["low"].status == Status.REVIEW
    assert {"actor": "auto", "action": "approve"}.items() <= db.one("SELECT actor, action FROM actions WHERE action = 'approve'").items()


async def test_a_failing_ticket_is_not_retried_every_tick(tmp_path, monkeypatch):
    attempts = []

    async def broken(cfg, tracker, t, report=None):
        attempts.append(t.id)
        raise RuntimeError("checkout sporco")

    monkeypatch.setattr(engine_mod, "fix_ticket", broken)
    e, db, _ = make(tmp_path, [ticket("a", Status.IN_PROGRESS)])
    e.set_mode("supervised")
    await e.tick()
    await e.wait_idle()
    assert await e.tick() is None
    assert attempts == ["a"]
    assert db.one("SELECT status, error FROM runs") == {"status": "failed", "error": "checkout sporco"}


async def test_stop_cancels_the_running_job(tmp_path, fakes):
    _, gate = fakes
    gate.clear()
    e, db, _ = make(tmp_path, [ticket("a", Status.NEW)])
    await e.start("a", "triage")
    await asyncio.sleep(0.05)
    assert e.stop() == 1
    await asyncio.wait_for(e.wait_idle(), timeout=5)
    assert db.one("SELECT status FROM runs")["status"] == "cancelled"
    assert e.stop() == 0


# ---- phase 5: quiet hours, notifications, housekeeping, projects ---------------------------------
import datetime as dt

from autodev import github


def at(hour, minute=0):
    return dt.datetime(2026, 10, 21, hour, minute).timestamp()


@pytest.mark.parametrize("spec,hour,expected", [
    ("22:00-07:00", 23, True), ("22:00-07:00", 3, True), ("22:00-07:00", 7, False), ("22:00-07:00", 12, False),
    ("09:00-17:00", 12, True), ("09:00-17:00", 17, False), ("09:00-17:00", 8, False), (None, 3, False), ("garbage", 3, False),
])
def test_quiet_hours_window_may_cross_midnight(spec, hour, expected):
    assert engine_mod.in_quiet_hours(spec, at(hour)) is expected


async def test_nothing_starts_by_itself_during_quiet_hours_but_a_manual_start_works(tmp_path, fakes):
    calls, _ = fakes
    e, _, _ = make(tmp_path, [ticket("a", Status.NEW)])
    e._clock = lambda: at(23)
    e.set_mode("supervised")
    e.set_quiet_hours("22:00-07:00")
    assert e.state()["quiet"] is True
    assert await e.tick() is None and calls == []
    await e.start("a", "triage")
    await e.wait_idle()
    assert calls == [("triage", "a")]
    e._clock = lambda: at(8)
    assert e.state()["quiet"] is False


def test_quiet_hours_set_in_the_dashboard_override_the_project_file(tmp_path):
    e, _, _ = make(tmp_path, [], quiet_hours="22:00-07:00")
    assert e.quiet_hours == "22:00-07:00"
    e.set_quiet_hours("")
    assert e.quiet_hours is None
    with pytest.raises(ValueError):
        e.set_quiet_hours("night")


async def test_finished_runs_and_requests_raise_a_desktop_notification(tmp_path, fakes, desktop_notifications):
    e, _, _ = make(tmp_path, [ticket("a", Status.NEW)])
    await e.start("a", "triage")
    await e.wait_idle()
    assert len(desktop_notifications) == 1
    assert desktop_notifications[0][-2:] == ["autodev: triage finished", "[demo] Ticket a: analysed, waiting for your approval"]
    e.set_notifications(False)
    e.notify("x", "y")
    assert len(desktop_notifications) == 1


async def test_a_merged_pull_request_closes_its_ticket_and_a_closed_one_escalates_it(tmp_path, monkeypatch, no_real_retrospective):
    e, db, tracker = make(tmp_path, [
        ticket("m", Status.REVIEW, pr_url="https://gh/pull/1"),
        ticket("c", Status.REVIEW, pr_url="https://gh/pull/2"),
        ticket("o", Status.REVIEW, pr_url="https://gh/pull/3"),
        ticket("x", Status.ANALYZED, pr_url="https://gh/pull/1"),
    ])
    e.cfg.pr.slug = "o/r"

    async def list_pulls(cfg, prefix, limit=30):
        return [{"url": f"https://gh/pull/{n}", "number": n, "state": s, "branch": f"autodev/b{n}"} for n, s in ((1, "merged"), (2, "closed"), (3, "open"))]

    monkeypatch.setattr(github, "list_pulls", list_pulls)
    assert sorted(await e.housekeeping()) == ["c", "m"]
    assert (tracker.tickets["m"].status, tracker.tickets["c"].status, tracker.tickets["o"].status, tracker.tickets["x"].status) == (
        Status.CLOSED, Status.ESCALATED, Status.REVIEW, Status.ANALYZED)
    assert "closed without being merged" in tracker.tickets["c"].agent_note
    assert {r["action"] for r in db.query("SELECT action FROM actions")} == {"merged", "pr_closed", "start_learn"}
    await e.wait_idle()
    assert no_real_retrospective == ["m"]


async def test_housekeeping_does_nothing_when_github_is_unreachable(tmp_path, monkeypatch):
    e, _, tracker = make(tmp_path, [ticket("m", Status.REVIEW, pr_url="https://gh/pull/1")])
    e.cfg.pr.slug = "o/r"

    async def broken(cfg, prefix, limit=30):
        raise RuntimeError("GITHUB_TOKEN missing")

    monkeypatch.setattr(github, "list_pulls", broken)
    assert await e.housekeeping() == []
    assert tracker.tickets["m"].status == Status.REVIEW


async def test_projects_keep_separate_modes_caps_and_busy_state(tmp_path, fakes):
    db = Database(tmp_path / "p.db")
    a = Engine(CFG, "alpha", db, Tracker([ticket("a", Status.NEW)]))
    b = Engine(CFG, "beta", db, Tracker([ticket("b", Status.NEW)]))
    a.set_mode("auto")
    a.set_daily_cap(3)
    assert (a.mode, b.mode) == ("auto", "manual")
    assert (a.state()["daily_cap"], b.state()["daily_cap"]) == (3, CFG.limits.daily_budget_usd)
    await a.start("a", "triage")
    assert a.busy() and not b.busy()
    await a.wait_idle()
    db.execute("INSERT INTO runs(project, ticket_id, ticket_title, kind, status, started_at, cost_usd) VALUES('alpha','z','z','fix','done',?,9)", (__import__("time").time(),))
    assert a.state()["spent_today"] >= 9 and b.state()["spent_today"] == 0



def test_switching_mode_starts_the_countdown_and_check_now_ends_it(tmp_path):
    e, _, _ = make(tmp_path, [])
    clock = [1000.0]
    e._clock = lambda: clock[0]
    assert e.state()["next_check"] is None  # manual: no countdown shown
    e.set_mode("auto")
    assert e.state()["next_check"] == 1000.0 + e.cfg.autonomy.poll_seconds
    clock[0] = 1030.0
    e.set_mode("supervised")
    assert e.state()["next_check"] == 1030.0 + e.cfg.autonomy.poll_seconds
    e.check_now()
    assert e.state()["next_check"] == 1030.0
