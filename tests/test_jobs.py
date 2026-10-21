import asyncio

import pytest

from autodev import jobs
from autodev.db import Database
from autodev.jobs import DailyCapReached, RunCancelled, RunSummary, mark_orphans, run_tracked, spent_today
from autodev.models import Status, Ticket

TICKET = Ticket(id="t-1", title="Bug", status=Status.NEW)


@pytest.fixture
def db(tmp_path):
    return Database(tmp_path / "t.db")


def summary(result):
    return RunSummary(outcome=result["outcome"], cost_usd=result["cost"], model="m", result_text="analisi")


async def test_a_finished_run_is_recorded_with_its_events_and_cost(db):
    async def work(report):
        report("legge x.py")
        report("cerca 'a'")
        return {"outcome": "analyzed", "cost": 0.4}

    echoed = []
    out = await run_tracked(db, project="p", ticket=TICKET, kind="triage", work=work, summarize=summary,
                            daily_cap_usd=10, echo=echoed.append)

    assert out == {"outcome": "analyzed", "cost": 0.4}
    run = db.one("SELECT * FROM runs")
    assert (run["status"], run["kind"], run["outcome"], run["cost_usd"], run["ticket_title"]) == ("done", "triage", "analyzed", 0.4, "Bug")
    assert run["finished_at"] >= run["started_at"]
    events = db.query("SELECT type, text FROM events ORDER BY id")
    assert [e["type"] for e in events] == ["started", "log", "log", "result", "finished"]
    assert echoed == ["legge x.py", "cerca 'a'"]


async def test_a_failing_run_is_marked_failed_and_the_error_is_raised(db):
    async def work(report):
        raise ValueError("boom")

    with pytest.raises(ValueError):
        await run_tracked(db, project="p", ticket=TICKET, kind="fix", work=work, summarize=summary, daily_cap_usd=10)
    run = db.one("SELECT * FROM runs")
    assert run["status"] == "failed" and run["error"] == "boom"
    assert db.one("SELECT text FROM events WHERE type = 'error'")["text"] == "boom"


async def test_a_run_can_be_cancelled_from_outside_through_the_database(db, monkeypatch):
    monkeypatch.setattr(jobs, "POLL_SECONDS", 0.05)
    started = asyncio.Event()

    async def work(report):
        report("working")
        started.set()
        await asyncio.sleep(30)

    async def other_process():
        await started.wait()
        db.execute("UPDATE runs SET cancel_requested = 1")

    asyncio.ensure_future(other_process())
    with pytest.raises(RunCancelled):
        await asyncio.wait_for(
            run_tracked(db, project="p", ticket=TICKET, kind="fix", work=work, summarize=summary, daily_cap_usd=10), 5
        )
    run = db.one("SELECT * FROM runs")
    assert run["status"] == "cancelled" and run["finished_at"] is not None
    assert db.one("SELECT 1 AS x FROM events WHERE type = 'cancelled'")


async def test_daily_cap_blocks_new_runs_but_not_before_it_is_reached(db):
    async def work(report):
        return {"outcome": "ok", "cost": 6.0}

    await run_tracked(db, project="p", ticket=TICKET, kind="fix", work=work, summarize=summary, daily_cap_usd=10)
    assert spent_today(db) == 6.0
    await run_tracked(db, project="p", ticket=TICKET, kind="fix", work=work, summarize=summary, daily_cap_usd=10)
    with pytest.raises(DailyCapReached, match=r"\$12\.00 su \$10\.00"):
        await run_tracked(db, project="p", ticket=TICKET, kind="fix", work=work, summarize=summary, daily_cap_usd=10)
    assert db.one("SELECT COUNT(*) AS n FROM runs")["n"] == 2


async def test_the_cap_set_in_the_dashboard_overrides_the_config_default(db):
    async def work(report):
        return {"outcome": "ok", "cost": 1.0}

    db.set_setting("p:daily_budget_usd", "1")
    await run_tracked(db, project="p", ticket=TICKET, kind="fix", work=work, summarize=summary, daily_cap_usd=100)
    with pytest.raises(DailyCapReached):
        await run_tracked(db, project="p", ticket=TICKET, kind="fix", work=work, summarize=summary, daily_cap_usd=100)


def test_runs_left_running_by_a_dead_process_are_closed(db):
    alive = db.execute("INSERT INTO runs(project, ticket_id, ticket_title, kind, status, started_at, pid) VALUES('p','a','A','fix','running',1,?)", (__import__('os').getpid(),))
    dead = db.execute("INSERT INTO runs(project, ticket_id, ticket_title, kind, status, started_at, pid) VALUES('p','b','B','fix','running',1,999999)")
    assert mark_orphans(db) == 1
    assert db.one("SELECT status FROM runs WHERE id = ?", (dead,))["status"] == "failed"
    assert db.one("SELECT status FROM runs WHERE id = ?", (alive,))["status"] == "running"
