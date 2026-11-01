"""Replay triage on tickets that were already fixed, to measure prompt and model changes instead of guessing.

A case is a ticket whose fix branch exists: its text and human comments, the commit the fix started from,
and the source files the fix changed. Running a case checks that commit out in a temporary worktree (so the
bug is still in the code), triages the ticket there and scores the result against what the fix touched.
"""

import json
import subprocess
import tempfile
import time
from pathlib import Path

from autodev.agents.triage import TriageResult, _run, normalize, run_triage
from autodev.config import ProjectConfig
from autodev.models import Status, Ticket
from autodev.trackers.notion import NotionTracker

EVAL_DIR = Path("data/evals")


def _git(cfg: ProjectConfig, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=cfg.local_path, capture_output=True, text=True, timeout=60)


def is_test(path: str) -> bool:
    parts = path.lower().split("/")
    name = parts[-1]
    return any(p in ("test", "tests", "__tests__", "e2e") for p in parts[:-1]) or name.startswith("test_") \
        or name.endswith(("_test.py", ".test.ts", ".test.tsx", ".spec.ts", ".spec.tsx")) or name == "conftest.py"


def fix_start(cfg: ProjectConfig, ref: str, title: str) -> str | None:
    """Parent of the oldest of the agent's own commits ("fix: <title>") at the tip of the branch.

    The merge-base with the base branch is only a fallback: a branch cut from local commits not yet pushed
    has a merge-base far in the past, which would put unrelated work into the diff and old code under triage.
    """
    log = _git(cfg, "log", "--first-parent", "--format=%H %P%x00%s", ref)
    if log.returncode != 0:
        return None
    start = None
    for line in log.stdout.splitlines():
        shas, _, subject = line.partition("\0")
        if subject.strip() != f"fix: {title}":
            break
        start = shas.split()[1] if len(shas.split()) > 1 else None
    if start:
        return start
    base = _git(cfg, "merge-base", f"origin/{cfg.base_branch}", ref)
    return base.stdout.strip() if base.returncode == 0 else None


def fix_facts(cfg: ProjectConfig, branch: str, title: str = "") -> tuple[str, list[str]] | None:
    """The commit the fix started from and the source files it changed, or None when the branch is gone."""
    for ref in (branch, f"origin/{branch}"):
        sha = fix_start(cfg, ref, title)
        if not sha:
            continue
        diff = _git(cfg, "diff", "--name-only", f"{sha}..{ref}")
        files = [f for f in diff.stdout.split() if not is_test(f)]
        if files:
            return sha, files
    return None


def cases_path(project: str) -> Path:
    return EVAL_DIR / project / "cases.jsonl"


async def build_cases(cfg: ProjectConfig, project: str, tracker: NotionTracker) -> tuple[int, list[str]]:
    """Writes a case for every ticket in review or closed whose branch is still in the checkout."""
    _git(cfg, "fetch", "--quiet", "origin")
    cases, skipped = [], []
    for t in await tracker.list_all():
        if not t.branch or t.status not in (Status.REVIEW, Status.CLOSED):
            continue
        facts = fix_facts(cfg, t.branch, t.title)
        if not facts:
            skipped.append(f"{t.title} (branch {t.branch} not found or touches only tests)")
            continue
        ticket, _ = await tracker.detail(t.id)
        cases.append({"ticket": ticket.model_dump(), "base_sha": facts[0], "files": facts[1], "expected_verdict": "ready"})
    path = cases_path(project)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(c, ensure_ascii=False) + "\n" for c in cases))
    return len(cases), skipped


def load_cases(project: str) -> list[dict]:
    path = cases_path(project)
    if not path.exists():
        raise SystemExit(f"no eval cases: build the cases first")
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def score(result: TriageResult, case: dict) -> dict:
    truth = set(case["files"])
    suspected = set(result.suspected_files)
    hit = truth & suspected
    u = result.understanding
    return {
        "verdict": result.verdict,
        "verdict_ok": result.verdict == case["expected_verdict"],
        "recall": len(hit) / len(truth) if truth else 0.0,
        "precision": len(hit) / len(suspected) if suspected else 0.0,
        "understanding": bool(u.expected and u.actual),
        "questions": len(result.questions),
    }


async def run_case(cfg: ProjectConfig, case: dict, model: str | None) -> dict:
    ticket = Ticket.model_validate(case["ticket"])
    with tempfile.TemporaryDirectory(prefix="autodev-eval-") as tmp:
        wt = Path(tmp) / "checkout"
        add = _git(cfg, "worktree", "add", "--detach", str(wt), case["base_sha"])
        if add.returncode != 0:
            return {"id": ticket.id, "title": ticket.title, "error": add.stderr.strip()}
        try:
            at = cfg.model_copy(update={"local_path": str(wt)})
            if model:
                result, info = await _run(at, ticket, model)
                result, runs = normalize(result), [info]
            else:
                result, runs = await run_triage(at, ticket)
        except RuntimeError as e:
            return {"id": ticket.id, "title": ticket.title, "error": str(e)}
        finally:
            _git(cfg, "worktree", "remove", "--force", str(wt))
    return {
        "id": ticket.id, "title": ticket.title, **score(result, case),
        "cost_usd": sum(r.cost_usd for r in runs), "turns": sum(r.turns for r in runs),
        "models": [r.model for r in runs], "expected_files": case["files"], "result": result.model_dump(),
    }


def summary(rows: list[dict]) -> dict:
    ok = [r for r in rows if "error" not in r]
    n = len(ok) or 1
    return {
        "cases": len(rows), "errors": len(rows) - len(ok),
        "verdict_ok": sum(r["verdict_ok"] for r in ok) / n,
        "recall": sum(r["recall"] for r in ok) / n,
        "precision": sum(r["precision"] for r in ok) / n,
        "understanding": sum(r["understanding"] for r in ok) / n,
        "cost_usd": sum(r["cost_usd"] for r in ok),
        "avg_turns": sum(r["turns"] for r in ok) / n,
    }


def save_report(project: str, label: str, rows: list[dict]) -> Path:
    path = EVAL_DIR / project / f"{time.strftime('%Y%m%d-%H%M%S')}{'-' + label if label else ''}.json"
    path.write_text(json.dumps({"label": label, "summary": summary(rows), "rows": rows}, ensure_ascii=False, indent=2))
    return path


def previous_report(project: str, current: Path) -> dict | None:
    reports = sorted(p for p in (EVAL_DIR / project).glob("2*.json") if p != current)
    return json.loads(reports[-1].read_text()) if reports else None


def format_report(rows: list[dict], previous: dict | None = None) -> str:
    lines = [f"{'verdict':<17} {'recall':>6} {'prec':>5} {'und':>3} {'cost':>6}  ticket"]
    for r in rows:
        if "error" in r:
            lines.append(f"{'ERROR':<17} {'':>6} {'':>5} {'':>3} {'':>6}  {r['title'][:50]}  ({r['error'][:80]})")
            continue
        mark = "ok" if r["verdict_ok"] else "XX"
        lines.append(f"{mark} {r['verdict']:<14} {r['recall']:>6.0%} {r['precision']:>5.0%} {'y' if r['understanding'] else 'n':>3} "
                     f"${r['cost_usd']:>5.2f}  {r['title'][:50]}")
    s = summary(rows)
    lines += ["", f"{s['cases']} cases, {s['errors']} errors · verdict {s['verdict_ok']:.0%} · recall {s['recall']:.0%} · "
                  f"precision {s['precision']:.0%} · understanding {s['understanding']:.0%} · ${s['cost_usd']:.2f}, {s['avg_turns']:.1f} turns/case"]
    if previous:
        p = previous["summary"]
        lines.append(f"previous ({previous.get('label') or 'unlabelled'}): verdict {p['verdict_ok']:.0%} · recall {p['recall']:.0%} · "
                     f"precision {p['precision']:.0%} · understanding {p['understanding']:.0%} · ${p['cost_usd']:.2f}")
    return "\n".join(lines)
