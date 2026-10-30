import subprocess

import pytest

from autodev import evals
from autodev.agents import triage
from autodev.agents.triage import RunInfo, TriageResult, Understanding
from autodev.pipeline import format_comment
from tests.fixture_repo import PRICING_FIXED, make_project


def git(cwd, *args):
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()


@pytest.fixture
def fixed_project(tmp_path):
    """The fixture project with the pricing bug fixed on a branch, plus a regression test."""
    cfg = make_project(tmp_path)
    local = cfg.local_path
    git(local, "checkout", "-q", "-b", "fix/pricing")
    (tmp_path / "local" / "shop" / "pricing.py").write_text(PRICING_FIXED)
    (tmp_path / "local" / "tests" / "test_discount.py").write_text("def test_x(): pass\n")
    git(local, "add", "-A")
    git(local, "commit", "-qm", "fix: Sconto sbagliato")
    git(local, "checkout", "-q", "main")
    return cfg


def test_fix_start_skips_unpushed_commits_under_the_fix(fixed_project):
    local = fixed_project.local_path
    git(local, "checkout", "-q", "-b", "fix/later", "main")
    (fixed_project_path := __import__("pathlib").Path(local)).joinpath("notes.md").write_text("local work\n")
    git(local, "add", "-A")
    git(local, "commit", "-qm", "local work, never pushed")
    unpushed = git(local, "rev-parse", "HEAD")
    (fixed_project_path / "shop" / "pricing.py").write_text(PRICING_FIXED)
    git(local, "commit", "-qam", "fix: Sconto sbagliato")
    git(local, "checkout", "-q", "main")
    sha, files = evals.fix_facts(fixed_project, "fix/later", "Sconto sbagliato")
    assert sha == unpushed and files == ["shop/pricing.py"]


def test_is_test():
    assert evals.is_test("tests/test_pricing.py") and evals.is_test("apps/frontend/src/a.test.tsx")
    assert evals.is_test("apps/backend/conftest.py") and not evals.is_test("shop/pricing.py")


def test_fix_facts_gives_start_commit_and_source_files_only(fixed_project):
    sha, files = evals.fix_facts(fixed_project, "fix/pricing", "Sconto sbagliato")
    assert files == ["shop/pricing.py"]
    assert sha == git(fixed_project.local_path, "rev-parse", "origin/main")
    assert evals.fix_facts(fixed_project, "fix/gone") is None


def test_score():
    case = {"files": ["a.py", "b.py"], "expected_verdict": "ready"}
    r = TriageResult(verdict="ready", confidence="high", risk="Low", analysis="x", suspected_files=["a.py", "c.py"],
                     understanding=Understanding(expected="e", actual="a"))
    s = evals.score(r, case)
    assert s["verdict_ok"] and s["recall"] == 0.5 and s["precision"] == 0.5 and s["understanding"]


async def test_run_case_triages_the_code_before_the_fix(fixed_project, monkeypatch):
    sha, files = evals.fix_facts(fixed_project, "fix/pricing", "Sconto sbagliato")
    seen = {}

    async def fake_run(cfg, ticket, model, *a, **k):
        from pathlib import Path
        seen["code"] = (Path(cfg.local_path) / "shop" / "pricing.py").read_text()
        return TriageResult(verdict="ready", confidence="high", risk="Low", analysis="x", suspected_files=files), RunInfo(model, 0.1, 3)

    monkeypatch.setattr(evals, "_run", fake_run)
    case = {"ticket": {"id": "t1", "title": "Sconto sbagliato", "status": "closed"}, "base_sha": sha, "files": files, "expected_verdict": "ready"}
    row = await evals.run_case(fixed_project, case, "m")
    assert "price - percent" in seen["code"]
    assert row["verdict_ok"] and row["recall"] == 1.0 and row["cost_usd"] == 0.1
    assert "autodev-eval" not in git(fixed_project.local_path, "worktree", "list")
    assert "ok ready" in evals.format_report([row])


def test_comment_opens_with_what_was_understood():
    r = TriageResult(verdict="ready", confidence="high", risk="Low", analysis="Causa in shop/pricing.py",
                     understanding=Understanding(where="Carrello", expected="sconto del 10%", actual="tolti 10 euro", steps=["Aggiungi un prodotto", "Applica il codice"]))
    comment = format_comment(r, "Low", [])
    assert comment.index("What I understood") < comment.index("Causa in shop/pricing.py")
    assert "- Expected: sconto del 10%" in comment and "  2. Applica il codice" in comment
    assert "What I understood" not in format_comment(TriageResult(verdict="ready", confidence="high", risk="Low", analysis="a"), "Low", [])
