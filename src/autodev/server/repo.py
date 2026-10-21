"""Read-only view of the project's own checkout (branch, uncommitted files, autodev branches)."""
import subprocess
from pathlib import Path

from autodev.config import ProjectConfig


def _git(path: Path, *args: str) -> str:
    r = subprocess.run(["git", *args], cwd=path, capture_output=True, text=True, timeout=30)
    return r.stdout.strip() if r.returncode == 0 else ""


def repo_state(cfg: ProjectConfig) -> dict:
    path = Path(cfg.local_path)
    base = f"origin/{cfg.base_branch}"
    branch = _git(path, "rev-parse", "--abbrev-ref", "HEAD")
    dirty = [line for line in _git(path, "status", "--porcelain").splitlines() if line.strip()]
    ahead_behind = _git(path, "rev-list", "--left-right", "--count", f"HEAD...{base}").split()
    merged = set(_git(path, "branch", "--merged", base, "--format=%(refname:short)").split())
    branches = []
    for name in _git(path, "branch", "--list", f"{cfg.branch_prefix}/*", "--format=%(refname:short)").split():
        branches.append({
            "name": name,
            "merged": name in merged,
            "current": name == branch,
            "last_commit": _git(path, "log", "-1", "--format=%s", name),
            "updated": _git(path, "log", "-1", "--format=%cI", name),
            "ahead": int(_git(path, "rev-list", "--count", f"{base}..{name}") or 0),
        })
    commits = [
        {"sha": line.split(" ", 1)[0], "subject": line.split(" ", 1)[1] if " " in line else ""}
        for line in _git(path, "log", "-8", "--format=%h %s").splitlines()
    ]
    return {
        "path": str(path),
        "base_branch": cfg.base_branch,
        "branch": branch,
        "on_agent_branch": branch.startswith(f"{cfg.branch_prefix}/"),
        "dirty": dirty,
        "clean": not dirty,
        "ahead": int(ahead_behind[0]) if len(ahead_behind) == 2 else None,
        "behind": int(ahead_behind[1]) if len(ahead_behind) == 2 else None,
        "branches": branches,
        "commits": commits,
    }
