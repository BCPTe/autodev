"""Tracked runs: every triage/fix is recorded, can be followed live, and can be cancelled.

The same code serves the CLI today and the dashboard server later. Cancellation is a flag in the
shared database that the runner polls, so a run started from a terminal can be stopped from the
dashboard (and the other way round).
"""
import asyncio
import os
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Awaitable, Callable, TypeVar

from autodev.db import Database, dumps, now
from autodev.models import Ticket
from autodev.progress import Report

T = TypeVar("T")
POLL_SECONDS = 1.0


class DailyCapReached(RuntimeError):
    pass


class RunCancelled(RuntimeError):
    pass


@dataclass
class RunSummary:
    outcome: str = ""
    cost_usd: float = 0.0
    model: str | None = None
    branch: str | None = None
    pr_url: str | None = None
    result_text: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)


def start_of_today() -> float:
    return datetime.now().replace(hour=0, minute=0, second=0, microsecond=0).timestamp()


def spent_today(db: Database) -> float:
    row = db.one("SELECT COALESCE(SUM(cost_usd), 0) AS s FROM runs WHERE started_at >= ?", (start_of_today(),))
    return float(row["s"]) if row else 0.0


def daily_cap(db: Database, default: float) -> float:
    return float(db.get_setting("daily_budget_usd", str(default)) or default)


def add_event(db: Database, run_id: int, type_: str, text: str = "", data: dict | None = None) -> int:
    return db.execute(
        "INSERT INTO events(run_id, ts, type, text, data) VALUES(?, ?, ?, ?, ?)",
        (run_id, now(), type_, text, dumps(data)),
    )


def mark_orphans(db: Database) -> int:
    """Runs left 'running' by a process that no longer exists (crash, kill -9) are closed as failed."""
    stale = []
    for r in db.query("SELECT id, pid FROM runs WHERE status = 'running'"):
        if r["pid"] and not _alive(r["pid"]):
            stale.append(r["id"])
    for run_id in stale:
        db.execute(
            "UPDATE runs SET status = 'failed', finished_at = ?, error = ? WHERE id = ?",
            (now(), "il processo è terminato senza chiudere il run", run_id),
        )
        add_event(db, run_id, "error", "il processo è terminato senza chiudere il run")
    return len(stale)


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


async def run_tracked(
    db: Database,
    *,
    project: str,
    ticket: Ticket,
    kind: str,
    work: Callable[[Report], Awaitable[T]],
    summarize: Callable[[T], RunSummary],
    daily_cap_usd: float,
    echo: Report | None = None,
    launched: Callable[[], None] | None = None,
) -> T:
    spent = spent_today(db)
    cap = daily_cap(db, daily_cap_usd)
    if spent >= cap:
        raise DailyCapReached(f"tetto giornaliero raggiunto (${spent:.2f} su ${cap:.2f})")

    run_id = db.execute(
        "INSERT INTO runs(project, ticket_id, ticket_title, kind, status, started_at, pid) VALUES(?, ?, ?, ?, 'running', ?, ?)",
        (project, ticket.id, ticket.title, kind, now(), os.getpid()),
    )
    add_event(db, run_id, "started", f"{kind} avviato")
    if launched:
        launched()

    def report(line: str) -> None:
        add_event(db, run_id, "log", line)
        if echo:
            echo(line)

    inner = asyncio.ensure_future(work(report))

    async def watch_cancel() -> None:
        while not inner.done():
            row = db.one("SELECT cancel_requested FROM runs WHERE id = ?", (run_id,))
            if row and row["cancel_requested"]:
                inner.cancel()
                return
            await asyncio.sleep(POLL_SECONDS)

    watcher = asyncio.ensure_future(watch_cancel())
    try:
        result = await inner
    except asyncio.CancelledError:
        _finish(db, run_id, "cancelled", error="interrotto dall'utente")
        add_event(db, run_id, "cancelled", "interrotto dall'utente")
        raise RunCancelled(f"run {run_id} interrotto") from None
    except Exception as e:
        _finish(db, run_id, "failed", error=str(e))
        add_event(db, run_id, "error", str(e))
        raise
    finally:
        watcher.cancel()

    summary = summarize(result)
    if summary.result_text:
        add_event(db, run_id, "result", summary.result_text)
    _finish(db, run_id, "done", summary=summary)
    add_event(db, run_id, "finished", summary.outcome, {"cost_usd": summary.cost_usd})
    return result


def _finish(db: Database, run_id: int, status: str, *, error: str | None = None, summary: RunSummary | None = None) -> None:
    s = summary or RunSummary()
    db.execute(
        "UPDATE runs SET status = ?, finished_at = ?, error = ?, outcome = ?, cost_usd = ?, model = ?, branch = ?, pr_url = ? WHERE id = ?",
        (status, now(), error, s.outcome or None, s.cost_usd, s.model, s.branch, s.pr_url, run_id),
    )
