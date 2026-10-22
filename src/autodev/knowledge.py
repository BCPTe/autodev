"""The project's playbook: short facts about the codebase that agents read before they work.

`projects/<name>.knowledge.md` is the source of truth, written for humans and parsed by machines:

    ## where
    - The PDF export lives in export.py. <!-- {"id":"k1a2b3","source":"<ticket id>","title":"...","date":"2026-10-22","area":"Export PDF","paths":["apps/backend/app/api/export.py"]} -->

One section per category, one bullet per entry; the trailing comment is optional (a bullet written by hand is
an entry too). Nothing enters the file without a human accepting a proposal, which lives in the `learnings` table.
"""
import hashlib
import json
import re
import threading
import uuid
from dataclasses import asdict, dataclass, field
from datetime import date
from pathlib import Path

from autodev.config import ProjectConfig
from autodev.db import Database, now
from autodev.models import Ticket

CATEGORIES = ("where", "domain", "gotcha", "command")
MAX_TEXT = 500

_LOCK = threading.Lock()
_BULLET = re.compile(r"^-\s+(.*?)\s*(?:<!--\s*(\{.*\})\s*-->)?\s*$")
_SECTION = re.compile(r"^##\s+(\w+)\s*$")
_PATH = re.compile(r"(?<![\w/.-])((?:[\w.-]+/)+[\w.-]+\.\w{1,6})")
_SECRET = [re.compile(p, re.I) for p in (
    r"\bsk-[a-z0-9_-]{16,}", r"\bgh[pousr]_[a-z0-9]{20,}", r"\bAKIA[0-9A-Z]{12,}", r"\beyJ[\w-]{15,}\.[\w-]{10,}",
    r"\b(password|passwd|secret|token|api[_-]?key)\b\s*[:=]\s*\S{4,}", r"\b[a-f0-9]{40,}\b", r"-----BEGIN [A-Z ]*PRIVATE KEY",
)]


@dataclass
class Entry:
    id: str
    category: str
    text: str
    source_id: str = ""
    source_title: str = ""
    date: str = ""
    area: str = ""
    paths: list[str] = field(default_factory=list)

    def prompt_line(self) -> str:
        line = f"- [{self.id}] ({self.category}) {self.text}"
        return line + (f" (paths: {', '.join(self.paths)})" if self.paths else "")


@dataclass
class Playbook:
    text: str = ""
    ids: list[str] = field(default_factory=list)


def enabled(cfg: ProjectConfig) -> bool:
    return cfg.knowledge.enabled and bool(cfg.knowledge_path)


def new_id() -> str:
    return "k" + uuid.uuid4().hex[:6]


def clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()[:MAX_TEXT]


def looks_secret(text: str) -> bool:
    return any(p.search(text) for p in _SECRET)


def parse(text: str) -> tuple[str, list[Entry]]:
    """Returns the free text before the first category section, and the entries."""
    preamble: list[str] = []
    entries: list[Entry] = []
    category: str | None = None
    seen_section = False
    for line in text.splitlines():
        m = _SECTION.match(line)
        if m:
            name = m.group(1).lower()
            category = name if name in CATEGORIES else None
            seen_section = seen_section or category is not None
            continue
        if not seen_section:
            preamble.append(line)
            continue
        b = _BULLET.match(line)
        if category and b and b.group(1):
            try:
                meta = json.loads(b.group(2)) if b.group(2) else {}
            except ValueError:
                meta = {}
            body = clean_text(b.group(1))
            entries.append(Entry(
                id=str(meta.get("id") or "k" + hashlib.sha1(f"{category}{body}".encode()).hexdigest()[:6]),
                category=category, text=body, source_id=str(meta.get("source") or ""), source_title=str(meta.get("title") or ""),
                date=str(meta.get("date") or ""), area=str(meta.get("area") or ""), paths=[str(p) for p in meta.get("paths") or []],
            ))
    return "\n".join(preamble).strip(), entries


def render(preamble: str, entries: list[Entry]) -> str:
    parts = [preamble.strip()] if preamble.strip() else []
    for category in CATEGORIES:
        lines = [f"## {category}"]
        for e in (e for e in entries if e.category == category):
            meta = {"id": e.id, "source": e.source_id, "title": e.source_title, "date": e.date, "area": e.area, "paths": e.paths}
            meta = {k: v for k, v in meta.items() if v}
            blob = json.dumps(meta, ensure_ascii=False, separators=(",", ":")).replace(">", "\\u003e")
            lines.append(f"- {e.text} <!-- {blob} -->")
        parts.append("\n".join(lines))
    return "\n\n".join(parts) + "\n"


def load(cfg: ProjectConfig) -> tuple[str, list[Entry]]:
    path = Path(cfg.knowledge_path) if cfg.knowledge_path else None
    if not path or not path.is_file():
        return "", []
    return parse(path.read_text())


def _write(cfg: ProjectConfig, preamble: str, entries: list[Entry]) -> None:
    path = Path(cfg.knowledge_path)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(render(preamble, entries))
    tmp.replace(path)


def add_entry(cfg: ProjectConfig, entry: Entry) -> Entry:
    if entry.category not in CATEGORIES:
        raise ValueError(f"category must be one of {', '.join(CATEGORIES)}")
    entry.text = clean_text(entry.text)
    if not entry.text:
        raise ValueError("the entry is empty")
    if looks_secret(entry.text):
        raise ValueError("the entry looks like it contains a secret")
    with _LOCK:
        preamble, entries = load(cfg)
        if not preamble:
            preamble = f"# {cfg.name or Path(cfg.knowledge_path).name.split('.')[0]} playbook\n\nFacts the agents read before they work. Edit freely; autodev rewrites this file in this format."
        entry.id = entry.id or new_id()
        entry.date = entry.date or date.today().isoformat()
        _write(cfg, preamble, [*entries, entry])
    return entry


def delete_entry(cfg: ProjectConfig, entry_id: str) -> bool:
    with _LOCK:
        preamble, entries = load(cfg)
        kept = [e for e in entries if e.id != entry_id]
        if len(kept) == len(entries):
            return False
        _write(cfg, preamble, kept)
    return True


def paths_in(text: str) -> list[str]:
    return list(dict.fromkeys(_PATH.findall(text)))


def _overlap(entry_path: str, wanted: str) -> bool:
    a, b = entry_path.rstrip("/*"), wanted.rstrip("/")
    return a == b or b.startswith(a + "/") or a.startswith(b + "/")


def select(entries: list[Entry], area: str | None, paths: list[str], max_chars: int) -> list[Entry]:
    """Entries for the ticket's area and paths first, then the most recent, as many as fit in `max_chars`."""
    def score(e: Entry) -> int:
        s = 2 if area and e.area and e.area.casefold() == area.casefold() else 0
        return s + (3 if any(_overlap(ep, p) for ep in e.paths for p in paths) else 0)

    order = sorted(range(len(entries)), key=lambda i: (score(entries[i]), entries[i].date, i), reverse=True)
    chosen, used = [], 0
    for i in order:
        size = len(entries[i].prompt_line()) + 1
        if used + size <= max_chars:
            chosen.append(entries[i])
            used += size
    return chosen


def playbook_for(cfg: ProjectConfig, ticket: Ticket, extra_text: str = "") -> Playbook:
    """The playbook text for a prompt, plus the ids of the entries in it (to record what was used)."""
    if not enabled(cfg):
        return Playbook()
    _, entries = load(cfg)
    mentioned = paths_in(f"{ticket.title}\n{ticket.body}\n{extra_text}")
    chosen = select(entries, ticket.area, mentioned, cfg.knowledge.max_chars)
    return Playbook("\n".join(e.prompt_line() for e in chosen), [e.id for e in chosen])


def section(playbook: Playbook) -> str:
    """The block appended to a system prompt (empty when there is nothing to say)."""
    if not playbook.text:
        return ""
    return (
        "\n\n# Project playbook\nFacts about this project, kept by its maintainers: trust them over your guesses. "
        "Each entry has an id in brackets.\n" + playbook.text
    )


def missing_paths(cfg: ProjectConfig, paths: list[str]) -> list[str]:
    """Paths that do not exist in the checkout (absolute or escaping ones count as missing)."""
    root = Path(cfg.local_path).resolve()
    missing = []
    for p in paths:
        if p.startswith("/") or ".." in Path(p).parts:
            missing.append(p)
        elif "*" in p:
            if not any(True for _ in root.glob(p)):
                missing.append(p)
        elif not (root / p).exists():
            missing.append(p)
    return missing


# ---- proposals and usage (SQLite) --------------------------------------------------------------
def propose(db: Database, cfg: ProjectConfig, project: str, ticket: Ticket, run_id: int | None, items: list[dict]) -> int:
    """Stores proposals for human review; skips what is already in the playbook or already proposed."""
    known = {e.text.casefold() for e in load(cfg)[1]}
    known |= {r["text"].casefold() for r in db.query("SELECT text FROM learnings WHERE project = ? AND status = 'proposed'", (project,))}
    saved = 0
    for item in items:
        text = clean_text(item["text"])
        if not text or text.casefold() in known:
            continue
        known.add(text.casefold())
        db.execute(
            "INSERT INTO learnings(project, status, category, text, area, paths, evidence, source_ticket_id, source_title, run_id, created_at) "
            "VALUES(?, 'proposed', ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (project, item["category"], text, item.get("area") or "", json.dumps(item.get("paths") or []), item.get("evidence") or "",
             ticket.id, ticket.title, run_id, now()),
        )
        saved += 1
    return saved


def list_proposals(db: Database, project: str, status: str = "proposed") -> list[dict]:
    rows = db.query("SELECT * FROM learnings WHERE project = ? AND status = ? ORDER BY id DESC", (project, status))
    for r in rows:
        r["paths"] = json.loads(r["paths"] or "[]")
    return rows


def accept(db: Database, cfg: ProjectConfig, project: str, learning_id: int, edits: dict | None = None) -> Entry:
    row = db.one("SELECT * FROM learnings WHERE id = ? AND project = ?", (learning_id, project))
    if not row:
        raise LookupError("proposal not found")
    if row["status"] != "proposed":
        raise ValueError(f"the proposal was already {row['status']}")
    edits = {k: v for k, v in (edits or {}).items() if v is not None}
    entry = add_entry(cfg, Entry(
        id="", category=edits.get("category", row["category"]), text=edits.get("text", row["text"]),
        source_id=row["source_ticket_id"], source_title=row["source_title"], area=edits.get("area", row["area"]).strip(),
        paths=[p.strip() for p in edits.get("paths", json.loads(row["paths"] or "[]")) if p.strip()],
    ))
    db.execute("UPDATE learnings SET status = 'accepted', decided_at = ?, entry_id = ? WHERE id = ?", (now(), entry.id, learning_id))
    return entry


def reject(db: Database, project: str, learning_id: int) -> None:
    row = db.one("SELECT status FROM learnings WHERE id = ? AND project = ?", (learning_id, project))
    if not row:
        raise LookupError("proposal not found")
    if row["status"] != "proposed":
        raise ValueError(f"the proposal was already {row['status']}")
    db.execute("UPDATE learnings SET status = 'rejected', decided_at = ? WHERE id = ?", (now(), learning_id))


def record_usage(db: Database, project: str, run_id: int, injected: list[str], cited: list[str]) -> None:
    for entry_id in injected:
        db.execute(
            "INSERT INTO playbook_usage(project, run_id, entry_id, cited, ts) VALUES(?, ?, ?, ?, ?)",
            (project, run_id, entry_id, int(entry_id in cited), now()),
        )


def usage_stats(db: Database, project: str) -> dict[str, dict]:
    rows = db.query(
        "SELECT entry_id, COUNT(*) AS uses, SUM(cited) AS cited, MAX(ts) AS last_used FROM playbook_usage WHERE project = ? GROUP BY entry_id",
        (project,),
    )
    return {r["entry_id"]: {"uses": r["uses"], "cited": r["cited"] or 0, "last_used": r["last_used"]} for r in rows}


def metrics(db: Database, project: str) -> list[dict]:
    """Per area: how much a ticket costs the agents. Derived from runs, nothing extra is recorded for it."""
    rows = db.query(
        "SELECT ticket_id, COALESCE(NULLIF(area, ''), '(no area)') AS area, kind, outcome, cost_usd, turns FROM runs "
        "WHERE project = ? AND kind IN ('triage', 'fix', 'publish') AND status != 'running'",
        (project,),
    )
    rejected = {
        r["ticket_id"]: r["n"] for r in db.query(
            "SELECT r.ticket_id, COUNT(*) AS n FROM approvals a JOIN runs r ON r.id = a.run_id "
            "WHERE r.project = ? AND a.kind = 'checkpoint' AND a.status = 'denied' GROUP BY r.ticket_id", (project,),
        )
    }
    tickets: dict[str, dict] = {}
    for r in rows:
        t = tickets.setdefault(r["ticket_id"], {"area": r["area"], "cost": 0.0, "turns": 0, "questions": 0, "fixes": 0})
        t["area"] = r["area"] if r["area"] != "(no area)" else t["area"]
        t["cost"] += r["cost_usd"] or 0
        t["turns"] += r["turns"] or 0
        t["questions"] += r["kind"] == "triage" and r["outcome"] == "needs_info"
        t["fixes"] += r["kind"] == "fix"
    by_area: dict[str, dict] = {}
    for ticket_id, t in tickets.items():
        a = by_area.setdefault(t["area"], {"area": t["area"], "tickets": 0, "cost": 0.0, "turns": 0, "questions": 0, "retries": 0, "rejections": 0})
        a["tickets"] += 1
        a["cost"] += t["cost"]
        a["turns"] += t["turns"]
        a["questions"] += t["questions"]
        a["retries"] += max(0, t["fixes"] - 1)
        a["rejections"] += rejected.get(ticket_id, 0)
    out = [
        {"area": a["area"], "tickets": a["tickets"], "avg_cost": a["cost"] / a["tickets"], "avg_turns": a["turns"] / a["tickets"],
         "questions": a["questions"], "retries": a["retries"], "rejections": a["rejections"]}
        for a in by_area.values()
    ]
    return sorted(out, key=lambda a: (-a["tickets"], a["area"]))


def entry_dict(e: Entry) -> dict:
    return asdict(e)
