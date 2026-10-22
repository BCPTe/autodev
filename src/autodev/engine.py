"""The orchestrator: runs triage and fix jobs, one at a time, either on request or by itself.

Autonomy (the `mode` setting, changeable from the dashboard):
  auto        picks up authorized tickets, and approves analysed ones whose risk is allowed
  supervised  picks up authorized tickets, but a human approves the move to "in progress"
  manual      nothing starts until someone presses Start
  paused      nothing starts at all (a running job finishes unless it is stopped)
`my_turn` is a lock for the person working in the checkout: nothing starts while it is on.
"""
import asyncio
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Callable

from autodev import github, knowledge, notify
from autodev.agents.learn import learn_ticket
from autodev.checks import run_check
from autodev.config import ProjectConfig
from autodev.control import RunControl, current_control
from autodev.db import Database
from autodev.jobs import DailyCapReached, RunCancelled, RunSummary, daily_cap, run_tracked, spent_today
from autodev.models import Status, Ticket
from autodev.pipeline import fix_ticket, publish_ticket, triage_ticket
from autodev.progress import Report

MODES = ("auto", "supervised", "manual", "paused")
TRIAGE_FROM = {Status.NEW, Status.NEEDS_INFO, Status.ANALYZED, Status.ESCALATED}
FIX_FROM = {Status.IN_PROGRESS}
PUBLISH_FROM = {Status.IN_PROGRESS, Status.ESCALATED}
LEARN_FROM = {Status.CLOSED, Status.REVIEW}


QUIET_RE = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)-([01]\d|2[0-3]):([0-5]\d)$")


def in_quiet_hours(spec: str | None, at: float) -> bool:
    """`spec` is "HH:MM-HH:MM" in local time; the window may cross midnight."""
    if not spec or not QUIET_RE.match(spec):
        return False
    start, end = spec.split("-")
    t = datetime.fromtimestamp(at).strftime("%H:%M")
    return start <= t < end if start <= end else (t >= start or t < end)


class Refused(Exception):
    """A start request that cannot be honoured right now; the message says why."""


def triage_job(cfg: ProjectConfig, tracker, ticket: Ticket):
    async def work(report: Report):
        return await triage_ticket(cfg, tracker, ticket, report=report)

    def summarize(r) -> RunSummary:
        return RunSummary(
            outcome=r[0].value, cost_usd=sum(x.cost_usd for x in r[1]),
            model=r[1][-1].model if r[1] else None, result_text=r[2],
            extra={
                "turns": sum(x.turns for x in r[1]),
                "playbook": {"injected": r[1][-1].injected, "cited": r[1][-1].cited} if r[1] else None,
            },
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
            extra={"turns": getattr(o, "turns", 0), "playbook": {"injected": o.playbook, "cited": []} if getattr(o, "playbook", None) else None},
        )

    return work, summarize


def publish_job(cfg: ProjectConfig, tracker, ticket: Ticket):
    async def work(report: Report):
        return await publish_ticket(cfg, tracker, ticket, report=report)

    def summarize(o) -> RunSummary:
        return RunSummary(outcome=o.status.value, branch=o.branch, pr_url=o.pr_url, result_text="\n".join(c.line() for c in o.checks) or None)

    return work, summarize


def learn_job(cfg: ProjectConfig, tracker, ticket: Ticket, db: Database, project: str):
    async def work(report: Report):
        return await learn_ticket(cfg, tracker, db, project, ticket, report)

    def summarize(o) -> RunSummary:
        return RunSummary(
            outcome="proposed" if o.saved else "nothing_to_learn", cost_usd=o.cost_usd, model=o.model,
            result_text="\n".join(f"- {t}" for t in o.texts) or "Nothing worth adding to the playbook.", extra={"turns": o.turns},
        )

    return work, summarize


def checks_job(cfg: ProjectConfig, tracker, ticket: Ticket):
    async def work(report: Report):
        results = []
        for check in cfg.checks:
            report(f"running {check.name}...")
            result = await asyncio.to_thread(run_check, cfg, check, Path(cfg.local_path))
            report(result.line())
            results.append(result)
        return results

    def summarize(results) -> RunSummary:
        ok = all(r.ok for r in results)
        text = "\n".join(r.line() + ("" if r.ok else "\n" + r.output) for r in results)
        return RunSummary(outcome="passed" if ok else "failed", result_text=text)

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
        self._learn_queue: dict[str, Ticket] = {}

    # ---- settings ------------------------------------------------------------------------
    def _k(self, name: str) -> str:
        """Settings are per project: one database serves every project of the dashboard."""
        return f"{self.project}:{name}"

    @property
    def mode(self) -> str:
        mode = self.db.get_setting(self._k("mode"), self.cfg.autonomy.default_mode)
        return mode if mode in MODES else self.cfg.autonomy.default_mode

    def set_mode(self, mode: str, actor: str = "user") -> None:
        if mode not in MODES:
            raise ValueError(f"unknown mode: {mode}")
        if mode != self.mode:
            self.db.set_setting(self._k("mode"), mode)
            self.db.audit(actor, "mode", detail=mode)
        self.notice = None

    @property
    def my_turn(self) -> bool:
        return self.db.get_setting(self._k("my_turn"), "0") == "1"

    def set_my_turn(self, on: bool, actor: str = "user") -> None:
        if on != self.my_turn:
            self.db.set_setting(self._k("my_turn"), "1" if on else "0")
            self.db.set_setting(self._k("my_turn_since"), str(self._clock()))
            self.db.audit(actor, "my_turn", detail="on" if on else "off")

    @property
    def quiet_hours(self) -> str | None:
        """The window set in the dashboard wins over the project file; "" there means no window."""
        value = self.db.get_setting(self._k("quiet_hours"))
        return (value or None) if value is not None else self.cfg.autonomy.quiet_hours

    def set_quiet_hours(self, spec: str, actor: str = "user") -> None:
        if spec and not QUIET_RE.match(spec):
            raise ValueError("quiet hours must look like 22:00-07:00 (empty to remove them)")
        self.db.set_setting(self._k("quiet_hours"), spec)
        self.db.audit(actor, "quiet_hours", detail=spec or "off")

    @property
    def permission_policy(self) -> str:
        value = self.db.get_setting(self._k("permission_policy"))
        return value if value in ("ask", "trusted") else self.cfg.autonomy.permission_policy

    def set_permission_policy(self, policy: str, actor: str = "user") -> None:
        if policy not in ("ask", "trusted"):
            raise ValueError("permission policy must be 'ask' or 'trusted'")
        self.db.set_setting(self._k("permission_policy"), policy)
        self.db.audit(actor, "permission_policy", detail=policy)

    @property
    def notifications(self) -> bool:
        return self.db.get_setting(self._k("notifications"), "1") == "1"

    def set_notifications(self, on: bool, actor: str = "user") -> None:
        self.db.set_setting(self._k("notifications"), "1" if on else "0")
        self.db.audit(actor, "notifications", detail="on" if on else "off")

    def notify(self, title: str, body: str) -> None:
        if self.notifications:
            notify.send(notify.resolve_command(self.cfg.autonomy.notify_command), title, f"[{self.project}] {body}")

    def set_daily_cap(self, usd: float, actor: str = "user") -> None:
        if not 0 < usd <= 1000:
            raise ValueError("the daily cap must be between 0 and 1000 dollars")
        self.db.set_setting(self._k("daily_budget_usd"), str(usd))
        self.db.audit(actor, "daily_cap", detail=f"{usd:.2f}")
        self.notice = None

    def busy(self) -> bool:
        return self._launching or bool(self.db.one("SELECT id FROM runs WHERE status = 'running' AND project = ?", (self.project,)))

    def state(self) -> dict:
        cap = daily_cap(self.db, self.cfg.limits.daily_budget_usd, self.project)
        spent = spent_today(self.db, self.project)
        poll = self.cfg.autonomy.poll_seconds
        return {
            "mode": self.mode,
            "modes": list(MODES),
            "my_turn": self.my_turn,
            "my_turn_since": float(self.db.get_setting(self._k("my_turn_since"), "0") or 0) if self.my_turn else None,
            "busy": self.busy(),
            "daily_cap": cap,
            "spent_today": spent,
            "blocked": self.notice or (f"daily cap reached (${spent:.2f} of ${cap:.2f})" if spent >= cap else None),
            "auto_approve_risks": self.cfg.autonomy.auto_approve_risks,
            "quiet_hours": self.quiet_hours,
            "quiet": in_quiet_hours(self.quiet_hours, self._clock()),
            "notifications": self.notifications,
            "permission_policy": self.permission_policy,
            "can_notify": notify.resolve_command(self.cfg.autonomy.notify_command) is not None,
            "poll_seconds": poll,
            "next_check": (self._last_tick + poll) if self._last_tick and self.mode in ("auto", "supervised") else None,
        }

    # ---- starting and stopping jobs ------------------------------------------------------
    async def start(self, ticket_id: str, kind: str, actor: str = "user") -> None:
        if kind not in ("triage", "fix", "publish", "learn"):
            raise Refused(f"unknown job type: {kind}")
        self._check_can_start(actor)
        self._launching = True
        try:
            ticket, _ = await self.tracker.detail(ticket_id)
            if kind == "learn" and not knowledge.enabled(self.cfg):
                raise Refused("the playbook is turned off for this project (`knowledge.enabled`)")
            allowed = {"triage": TRIAGE_FROM, "fix": FIX_FROM, "publish": PUBLISH_FROM, "learn": LEARN_FROM}[kind]
            if ticket.status not in allowed:
                raise Refused(
                    f"the ticket is in state '{self.cfg.tracker.status_map[ticket.status]}': "
                    + ("it needs a ticket that can be analysed" if kind == "triage" else "approve it first (state 'In progress')" if kind == "fix" else "only a ticket that was worked on can be published" if kind == "publish" else "only a closed ticket, or one in review, can be learned from")
                )
            self.db.audit(actor, f"start_{kind}", ticket.id, ticket.title)
            task = asyncio.ensure_future(self._execute(ticket, kind))
        except BaseException:
            self._launching = False
            raise
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    def _check_can_start(self, actor: str, *, respect_my_turn: bool = True) -> None:
        if self.mode == "paused":
            raise Refused("the mode is 'Paused': switch it to start an agent")
        if self.my_turn and respect_my_turn:
            raise Refused("the checkout is yours: no agent starts until you hand it back")
        if self.busy():
            raise Refused("an agent is already working: only one runs at a time on the checkout")
        spent, cap = spent_today(self.db, self.project), daily_cap(self.db, self.cfg.limits.daily_budget_usd, self.project)
        if spent >= cap:
            raise Refused(f"daily cap reached (${spent:.2f} of ${cap:.2f}): raise it in Settings")

    async def start_checks(self, actor: str = "user") -> None:
        """Runs the project's configured checks (tests, typecheck) on the checkout as it is now."""
        if not self.cfg.checks:
            raise Refused("no checks configured: add `checks` to the project file")
        self._check_can_start(actor, respect_my_turn=False)
        self._launching = True
        self.db.audit(actor, "start_checks", None, "")
        task = asyncio.ensure_future(self._execute(Ticket(id="repo", title="Checks on the checkout", status=Status.NEW), "checks"))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def _execute(self, ticket: Ticket, kind: str) -> None:
        if kind == "learn":
            work, summarize = learn_job(self.cfg, self.tracker, ticket, self.db, self.project)
        else:
            job = {"triage": triage_job, "fix": fix_job, "checks": checks_job, "publish": publish_job}[kind]
            work, summarize = job(self.cfg, self.tracker, ticket)
        if kind not in ("checks", "learn"):
            self._tried[(ticket.id, ticket.status.value)] = self._clock()
        control = RunControl(self.db, lambda: self.mode, self.notify, lambda: self.permission_policy)
        current_control.set(control)
        try:
            result = await run_tracked(
                self.db, project=self.project, ticket=ticket, kind=kind, work=work, summarize=summarize,
                daily_cap_usd=self.cfg.limits.daily_budget_usd, launched=lambda run_id: self._release(run_id, control),
            )
            self.notify(*self._finished_message(kind, ticket, summarize(result)))
        except DailyCapReached as e:
            self.notice = str(e)
            self.notify("autodev: daily cap reached", str(e))
        except RunCancelled:
            pass
        except Exception as e:  # run_tracked has already recorded the failure on the run
            self.notify(f"autodev: {kind} failed", f"{ticket.title}: {e}")
        finally:
            self._launching = False
            if control.run_id is not None:
                self.controls.pop(control.run_id, None)
            self.on_change()
            self.drain_learn()

    @staticmethod
    def _finished_message(kind: str, ticket: Ticket, summary: RunSummary) -> tuple[str, str]:
        verdict = {"review": "ready for review", "escalated": "needs your attention", "analyzed": "analysed, waiting for your approval", "proposed": "playbook proposals ready for review", "nothing_to_learn": "nothing new for the playbook",
                   "needs_info": "needs more information", "passed": "checks passed", "failed": "checks failed"}.get(summary.outcome, summary.outcome)
        return f"autodev: {kind} finished", f"{ticket.title}: {verdict}"

    # ---- the playbook ----------------------------------------------------------------------
    def after_close(self, ticket: Ticket) -> None:
        """A ticket was closed with a merged PR: queue a retrospective (it only proposes; a person accepts)."""
        k = self.cfg.knowledge
        if not (knowledge.enabled(self.cfg) and k.auto_propose_on_close) or self._learned(ticket.id):
            return
        self._learn_queue[ticket.id] = ticket
        self.drain_learn()

    def _learned(self, ticket_id: str) -> bool:
        return bool(self.db.one(
            "SELECT id FROM runs WHERE project = ? AND ticket_id = ? AND kind = 'learn' AND status IN ('running', 'done')", (self.project, ticket_id)
        ))

    def drain_learn(self) -> None:
        """Starts the next queued retrospective when the engine is free; otherwise it waits for the next round."""
        while self._learn_queue:
            ticket_id = next(iter(self._learn_queue))
            if self._learned(ticket_id):
                del self._learn_queue[ticket_id]
                continue
            try:
                self._check_can_start("auto")
            except Refused:
                return
            ticket = self._learn_queue.pop(ticket_id)
            self._launching = True
            self.db.audit("auto", "start_learn", ticket.id, ticket.title)
            task = asyncio.ensure_future(self._execute(ticket, "learn"))
            self._tasks.add(task)
            task.add_done_callback(self._tasks.discard)
            return

    def _release(self, run_id: int, control: RunControl) -> None:
        """The run row exists now: the database reports busy by itself, and the run can be talked to."""
        control.run_id = run_id
        self.controls[run_id] = control
        self._launching = False

    def stop(self, run_id: int | None = None, actor: str = "user") -> int:
        where, params = ("AND id = ?", (run_id,)) if run_id else ("", ())
        n = len(self.db.query(f"SELECT id FROM runs WHERE status = 'running' AND project = ? {where}", (self.project, *params)))
        if n:
            self.db.execute(f"UPDATE runs SET cancel_requested = 1 WHERE status = 'running' AND project = ? {where}", (self.project, *params))
            self.db.audit(actor, "stop", detail=f"run {run_id}" if run_id else "tutti")
        return n

    async def wait_idle(self) -> None:
        while self._tasks:
            await asyncio.gather(*list(self._tasks), return_exceptions=True)

    # ---- the automatic part --------------------------------------------------------------
    async def run_forever(self) -> None:
        while True:
            try:
                await self.housekeeping()
                self.drain_learn()
                await self.tick()
            except Exception as e:  # a Notion hiccup must not kill the loop
                self.notice = f"automatic check failed: {e}"
            await asyncio.sleep(self.cfg.autonomy.poll_seconds)

    async def housekeeping(self) -> list[str]:
        """Keeps Notion in line with GitHub: a merged PR closes its ticket, a PR closed unmerged escalates it."""
        if not self.cfg.pr.slug:
            return []
        try:
            pulls = {p["url"]: p for p in await github.list_pulls(self.cfg, self.cfg.branch_prefix)}
        except Exception:
            return []  # no token or GitHub unreachable: try again next round
        done = []
        for t in await self.tracker.list_all():
            pr = pulls.get(t.pr_url or "")
            if not pr or t.status != Status.REVIEW or pr["state"] == "open":
                continue
            if pr["state"] == "merged":
                await self.tracker.set_status(t.id, Status.CLOSED)
                self.db.audit("auto", "merged", t.id, f"PR {pr['number']}")
                self.after_close(t)
                self.notify("autodev: pull request merged", t.title)
                if self.cfg.autonomy.auto_cleanup_branches and not self.busy():
                    from autodev.server import repo

                    try:
                        repo.delete_branches(self.cfg, [pr["branch"]], {pr["branch"]})
                    except repo.RepoError:
                        pass
            else:
                await self.tracker.update(t.id, agent_note=f"PR #{pr['number']} was closed without being merged")
                await self.tracker.set_status(t.id, Status.ESCALATED)
                self.db.audit("auto", "pr_closed", t.id, f"PR {pr['number']}")
            done.append(t.id)
        if done:
            self.on_change()
        return done

    def _cooling(self, ticket: Ticket) -> bool:
        at = self._tried.get((ticket.id, ticket.status.value))
        return at is not None and self._clock() - at < self.cfg.autonomy.retry_cooldown_seconds

    async def tick(self) -> str | None:
        """One look at the board: starts at most one job. Returns what it did, for tests and logs."""
        self._last_tick = self._clock()
        if self.mode not in ("auto", "supervised") or self.my_turn or self.busy():
            return None
        if in_quiet_hours(self.quiet_hours, self._clock()):
            return None
        if spent_today(self.db, self.project) >= daily_cap(self.db, self.cfg.limits.daily_budget_usd, self.project):
            return None
        self.notice = None
        tickets = [t for t in await self.tracker.list_all() if t.authorized and not self._cooling(t)]

        if self.mode == "auto":
            for t in tickets:
                if t.status == Status.ANALYZED and t.risk in self.cfg.autonomy.auto_approve_risks:
                    await self.tracker.set_status(t.id, Status.IN_PROGRESS)
                    self.db.audit("auto", "approve", t.id, f"risk {t.risk}")
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
