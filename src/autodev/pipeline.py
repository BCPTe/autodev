from pathlib import Path

import httpx

from autodev import knowledge
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
    return f"per-ticket spending cap reached (${spent:.2f} of ${cfg.limits.budget_usd_per_ticket:.2f})"


def prefilter(cfg: ProjectConfig, ticket: Ticket) -> str | None:
    """Cheap checks that avoid launching an agent on tickets that cannot be analysed."""
    if len(ticket.body.strip()) < cfg.min_body_chars:
        return (
            "The ticket does not have a sufficient description. Say what happened, the steps to reproduce it "
            "and the expected behaviour, then move the ticket back to New."
        )
    return None


def format_comment(result: TriageResult, risk: str, runs: list[RunInfo]) -> str:
    lines = [f"Triage: {result.verdict} (risk {risk})", "", result.analysis]
    if result.suspected_files:
        lines += ["", "Files involved:", *[f"- {f}" for f in dict.fromkeys(result.suspected_files)]]
    if result.questions:
        lines += ["", "Questions (needed to proceed):", *[f"- {q}" for q in result.questions]]
    if result.assumptions:
        lines += ["", "Assumptions to confirm in review (not blocking):", *[f"- {a}" for a in result.assumptions]]
    if result.suggested_test:
        lines += ["", f"Suggested test: {result.suggested_test}"]
    if result.playbook_cited:
        lines += ["", "Playbook entries used: " + ", ".join(result.playbook_cited)]
    lines += ["", "Run: " + " -> ".join(f"{r.model} ({r.turns} turns, ${r.cost_usd:.2f})" for r in runs)]
    return "\n".join(lines)


async def _publish(tracker: Tracker, ticket: Ticket, text: str) -> None:
    try:
        await tracker.comment(ticket.id, text)
    except httpx.HTTPStatusError:
        await tracker.update(ticket.id, agent_note=text)


async def _escalate_triage(tracker: Tracker, ticket: Ticket, reason: str) -> None:
    await _publish(tracker, ticket, f"Triage not run: {reason}")
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
        earlier = [c for c in await tracker.bot_comments(ticket.id) if c.startswith("Triage:")]
        result, runs = await run_triage(
            cfg, ticket, report, budget_usd=remaining_budget(cfg, ticket), previous=earlier[-1][:6000] if earlier else None
        )
    except Exception as e:
        await tracker.update(ticket.id, agent_note=f"Triage failed: {e}")
        await tracker.set_status(ticket.id, Status.ESCALATED)
        raise

    risk: Risk = escalate_risk(result, cfg)
    comment = format_comment(result, risk.value, runs)
    await _publish(tracker, ticket, comment)
    await tracker.update(ticket.id, risk=risk, cost_usd=ticket.cost_usd + sum(r.cost_usd for r in runs))
    status = VERDICT_STATUS[result.verdict]
    if result.verdict == "not_reproducible":
        await tracker.update(ticket.id, agent_note="Closed by triage: not reproducible")
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
    turns: int = 0
    playbook: list[str] = field(default_factory=list)


def _notion_url(ticket_id: str) -> str:
    return f"https://www.notion.so/{ticket_id.replace('-', '')}"


def _risk_for_changes(cfg: ProjectConfig, ws: Workspace, base: Risk) -> tuple[Risk, list[str]]:
    flags = []
    risk = base
    touched = [f for f in ws.changed_files(ws.base_ref) if matches(f, cfg.risk.never_automerge)]
    if touched:
        risk = Risk.HIGH
        flags.append(f"touches high-risk files: {', '.join(touched)}")
    test_globs = [g for reg in cfg.regressions for g in reg.test_globs]
    if test_globs and any(matches(f, test_globs) for f in ws.modified_existing()):
        risk = Risk.HIGH
        flags.append("modifies existing tests")
    return risk, flags


def pr_body(ticket: Ticket, fix: FixResult, checks: list[CheckResult], risk: Risk, flags: list[str], files: list[str]) -> str:
    lines = [
        f"Ticket: {_notion_url(ticket.id)}",
        "",
        "## What changes",
        fix.summary,
        "",
        "## Automatic checks",
        *[f"- {c.line()}" for c in checks],
        "",
        f"## Risk: {risk.value}",
        *[f"- {f}" for f in flags],
    ]
    if any(f.startswith("apps/frontend") for f in files):
        lines += ["", "**Check by hand in the UI**: frontend changes are not covered by automated tests."]
    if fix.notes:
        lines += ["", "## Agent notes", fix.notes]
    lines += ["", "Changed files:", *[f"- `{f}`" for f in files], "", "Generated by autodev."]
    return "\n".join(lines)


async def _escalate(
    tracker: Tracker, ticket: Ticket, reason: str, cost: float, branch: str | None = None, verification: str | None = "Failed"
) -> None:
    await _publish(tracker, ticket, f"Fix not completed: {reason}")
    await tracker.update(
        ticket.id, agent_note=reason, cost_usd=ticket.cost_usd + cost, branch=branch, verification=verification
    )
    await tracker.set_status(ticket.id, Status.ESCALATED)


async def fix_ticket(
    cfg: ProjectConfig, tracker: Tracker, ticket: Ticket, report: Report | None = None
) -> FixOutcome:
    if ticket.attempts >= cfg.limits.max_fix_runs:
        await _escalate(tracker, ticket, f"already run {ticket.attempts} times (limit {cfg.limits.max_fix_runs}); reset 'Attempts' to try again", 0.0)
        return FixOutcome(Status.ESCALATED, message="max fix runs")

    if remaining_budget(cfg, ticket) < MIN_USEFUL_BUDGET:
        await _escalate(tracker, ticket, budget_message(cfg, ticket), 0.0)
        return FixOutcome(Status.ESCALATED, message="budget")

    ws = Workspace.create(cfg, ticket)
    await tracker.update(ticket.id, attempts=ticket.attempts + 1)
    if report:
        where = f"checkout of {cfg.name or Path(cfg.local_path).name}" if ws.inplace else ws.path.name
        report(f"workspace: {where} ({'resumed, ' + str(len(ws.history().splitlines())) + ' lines of history' if ws.resumed else 'new'}), branch {ws.branch}")
    models_used: list[str] = []
    stats = {"turns": 0}
    triage_notes = await tracker.bot_comments(ticket.id)
    playbook = knowledge.playbook_for(cfg, ticket, "\n".join(triage_notes))
    try:
        outcome = await _fix_in_workspace(cfg, tracker, ticket, report, ws, models_used, triage_notes, playbook, stats)
        outcome.models = models_used
        outcome.turns = stats["turns"]
        outcome.playbook = playbook.ids
        return outcome
    finally:
        _publish_local(cfg, ws, report)


def _publish_local(cfg: ProjectConfig, ws: Workspace, report: Report | None) -> None:
    """Whatever happened, expose the agent's commits as a branch in the user's repo."""
    say = report or (lambda _line: None)
    if ws.inplace:
        if ws.has_commits():
            say(f"the checkout {ws.path} is now on branch {ws.branch}; to go back: git checkout {cfg.base_branch}")
        return
    if not ws.has_commits():
        return
    try:
        ws.publish_local(cfg.local_path)
        say(f"branch published in {cfg.local_path}: git checkout {ws.branch}")
    except RuntimeError as e:
        say(f"branch not published in {cfg.local_path}: {e}")


async def _fix_in_workspace(
    cfg: ProjectConfig, tracker: Tracker, ticket: Ticket, report: Report | None, ws: Workspace,
    models_used: list[str], triage_notes: list[str], playbook: knowledge.Playbook, stats: dict,
) -> FixOutcome:
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
                progress("starting")
            fix, spent, turns = await run_fix(
                cfg, ticket, ws, triage_notes, failure,
                budget_usd=remaining_budget(cfg, ticket, cost), model=model, progress=progress, playbook=playbook,
            )
            stats["turns"] += turns
            if progress:
                progress(f"done: {fix.outcome}, {turns} turns, ${spent:.2f}")
        except Exception as e:
            await _escalate(tracker, ticket, f"fix agent failed: {e}", cost, ws.branch)
            return FixOutcome(Status.ESCALATED, ws.branch, cost_usd=cost, message=str(e))
        cost += spent

        if fix.outcome == "cannot_fix":
            patch = ws.discard_changes()
            reason = f"the agent could not find a safe fix: {fix.summary}"
            if patch:
                reason += f" (unverified change discarded, saved in {patch})"
            await _escalate(tracker, ticket, reason, cost, ws.branch)
            return FixOutcome(Status.ESCALATED, ws.branch, cost_usd=cost, message=fix.summary)

        files = ws.changed_files()
        if not files:
            failure = "No file was changed."
            continue
        if len(files) > cfg.limits.max_files:
            await _escalate(tracker, ticket, f"too many files changed ({len(files)} > {cfg.limits.max_files})", cost, ws.branch)
            return FixOutcome(Status.ESCALATED, ws.branch, cost_usd=cost, message="too many files")

        approved, note = await checkpoint(
            cfg.autonomy.checkpoints, "after_agent", f"The agent has finished ({len(files)} files): run the verification?",
            {"files": files, "summary": fix.summary, "notes": fix.notes},
        )
        if not approved:
            if note and attempt < cfg.limits.max_attempts:
                failure = _reviewer_feedback(note)
                if report:
                    report("the reviewer asked for changes: the agent continues with the feedback")
                continue
            ws.discard_changes()
            await _escalate(tracker, ticket, "change not approved before verification" + (f": {note}" if note else ""), cost, ws.branch, verification="Not run")
            return FixOutcome(Status.ESCALATED, ws.branch, cost_usd=cost, message="rejected at checkpoint")

        ws.commit(f"fix: {ticket.title}\n\nTicket: {_notion_url(ticket.id)}")
        if report:
            report("verification: regression gate and checks...")
        checks = [regression_gate(cfg, ws), *run_checks(cfg, ws)]
        if report:
            for c in checks:
                report(f"verification: {c.line()}")
        if all(c.ok for c in checks):
            risk, flags = _risk_for_changes(cfg, ws, Risk.LOW)
            files = ws_files_in_head(ws)
            approved, note = await checkpoint(
                cfg.autonomy.checkpoints, "before_pr",
                "Fix verified: open the pull request?" if cfg.pr.create else "Fix verified: mark it for review?",
                {"files": files, "summary": fix.summary, "checks": [c.line() for c in checks], "risk": risk.value},
            )
            if approved:
                break
            if not note or attempt >= cfg.limits.max_attempts:
                await _escalate(
                    tracker, ticket, "not approved before the pull request" + (f": {note}" if note else ""), cost, ws.branch,
                    verification="Passed",
                )
                return FixOutcome(Status.ESCALATED, ws.branch, cost_usd=cost, checks=checks, message="rejected at checkpoint")
            failure = _reviewer_feedback(note)
            if report:
                report("the reviewer asked for changes: the agent continues with the feedback")
            git_soft_reset(ws)
            continue
        failure = "\n\n".join(f"{c.name}:\n{c.output}" for c in checks if not c.ok)
        git_soft_reset(ws)
    else:
        await _escalate(tracker, ticket, "verification failed after all attempts:\n" + (failure or ""), cost, ws.branch)
        return FixOutcome(Status.ESCALATED, ws.branch, cost_usd=cost, checks=checks, message=failure or "")

    assert fix is not None
    summary = "\n".join(["Checks:", *[f"- {c.line()}" for c in checks], f"Model: {' -> '.join(models_used)}"])

    if cfg.pr.create:
        try:
            ws.push()
            pr_url = await create_pull_request(cfg, ws.branch, f"fix: {ticket.title}", pr_body(ticket, fix, checks, risk, flags, files))
        except (RuntimeError, httpx.HTTPError) as e:
            await _escalate(
                tracker, ticket,
                f"the fix is verified and committed on {ws.branch}, but the pull request could not be opened: {e}. "
                "Fix the cause, then press 'Open PR' on the ticket (no agent run needed).",
                cost, ws.branch, verification="Passed",
            )
            return FixOutcome(Status.ESCALATED, ws.branch, cost_usd=cost, checks=checks, message=str(e))
        await _publish(tracker, ticket, f"PR opened: {pr_url}\n\n{fix.summary}\n\n{summary}")
        await tracker.update(ticket.id, pr_url=pr_url, branch=ws.branch, cost_usd=ticket.cost_usd + cost, risk=risk, verification="Passed")
        await tracker.set_status(ticket.id, Status.REVIEW)
        return FixOutcome(Status.REVIEW, ws.branch, pr_url, cost, checks)

    await _publish(
        tracker, ticket,
        f"Fix ready and verified locally (push disabled).\nBranch: {ws.branch}\n\n{fix.summary}\n\n{summary}",
    )
    await tracker.update(ticket.id, branch=ws.branch, cost_usd=ticket.cost_usd + cost, risk=risk, verification="Passed")
    await tracker.set_status(ticket.id, Status.REVIEW)
    return FixOutcome(Status.REVIEW, ws.branch, None, cost, checks, message=str(ws.path))


async def publish_ticket(cfg: ProjectConfig, tracker: Tracker, ticket: Ticket, report: Report | None = None) -> FixOutcome:
    """Opens the pull request for a branch that already holds a verified fix (no agent involved).

    Used when the PR step failed (token, network) after the work was done. The checks are run again;
    the regression gate cannot be, because it needs the run that added the tests.
    """
    say = report or (lambda _line: None)
    ws = Workspace.create(cfg, ticket)
    if not ws.has_commits():
        raise RuntimeError(f"branch {ws.branch} has no commits to publish")
    say(f"checking {ws.branch} before opening the pull request...")
    checks = run_checks(cfg, ws)
    for c in checks:
        say(f"verification: {c.line()}")
    if not all(c.ok for c in checks):
        raise RuntimeError("checks fail on the branch:\n" + "\n".join(f"{c.name}:\n{c.output}" for c in checks if not c.ok))
    risk, flags = _risk_for_changes(cfg, ws, Risk.LOW)
    files = ws_files_in_head(ws)
    last = ws.history().splitlines()[0] if ws.history() else ticket.title
    fix = FixResult(outcome="fixed", summary=f"{last}\n\nOpened by autodev after the first attempt to open it failed.", notes="")
    if not cfg.pr.create:
        raise RuntimeError("pr.create is off in the project file")
    ws.push()
    pr_url = await create_pull_request(cfg, ws.branch, f"fix: {ticket.title}", pr_body(ticket, fix, checks, risk, flags, files))
    await _publish(tracker, ticket, f"PR opened: {pr_url}")
    await tracker.update(ticket.id, pr_url=pr_url, branch=ws.branch, risk=risk, verification="Passed")
    await tracker.set_status(ticket.id, Status.REVIEW)
    return FixOutcome(Status.REVIEW, ws.branch, pr_url, 0.0, checks)


def _reviewer_feedback(note: str) -> str:
    return f"A human reviewer rejected the result and asked for this change:\n{note}"


def git_soft_reset(ws: Workspace) -> None:
    """Undo the verification commit but keep the changes so the agent can amend them."""
    from autodev.sandbox.workspace import git

    git(ws.path, "reset", "--quiet", "--soft", ws.start_ref)
    git(ws.path, "reset", "--quiet")


def ws_files_in_head(ws: Workspace) -> list[str]:
    from autodev.sandbox.workspace import git

    return git(ws.path, "diff", "--name-only", ws.base_ref, "HEAD").splitlines()
