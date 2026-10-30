import subprocess
from pathlib import Path

import pytest

from autodev.config import load_project
from autodev.server import repo

CFG = load_project(Path(__file__).parent.parent / "projects" / "demo.yaml")


def git(path: Path, *args: str) -> str:
    return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *args], cwd=path, check=True, capture_output=True, text=True).stdout.strip()


@pytest.fixture
def checkout(tmp_path):
    git(tmp_path, "init", "-q", "-b", "main")
    (tmp_path / "a.txt").write_text("a")
    git(tmp_path, "add", "."), git(tmp_path, "commit", "-qm", "base")
    cfg = CFG.model_copy(update={"local_path": str(tmp_path), "base_branch": "main"})
    return cfg, tmp_path, f"{cfg.branch_prefix}/fix-1"


def commit_on(path: Path, branch: str) -> None:
    git(path, "checkout", "-qb", branch)
    (path / "b.txt").write_text("b")
    git(path, "add", "."), git(path, "commit", "-qm", "fix")


def test_fast_forwards_base_and_removes_the_branch(checkout):
    cfg, path, branch = checkout
    commit_on(path, branch)
    assert repo.merge_branch(cfg, branch) == "main"
    assert git(path, "rev-parse", "--abbrev-ref", "HEAD") == "main"
    assert (path / "b.txt").exists()
    assert branch not in git(path, "branch", "--list")


def test_refuses_foreign_branch_and_dirty_tree(checkout):
    cfg, path, branch = checkout
    commit_on(path, branch)
    with pytest.raises(repo.RepoError, match="only a"):
        repo.merge_branch(cfg, "main")
    (path / "a.txt").write_text("dirty")
    with pytest.raises(repo.RepoError, match="uncommitted"):
        repo.merge_branch(cfg, branch)


def test_refuses_diverged_branch_and_leaves_checkout_alone(checkout):
    cfg, path, branch = checkout
    commit_on(path, branch)
    git(path, "checkout", "-q", "main")
    (path / "c.txt").write_text("c")
    git(path, "add", "."), git(path, "commit", "-qm", "main moved")
    git(path, "checkout", "-q", branch)
    with pytest.raises(repo.RepoError, match="not up to date"):
        repo.merge_branch(cfg, branch)
    assert git(path, "rev-parse", "--abbrev-ref", "HEAD") == branch
