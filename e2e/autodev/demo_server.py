"""Dashboard backed by fake data, for browser tests and screenshots (no Notion, no agents).

Run from the repo root:  uv run python e2e/autodev/demo_server.py <port> <db-path>
A run is left in progress and keeps appending events for a while, to exercise the live view.
"""
import asyncio
import sys
import threading
import tempfile
import time
from pathlib import Path

import uvicorn

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from autodev import engine as engine_mod  # noqa: E402
from autodev.db import Database  # noqa: E402
from autodev.engine import Engine  # noqa: E402
from autodev.models import Comment, Status, Ticket  # noqa: E402
from autodev.server.app import create_app  # noqa: E402
from tests.fixture_repo import make_project  # noqa: E402

NOW = time.time()
MIN = 60


def tickets() -> list[Ticket]:
    def t(i, title, status, **kw):
        return Ticket(id=f"t{i}", title=title, status=status, url=f"https://notion.so/t{i}", updated_at="2026-10-21T10:00:00+00:00", **kw)

    return [
        t(1, "Il pulsante Scarica non scarica nulla", Status.NEW, area="Export PDF", priority="Media"),
        t(2, "Firma del direttore obbligatoria solo se il progettista ha il nome", Status.ANALYZED, area="Autofill", risk="Medio", cost_usd=0.16),
        t(3, "Telefono o cellulare del progettista: basta uno", Status.ANALYZED, area="Autofill", risk="Basso", cost_usd=0.12),
        t(4, "Required and dependency fields logic", Status.IN_PROGRESS, area="Autofill", risk="Medio", model="Auto", attempts=1, cost_usd=3.56),
        t(5, "Il wizard perde i dati al ricarico dello step 4", Status.REVIEW, area="Wizard", risk="Basso", attempts=1, cost_usd=1.4, branch="autodev/wizard-perde-dati-a1b2c3", verification="Passata"),
        t(6, "Esporta ZIP vuoto con documenti secondari", Status.NEEDS_INFO, area="Export PDF", cost_usd=0.62),
        t(7, "Billing: il piano non si aggiorna dopo il pagamento", Status.ESCALATED, area="Billing", risk="Alto", attempts=3, cost_usd=5.9, agent_note="tetto di spesa per ticket raggiunto ($5.90 su $6.00)"),
        t(8, "Rubrica: duplicati dopo l'import", Status.CLOSED, area="Rubrica", cost_usd=0.9, verification="Passata"),
        t(9, "Il tema scuro dell'admin ha il testo illeggibile", Status.CLOSED, area="Admin"),
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
            update={"body": "Cosa succede\nNella pagina di dettaglio della order, cliccando il pulsante non parte nessun download.\n\nPassi\n1. Apri una order\n2. Clicca Scarica"}
        )
        return t, [
            Comment(author="autodev", is_bot=True, created_at="2026-10-21T09:00:00+00:00", text="Triage: ready (rischio Medio)\n\nIl ticket è chiaro. Causa probabile in export.py: prende il primo PDF compilabile senza ordinamento.\n\nFile coinvolti:\n- apps/backend/app/api/orders/export.py"),
            Comment(author="Christian Gatto", created_at="2026-10-21T09:10:00+00:00", text="Solo la SCIA SUE. Entrambi obbligatori."),
        ]


def seed(db: Database) -> int:
    def run(**kw):
        cols = dict(project="demo", status="done", started_at=NOW - 3 * 3600, finished_at=NOW - 3 * 3600 + 90, cost_usd=0.17, model="claude-haiku-5-5", outcome="analyzed", kind="triage", ticket_id="t2", ticket_title="Firma del direttore obbligatoria solo se il progettista ha il nome")
        cols.update(kw)
        return db.execute(f"INSERT INTO runs({','.join(cols)}) VALUES({','.join('?' * len(cols))})", tuple(cols.values()))

    def ev(rid, ts, typ, text):
        db.execute("INSERT INTO events(run_id, ts, type, text) VALUES(?,?,?,?)", (rid, ts, typ, text))

    r1 = run()
    for i, line in enumerate(["[0:04] haiku: avvio analisi", "[0:09] haiku:  1. legge data/knowledge_base/scia_sue_calabria_fields.json", "[0:15] haiku:  2. cerca 'required_group' in apps/backend", "[1:20] haiku: fine: ready, confidenza high, 8 turni, $0.17"]):
        ev(r1, NOW - 3 * 3600 + i * 20, "log", line)
    ev(r1, NOW - 3 * 3600 + 90, "result", "Triage: ready (rischio Medio)\n\nIl ticket è chiaro.\n\nFile coinvolti:\n- data/knowledge_base/scia_sue_calabria_fields.json")
    run(kind="fix", status="done", cost_usd=1.62, model="claude-sonnet-5-5", outcome="review", ticket_id="t5", ticket_title="Il wizard perde i dati al ricarico dello step 4", started_at=NOW - 50 * MIN, finished_at=NOW - 30 * MIN, branch="autodev/wizard-perde-dati-a1b2c3")
    r3 = run(kind="fix", status="failed", cost_usd=0.4, model="claude-sonnet-5-5", outcome=None, ticket_id="t7", ticket_title="Billing: il piano non si aggiorna dopo il pagamento", started_at=NOW - 20 * MIN, finished_at=NOW - 18 * MIN, error="agente di fix fallito: permesso Bash negato")
    ev(r3, NOW - 19 * MIN, "error", "agente di fix fallito: permesso Bash negato")
    live = run(kind="fix", status="running", cost_usd=0, model="claude-sonnet-5-5", outcome=None, ticket_id="t4", ticket_title="Required and dependency fields logic", started_at=NOW - 40, finished_at=None, pid=__import__("os").getpid())
    ev(live, NOW - 40, "started", "fix avviato")
    ev(live, NOW - 38, "log", "[0:02] workspace: checkout di demo (ripreso, 6 righe di storia), branch autodev/bug-required-and-dependency-fields-logic-400256")
    return live


async def feed(db: Database, run_id: int) -> None:
    """Keeps the 'running' run alive: one new action every second, then finishes."""
    steps = ["legge apps/frontend/app/(dashboard)/new/steps/use-step-editor/derive.ts", "cerca 'applyLiveDerive' in apps/frontend", "legge apps/frontend/app/(dashboard)/new/steps/use-step-editor/use-field-changes.ts", "scrive apps/frontend/app/(dashboard)/new/steps/use-step-editor/derive.test.ts", "esegue npm --prefix apps/frontend test -- derive.test.ts", "verifica: gate di regressione e controlli...", "verifica: PASS  regression test"]
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
        for line in ["legge il codice dell'area", "forma un'ipotesi", "fine: ready, confidenza high"]:
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
        for line in ["legge il file", "scrive il test", "esegue i test"]:
            report(line)
            await asyncio.sleep(1)
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
    tracker = FakeTracker()
    app = create_app(cfg, "demo", db, tracker, engine=Engine(cfg, "demo", db, tracker))
    print(f"SETUP_CODE={app.state.auth.setup_code}", flush=True)

    threading.Thread(target=lambda: asyncio.run(feed(db, live)), daemon=True).start()

    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")


if __name__ == "__main__":
    main()
