"""Cost breakdowns for the dashboard: by stage and model with tokens, by area, by outcome."""
import json
from collections import defaultdict
from typing import Any

from autodev.db import Database

# Above roughly this many prompt tokens a request is billed at a much higher rate per token (measured: about 5x on Haiku).
LONG_CONTEXT = 100_000


def sessions_of(row: dict) -> list[dict]:
    try:
        return json.loads(row["usage"]) if row.get("usage") else []
    except ValueError:
        return []


def by_stage_model(db: Database, project: str) -> list[dict[str, Any]]:
    """One row per (stage, model): sessions, tokens by kind and cost. Runs from before usage was recorded count as untracked."""
    rows: dict[tuple[str, str], dict[str, Any]] = defaultdict(lambda: dict(sessions=0, turns=0, input=0, output=0, cache_read=0, cache_write=0, cost=0.0, untracked=0, peak_context=0, long_context=0))
    for run in db.query("SELECT kind, model, cost_usd, usage FROM runs WHERE project = ? AND kind IN ('triage', 'fix', 'learn') AND status != 'running'", (project,)):
        sessions = sessions_of(run)
        if not sessions:
            row = rows[(run["kind"], run["model"] or "n/d")]
            row["sessions"] += 1
            row["untracked"] += 1
            row["cost"] += run["cost_usd"]
            continue
        for s in sessions:
            row = rows[(s.get("stage") or run["kind"], s.get("model") or run["model"] or "n/d")]
            row["sessions"] += 1
            row["turns"] += s.get("turns", 0)
            row["input"] += s.get("input", 0)
            row["output"] += s.get("output", 0)
            row["cache_read"] += s.get("cache_read", 0)
            row["cache_write"] += s.get("cache_write", 0)
            row["cost"] += s.get("cost_usd", 0.0)
            row["peak_context"] = max(row["peak_context"], s.get("peak_context", 0))
            row["long_context"] += s.get("peak_context", 0) > LONG_CONTEXT
    return sorted(({"kind": k, "model": m, **v} for (k, m), v in rows.items()), key=lambda r: -r["cost"])


def by_area(db: Database, project: str) -> list[dict[str, Any]]:
    return db.query(
        "SELECT kind, COALESCE(NULLIF(area, ''), '(no area)') AS area, COUNT(*) AS runs, SUM(cost_usd) AS cost, AVG(cost_usd) AS avg_cost "
        "FROM runs WHERE project = ? AND kind IN ('triage', 'fix') AND status = 'done' GROUP BY kind, area ORDER BY kind, cost DESC",
        (project,),
    )


def by_outcome(db: Database, project: str) -> list[dict[str, Any]]:
    """Per run kind and outcome, and per ticket by how its last fix ended (all its runs counted)."""
    runs = db.query(
        "SELECT kind, COALESCE(outcome, status) AS outcome, COUNT(*) AS runs, SUM(cost_usd) AS cost, AVG(cost_usd) AS avg_cost "
        "FROM runs WHERE project = ? AND kind IN ('triage', 'fix', 'learn') AND status != 'running' GROUP BY kind, outcome ORDER BY kind, cost DESC",
        (project,),
    )
    last_fix = {
        r["ticket_id"]: r["outcome"] or r["status"]
        for r in db.query("SELECT ticket_id, outcome, status FROM runs WHERE id IN (SELECT MAX(id) FROM runs WHERE project = ? AND kind = 'fix' AND status != 'running' GROUP BY ticket_id)", (project,))
    }
    total = {r["ticket_id"]: r["cost"] for r in db.query("SELECT ticket_id, SUM(cost_usd) AS cost FROM runs WHERE project = ? GROUP BY ticket_id", (project,))}
    tickets: dict[str, list[float]] = defaultdict(list)
    for ticket_id, outcome in last_fix.items():
        tickets[outcome].append(total.get(ticket_id, 0.0))
    return {
        "runs": runs,
        "tickets": [{"outcome": o, "tickets": len(c), "cost": sum(c), "avg_cost": sum(c) / len(c)} for o, c in sorted(tickets.items(), key=lambda kv: -sum(kv[1]))],
    }
