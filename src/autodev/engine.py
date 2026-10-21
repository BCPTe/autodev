"""The orchestrator: runs triage and fix jobs, one at a time, either on request or by itself.

Autonomy (the `mode` setting, changeable from the dashboard):
  auto        picks up authorized tickets, and approves analysed ones whose risk is allowed
  supervised  picks up authorized tickets, but a human approves the move to "in progress"
  manual      nothing starts until someone presses Start
  paused      nothing starts at all (a running job finishes unless it is stopped)
`my_turn` is a lock for the person working in the checkout: nothing starts while it is on.
"""
import asyncio
import time
from typing import Callable

from autodev.config import ProjectConfig
from autodev.control import RunControl, current_control
from autodev.db import Database
from autodev.jobs import DailyCapReached, RunCancelled, RunSummary, daily_cap, run_tracked, spent_today
from autodev.models import Status, Ticket
from autodev.pipeline import fix_ticket, triage_ticket
from autodev.progress import Report

MODES = ("auto", "supervised", "manual", "paused")
TRIAGE_FROM = {Status.NEW, Status.NEEDS_INFO, Status.ANALYZED, Status.ESCALATED}
FIX_FROM = {Status.IN_PROGRESS}


class Refused(Exception):
    """A start request that cannot be honoured right now; the message says why."""


def triage_job(cfg: ProjectConfig, tracker, ticket: Ticket):
    async def work(report: Report):
        return await triage_ticket(cfg, tracker, ticket, report=report)

    def summarize(r) -> RunSummary:
        return RunSummary(
            outcome=r[0].value, cost_usd=sum(x.cost_usd for x in r[1]),
            model=r[1][-1].model if r[1] else None, result_text=r[2],
        )

    return work, summarize


def fix_job(cfg: ProjectConfig, tracker, ticket: Ticket):
    async def work(report: Report):
        return await fix_ticket(cfg, tracker, ticket, report=report)

    def summarize(o) -> RunSummary:
        return RunSummary(
            outcome=o.status.value, cost_usd=o.cost_usd, model=o.models[-1] if o.models else None,
            branch=o.branch, pr_url=o.pr_url,
            result_text="\n".join([*(c.line() for c in o.checks), o.message]).strip() or None,
        )

    return work, summarize


class Engine:
    def __init__(self, cfg: ProjectConfig, project: str, db: Database, tracker, *, clock: Callable[[], float] = time.time):
        self.cfg, self.project, self.db, self.tracker, self._clock = cfg, project, db, tracker, clock
        self.on_change: Callable[[], None] = lambda: None
        self.notice: str | None = None
        self.controls: dict[int, RunControl] = {}
        self._launching = False
        self._tasks: set[asyncio.Task] = set()
        self._tried: dict[tuple[str, str], float] = {}
        self._last_tick: float | None = None

    # ---- settings ------------------------------------------------------------------------
    @property
    def mode(self) -> str:
        mode = self.db.get_setting("mode", self.cfg.autonomy.default_mode)
        return mode if mode in MODES else self.cfg.autonomy.default_mode

    def set_mode(self, mode: str, actor: str = "user") -> None:
        if mode not in MODES:
            raise ValueError(f"modalità sconosciuta: {mode}")
        if mode != self.mode:
            self.db.set_setting("mode", mode)
            self.db.audit(actor, "mode", detail=mode)
        self.notice = None

    @property
    def my_turn(self) -> bool:
        return self.db.get_setting("my_turn", "0") == "1"

    def set_my_turn(self, on: bool, actor: str = "user") -> None:
        if on != self.my_turn:
            self.db.set_setting("my_turn", "1" if on else "0")
            self.db.set_setting("my_turn_since", str(self._clock()))
            self.db.audit(actor, "my_turn", detail="on" if on else "off")

    def set_daily_cap(self, usd: float, actor: str = "user") -> None:
        if not 0 < usd <= 1000:
            raise ValueError("il tetto giornaliero deve essere tra 0 e 1000 dollari")
        self.db.set_setting("daily_budget_usd", str(usd))
        self.db.audit(actor, "daily_cap", detail=f"{usd:.2f}")
        self.notice = None

    def busy(self) -> bool:
        return self._launching or bool(self.db.one("SELECT id FROM runs WHERE status = 'running'"))

    def state(self) -> dict:
        cap = daily_cap(self.db, self.cfg.limits.daily_budget_usd)
        spent = spent_today(self.db)
        poll = self.cfg.autonomy.poll_seconds
        return {
            "mode": self.mode,
            "modes": list(MODES),
            "my_turn": self.my_turn,
            "my_turn_since": float(self.db.get_setting("my_turn_since", "0") or 0) if self.my_turn else None,
            "busy": self.busy(),
            "daily_cap": cap,
            "spent_today": spent,
            "blocked": self.notice or (f"tetto giornaliero raggiunto (${spent:.2f} su ${cap:.2f})" if spent >= cap else None),
            "auto_approve_risks": self.cfg.autonomy.auto_approve_risks,
            "poll_seconds": poll,
            "next_check": (self._last_tick + poll) if self._last_tick and self.mode in ("auto", "supervised") else None,
        }

    # ---- starting and stopping jobs ------------------------------------------------------
    async def start(self, ticket_id: str, kind: str, actor: str = "user") -> None:
        if kind not in ("triage", "fix"):
            raise Refused(f"tipo di job sconosciuto: {kind}")
        self._check_can_start(actor)
        self._launching = True
        try:
            ticket, _ = await self.tracker.detail(ticket_id)
            allowed = TRIAGE_FROM if kind == "triage" else FIX_FROM
            if ticket.status not in allowed:
                raise Refused(
                    f"il ticket è in stato '{self.cfg.tracker.status_map[ticket.status]}': "
                    + ("serve un ticket da analizzare" if kind == "triage" else "approvalo prima (stato 'In lavorazione')")
                )
            self.db.audit(actor, f"start_{kind}", ticket.id, ticket.title)
            task = asyncio.ensure_future(self._execute(ticket, kind))
        except BaseException:
            self._launching = False
            raise
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    def _check_can_start(self, actor: str) -> None:
        if self.mode == "paused":
            raise Refused("la modalità è 'In pausa': riattivala per far partire un agente")
        if self.my_turn:
            raise Refused("è il tuo turno: finché non lo restituisci nessun agente parte")
        if self.busy():
            raise Refused("un agente è già al lavoro: ne gira uno alla volta sul checkout")
        spent, cap = spent_today(self.db), daily_cap(self.db, self.cfg.limits.daily_budget_usd)
        if spent >= cap:
            raise Refused(f"tetto giornaliero raggiunto (${spent:.2f} su ${cap:.2f}): alzalo nelle impostazioni")

    async def _execute(self, ticket: Ticket, kind: str) -> None:
        job = triage_job if kind == "triage" else fix_job
        work, summarize = job(self.cfg, self.tracker, ticket)
        self._tried[(ticket.id, ticket.status.value)] = self._clock()
        control = RunControl(self.db, lambda: self.mode)
        current_control.set(control)
        try:
            await run_tracked(
                self.db, project=self.project, ticket=ticket, kind=kind, work=work, summarize=summarize,
                daily_cap_usd=self.cfg.limits.daily_budget_usd, launched=lambda run_id: self._release(run_id, control),
            )
        except DailyCapReached as e:
            self.notice = str(e)
        except RunCancelled:
            pass
        except Exception:
            pass  # run_tracked has already recorded the failure on the run
        finally:
            self._launching = False
            if control.run_id is not None:
                self.controls.pop(control.run_id, None)
            self.on_change()

    def _release(self, run_id: int, control: RunControl) -> None:
        """The run row exists now: the database reports busy by itself, and the run can be talked to."""
        control.run_id = run_id
        self.controls[run_id] = control
        self._launching = False

    def stop(self, run_id: int | None = None, actor: str = "user") -> int:
        where, params = ("AND id = ?", (run_id,)) if run_id else ("", ())
        n = len(self.db.query(f"SELECT id FROM runs WHERE status = 'running' {where}", params))
        if n:
            self.db.execute(f"UPDATE runs SET cancel_requested = 1 WHERE status = 'running' {where}", params)
            self.db.audit(actor, "stop", detail=f"run {run_id}" if run_id else "tutti")
        return n

    async def wait_idle(self) -> None:
        while self._tasks:
            await asyncio.gather(*list(self._tasks), return_exceptions=True)

    # ---- the automatic part --------------------------------------------------------------
    async def run_forever(self) -> None:
        while True:
            try:
                await self.tick()
            except Exception as e:  # a Notion hiccup must not kill the loop
                self.notice = f"controllo automatico non riuscito: {e}"
            await asyncio.sleep(self.cfg.autonomy.poll_seconds)

    def _cooling(self, ticket: Ticket) -> bool:
        at = self._tried.get((ticket.id, ticket.status.value))
        return at is not None and self._clock() - at < self.cfg.autonomy.retry_cooldown_seconds

    async def tick(self) -> str | None:
        """One look at the board: starts at most one job. Returns what it did, for tests and logs."""
        self._last_tick = self._clock()
        if self.mode not in ("auto", "supervised") or self.my_turn or self.busy():
            return None
        if spent_today(self.db) >= daily_cap(self.db, self.cfg.limits.daily_budget_usd):
            return None
        self.notice = None
        tickets = [t for t in await self.tracker.list_all() if t.authorized and not self._cooling(t)]

        if self.mode == "auto":
            for t in tickets:
                if t.status == Status.ANALYZED and t.risk in self.cfg.autonomy.auto_approve_risks:
                    await self.tracker.set_status(t.id, Status.IN_PROGRESS)
                    self.db.audit("auto", "approve", t.id, f"rischio {t.risk}")
                    t.status = Status.IN_PROGRESS
                    self.on_change()

        for kind, status in (("fix", Status.IN_PROGRESS), ("triage", Status.NEW)):
            for t in tickets:
                if t.status == status:
                    try:
                        await self.start(t.id, kind, actor="auto")
                    except Refused:
                        return None
                    return f"{kind} {t.id}"
        return None
