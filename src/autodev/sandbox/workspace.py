import re
import shlex
import subprocess
from dataclasses import dataclass
from fnmatch import fnmatch
from pathlib import Path

from autodev.config import ProjectConfig
from autodev.models import Ticket

WORKSPACES = Path(__file__).resolve().parents[3] / "workspaces"
AUTHOR = ["-c", "user.name=autodev", "-c", "user.email=autodev@users.noreply.github.com"]


class DirtyCheckout(RuntimeError):
    """The user's own checkout has uncommitted work, which an agent must never mix with its own."""


def run(cmd: str | list[str], cwd: Path, *, timeout: int = 900) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd if isinstance(cmd, list) else shlex.split(cmd),
        cwd=cwd, capture_output=True, text=True, timeout=timeout,
    )


def sh(cmd: str, cwd: Path, *, timeout: int = 1800) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, shell=True, cwd=cwd, capture_output=True, text=True, timeout=timeout)


def git(cwd: Path, *args: str) -> str:
    r = run(["git", *args], cwd)
    if r.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {r.stderr.strip()}")
    return r.stdout.strip()


def slugify(text: str, limit: int = 40) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:limit].strip("-") or "ticket"


def expand(cmd: str, cfg: ProjectConfig, **extra: str) -> str:
    return cmd.format(python=cfg.python or "python3", local_path=cfg.local_path, **extra)


@dataclass
class Workspace:
    """A working copy on its own branch: a disposable clone, or the project checkout itself.

    ``base_ref`` is the remote base branch the whole branch is measured against (risk, PR
    contents). ``start_ref`` is the commit this run started from: equal to the base for a fresh
    clone, or the previous run's last commit when work is resumed. Verification looks only at
    what changed since ``start_ref``.
    """

    path: Path
    branch: str
    base_ref: str
    start_ref: str = ""
    resumed: bool = False
    inplace: bool = False

    @classmethod
    def create(cls, cfg: ProjectConfig, ticket: Ticket) -> "Workspace":
        if cfg.workspace_mode == "inplace":
            return cls._create_inplace(cfg, ticket)
        return cls._create_clone(cfg, ticket)

    @classmethod
    def _create_inplace(cls, cfg: ProjectConfig, ticket: Ticket) -> "Workspace":
        """Work on the project's own checkout, on a dedicated branch, so the user can test it right there.

        Branches do not isolate uncommitted work (it follows you across a checkout), so a dirty
        tree is refused instead of being swept into the agent's commits.
        """
        path = Path(cfg.local_path)
        branch = f"autodev/{slugify(ticket.title)}-{ticket.id.replace('-', '')[:6]}"
        dirty = git(path, "status", "--porcelain").splitlines()
        if dirty:
            shown = "\n".join(f"  {line}" for line in dirty[:12]) + (f"\n  ... e altri {len(dirty) - 12}" if len(dirty) > 12 else "")
            raise DirtyCheckout(
                f"{path} ha modifiche non committate; l'agente lavora lì e le mischierebbe ai suoi commit.\n{shown}\n"
                "Fai commit o `git stash`, poi rilancia."
            )
        git(path, "fetch", "--quiet", "origin", cfg.base_branch)
        base_ref = f"origin/{cfg.base_branch}"
        if run(["git", "rev-parse", "--verify", "--quiet", f"refs/heads/{branch}"], path).returncode == 0:
            git(path, "checkout", "--quiet", branch)
            cls._merge_base(cfg, path, branch, base_ref)
            resumed = True
        else:
            git(path, "checkout", "--quiet", "-b", branch, base_ref)
            resumed = False
        return cls(path, branch, base_ref, start_ref=git(path, "rev-parse", "HEAD"), resumed=resumed, inplace=True)

    @classmethod
    def _merge_base(cls, cfg: ProjectConfig, path: Path, branch: str, base_ref: str) -> None:
        if run(["git", "merge-base", "--is-ancestor", base_ref, "HEAD"], path).returncode == 0:
            return
        merged = run(["git", *AUTHOR, "merge", "--no-edit", "--quiet", base_ref], path)
        if merged.returncode != 0:
            run(["git", "merge", "--abort"], path)
            raise RuntimeError(
                f"{cfg.base_branch} moved on and merging it into {branch} conflicts; "
                f"resolve it by hand in {path} or delete that folder to start over"
            )

    @classmethod
    def _create_clone(cls, cfg: ProjectConfig, ticket: Ticket) -> "Workspace":
        """Fresh clone of the project at origin/<base_branch> on its own branch.

        Cloned from the local checkout for speed, but based on the remote's tip so the
        user's uncommitted or unpushed work never leaks into an agent's branch.
        """
        WORKSPACES.mkdir(exist_ok=True)
        path = WORKSPACES / f"{slugify(cfg.local_path.rsplit('/', 1)[-1])}-{ticket.id.replace('-', '')[:8]}"
        branch = f"autodev/{slugify(ticket.title)}-{ticket.id.replace('-', '')[:6]}"
        if path.exists():
            return cls._resume(cfg, path, branch)
        git(WORKSPACES, "clone", "--quiet", "--local", cfg.local_path, str(path))
        git(path, "remote", "set-url", "origin", cfg.repo)
        git(path, "fetch", "--quiet", "origin", cfg.base_branch)
        base_ref = f"origin/{cfg.base_branch}"
        git(path, "checkout", "--quiet", "-b", branch, base_ref)
        exclude = path / ".git" / "info" / "exclude"
        exclude.write_text(exclude.read_text() + "\n".join(cfg.exclude) + "\n")
        for cmd in cfg.prepare:
            r = sh(expand(cmd, cfg), path)
            if r.returncode != 0:
                raise RuntimeError(f"prepare step failed: {cmd}\n{r.stderr.strip()}")
        return cls(path, branch, base_ref, start_ref=git(path, "rev-parse", "HEAD"))

    @classmethod
    def _resume(cls, cfg: ProjectConfig, path: Path, branch: str) -> "Workspace":
        """Continue on the branch of an earlier run: drop leftovers, keep its commits."""
        git(path, "fetch", "--quiet", "origin", cfg.base_branch)
        git(path, "checkout", "--quiet", branch)
        git(path, "reset", "--quiet", "--hard", "HEAD")
        git(path, "clean", "-fdq")
        base_ref = f"origin/{cfg.base_branch}"
        cls._merge_base(cfg, path, branch, base_ref)
        return cls(path, branch, base_ref, start_ref=git(path, "rev-parse", "HEAD"), resumed=True)

    def changed_files(self, since: str | None = None) -> list[str]:
        """Files changed relative to ``since`` (default: where this run started)."""
        ref = since or self.start_ref
        tracked = git(self.path, "diff", "--name-only", ref).splitlines()
        untracked = git(self.path, "ls-files", "--others", "--exclude-standard").splitlines()
        return sorted(set(tracked) | set(untracked))

    def modified_existing(self, since: str | None = None) -> list[str]:
        """Files that existed at ``since`` (default: the base branch) and were changed or deleted."""
        out = git(self.path, "diff", "--name-status", since or self.base_ref).splitlines()
        return [line.split("\t", 1)[1] for line in out if line[0] in "MD"]

    def restore_files(self, files: list[str]) -> None:
        """Put exactly these files back to their state at HEAD; delete the ones HEAD does not have.

        Targeted on purpose: in an in-place checkout nothing else may be reset or cleaned.
        """
        for f in files:
            if self.exists_at("HEAD", f):
                git(self.path, "checkout", "HEAD", "--", f)
            else:
                run(["git", "rm", "-f", "--cached", "--quiet", "--ignore-unmatch", "--", f], self.path)
                (self.path / f).unlink(missing_ok=True)

    def discard_changes(self) -> Path | None:
        """Throw away this run's uncommitted work, keeping it as a patch file for inspection."""
        files = self.changed_files()
        if not files:
            return None
        git(self.path, "add", "-A", "--", *files)
        diff = git(self.path, "diff", "--cached", "HEAD", "--", *files)
        if not diff:
            return None
        patch = Path(git(self.path, "rev-parse", "--absolute-git-dir")) / "autodev-discarded.patch"
        patch.write_text(diff + "\n")
        self.restore_files(files)
        return patch

    def exists_at(self, ref: str, file: str) -> bool:
        return run(["git", "cat-file", "-e", f"{ref}:{file}"], self.path).returncode == 0

    def history(self) -> str:
        """Commits and files already on this branch (empty for a fresh clone)."""
        if not self.resumed:
            return ""
        log = git(self.path, "log", "--oneline", f"{self.base_ref}..HEAD")
        stat = git(self.path, "diff", "--stat", self.base_ref, "HEAD")
        return f"{log}\n\n{stat}".strip()

    def commit(self, message: str) -> str:
        git(self.path, "add", "-A")
        git(self.path, *AUTHOR, "commit", "--quiet", "-m", message)
        return git(self.path, "rev-parse", "HEAD")

    def has_commits(self) -> bool:
        return int(git(self.path, "rev-list", "--count", f"{self.base_ref}..HEAD") or 0) > 0

    def publish_local(self, local_path: str) -> None:
        """Make the branch visible in the user's own checkout (`git branch` there lists it).

        Pushes into the local repository without touching its working tree. Git refuses if the
        branch is currently checked out there, which is reported to the caller.
        """
        git(self.path, "push", "--quiet", local_path, f"{self.branch}:refs/heads/{self.branch}")

    def push(self) -> None:
        git(self.path, "push", "--quiet", "-u", "origin", self.branch)


def matches(path: str, globs: list[str]) -> bool:
    return any(fnmatch(path, g) for g in globs)
