"""What the setup wizard needs: look at a checkout, build a project file, save secrets and files."""
import asyncio
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import yaml

from autodev.config import ProjectConfig
from autodev.sandbox import workspace
from autodev.trackers import notion_schema

NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,39}$")
MODELS = {"Haiku": "claude-haiku-5-5", "Sonnet": "claude-sonnet-5-5", "Opus": "claude-opus-5-5"}
PRESETS = {
    "careful": {"default_mode": "manual", "permission_policy": "ask", "checkpoints": ["before_pr"], "auto_approve_risks": []},
    "balanced": {"default_mode": "supervised", "permission_policy": "ask", "checkpoints": ["before_pr"], "auto_approve_risks": []},
    "autonomous": {"default_mode": "auto", "permission_policy": "trusted", "checkpoints": [], "auto_approve_risks": ["Low"]},
}
SKIP_DIRS = {"node_modules", "venv", "dist", "build", "tests", "test", "docs", "scripts", "__pycache__"}


def claude_status() -> dict:
    """Is the `claude` CLI installed and logged in? (the agents run through it)"""
    try:
        r = subprocess.run(["claude", "auth", "status"], capture_output=True, text=True, timeout=20)
    except FileNotFoundError:
        return {"ok": False, "installed": False, "detail": "The `claude` command was not found. Install Claude Code, then check again."}
    except subprocess.TimeoutExpired:
        return {"ok": False, "installed": True, "detail": "`claude auth status` did not answer."}
    try:
        info = json.loads(r.stdout)
    except ValueError:
        info = {}
    if info.get("loggedIn"):
        return {"ok": True, "installed": True, "method": info.get("authMethod"), "email": info.get("email")}
    return {"ok": False, "installed": True, "detail": "Not logged in. Run `claude` in a terminal and sign in, then check again."}


def list_folders(path: str | None) -> dict:
    """Subfolders of a folder (home by default), flagging git checkouts, for the wizard's folder picker."""
    here = Path(path).expanduser() if path else Path.home()
    try:
        here = here.resolve()
        children = sorted((d for d in here.iterdir() if d.is_dir() and not d.name.startswith(".")), key=lambda d: d.name.lower())
    except (OSError, PermissionError) as e:
        return {"ok": False, "error": f"Cannot open {here}: {e.strerror or e}"}
    return {
        "ok": True, "path": str(here), "parent": str(here.parent) if here.parent != here else None,
        "git": (here / ".git").exists(),
        "folders": [{"name": d.name, "path": str(d), "git": (d / ".git").exists()} for d in children],
    }


def _git(path: Path, *args: str) -> str:
    r = subprocess.run(["git", *args], cwd=path, capture_output=True, text=True, timeout=30)
    return r.stdout.strip() if r.returncode == 0 else ""


def _base_branch(path: Path) -> str:
    head = _git(path, "symbolic-ref", "--short", "refs/remotes/origin/HEAD")
    if head:
        return head.removeprefix("origin/")
    for name in ("main", "master"):
        if _git(path, "rev-parse", "--verify", "--quiet", f"origin/{name}"):
            return name
    return _git(path, "rev-parse", "--abbrev-ref", "HEAD") or "main"


def _python(path: Path) -> str | None:
    for base in [path, *sorted(p for p in path.iterdir() if p.is_dir() and not p.name.startswith("."))]:
        candidate = base / ".venv" / "bin" / "python"
        if candidate.is_file():
            return str(candidate)
    return None


def _checks(path: Path, python: str | None) -> list[dict]:
    found = []
    for base in [path, *sorted(p for p in path.iterdir() if p.is_dir() and not p.name.startswith(".") and p.name not in SKIP_DIRS)]:
        rel = str(base.relative_to(path))
        where = "" if rel == "." else f" ({rel})"
        pyproject = base / "pyproject.toml"
        if pyproject.is_file() and "pytest" in pyproject.read_text(errors="ignore"):
            found.append({"name": f"Python tests{where}", "cmd": "{python} -m pytest -q -p no:cacheprovider", "cwd": rel})
        package = base / "package.json"
        if package.is_file():
            try:
                scripts = json.loads(package.read_text()).get("scripts", {})
            except ValueError:
                scripts = {}
            if "test" in scripts:
                found.append({"name": f"JS tests{where}", "cmd": "npm test --silent", "cwd": rel})
            if (base / "tsconfig.json").is_file():
                found.append({"name": f"Typecheck{where}", "cmd": "npx tsc --noEmit", "cwd": rel})
            if "lint" in scripts:
                found.append({"name": f"Lint{where}", "cmd": "npm run lint --silent", "cwd": rel})
    return found


def inspect_repo(path: str) -> dict:
    """Facts about a checkout, each one a suggestion the wizard shows and the user can change."""
    p = Path(path).expanduser()
    if not p.is_dir():
        return {"ok": False, "error": f"{p} is not a folder"}
    if not _git(p, "rev-parse", "--git-dir"):
        return {"ok": False, "error": f"{p} is not a git repository"}
    p = Path(_git(p, "rev-parse", "--show-toplevel"))
    remote = _git(p, "remote", "get-url", "origin")
    if not remote:
        return {"ok": False, "error": "This repository has no `origin` remote: agents push their branches there."}
    slug = re.search(r"github\.com[:/]([^/]+/[^/]+?)(?:\.git)?$", remote)
    python = _python(p)
    dirty = [line for line in _git(p, "status", "--porcelain").splitlines() if line.strip()]
    areas = sorted(d.name for d in p.iterdir() if d.is_dir() and not d.name.startswith(".") and d.name not in SKIP_DIRS and d.name != "__pycache__")
    return {
        "ok": True, "path": str(p), "name": re.sub(r"[^a-z0-9_-]+", "-", p.name.lower()).strip("-") or "project",
        "remote": remote, "github_slug": slug.group(1) if slug else None,
        "base_branch": _base_branch(p), "branch": _git(p, "rev-parse", "--abbrev-ref", "HEAD"),
        "clean": not dirty, "dirty": len(dirty), "python": python, "checks": _checks(p, python), "areas": areas,
    }


def _ssh_url(remote: str) -> str | None:
    m = re.match(r"https://github\.com/([^/]+/[^/]+?)(?:\.git)?/?$", remote)
    return f"git@github.com:{m.group(1)}.git" if m else None


def _ls_remote(target: str, cwd: Path, env: dict[str, str]) -> str | None:
    """None when git can read the remote; otherwise git's own explanation."""
    try:
        r = subprocess.run(["git", "ls-remote", "--exit-code", target, "HEAD"], cwd=cwd, env=env, capture_output=True, text=True, timeout=25)
    except subprocess.TimeoutExpired:
        return "the remote did not answer in time"
    return None if r.returncode == 0 else (r.stderr.strip().splitlines() or ["git could not read the remote"])[-1]


def git_access(path: str, token: str | None = None) -> dict:
    """Can git read this checkout's `origin` the way autodev will (no terminal, the project's token for https)?

    If not, and the remote is a GitHub https URL, says whether the same repository answers over SSH.
    """
    p = Path(path).expanduser()
    remote = _git(p, "remote", "get-url", "origin")
    if not remote:
        return {"ok": False, "remote": "", "error": "no origin remote"}
    problem = _ls_remote("origin", p, workspace.network_env(token=token))
    out = {"ok": problem is None, "remote": remote, "error": problem, "ssh_url": None}
    ssh = _ssh_url(remote)
    if problem and ssh:
        ssh_env = {**os.environ, "GIT_TERMINAL_PROMPT": "0", "GIT_SSH_COMMAND": "ssh -o BatchMode=yes -o ConnectTimeout=8"}
        if _ls_remote(ssh, p, ssh_env) is None:
            out["ssh_url"] = ssh
    return out


def use_ssh(path: str) -> dict:
    """Points `origin` at the SSH address of the same GitHub repository, when that answers."""
    p = Path(path).expanduser()
    access = git_access(path)
    if not access.get("ssh_url"):
        raise ValueError("the SSH address of this repository does not answer: nothing was changed")
    _git(p, "remote", "set-url", "origin", access["ssh_url"])
    return git_access(path)


def project_dict(*, name: str, repo: str, base_branch: str, local_path: str, language: str = "English",
                 database_id: str, data_source_id: str, python: str | None = None, workspace_mode: str = "inplace",
                 preset: str = "careful", daily_budget_usd: float = 20.0, quiet_hours: str | None = None,
                 checks: list[dict] | None = None, github_slug: str | None = None, github_token_env: str = "GITHUB_TOKEN",
                 area_map_file: str | None = None) -> dict:
    checks = checks or []
    bash = ["git status", "git diff", "git log"] + [c["cmd"] for c in checks]
    cfg: dict = {
        "name": name, "language": language, "repo": repo, "base_branch": base_branch, "local_path": local_path,
        "workspace_mode": workspace_mode,
        "tracker": {"type": "notion", "database_id": database_id, "data_source_id": data_source_id, "status_map": notion_schema.status_map(), "properties": notion_schema.bot_properties()},
        "python": python,
        "agents": {
            "triage": {"models": [MODELS["Haiku"], MODELS["Sonnet"]], "max_turns": 25},
            "fix": {"models": [MODELS["Sonnet"], MODELS["Opus"]], "max_turns": 30, "allowed_bash": bash},
        },
        "model_choices": MODELS,
        "checks": checks,
        "autonomy": {**PRESETS[preset], **({"quiet_hours": quiet_hours} if quiet_hours else {})},
        "limits": {"daily_budget_usd": daily_budget_usd},
        "pr": {"create": True, "slug": github_slug, **({"token_env": github_token_env} if github_token_env != "GITHUB_TOKEN" else {})} if github_slug else {"create": False},
    }
    if area_map_file:
        cfg["area_map"] = area_map_file
    cfg = {k: v for k, v in cfg.items() if v is not None}
    ProjectConfig.model_validate(cfg)  # fail here, not when the dashboard tries to load it
    return cfg


def token_env_for(project: str) -> str:
    """The .env variable that holds one project's GitHub token (each project may belong to another account)."""
    return "GITHUB_TOKEN_" + re.sub(r"[^A-Z0-9]+", "_", project.upper()).strip("_")


def area_map_text(areas: dict[str, list[str]]) -> str:
    out = ["# Code map by ticket area", ""]
    for area, paths in areas.items():
        out += [f"## {area}", *(f"- `{p}`" for p in paths), ""]
    return "\n".join(out)


def write_env(path: Path, values: dict[str, str]) -> None:
    """Sets keys in a .env file (keeping the other lines), readable by the owner only."""
    lines = path.read_text().splitlines() if path.is_file() else []
    for key, value in values.items():
        if not re.fullmatch(r"[A-Z_][A-Z0-9_]*", key) or "\n" in value:
            raise ValueError(f"bad environment entry: {key}")
        entry = f"{key}={value}"
        for i, line in enumerate(lines):
            if line.startswith(f"{key}="):
                lines[i] = entry
                break
        else:
            lines.append(entry)
        os.environ[key] = value
    path.write_text("\n".join(lines) + "\n")
    path.chmod(0o600)


def write_project(projects_dir: Path, name: str, cfg: dict, areas: dict[str, list[str]] | None = None) -> Path:
    if not NAME_RE.match(name):
        raise ValueError("the name may use lowercase letters, digits, - and _ (max 40)")
    target = projects_dir / f"{name}.yaml"
    if target.exists():
        raise FileExistsError(f"{target} already exists")
    projects_dir.mkdir(exist_ok=True)
    if areas:
        (projects_dir / f"{name}.area_map.md").write_text(area_map_text(areas))
    target.write_text(yaml.safe_dump(cfg, sort_keys=False, allow_unicode=True))
    return target


# ---- the GitHub CLI: an account already signed in is the shortest way to connect --------------------
GH_LOGIN = ["gh", "auth", "login", "--hostname", "github.com", "--git-protocol", "https", "--web", "--skip-ssh-key"]
CODE_RE = re.compile(r"\b([A-Z0-9]{4}-[A-Z0-9]{4})\b")
URL_RE = re.compile(r"https://github\.com/login/device\S*")


def gh_accounts() -> list[str] | None:
    """Logins `gh` is signed in with on github.com; [] when it is installed but nobody is, None when it is not installed."""
    if not shutil.which("gh"):
        return None
    try:
        r = subprocess.run(["gh", "auth", "status", "--json", "hosts"], capture_output=True, text=True, timeout=15)
        hosts = json.loads(r.stdout).get("hosts", {}).get("github.com", [])
    except (ValueError, subprocess.TimeoutExpired):
        return []
    return [h["login"] for h in hosts if h.get("state") == "success"]


def gh_token(login: str) -> str | None:
    try:
        r = subprocess.run(["gh", "auth", "token", "--hostname", "github.com", "--user", login], capture_output=True, text=True, timeout=15)
    except subprocess.TimeoutExpired:
        return None
    return r.stdout.strip() or None if r.returncode == 0 else None


class GhLogin:
    """`gh auth login --web` run for the user: it prints a one-time code and an address, then waits for them to approve."""

    def __init__(self, command: list[str] | None = None):
        self.command = command or GH_LOGIN
        self.code: str | None = None
        self.url: str | None = None
        self.done = False
        self.ok = False
        self.error: str | None = None
        self._proc: asyncio.subprocess.Process | None = None
        self._task: asyncio.Task | None = None

    def start(self) -> None:
        self._task = asyncio.ensure_future(self._run())

    async def _run(self) -> None:
        try:
            self._proc = await asyncio.create_subprocess_exec(
                *self.command, stdin=asyncio.subprocess.DEVNULL, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT, cwd=Path.home())
            assert self._proc.stdout
            async with asyncio.timeout(15 * 60):
                async for raw in self._proc.stdout:
                    line = raw.decode(errors="replace")
                    self.code = self.code or (m.group(1) if (m := CODE_RE.search(line)) else None)
                    self.url = self.url or (m.group(0) if (m := URL_RE.search(line)) else None)
                await self._proc.wait()
            self.ok = self._proc.returncode == 0
            if not self.ok:
                self.error = "GitHub sign-in did not finish"
        except TimeoutError:
            self.error = "Nobody approved the code in time"
            self.stop()
        except Exception as e:
            self.error = f"Could not start `gh`: {e}"
        finally:
            self.done = True

    def stop(self) -> None:
        if self._proc and self._proc.returncode is None:
            self._proc.kill()

    def state(self) -> dict:
        return {"code": self.code, "url": self.url, "done": self.done, "ok": self.ok, "error": self.error}
