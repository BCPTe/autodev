from pathlib import Path

import httpx

from autodev.agents.triage import RunInfo, TriageResult, escalate_risk, run_triage
from autodev.config import ProjectConfig
from autodev.control import checkpoint
from autodev.models import Risk, Status, Ticket
from autodev.progress import Progress, Report
from autodev.trackers.base import Tracker

VERDICT_STATUS = {
    "needs_info": Status.NEEDS_INFO,
    "not_reproducible": Status.CLOSED,
    "ready": Status.ANALYZED,
}


MIN_USEFUL_BUDGET = 0.25


def remaining_budget(cfg: ProjectConfig, ticket: Ticket, spent_now: float = 0.0) -> float:
    """What is left of the per-ticket cap: everything already booked on the ticket plus this run."""
    return cfg.limits.budget_usd_per_ticket - ticket.cost_usd - spent_now


def budget_message(cfg: ProjectConfig, ticket: Ticket, spent_now: float = 0.0) -> str:
    spent = ticket.cost_usd + spent_now
    return f"tetto di spesa per ticket raggiunto (${spent:.2f} su ${cfg.limits.budget_usd_per_ticket:.2f})"


def prefilter(cfg: ProjectConfig, ticket: Ticket) -> str | None:
    """Cheap checks that avoid launching an agent on tickets that cannot be analysed."""
    if len(ticket.body.strip()) < cfg.min_body_chars:
        return (
            "Il ticket non ha una descrizione sufficiente. Indica cosa è successo, i passi per riprodurlo "
            "e il comportamento atteso, poi riporta il ticket in stato Nuovo."
        )
    return None


def format_comment(result: TriageResult, risk: str, runs: list[RunInfo]) -> str:
    lines = [f"Triage: {result.verdict} (rischio {risk})", "", result.analysis]
    if result.suspected_files:
        lines += ["", "File coinvolti:", *[f"- {f}" for f in dict.fromkeys(result.suspected_files)]]
    if result.questions:
        lines += ["", "Domande (servono per procedere):", *[f"- {q}" for q in result.questions]]
    if result.assumptions:
        lines += ["", "Assunzioni da confermare in review (non bloccanti):", *[f"- {a}" for a in result.assumptions]]
    if result.suggested_test:
        lines += ["", f"Test suggerito: {result.suggested_test}"]
    lines += ["", "Run: " + " -> ".join(f"{r.model} ({r.turns} turni, ${r.cost_usd:.2f})" for r in runs)]
    return "\n".join(lines)


async def _publish(tracker: Tracker, ticket: Ticket, text: str) -> None:
    try:
        await tracker.comment(ticket.id, text)
    except httpx.HTTPStatusError:
        await tracker.update(ticket.id, agent_note=text)


async def _escalate_triage(tracker: Tracker, ticket: Ticket, reason: str) -> None:
    await _publish(tracker, ticket, f"Triage non eseguito: {reason}")
    await tracker.update(ticket.id, agent_note=reason)
    await tracker.set_status(ticket.id, Status.ESCALATED)


async def triage_ticket(
    cfg: ProjectConfig, tracker: Tracker, ticket: Ticket, report: Report | None = None
) -> tuple[Status, list[RunInfo], str]:
    if remaining_budget(cfg, ticket) < MIN_USEFUL_BUDGET:
        await _escalate_triage(tracker, ticket, budget_message(cfg, ticket))
        return Status.ESCALATED, [], budget_message(cfg, ticket)

    missing = prefilter(cfg, ticket)
    if missing:
        await _publish(tracker, ticket, f"Triage: needs_info\n\n{missing}")
        await tracker.set_status(ticket.id, Status.NEEDS_INFO)
        return Status.NEEDS_INFO, [], f"Triage: needs_info\n\n{missing}"

    try:
        result, runs = await run_triage(cfg, ticket, report, budget_usd=remaining_budget(cfg, ticket))
    except Exception as e:
        await tracker.update(ticket.id, agent_note=f"Triage fallito: {e}")
        await tracker.set_status(ticket.id, Status.ESCALATED)
        raise

    risk: Risk = escalate_risk(result, cfg)
    comment = format_comment(result, risk.value, runs)
    await _publish(tracker, ticket, comment)
    await tracker.update(ticket.id, risk=risk, cost_usd=ticket.cost_usd + sum(r.cost_usd for r in runs))
    status = VERDICT_STATUS[result.verdict]
    if result.verdict == "not_reproducible":
        await tracker.update(ticket.id, agent_note="Chiuso dal triage: non riproducibile")
    await tracker.set_status(ticket.id, status)
    return status, runs, comment


# ---------------------------------------------------------------------------
# Fix stage
# ---------------------------------------------------------------------------

from dataclasses import dataclass, field  # noqa: E402

from autodev.agents.fix import FixResult, pick_model, run_fix  # noqa: E402
from autodev.checks import CheckResult, regression_gate, run_checks  # noqa: E402
from autodev.github import create_pull_request  # noqa: E402
from autodev.sandbox.workspace import Workspace, matches  # noqa: E402


@dataclass
class FixOutcome:
    status: Status
    branch: str | None = None
    pr_url: str | None = None
    cost_usd: float = 0.0
    checks: list[CheckResult] = field(default_factory=list)
    message: str = ""
    models: list[str] = field(default_factory=list)


def _notion_url(ticket_id: str) -> str:
    return f"https://www.notion.so/{ticket_id.replace('-', '')}"


def _risk_for_changes(cfg: ProjectConfig, ws: Workspace, base: Risk) -> tuple[Risk, list[str]]:
    flags = []
    risk = base
    touched = [f for f in ws.changed_files(ws.base_ref) if matches(f, cfg.risk.never_automerge)]
    if touched:
        risk = Risk.HIGH
        flags.append(f"tocca file ad alto rischio: {', '.join(touched)}")
    test_globs = [g for reg in cfg.regressions for g in reg.test_globs]
    if test_globs and any(matches(f, test_globs) for f in ws.modified_existing()):
        risk = Risk.HIGH
        flags.append("modifica test esistenti")
    return risk, flags


def pr_body(ticket: Ticket, fix: FixResult, checks: list[CheckResult], risk: Risk, flags: list[str], files: list[str]) -> str:
    lines = [
        f"Ticket: {_notion_url(ticket.id)}",
        "",
        "## Cosa cambia",
        fix.summary,
        "",
        "## Verifiche automatiche",
        *[f"- {c.line()}" for c in checks],
        "",
        f"## Rischio: {risk.value}",
        *[f"- {f}" for f in flags],
    ]
    if any(f.startswith("apps/frontend") for f in files):
        lines += ["", "**Da verificare a mano nella UI**: le modifiche al frontend non sono coperte da test automatici."]
    if fix.notes:
        lines += ["", "## Note dell'agente", fix.notes]
    lines += ["", "File modificati:", *[f"- `{f}`" for f in files], "", "Generato da autodev."]
    return "\n".join(lines)


async def _escalate(tracker: Tracker, ticket: Ticket, reason: str, cost: float, branch: str | None = None) -> None:
    await _publish(tracker, ticket, f"Fix non completato: {reason}")
    await tracker.update(
        ticket.id, agent_note=reason, cost_usd=ticket.cost_usd + cost, branch=branch, verification="Fallita"
    )
    await tracker.set_status(ticket.id, Status.ESCALATED)


async def fix_ticket(
    cfg: ProjectConfig, tracker: Tracker, ticket: Ticket, report: Report | None = None
) -> FixOutcome:
    if ticket.attempts >= cfg.limits.max_fix_runs:
        await _escalate(tracker, ticket, f"già eseguito {ticket.attempts} volte (limite {cfg.limits.max_fix_runs}); azzera 'Attempts' per riprovare", 0.0)
        return FixOutcome(Status.ESCALATED, message="max fix runs")

    if remaining_budget(cfg, ticket) < MIN_USEFUL_BUDGET:
        await _escalate(tracker, ticket, budget_message(cfg, ticket), 0.0)
        return FixOutcome(Status.ESCALATED, message="budget")

    ws = Workspace.create(cfg, ticket)
    await tracker.update(ticket.id, attempts=ticket.attempts + 1)
    if report:
        where = f"checkout di {cfg.name or Path(cfg.local_path).name}" if ws.inplace else ws.path.name
        report(f"workspace: {where} ({'ripreso, ' + str(len(ws.history().splitlines())) + ' righe di storia' if ws.resumed else 'nuovo'}), branch {ws.branch}")
    models_used: list[str] = []
    try:
        outcome = await _fix_in_workspace(cfg, tracker, ticket, report, ws, models_used)
        outcome.models = models_used
        return outcome
    finally:
        _publish_local(cfg, ws, report)


def _publish_local(cfg: ProjectConfig, ws: Workspace, report: Report | None) -> None:
    """Whatever happened, expose the agent's commits as a branch in the user's repo."""
    say = report or (lambda _line: None)
    if ws.inplace:
        if ws.has_commits():
            say(f"il checkout {ws.path} è ora sul branch {ws.branch}; per tornare indietro: git checkout {cfg.base_branch}")
        return
    if not ws.has_commits():
        return
    try:
        ws.publish_local(cfg.local_path)
        say(f"branch pubblicato in {cfg.local_path}: git checkout {ws.branch}")
    except RuntimeError as e:
        say(f"branch non pubblicato in {cfg.local_path}: {e}")


async def _fix_in_workspace(
    cfg: ProjectConfig, tracker: Tracker, ticket: Ticket, report: Report | None, ws: Workspace,
    models_used: list[str],
) -> FixOutcome:
    triage_notes = await tracker.bot_comments(ticket.id)
    cost = 0.0
    failure: str | None = None
    fix: FixResult | None = None
    checks: list[CheckResult] = []

    for attempt in range(1, cfg.limits.max_attempts + 1):
        if remaining_budget(cfg, ticket, cost) < MIN_USEFUL_BUDGET:
            await _escalate(tracker, ticket, budget_message(cfg, ticket, cost), cost, ws.branch)
            return FixOutcome(Status.ESCALATED, ws.branch, cost_usd=cost, message="budget")
        try:
            model = pick_model(cfg, ticket, attempt)
            models_used.append(model)
            progress = Progress(f"fix {attempt}/{cfg.limits.max_attempts} {model.replace('claude-', '')}", report) if report else None
            if progress:
                progress("avvio")
            fix, spent, turns = await run_fix(
                cfg, ticket, ws, triage_notes, failure,
                budget_usd=remaining_budget(cfg, ticket, cost), model=model, progress=progress,
            )
            if progress:
                progress(f"fine: {fix.outcome}, {turns} turni, ${spent:.2f}")
        except Exception as e:
            await _escalate(tracker, ticket, f"agente di fix fallito: {e}", cost, ws.branch)
            return FixOutcome(Status.ESCALATED, ws.branch, cost_usd=cost, message=str(e))
        cost += spent

        if fix.outcome == "cannot_fix":
            patch = ws.discard_changes()
            reason = f"l'agente non ha trovato un fix sicuro: {fix.summary}"
            if patch:
                reason += f" (modifica non verificata scartata, salvata in {patch})"
            await _escalate(tracker, ticket, reason, cost, ws.branch)
            return FixOutcome(Status.ESCALATED, ws.branch, cost_usd=cost, message=fix.summary)

        files = ws.changed_files()
        if not files:
            failure = "No file was changed."
            continue
        if len(files) > cfg.limits.max_files:
            await _escalate(tracker, ticket, f"troppi file modificati ({len(files)} > {cfg.limits.max_files})", cost, ws.branch)
            return FixOutcome(Status.ESCALATED, ws.branch, cost_usd=cost, message="too many files")

        approved, note = await checkpoint(
            cfg.autonomy.checkpoints, "after_agent", f"L'agente ha finito ({len(files)} file): procedo con le verifiche?",
            {"files": files, "summary": fix.summary, "notes": fix.notes},
        )
        if not approved:
            ws.discard_changes()
            await _escalate(tracker, ticket, "modifica non approvata prima delle verifiche" + (f": {note}" if note else ""), cost, ws.branch)
            return FixOutcome(Status.ESCALATED, ws.branch, cost_usd=cost, message="rejected at checkpoint")

        ws.commit(f"fix: {ticket.title}\n\nTicket: {_notion_url(ticket.id)}")
        if report:
            report("verifica: gate di regressione e controlli...")
        checks = [regression_gate(cfg, ws), *run_checks(cfg, ws)]
        if report:
            for c in checks:
                report(f"verifica: {c.line()}")
        if all(c.ok for c in checks):
            break
        failure = "\n\n".join(f"{c.name}:\n{c.output}" for c in checks if not c.ok)
        git_soft_reset(ws)
    else:
        await _escalate(tracker, ticket, "verifiche fallite dopo tutti i tentativi:\n" + (failure or ""), cost, ws.branch)
        return FixOutcome(Status.ESCALATED, ws.branch, cost_usd=cost, checks=checks, message=failure or "")

    assert fix is not None
    risk, flags = _risk_for_changes(cfg, ws, Risk.LOW)
    files = ws_files_in_head(ws)
    summary = "\n".join(["Verifiche:", *[f"- {c.line()}" for c in checks], f"Modello: {' -> '.join(models_used)}"])
    approved, note = await checkpoint(
        cfg.autonomy.checkpoints, "before_pr",
        "Fix verificato: apro la pull request?" if cfg.pr.create else "Fix verificato: lo segno da rivedere?",
        {"files": files, "summary": fix.summary, "checks": [c.line() for c in checks], "risk": risk.value},
    )
    if not approved:
        await _escalate(tracker, ticket, "non approvato prima della pull request" + (f": {note}" if note else ""), cost, ws.branch)
        return FixOutcome(Status.ESCALATED, ws.branch, cost_usd=cost, checks=checks, message="rejected at checkpoint")

    if cfg.pr.create:
        ws.push()
        pr_url = await create_pull_request(cfg, ws.branch, f"fix: {ticket.title}", pr_body(ticket, fix, checks, risk, flags, files))
        await _publish(tracker, ticket, f"PR aperta: {pr_url}\n\n{fix.summary}\n\n{summary}")
        await tracker.update(ticket.id, pr_url=pr_url, branch=ws.branch, cost_usd=ticket.cost_usd + cost, risk=risk, verification="Passata")
        await tracker.set_status(ticket.id, Status.REVIEW)
        return FixOutcome(Status.REVIEW, ws.branch, pr_url, cost, checks)

    await _publish(
        tracker, ticket,
        f"Fix pronto e verificato in locale (push disabilitato).\nBranch: {ws.branch}\n\n{fix.summary}\n\n{summary}",
    )
    await tracker.update(ticket.id, branch=ws.branch, cost_usd=ticket.cost_usd + cost, risk=risk, verification="Passata")
    await tracker.set_status(ticket.id, Status.REVIEW)
    return FixOutcome(Status.REVIEW, ws.branch, None, cost, checks, message=str(ws.path))


def git_soft_reset(ws: Workspace) -> None:
    """Undo the verification commit but keep the changes so the agent can amend them."""
    from autodev.sandbox.workspace import git

    git(ws.path, "reset", "--quiet", "--soft", ws.start_ref)
    git(ws.path, "reset", "--quiet")


def ws_files_in_head(ws: Workspace) -> list[str]:
    from autodev.sandbox.workspace import git

    return git(ws.path, "diff", "--name-only", ws.base_ref, "HEAD").splitlines()
