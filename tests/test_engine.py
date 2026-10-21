import asyncio
from pathlib import Path

import pytest

from autodev import engine as engine_mod
from autodev.config import load_project
from autodev.db import Database
from autodev.engine import Engine, Refused
from autodev.models import Comment, Status, Ticket

CFG = load_project(Path(__file__).parent.parent / "projects" / "demo.yaml")


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

    async def comment(self, ticket_id, text, *, as_human=False):
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
    with pytest.raises(Refused, match="già al lavoro"):
        await e.start("b", "triage")
    gate.set()
    await e.wait_idle()


async def test_paused_and_my_turn_refuse_every_start(tmp_path, fakes):
    e, _, _ = make(tmp_path, [ticket("a", Status.NEW)])
    e.set_mode("paused")
    with pytest.raises(Refused, match="pausa"):
        await e.start("a", "triage")
    e.set_mode("manual")
    e.set_my_turn(True)
    with pytest.raises(Refused, match="tuo turno"):
        await e.start("a", "triage")
    e.set_my_turn(False)
    await e.start("a", "triage")
    await e.wait_idle()


async def test_fix_needs_the_ticket_to_be_approved_first(tmp_path, fakes):
    e, _, _ = make(tmp_path, [ticket("a", Status.ANALYZED)])
    with pytest.raises(Refused, match="approvalo"):
        await e.start("a", "fix")


async def test_daily_cap_blocks_starts(tmp_path, fakes):
    e, db, _ = make(tmp_path, [ticket("a", Status.NEW)])
    e.set_daily_cap(1.0)
    db.execute("INSERT INTO runs(project, ticket_id, ticket_title, kind, status, started_at, cost_usd) VALUES('p','z','z','fix','done',?,1.5)", (__import__("time").time(),))
    with pytest.raises(Refused, match="tetto giornaliero"):
        await e.start("a", "triage")
    assert "tetto giornaliero" in e.state()["blocked"]


async def test_supervised_triages_and_fixes_only_what_is_authorized_and_approved(tmp_path, fakes):
    calls, _ = fakes
    e, db, tracker = make(tmp_path, [
        ticket("new-ok", Status.NEW),
        ticket("new-unauthorized", Status.NEW, authorized=False),
        ticket("analyzed", Status.ANALYZED, risk="Basso"),
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
        ticket("low", Status.ANALYZED, risk="Basso"),
        ticket("high", Status.ANALYZED, risk="Alto"),
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
