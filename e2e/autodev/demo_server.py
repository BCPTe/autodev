"""Dashboard backed by fake data, for browser tests and screenshots (no Notion, no agents).

Run from the repo root:  uv run python e2e/autodev/demo_server.py <port> <db-path>
A run is left in progress and keeps appending events for a while, to exercise the live view.
"""
import asyncio
import sys
import threading
from types import SimpleNamespace
import tempfile
import time
from pathlib import Path

import uvicorn

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from autodev import engine as engine_mod  # noqa: E402
from autodev.control import checkpoint, current_control  # noqa: E402
from autodev.db import Database  # noqa: E402
from autodev.engine import Engine  # noqa: E402
from autodev.models import Comment, Status, Ticket  # noqa: E402
from autodev.server.app import Ctx, create_app  # noqa: E402
from tests.fixture_repo import make_project  # noqa: E402
from tests.test_repo_ops import agent_branch, git  # noqa: E402
from autodev import github  # noqa: E402

NOW = time.time()
MIN = 60


def tickets() -> list[Ticket]:
    def t(i, title, status, **kw):
        return Ticket(id=f"t{i}", title=title, status=status, url=f"https://notion.so/t{i}", updated_at="2026-10-21T10:00:00+00:00", **kw)

    return [
        t(1, "The Download button downloads nothing", Status.NEW, area="Export PDF", priority="Medium"),
        t(2, "Director signature required only if the designer has a name", Status.ANALYZED, area="Autofill", risk="Medium", cost_usd=0.16),
        t(3, "Designer phone or mobile: one is enough", Status.ANALYZED, area="Autofill", risk="Low", cost_usd=0.12),
        t(4, "Required and dependency fields logic", Status.IN_PROGRESS, area="Autofill", risk="Medium", model="Auto", attempts=1, cost_usd=3.56),
        t(5, "The wizard loses data when step 4 is reloaded", Status.REVIEW, area="Wizard", risk="Low", attempts=1, cost_usd=1.4, branch="autodev/wizard-perde-dati-a1b2c3", verification="Passed", pr_url="https://github.com/o/r/pull/12"),
        t(6, "ZIP export is empty with secondary documents", Status.NEEDS_INFO, area="Export PDF", cost_usd=0.62),
        t(7, "Billing: the plan does not update after payment", Status.ESCALATED, area="Billing", risk="High", attempts=3, cost_usd=5.9, agent_note="per-ticket spending cap reached ($5.90 of $6.00)"),
        t(8, "Address book: duplicates after import", Status.CLOSED, area="Rubrica", cost_usd=0.9, verification="Passed"),
        t(9, "The admin dark theme has unreadable text", Status.CLOSED, area="Admin"),
    ]


class FakeTracker:
    def __init__(self):
        self._t = tickets()

    async def list_all(self):
        return self._t

    async def set_status(self, ticket_id, status):
        next(t for t in self._t if t.id == ticket_id).status = status

    async def update(self, ticket_id, **kw):
        t = next(t for t in self._t if t.id == ticket_id)
        for k, v in kw.items():
            setattr(t, k, v)

    async def comment(self, ticket_id, text, *, as_human=False):
        self.comments = getattr(self, "comments", []) + [(ticket_id, text, as_human)]

    async def detail(self, ticket_id):
        t = next(t for t in self._t if t.id == ticket_id).model_copy(
            update={"body": "What happens\nOn the case detail page, clicking the button does not start any download.\n\nSteps\n1. Open a case\n2. Click Download"}
        )
        return t, [
            Comment(author="autodev", is_bot=True, created_at="2026-10-21T09:00:00+00:00", text="Triage: ready (risk Medium)\n\nThe ticket is clear. Probable cause in export.py: it takes the first fillable PDF without ordering.\n\nFiles involved:\n- apps/backend/app/api/orders/export.py"),
            Comment(author="Christian Gatto", created_at="2026-10-21T09:10:00+00:00", text="Only the SCIA SUE. Both are required."),
        ]


def seed(db: Database) -> int:
    def run(**kw):
        cols = dict(project="demo", status="done", started_at=NOW - 3 * 3600, finished_at=NOW - 3 * 3600 + 90, cost_usd=0.17, model="claude-haiku-5-5", outcome="analyzed", kind="triage", ticket_id="t2", ticket_title="Director signature required only if the designer has a name")
        cols.update(kw)
        return db.execute(f"INSERT INTO runs({','.join(cols)}) VALUES({','.join('?' * len(cols))})", tuple(cols.values()))

    def ev(rid, ts, typ, text):
        db.execute("INSERT INTO events(run_id, ts, type, text) VALUES(?,?,?,?)", (rid, ts, typ, text))

    r1 = run()
    for i, line in enumerate(["[0:04] haiku: avvio analisi", "[0:09] haiku:  1. legge data/knowledge_base/scia_sue_calabria_fields.json", "[0:15] haiku:  2. cerca 'required_group' in apps/backend", "[1:20] haiku: done: ready, confidence high, 8 turni, $0.17"]):
        ev(r1, NOW - 3 * 3600 + i * 20, "log", line)
    ev(r1, NOW - 3 * 3600 + 90, "result", "Triage: ready (risk Medium)\n\nThe ticket is clear.\n\nFiles involved:\n- data/knowledge_base/scia_sue_calabria_fields.json")
    run(kind="fix", status="done", cost_usd=1.62, model="claude-sonnet-5-5", outcome="review", ticket_id="t5", ticket_title="The wizard loses data when step 4 is reloaded", started_at=NOW - 50 * MIN, finished_at=NOW - 30 * MIN, branch="autodev/wizard-perde-dati-a1b2c3")
    r3 = run(kind="fix", status="failed", cost_usd=0.4, model="claude-sonnet-5-5", outcome=None, ticket_id="t7", ticket_title="Billing: the plan does not update after payment", started_at=NOW - 20 * MIN, finished_at=NOW - 18 * MIN, error="fix agent failed: Bash permission denied")
    ev(r3, NOW - 19 * MIN, "error", "fix agent failed: Bash permission denied")
    live = run(kind="fix", status="running", cost_usd=0, model="claude-sonnet-5-5", outcome=None, ticket_id="t4", ticket_title="Required and dependency fields logic", started_at=NOW - 40, finished_at=None, pid=__import__("os").getpid())
    ev(live, NOW - 40, "started", "fix started")
    ev(live, NOW - 38, "log", "[0:02] workspace: checkout of demo (resumed, 6 lines of history), branch autodev/bug-required-and-dependency-fields-logic-400256")
    return live


async def feed(db: Database, run_id: int) -> None:
    """Keeps the 'running' run alive: one new action every second, then finishes."""
    steps = ["reads apps/frontend/app/(dashboard)/new/steps/use-step-editor/derive.ts", "searches 'applyLiveDerive' in apps/frontend", "reads apps/frontend/app/(dashboard)/new/steps/use-step-editor/use-field-changes.ts", "writes apps/frontend/app/(dashboard)/new/steps/use-step-editor/derive.test.ts", "runs npm --prefix apps/frontend test -- derive.test.ts", "verification: regression gate and checks...", "verification: PASS  regression test"]
    for i, step in enumerate(steps):
        await asyncio.sleep(1.2)
        db.execute("INSERT INTO events(run_id, ts, type, text) VALUES(?,?,?,?)", (run_id, time.time(), "log", f"[0:{10 + i * 5:02d}] fix 1/3 sonnet-5-5: {i + 1:>2}. {step}"))
    await asyncio.sleep(1.2)
    db.execute("UPDATE runs SET status='done', finished_at=?, cost_usd=1.1, outcome='review' WHERE id=?", (time.time(), run_id))
    db.execute("INSERT INTO events(run_id, ts, type, text) VALUES(?,?,?,?)", (run_id, time.time(), "result", "PASS  regression test\nPASS  backend tests"))
    db.execute("INSERT INTO events(run_id, ts, type, text) VALUES(?,?,?,?)", (run_id, time.time(), "finished", "review"))


def fake_agents() -> None:
    """Triage and fix that only narrate and move the ticket, so the controls can be exercised."""

    async def triage(cfg, tracker, ticket, report=None):
        for line in ["reads the area's code", "forms a hypothesis", "done: ready, confidence high"]:
            report(line)
            await asyncio.sleep(1)
        await tracker.set_status(ticket.id, Status.ANALYZED)
        return Status.ANALYZED, [], "Triage: ready (demo)"

    class Outcome:
        status = Status.REVIEW
        cost_usd = 0.4
        models = ["claude-sonnet-5-5"]
        branch = "autodev/demo"
        pr_url = None
        checks = []
        message = "demo"

    async def fix(cfg, tracker, ticket, report=None):
        control = current_control.get()
        for line in ["reads the file", "writes the test"]:
            report(line)
            await asyncio.sleep(1)
        if control:
            verdict = await control.can_use_tool("Bash", {"command": "docker compose ps"}, SimpleNamespace(title=None))
            report("permission " + verdict.behavior)
            for _ in range(40):  # long enough to be paused or spoken to
                await asyncio.sleep(0.5)
                if control.take_interrupt():
                    report("message received: " + await control.next_instruction())
                    break
        approved, note = await checkpoint(["before_pr"], "before_pr", "Fix verified: open the pull request?", {"files": ["apps/frontend/derive.ts"], "summary": "Demo", "checks": ["PASS  regression test"]})
        if not approved:
            await tracker.set_status(ticket.id, Status.ESCALATED)
            return Outcome()
        await tracker.set_status(ticket.id, Status.REVIEW)
        return Outcome()

    engine_mod.triage_ticket, engine_mod.fix_ticket = triage, fix


def main() -> None:
    port, db_path = int(sys.argv[1]), sys.argv[2]
    Path(db_path).unlink(missing_ok=True)
    db = Database(db_path)
    cfg = make_project(Path(tempfile.mkdtemp(prefix="autodev-demo-")))
    live = seed(db)
    fake_agents()
    cfg.pr.slug = "o/r"
    git(cfg.local_path, "fetch", "-q")
    agent_branch(cfg, "autodev/wizard-perde-dati-a1b2c3", "def apply_discount(price, percent):\n    return price * (1 - percent / 100)\n")
    agent_branch(cfg, "autodev/rubrica-duplicati-ff00aa", "RUBRICA = True\n", merge=True)

    def pr(n, branch, title, state="open", verdict="passing", body=""):
        return {"number": n, "title": title, "url": f"https://github.com/o/r/pull/{n}", "branch": branch, "state": state, "draft": False, "body": body,
                "updated_at": "2026-10-21T09:30:00Z", "author": "bot", "mergeable": True,
                "checks": {"verdict": verdict, "total": 3, "failed": 0, "pending": 0} if state == "open" else None}

    async def list_pulls(cfg, prefix, limit=30):
        return [
            pr(12, "autodev/wizard-perde-dati-a1b2c3", "fix: The wizard loses data when step 4 is reloaded", body="## Checks\n- PASS  regression test\n- PASS  backend tests\n\n## Risk: Low"),
            pr(9, "autodev/rubrica-duplicati-ff00aa", "fix: Address book: duplicates after import", state="merged"),
        ]

    async def merge_pull(cfg, number, method="squash"):
        return "sha"

    async def delete_remote_branch(cfg, branch):
        return True

    github.list_pulls, github.merge_pull, github.delete_remote_branch = list_pulls, merge_pull, delete_remote_branch
    tracker = FakeTracker()
    other_cfg = cfg.model_copy(deep=True)
    other_tracker = FakeTracker()
    other_tracker._t = other_tracker._t[:3]
    other = Ctx(other_cfg, "gestionale", db, other_tracker, Engine(other_cfg, "gestionale", db, other_tracker))
    app = create_app(cfg, "demo", db, tracker, engine=Engine(cfg, "demo", db, tracker), others=[other])
    print(f"SETUP_CODE={app.state.auth.setup_code}", flush=True)

    threading.Thread(target=lambda: asyncio.run(feed(db, live)), daemon=True).start()

    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")


if __name__ == "__main__":
    main()
