import subprocess

import pytest

from autodev.checks import regression_gate
from autodev.models import Status, Ticket
from autodev.sandbox.workspace import DirtyCheckout, Workspace

from tests.fixture_repo import PRICING_FIXED, make_project
from tests.test_regression_gate import REGRESSION_TEST

TICKET = Ticket(id="abcdef12-0000-0000-0000-000000000000", title="Discount is wrong", status=Status.NEW)


def git_out(path, *args):
    return subprocess.run(["git", *args], cwd=path, capture_output=True, text=True, check=True).stdout.strip()


@pytest.fixture
def project(tmp_path):
    cfg = make_project(tmp_path)
    cfg.workspace_mode = "inplace"
    return cfg, tmp_path / "local"


def test_works_directly_in_the_project_checkout_on_its_own_branch(project):
    cfg, local = project
    ws = Workspace.create(cfg, TICKET)
    assert ws.path == local and ws.inplace and not ws.resumed
    assert git_out(local, "rev-parse", "--abbrev-ref", "HEAD") == ws.branch
    assert ws.branch.startswith("autodev/discount-is-wrong-")


def test_refuses_to_start_when_the_checkout_has_uncommitted_work(project):
    cfg, local = project
    (local / "shop" / "pricing.py").write_text("# my wip\n")
    (local / "notes.txt").write_text("untracked wip\n")
    with pytest.raises(DirtyCheckout) as e:
        Workspace.create(cfg, TICKET)
    assert "shop/pricing.py" in str(e.value) and "notes.txt" in str(e.value) and "git stash" in str(e.value)
    assert git_out(local, "rev-parse", "--abbrev-ref", "HEAD") == "main"
    assert (local / "shop" / "pricing.py").read_text() == "# my wip\n"


def test_commits_are_authored_by_autodev_without_touching_the_repo_config(project):
    cfg, local = project
    ws = Workspace.create(cfg, TICKET)
    (ws.path / "shop" / "new.py").write_text("X = 1\n")
    ws.commit("add new")
    assert git_out(local, "log", "-1", "--format=%an <%ae>") == "autodev <autodev@users.noreply.github.com>"
    assert git_out(local, "config", "user.name") == "t"


def test_second_run_resumes_the_branch_it_left_checked_out(project):
    cfg, local = project
    ws = Workspace.create(cfg, TICKET)
    (ws.path / "shop" / "new.py").write_text("X = 1\n")
    ws.commit("first run")
    again = Workspace.create(cfg, TICKET)
    assert again.resumed and again.branch == ws.branch and "first run" in again.history()
    assert again.changed_files() == []


def test_can_come_back_to_an_existing_branch_from_another_one(project):
    cfg, local = project
    ws = Workspace.create(cfg, TICKET)
    (ws.path / "shop" / "new.py").write_text("X = 1\n")
    ws.commit("first run")
    git_out(local, "checkout", "main")
    again = Workspace.create(cfg, TICKET)
    assert again.resumed and (local / "shop" / "new.py").exists()


def test_gate_only_touches_the_files_of_the_run_and_leaves_ignored_files_alone(project):
    cfg, local = project
    (local / ".gitignore").write_text("cache/\n")
    git_out(local, "add", "-A")
    git_out(local, "commit", "-q", "-m", "ignore cache")
    git_out(local, "push", "-q", "origin", "main")
    ws = Workspace.create(cfg, TICKET)
    (local / "cache").mkdir()
    (local / "cache" / "kept.txt").write_text("do not delete\n")

    (ws.path / "tests" / "test_discount_regression.py").write_text(REGRESSION_TEST)
    (ws.path / "shop" / "pricing.py").write_text(PRICING_FIXED)
    ws.commit("fix")
    assert regression_gate(cfg, ws).ok
    assert (local / "cache" / "kept.txt").read_text() == "do not delete\n"
    assert (local / "shop" / "pricing.py").read_text() == PRICING_FIXED
    assert git_out(local, "status", "--porcelain") == ""


def test_discard_removes_only_the_runs_changes_including_new_files(project):
    cfg, local = project
    (local / ".gitignore").write_text("cache/\n")
    git_out(local, "add", "-A")
    git_out(local, "commit", "-q", "-m", "ignore cache")
    git_out(local, "push", "-q", "origin", "main")
    ws = Workspace.create(cfg, TICKET)
    (local / "cache").mkdir()
    (local / "cache" / "kept.txt").write_text("keep\n")
    (ws.path / "shop" / "pricing.py").write_text("# half done\n")
    (ws.path / "shop" / "brand_new.py").write_text("Z = 3\n")

    patch = ws.discard_changes()

    assert patch is not None and "brand_new.py" in patch.read_text() and "half done" in patch.read_text()
    assert not (local / "shop" / "brand_new.py").exists()
    assert (local / "shop" / "pricing.py").read_text() != "# half done\n"
    assert (local / "cache" / "kept.txt").exists()
    assert git_out(local, "status", "--porcelain") == ""
