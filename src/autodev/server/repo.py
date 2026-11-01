"""Read-only view of the project's own checkout (branch, uncommitted files, autodev branches)."""
import shutil
import subprocess
from pathlib import Path

from autodev.config import ProjectConfig
from autodev.sandbox import workspace


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


def _run(path: Path, *args: str, timeout: int = 60, token_env: str | None = None) -> subprocess.CompletedProcess[str]:
    env = workspace.network_env(token_env) if args and args[0] in workspace.NETWORK_COMMANDS else None
    return subprocess.run(["git", *args], cwd=path, capture_output=True, text=True, timeout=timeout, env=env)


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
            raise RepoError("unknown branch")
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
        raise RepoError(f"you can only switch to {cfg.base_branch} or to a {cfg.branch_prefix}/* branch")
    if _run(path, "status", "--porcelain").stdout.strip():
        raise RepoError("there are uncommitted changes: commit or stash before switching branch")
    r = _run(path, "checkout", branch)
    if r.returncode != 0:
        raise RepoError(r.stderr.strip() or "checkout failed")
    if branch == cfg.base_branch:
        update_base(cfg)
    return branch


def update_base(cfg: ProjectConfig) -> bool:
    """Fast-forwards the checked-out base branch to origin (best effort: never merges, never overwrites)."""
    path = Path(cfg.local_path)
    if _run(path, "fetch", "--quiet", "origin", cfg.base_branch, timeout=120, token_env=cfg.pr.token_env).returncode != 0:
        return False
    return _run(path, "merge", "--ff-only", "--quiet", f"origin/{cfg.base_branch}").returncode == 0


def merge_branch(cfg: ProjectConfig, branch: str) -> str:
    """Fast-forwards the base branch to an autodev branch (projects without pull requests) and deletes the branch.
    Refuses on uncommitted changes or when the branch is not a straight continuation of the base; nothing is rewritten."""
    path = Path(cfg.local_path)
    if not branch.startswith(f"{cfg.branch_prefix}/"):
        raise RepoError(f"only a {cfg.branch_prefix}/* branch can be merged here")
    if _run(path, "rev-parse", "--verify", "--quiet", branch).returncode != 0:
        raise RepoError(f"the branch {branch} does not exist in the checkout")
    if _run(path, "status", "--porcelain").stdout.strip():
        raise RepoError("there are uncommitted changes: commit or stash before merging")
    start = _run(path, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
    if _run(path, "merge-base", "--is-ancestor", cfg.base_branch, branch).returncode != 0:
        raise RepoError(f"{branch} is not up to date with {cfg.base_branch}: it cannot be fast-forwarded, merge it by hand")
    r = _run(path, "checkout", cfg.base_branch)
    if r.returncode != 0:
        raise RepoError(r.stderr.strip() or "checkout failed")
    r = _run(path, "merge", "--ff-only", "--quiet", branch)
    if r.returncode != 0:
        _run(path, "checkout", start)
        raise RepoError(r.stderr.strip() or "the merge failed")
    _run(path, "branch", "-d", branch)
    return cfg.base_branch


def return_to_base_after_merge(cfg: ProjectConfig, merged_branch: str) -> str | None:
    """After a pull request is merged, leaves the merged branch: back on the base branch, brought up to date,
    and the merged local branch deleted. Does nothing unless the checkout sits on that branch and is clean."""
    path = Path(cfg.local_path)
    if _run(path, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip() != merged_branch:
        return None
    if _run(path, "status", "--porcelain").stdout.strip():
        return None
    if _run(path, "checkout", cfg.base_branch).returncode != 0:
        return None
    update_base(cfg)
    _run(path, "branch", "-D", merged_branch)
    return cfg.base_branch


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
        raise RepoError("cannot be deleted (not merged, active or outside the prefix): " + ", ".join(refused))
    path = Path(cfg.local_path)
    done = []
    for name in names:
        r = _run(path, "branch", "-D", name)
        if r.returncode != 0:
            raise RepoError(r.stderr.strip() or f"cannot delete {name}")
        done.append(name)
    return done


def leftover_clones(cfg: ProjectConfig) -> list[Path]:
    """Throwaway clones this project's agents left in workspaces/ (shared by all projects, named after the checkout)."""
    if not workspace.WORKSPACES.is_dir():
        return []
    prefix = workspace.slugify(cfg.local_path.rsplit("/", 1)[-1]) + "-"
    return sorted(d for d in workspace.WORKSPACES.iterdir() if d.is_dir() and d.name.startswith(prefix))


def remove_clones(cfg: ProjectConfig) -> list[str]:
    clones = leftover_clones(cfg)
    for d in clones:
        shutil.rmtree(d)
    return [d.name for d in clones]


def _is_ancestor(path: Path, older: str, newer: str) -> bool:
    return _run(path, "merge-base", "--is-ancestor", older, newer).returncode == 0


def push_plan(cfg: ProjectConfig, tip: str | None = None) -> dict:
    """What pushing the base branch would send to origin, so a person can read it before confirming.

    It stops at `tip` (the commit of the last merge autodev did) when that is still part of the branch, so commits
    made afterwards stay local. Commits made before it cannot be left behind: git sends every ancestor.
    """
    path = Path(cfg.local_path)
    base, remote = cfg.base_branch, f"origin/{cfg.base_branch}"
    plan: dict = {"base": base, "commits": [], "target": None, "can_push": False, "reason": None}
    if _run(path, "fetch", "--quiet", "origin", base, timeout=120, token_env=cfg.pr.token_env).returncode != 0:
        plan["reason"] = "origin could not be reached, so it is not known what is already there"
        return plan
    head = _git(path, "rev-parse", f"refs/heads/{base}")
    if not head:
        plan["reason"] = f"there is no local {base} branch"
        return plan
    target = tip if tip and _git(path, "rev-parse", "--verify", "--quiet", f"{tip}^{{commit}}") and _is_ancestor(path, tip, head) else head
    plan["target"] = target
    if not _is_ancestor(path, remote, target):
        plan["reason"] = f"origin has commits you do not have yet: pull {base} first, then push"
        return plan
    out = _git(path, "log", "--reverse", "--format=%H%x1f%s%x1f%b%x1e", f"{remote}..{target}")
    for entry in filter(None, (e.strip() for e in out.split("\x1e"))):
        sha, subject, body = (entry.split("\x1f") + ["", ""])[:3]
        plan["commits"].append({"sha": sha[:8], "subject": subject, "autodev": "Ticket: " in body})
    plan["own_count"] = sum(1 for c in plan["commits"] if not c["autodev"])
    plan["can_push"] = bool(plan["commits"])
    plan["reason"] = None if plan["commits"] else "everything is already on origin"
    return plan


def push_base(cfg: ProjectConfig, tip: str | None = None) -> dict:
    """Pushes the base branch to origin up to the planned commit. Never forced: git refuses anything but a plain advance."""
    plan = push_plan(cfg, tip)
    if not plan["can_push"]:
        raise RepoError(plan["reason"] or "nothing to push")
    r = _run(Path(cfg.local_path), "push", "--quiet", "origin", f"{plan['target']}:refs/heads/{cfg.base_branch}", timeout=120, token_env=cfg.pr.token_env)
    if r.returncode != 0:
        raise RepoError((r.stderr.strip().splitlines() or ["the push failed"])[-1])
    return plan
