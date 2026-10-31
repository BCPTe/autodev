"""Local SQLite store shared by the CLI and the dashboard server.

WAL mode lets the dashboard read while a CLI run is writing, so a run started from the terminal
shows up live in the dashboard without any other plumbing.
"""
import json
import os
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any

DEFAULT_PATH = Path(os.environ.get("AUTODEV_DB") or Path(__file__).resolve().parents[2] / "data" / "autodev.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project TEXT NOT NULL,
    ticket_id TEXT NOT NULL,
    ticket_title TEXT NOT NULL,
    kind TEXT NOT NULL,
    status TEXT NOT NULL,
    model TEXT,
    started_at REAL NOT NULL,
    finished_at REAL,
    cost_usd REAL NOT NULL DEFAULT 0,
    outcome TEXT,
    branch TEXT,
    pr_url TEXT,
    error TEXT,
    cancel_requested INTEGER NOT NULL DEFAULT 0,
    pid INTEGER
);
CREATE INDEX IF NOT EXISTS runs_ticket ON runs(ticket_id);
CREATE INDEX IF NOT EXISTS runs_started ON runs(started_at);
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL REFERENCES runs(id),
    ts REAL NOT NULL,
    type TEXT NOT NULL,
    text TEXT NOT NULL DEFAULT '',
    data TEXT
);
CREATE INDEX IF NOT EXISTS events_run ON events(run_id, id);
CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS approvals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL REFERENCES runs(id),
    kind TEXT NOT NULL,
    title TEXT NOT NULL,
    detail TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    created_at REAL NOT NULL,
    decided_at REAL,
    note TEXT
);
CREATE INDEX IF NOT EXISTS approvals_status ON approvals(status, run_id);
CREATE TABLE IF NOT EXISTS actions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts REAL NOT NULL,
    actor TEXT NOT NULL,
    action TEXT NOT NULL,
    ticket_id TEXT,
    detail TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS actions_ticket ON actions(ticket_id, id);
CREATE TABLE IF NOT EXISTS learnings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'proposed',
    category TEXT NOT NULL,
    text TEXT NOT NULL,
    area TEXT NOT NULL DEFAULT '',
    paths TEXT NOT NULL DEFAULT '[]',
    evidence TEXT NOT NULL DEFAULT '',
    source_ticket_id TEXT NOT NULL,
    source_title TEXT NOT NULL,
    run_id INTEGER,
    created_at REAL NOT NULL,
    decided_at REAL,
    entry_id TEXT
);
CREATE INDEX IF NOT EXISTS learnings_status ON learnings(project, status);
CREATE TABLE IF NOT EXISTS playbook_usage (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project TEXT NOT NULL,
    run_id INTEGER NOT NULL,
    entry_id TEXT NOT NULL,
    cited INTEGER NOT NULL DEFAULT 0,
    ts REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS playbook_usage_entry ON playbook_usage(project, entry_id);
CREATE TABLE IF NOT EXISTS sessions (
    token_hash TEXT PRIMARY KEY,
    created_at REAL NOT NULL,
    expires_at REAL NOT NULL
);
"""


class Database:
    def __init__(self, path: str | Path | None = None):
        self.path = Path(path) if path else DEFAULT_PATH
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(self.path, check_same_thread=False, timeout=30)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._conn.executescript(SCHEMA)
        columns = {row["name"] for row in self._conn.execute("PRAGMA table_info(runs)")}
        for name, ddl in (("dismissed", "INTEGER NOT NULL DEFAULT 0"), ("turns", "INTEGER NOT NULL DEFAULT 0"), ("area", "TEXT"), ("usage", "TEXT")):
            if name not in columns:  # added after the first release
                self._conn.execute(f"ALTER TABLE runs ADD COLUMN {name} {ddl}")
        self._conn.commit()

    def execute(self, sql: str, params: tuple | dict = ()) -> int:
        with self._lock:
            cur = self._conn.execute(sql, params)
            self._conn.commit()
            return cur.lastrowid or 0

    def query(self, sql: str, params: tuple | dict = ()) -> list[dict[str, Any]]:
        with self._lock:
            return [dict(r) for r in self._conn.execute(sql, params).fetchall()]

    def one(self, sql: str, params: tuple | dict = ()) -> dict[str, Any] | None:
        rows = self.query(sql, params)
        return rows[0] if rows else None

    def audit(self, actor: str, action: str, ticket_id: str | None = None, detail: str = "") -> None:
        """Who decided what: `actor` is 'user' (the dashboard) or 'auto' (the orchestrator)."""
        self.execute(
            "INSERT INTO actions(ts, actor, action, ticket_id, detail) VALUES(?, ?, ?, ?, ?)",
            (now(), actor, action, ticket_id, detail),
        )

    def close(self) -> None:
        self._conn.close()

    # settings -----------------------------------------------------------------------------
    def get_setting(self, key: str, default: str | None = None) -> str | None:
        row = self.one("SELECT value FROM settings WHERE key = ?", (key,))
        return row["value"] if row else default

    def set_setting(self, key: str, value: str) -> None:
        self.execute(
            "INSERT INTO settings(key, value) VALUES(?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )

    def delete_setting(self, key: str) -> None:
        self.execute("DELETE FROM settings WHERE key = ?", (key,))


def dumps(data: dict | None) -> str | None:
    return json.dumps(data, ensure_ascii=False) if data else None


def now() -> float:
    return time.time()
