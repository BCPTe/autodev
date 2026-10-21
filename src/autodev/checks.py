import os
import shlex
from dataclasses import dataclass

from autodev.config import ProjectConfig
from autodev.sandbox.workspace import Workspace, expand, git, matches, sh


@dataclass
class CheckResult:
    name: str
    ok: bool
    output: str = ""

    def line(self) -> str:
        return f"{'PASS' if self.ok else 'FAIL'}  {self.name}"


def _tail(text: str, lines: int = 40) -> str:
    return "\n".join(text.strip().splitlines()[-lines:])


def run_check(cfg: ProjectConfig, check, path) -> CheckResult:
    r = sh(expand(check.cmd, cfg), path / check.cwd)
    return CheckResult(check.name, r.returncode == 0, _tail(r.stdout + r.stderr))


def run_checks(cfg: ProjectConfig, ws: Workspace) -> list[CheckResult]:
    changed = ws.changed_files(ws.base_ref)
    results = []
    for check in cfg.checks:
        if check.when_changed and not any(f.startswith(p) for f in changed for p in check.when_changed):
            continue
        r = sh(expand(check.cmd, cfg), ws.path / check.cwd)
        results.append(CheckResult(check.name, r.returncode == 0, _tail(r.stdout + r.stderr)))
    return results


def regression_gate(cfg: ProjectConfig, ws: Workspace) -> CheckResult:
    """Tests added by the fix must fail without the fix and pass with it.

    Each configured test suite (e.g. backend pytest, frontend vitest) that received new test files
    is checked on its own. Run on a committed workspace: source files go back to their state at the
    start of the run, the new tests are run (each suite must fail), then the workspace is restored.
    """
    if not cfg.regressions:
        return CheckResult("regression test", True, "not configured")

    changed = ws.changed_files()
    suites = []
    for reg in cfg.regressions:
        tests = [f for f in changed if matches(f, reg.test_globs)]
        new = [f for f in tests if not ws.exists_at(ws.base_ref, f) or not ws.exists_at(ws.start_ref, f)]
        if new:
            suites.append((reg, new))
    if not suites:
        return CheckResult("regression test", False, "the fix adds no new test file")

    test_files = {f for reg in cfg.regressions for f in changed if matches(f, reg.test_globs)}
    sources = [f for f in changed if f not in test_files]
    if not sources:
        return CheckResult("regression test", False, "the fix changes no source file")

    def run_suite(reg, new):
        rel = [shlex.quote(os.path.relpath(t, reg.cwd)) for t in new]
        return sh(expand(reg.cmd, cfg, tests=" ".join(rel)), ws.path / reg.cwd)

    proves_nothing: list[str] = []
    try:
        for f in sources:
            if ws.exists_at(ws.start_ref, f):
                git(ws.path, "checkout", ws.start_ref, "--", f)
            else:
                (ws.path / f).unlink(missing_ok=True)
        for reg, new in suites:
            if run_suite(reg, new).returncode == 0:
                proves_nothing.append(", ".join(new))
    finally:
        ws.restore_files(sources)

    if proves_nothing:
        return CheckResult(
            "regression test", False,
            "new tests pass even without the fix, so they prove nothing: " + "; ".join(proves_nothing),
        )
    for reg, new in suites:
        r = run_suite(reg, new)
        if r.returncode != 0:
            return CheckResult("regression test", False, "new tests fail with the fix:\n" + _tail(r.stdout + r.stderr))
    n = sum(len(new) for _, new in suites)
    return CheckResult("regression test", True, f"{n} new test file(s) in {len(suites)} suite(s) fail without the fix and pass with it")
