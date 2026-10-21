import argparse
import asyncio
import os
import sys

import httpx
from dotenv import load_dotenv

from autodev.config import load_project
from autodev.models import Status
from autodev.pipeline import fix_ticket, triage_ticket
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
        print(f"Ready tickets (status Nuovo + Autorizzato): {len(tickets)}")
        for t in tickets:
            print(f"  - {t.title} [{t.kind}/{t.area}/{t.priority}]")
    except httpx.HTTPStatusError as e:
        print(f"Notion error {e.response.status_code}: {e.response.text}")
        return 1
    finally:
        await tracker.aclose()
    return 0


async def explain_idle(tracker: NotionTracker, wanted: Status, wanted_label: str) -> None:
    """Say why nothing ran: list tickets sitting in other states and what to do with them."""
    labels = tracker._cfg.status_map
    print(f"Nessun ticket in '{labels[wanted]}' con 'Autorizzato' spuntato: niente da fare.")
    hints = {
        Status.NEW: "non autorizzato: spunta 'Autorizzato'",
        Status.NEEDS_INFO: "rispondi con un commento e riportalo in 'Nuovo'",
        Status.ANALYZED: "se l'analisi ti convince, spostalo in 'In lavorazione'",
        Status.ESCALATED: "guarda 'Note agente' per il motivo",
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
    tracker = NotionTracker(cfg.tracker, os.environ["NOTION_TOKEN"])
    try:
        tickets = await tracker.fetch_ready()
        if not tickets:
            await explain_idle(tracker, Status.NEW, "triage")
        for ticket in tickets:
            print(f"Triage: {ticket.title}")
            try:
                status, runs, comment = await triage_ticket(cfg, tracker, ticket, report=lambda line: print(f"  {line}", flush=True))
            except Exception as e:
                print(f"  failed: {e}")
                continue
            detail = ", ".join(f"{r.model} {r.turns} turns ${r.cost_usd:.2f}" for r in runs) or "no agent run"
            print(f"\n{'-' * 60}\n{comment}\n{'-' * 60}")
            print(f"-> stato: {status.value} ({detail})")
    finally:
        await tracker.aclose()
    return 0


async def fix(project: str) -> int:
    cfg = load_project(f"projects/{project}.yaml")
    tracker = NotionTracker(cfg.tracker, os.environ["NOTION_TOKEN"])
    try:
        tickets = await tracker.fetch_by_status(Status.IN_PROGRESS)
        if not tickets:
            await explain_idle(tracker, Status.IN_PROGRESS, "fix")
        for ticket in tickets:
            print(f"Fix: {ticket.title}")
            try:
                outcome = await fix_ticket(cfg, tracker, ticket, report=lambda line: print(f"  {line}", flush=True))
            except Exception as e:
                print(f"  failed: {e}")
                continue
            print(f"  -> {outcome.status.value} ${outcome.cost_usd:.2f} {outcome.branch or ''} {outcome.pr_url or ''}")
            for c in outcome.checks:
                print(f"     {c.line()}")
    finally:
        await tracker.aclose()
    return 0


def main() -> None:
    load_dotenv()
    parser = argparse.ArgumentParser(prog="autodev")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("check", help="verify tracker connectivity")
    p.add_argument("--project", default="demo")
    t = sub.add_parser("triage", help="triage all ready tickets")
    t.add_argument("--project", default="demo")
    f = sub.add_parser("fix", help="fix all approved tickets (status In lavorazione)")
    f.add_argument("--project", default="demo")
    args = parser.parse_args()
    if args.cmd == "check":
        sys.exit(asyncio.run(check(args.project)))
    if args.cmd == "fix":
        sys.exit(asyncio.run(fix(args.project)))
    if args.cmd == "triage":
        sys.exit(asyncio.run(triage(args.project)))


if __name__ == "__main__":
    main()
