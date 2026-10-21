import argparse
import asyncio
import os
import subprocess
import sys
from pathlib import Path

import httpx
from dotenv import load_dotenv

from autodev.config import load_project
from autodev.db import Database
from autodev.engine import fix_job, triage_job
from autodev.jobs import DailyCapReached, RunCancelled, mark_orphans, run_tracked
from autodev.github import verify_access
from autodev.models import Status
from autodev.trackers.notion import NotionTracker


async def check(project: str) -> int:
    cfg = load_project(f"projects/{project}.yaml")
    token = os.environ.get("NOTION_TOKEN")
    if not token:
        print("NOTION_TOKEN missing in .env")
        return 1
    tracker = NotionTracker(cfg.tracker, token)
    try:
        props = await tracker.verify()
        print(f"Notion OK: data source reachable, {len(props)} properties")
        tickets = await tracker.fetch_ready()
        print(f"Ready tickets (status New + Authorized): {len(tickets)}")
        for t in tickets:
            print(f"  - {t.title} [{t.kind}/{t.area}/{t.priority}]")
        print(await verify_access(cfg))
    except httpx.HTTPStatusError as e:
        print(f"Notion error {e.response.status_code}: {e.response.text}")
        return 1
    finally:
        await tracker.aclose()
    return 0


async def explain_idle(tracker: NotionTracker, wanted: Status, wanted_label: str) -> None:
    """Say why nothing ran: list tickets sitting in other states and what to do with them."""
    labels = tracker._cfg.status_map
    print(f"No ticket in '{labels[wanted]}' with 'Authorized' ticked: nothing to do.")
    hints = {
        Status.NEW: "not authorised: tick 'Authorized'",
        Status.NEEDS_INFO: "answer with a comment and move it back to 'New'",
        Status.ANALYZED: "if the analysis convinces you, move it to 'In progress'",
        Status.ESCALATED: "see 'Agent notes' for the reason",
    }
    for status, hint in hints.items():
        if status == wanted and status != Status.NEW:
            continue
        for t in await tracker.fetch_by_status(status, authorized_only=(status != Status.NEW)):
            if status == Status.NEW and t.authorized:
                continue
            print(f"  - [{labels[status]}] {t.title}  ->  {hint}")


async def triage(project: str) -> int:
    cfg = load_project(f"projects/{project}.yaml")
    db = Database()
    mark_orphans(db)
    tracker = NotionTracker(cfg.tracker, os.environ["NOTION_TOKEN"])
    try:
        tickets = await tracker.fetch_ready()
        if not tickets:
            await explain_idle(tracker, Status.NEW, "triage")
        for ticket in tickets:
            print(f"Triage: {ticket.title}")
            try:
                work, summarize = triage_job(cfg, tracker, ticket)
                status, runs, comment = await run_tracked(
                    db, project=project, ticket=ticket, kind="triage", work=work, summarize=summarize,
                    daily_cap_usd=cfg.limits.daily_budget_usd,
                    echo=lambda line: print(f"  {line}", flush=True),
                )
            except (DailyCapReached, RunCancelled) as e:
                print(f"  stopped: {e}")
                break
            except Exception as e:
                print(f"  failed: {e}")
                continue
            detail = ", ".join(f"{r.model} {r.turns} turns ${r.cost_usd:.2f}" for r in runs) or "no agent run"
            print(f"\n{'-' * 60}\n{comment}\n{'-' * 60}")
            print(f"-> status: {status.value} ({detail})")
    finally:
        await tracker.aclose()
    return 0


async def fix(project: str) -> int:
    cfg = load_project(f"projects/{project}.yaml")
    db = Database()
    mark_orphans(db)
    tracker = NotionTracker(cfg.tracker, os.environ["NOTION_TOKEN"])
    try:
        tickets = await tracker.fetch_by_status(Status.IN_PROGRESS)
        if not tickets:
            await explain_idle(tracker, Status.IN_PROGRESS, "fix")
        for ticket in tickets:
            print(f"Fix: {ticket.title}")
            try:
                work, summarize = fix_job(cfg, tracker, ticket)
                outcome = await run_tracked(
                    db, project=project, ticket=ticket, kind="fix", work=work, summarize=summarize,
                    daily_cap_usd=cfg.limits.daily_budget_usd,
                    echo=lambda line: print(f"  {line}", flush=True),
                )
            except (DailyCapReached, RunCancelled) as e:
                print(f"  stopped: {e}")
                break
            except Exception as e:
                print(f"  failed: {e}")
                continue
            print(f"  -> {outcome.status.value} ${outcome.cost_usd:.2f} {outcome.branch or ''} {outcome.pr_url or ''}")
            for c in outcome.checks:
                print(f"     {c.line()}")
    finally:
        await tracker.aclose()
    return 0


async def cleanup(project: str, remote: bool, dry_run: bool, workspaces: bool) -> int:
    """Deletes agent branches already merged into the base branch (git or a merged pull request)."""
    import shutil

    from autodev import github
    from autodev.sandbox.workspace import WORKSPACES
    from autodev.server import repo

    cfg = load_project(f"projects/{project}.yaml")
    subprocess.run(["git", "fetch", "--prune", "--quiet", "origin"], cwd=cfg.local_path, check=False)
    pr_merged: set[str] = set()
    try:
        pr_merged = {p["branch"] for p in await github.list_pulls(cfg, cfg.branch_prefix) if p["state"] == "merged"}
    except Exception as e:
        print(f"Pull requests not read ({e}): using git state only (squash merges will not show)")
    names = repo.removable_branches(cfg, pr_merged)
    print("\n".join(f"{'[dry-run] ' if dry_run else ''}delete {n}" for n in names) or "No branches to delete.")
    if not dry_run:
        for n in repo.delete_branches(cfg, names, pr_merged):
            if remote and await github.delete_remote_branch(cfg, n):
                print(f"  rimosso anche su GitHub: {n}")
    if workspaces and WORKSPACES.is_dir():
        for d in sorted(p for p in WORKSPACES.iterdir() if p.is_dir()):
            print(f"{'[dry-run] ' if dry_run else ''}removing clone {d.name}")
            if not dry_run:
                shutil.rmtree(d)
    return 0


def serve(projects: list[str], port: int) -> int:
    """Serves the dashboard for the given projects, or for every file in projects/ when none is named."""
    import uvicorn

    from autodev.engine import Engine
    from autodev.server.app import Ctx, create_app

    token = os.environ.get("NOTION_TOKEN")
    if not token:
        print("NOTION_TOKEN missing in .env")
        return 1
    names = projects or sorted(p.stem for p in Path("projects").glob("*.yaml"))
    if not names:
        print("no project in projects/")
        return 1
    db = Database()

    def context(name: str) -> Ctx:
        cfg = load_project(f"projects/{name}.yaml")
        tracker = NotionTracker(cfg.tracker, token)
        return Ctx(cfg, name, db, tracker, Engine(cfg, name, db, tracker))

    first, *rest = (context(n) for n in names)
    app = create_app(first.cfg, first.project, db, first.tracker, engine=first.engine, run_loop=True, others=rest)
    code = app.state.auth.setup_code
    print(f"\nautodev dashboard: http://localhost:{port}")
    if code:
        print(f"First setup: on the page enter the code  {code}  and choose a password.\n")
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")
    return 0


def default_project() -> str:
    """The only project under projects/, so a single-project setup needs no --project flag."""
    names = sorted(p.stem for p in Path("projects").glob("*.yaml"))
    if len(names) != 1:
        sys.exit(f"pass --project (available: {', '.join(names) or 'none'})")
    return names[0]


def main() -> None:
    load_dotenv()
    parser = argparse.ArgumentParser(prog="autodev")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("check", help="verify tracker connectivity")
    p.add_argument("--project", default=None)
    t = sub.add_parser("triage", help="triage all ready tickets")
    t.add_argument("--project", default=None)
    f = sub.add_parser("fix", help="fix all approved tickets (status In lavorazione)")
    f.add_argument("--project", default=None)
    cl = sub.add_parser("cleanup", help="delete merged agent branches")
    cl.add_argument("--project", default=None)
    cl.add_argument("--remote", action="store_true", help="also delete them on GitHub")
    cl.add_argument("--dry-run", action="store_true")
    cl.add_argument("--workspaces", action="store_true", help="also remove leftover clones in workspaces/")
    sv = sub.add_parser("serve", help="start the local dashboard")
    sv.add_argument("--project", action="append", default=[], help="repeatable; default: every file in projects/")
    sv.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    if args.cmd != "serve":
        args.project = args.project or default_project()
    if args.cmd == "check":
        sys.exit(asyncio.run(check(args.project)))
    if args.cmd == "cleanup":
        sys.exit(asyncio.run(cleanup(args.project, args.remote, args.dry_run, args.workspaces)))
    if args.cmd == "serve":
        sys.exit(serve(args.project, args.port))
    if args.cmd == "fix":
        sys.exit(asyncio.run(fix(args.project)))
    if args.cmd == "triage":
        sys.exit(asyncio.run(triage(args.project)))


if __name__ == "__main__":
    main()
