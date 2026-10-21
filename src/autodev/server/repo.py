"""Read-only view of the project's own checkout (branch, uncommitted files, autodev branches)."""
import subprocess
from pathlib import Path

from autodev.config import ProjectConfig


def _git(path: Path, *args: str) -> str:
    r = subprocess.run(["git", *args], cwd=path, capture_output=True, text=True, timeout=30)
    return r.stdout.strip() if r.returncode == 0 else ""


def repo_state(cfg: ProjectConfig, pr_merged: set[str] = frozenset()) -> dict:
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
            "merged": name in merged or name in pr_merged,
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


class RepoError(RuntimeError):
    """An operation on the checkout that was refused or failed; the message is meant for the user."""


def _run(path: Path, *args: str, timeout: int = 60) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], cwd=path, capture_output=True, text=True, timeout=timeout)


def _split_patch(text: str) -> dict[str, str]:
    patches: dict[str, str] = {}
    for chunk in text.split("\ndiff --git ")[0:]:
        chunk = chunk if chunk.startswith("diff --git ") else "diff --git " + chunk
        first = chunk.splitlines()[0]
        patches[first.rsplit(" b/", 1)[-1]] = chunk
    return patches


def diff(cfg: ProjectConfig, branch: str | None = None, max_bytes: int = 200_000) -> dict:
    """Changes of an agent branch against the base branch, or the uncommitted ones when no branch is given."""
    path = Path(cfg.local_path)
    if branch:
        if not branch.startswith(f"{cfg.branch_prefix}/") or _run(path, "rev-parse", "--verify", "--quiet", branch).returncode != 0:
            raise RepoError("branch sconosciuto")
        spec = [f"origin/{cfg.base_branch}...{branch}"]
    else:
        spec = ["HEAD"]
    numstat = _run(path, "diff", "--numstat", *spec).stdout.splitlines()
    patch = _run(path, "diff", "--no-color", *spec).stdout
    patches = _split_patch(patch) if patch.strip() else {}
    files, used = [], 0
    for line in numstat:
        add, rem, name = line.split("\t", 2)
        name = name.split(" => ")[-1].strip("{}")
        text = patches.get(name, "")
        truncated = used + len(text) > max_bytes
        files.append({
            "path": name, "additions": None if add == "-" else int(add), "deletions": None if rem == "-" else int(rem),
            "patch": "" if truncated else text, "truncated": truncated,
        })
        used += 0 if truncated else len(text)
    return {"branch": branch, "base": cfg.base_branch, "files": files}


def checkout(cfg: ProjectConfig, branch: str) -> str:
    path = Path(cfg.local_path)
    if branch != cfg.base_branch and not branch.startswith(f"{cfg.branch_prefix}/"):
        raise RepoError(f"si può passare solo a {cfg.base_branch} o a un branch {cfg.branch_prefix}/*")
    if _run(path, "status", "--porcelain").stdout.strip():
        raise RepoError("ci sono modifiche non committate: fai commit o stash prima di cambiare branch")
    r = _run(path, "checkout", branch)
    if r.returncode != 0:
        raise RepoError(r.stderr.strip() or "checkout non riuscito")
    return branch


def removable_branches(cfg: ProjectConfig, pr_merged: set[str] = frozenset()) -> list[str]:
    """Agent branches whose work is in the base branch (git says so, or their pull request was merged)."""
    path = Path(cfg.local_path)
    current = _run(path, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
    merged = set(_run(path, "branch", "--merged", f"origin/{cfg.base_branch}", "--format=%(refname:short)").stdout.split())
    local = _run(path, "branch", "--list", f"{cfg.branch_prefix}/*", "--format=%(refname:short)").stdout.split()
    return [b for b in local if b != current and (b in merged or b in pr_merged)]


def delete_branches(cfg: ProjectConfig, names: list[str], pr_merged: set[str] = frozenset()) -> list[str]:
    """Deletes local branches that are verified as merged; anything else is refused, never forced."""
    allowed = set(removable_branches(cfg, pr_merged))
    refused = [n for n in names if n not in allowed]
    if refused:
        raise RepoError("non eliminabili (non uniti, attivi o fuori dal prefisso): " + ", ".join(refused))
    path = Path(cfg.local_path)
    done = []
    for name in names:
        r = _run(path, "branch", "-D", name)
        if r.returncode != 0:
            raise RepoError(r.stderr.strip() or f"non riesco a eliminare {name}")
        done.append(name)
    return done
