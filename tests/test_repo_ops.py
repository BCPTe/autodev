import subprocess

import httpx
import pytest
import respx

from autodev import github
from autodev.server import repo
from autodev.server.repo import RepoError
from tests.fixture_repo import make_project


def git(cwd, *args):
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()


@pytest.fixture
def project(tmp_path):
    cfg = make_project(tmp_path)
    git(cfg.local_path, "fetch", "-q")
    return cfg


def agent_branch(cfg, name, content, *, merge=False):
    git(cfg.local_path, "checkout", "-q", "-b", name)
    (__import__("pathlib").Path(cfg.local_path) / "shop" / "pricing.py").write_text(content)
    git(cfg.local_path, "commit", "-qam", f"work on {name}")
    git(cfg.local_path, "checkout", "-q", "main")
    if merge:
        git(cfg.local_path, "merge", "-q", "--no-ff", name, "-m", "merge")
        git(cfg.local_path, "push", "-q", "origin", "main")
        git(cfg.local_path, "fetch", "-q")


def test_diff_of_a_branch_lists_files_with_counts_and_patch(project):
    agent_branch(project, "autodev/fix-a", "def apply_discount(price, percent):\n    return price * (1 - percent / 100)\n")
    d = repo.diff(project, "autodev/fix-a")
    assert [f["path"] for f in d["files"]] == ["shop/pricing.py"]
    f = d["files"][0]
    assert (f["additions"], f["deletions"]) == (2, 2)
    assert "+    return price * (1 - percent / 100)" in f["patch"]


def test_diff_without_a_branch_shows_uncommitted_changes_and_refuses_foreign_branches(project):
    assert repo.diff(project)["files"] == []
    (__import__("pathlib").Path(project.local_path) / "shop" / "pricing.py").write_text("x = 1\n")
    assert [f["path"] for f in repo.diff(project)["files"]] == ["shop/pricing.py"]
    with pytest.raises(RepoError):
        repo.diff(project, "main")


def test_checkout_refuses_a_dirty_tree_and_foreign_branches(project):
    agent_branch(project, "autodev/fix-a", "y = 2\n")
    (__import__("pathlib").Path(project.local_path) / "scratch.txt").write_text("wip")
    with pytest.raises(RepoError, match="uncommitted"):
        repo.checkout(project, "autodev/fix-a")
    with pytest.raises(RepoError, match="only switch"):
        repo.checkout(project, "somebody/else")
    (__import__("pathlib").Path(project.local_path) / "scratch.txt").unlink()
    repo.checkout(project, "autodev/fix-a")
    assert git(project.local_path, "rev-parse", "--abbrev-ref", "HEAD") == "autodev/fix-a"
    repo.checkout(project, "main")


def test_only_merged_branches_are_removable_and_unmerged_ones_are_never_forced(project):
    agent_branch(project, "autodev/merged", "a = 1\n", merge=True)
    agent_branch(project, "autodev/open", "b = 2\n")
    assert repo.removable_branches(project) == ["autodev/merged"]
    with pytest.raises(RepoError, match="autodev/open"):
        repo.delete_branches(project, ["autodev/open"])
    assert repo.delete_branches(project, ["autodev/merged"]) == ["autodev/merged"]
    assert "autodev/merged" not in git(project.local_path, "branch")
    assert "autodev/open" in git(project.local_path, "branch")


def test_a_branch_whose_pull_request_was_squash_merged_counts_as_merged(project):
    agent_branch(project, "autodev/squashed", "c = 3\n")
    assert repo.removable_branches(project) == []
    assert repo.removable_branches(project, {"autodev/squashed"}) == ["autodev/squashed"]
    assert repo.delete_branches(project, ["autodev/squashed"], {"autodev/squashed"}) == ["autodev/squashed"]


def test_the_active_branch_is_never_removed(project):
    agent_branch(project, "autodev/merged", "a = 1\n", merge=True)
    git(project.local_path, "checkout", "-q", "autodev/merged")
    assert repo.removable_branches(project) == []


def pr(number, branch, state="open", merged_at=None, sha="abc"):
    return {
        "number": number, "title": f"fix {number}", "html_url": f"https://github.com/o/r/pull/{number}", "state": state,
        "merged_at": merged_at, "draft": False, "body": "corpo", "updated_at": "2026-10-21T10:00:00Z",
        "user": {"login": "bot"}, "head": {"ref": branch, "sha": sha},
    }


@respx.mock
async def test_pull_requests_are_filtered_by_prefix_and_open_ones_carry_check_status(project, monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "t")
    project.pr.slug = "o/r"
    base = "https://api.github.com/repos/o/r"
    respx.get(f"{base}/pulls", params={"state": "all"}).mock(return_value=httpx.Response(200, json=[
        pr(1, "autodev/fix-a"), pr(2, "feature/other"), pr(3, "autodev/old", state="closed", merged_at="2026-10-20T00:00:00Z"),
    ]))
    respx.get(f"{base}/commits/abc/check-runs").mock(return_value=httpx.Response(200, json={"check_runs": [
        {"status": "completed", "conclusion": "success"}, {"status": "in_progress", "conclusion": None}]}))
    respx.get(f"{base}/commits/abc/status").mock(return_value=httpx.Response(200, json={"statuses": []}))
    respx.get(f"{base}/actions/runs").mock(return_value=httpx.Response(200, json={"workflow_runs": []}))
    respx.get(f"{base}/pulls/1").mock(return_value=httpx.Response(200, json={"mergeable": True}))
    prs = await github.list_pulls(project, "autodev")
    assert [(p["number"], p["state"]) for p in prs] == [(1, "open"), (3, "merged")]
    assert prs[0]["checks"] == {"verdict": "pending", "total": 2, "failed": 0, "pending": 1}
    assert prs[0]["mergeable"] is True and prs[1]["checks"] is None


def test_check_verdicts():
    s = github._checks_summary
    assert s([], [])["verdict"] == "none"
    assert s([{"status": "completed", "conclusion": "success"}], [])["verdict"] == "passing"
    assert s([{"status": "completed", "conclusion": "failure"}], [{"state": "success"}])["verdict"] == "failing"


@respx.mock
async def test_merge_surfaces_githubs_reason_when_refused(project, monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "t")
    project.pr.slug = "o/r"
    respx.put("https://api.github.com/repos/o/r/pulls/1/merge").mock(return_value=httpx.Response(405, json={"message": "Required status check is failing"}))
    with pytest.raises(RuntimeError, match="Required status check"):
        await github.merge_pull(project, 1)


@respx.mock
async def test_statuses_the_token_cannot_read_are_unknown_not_absent(project, monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "t")
    project.pr.slug = "o/r"
    base = "https://api.github.com/repos/o/r"
    respx.get(f"{base}/pulls", params={"state": "all"}).mock(return_value=httpx.Response(200, json=[pr(1, "autodev/fix-a")]))
    respx.get(f"{base}/commits/abc/status").mock(return_value=httpx.Response(403, json={"message": "Resource not accessible"}))
    respx.get(f"{base}/pulls/1").mock(return_value=httpx.Response(200, json={"mergeable": True}))
    prs = await github.list_pulls(project, "autodev")
    assert prs[0]["checks"]["verdict"] == "unknown" and "Commit statuses" in prs[0]["checks"]["reason"]


@respx.mock
async def test_a_fine_grained_token_has_no_check_runs_but_statuses_and_actions_still_count(project, monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "t")
    project.pr.slug = "o/r"
    base = "https://api.github.com/repos/o/r"
    respx.get(f"{base}/pulls", params={"state": "all"}).mock(return_value=httpx.Response(200, json=[pr(1, "autodev/fix-a")]))
    respx.get(f"{base}/commits/abc/status").mock(return_value=httpx.Response(200, json={"statuses": [{"state": "failure"}, {"state": "success"}]}))
    respx.get(f"{base}/commits/abc/check-runs").mock(return_value=httpx.Response(403))
    respx.get(f"{base}/actions/runs").mock(return_value=httpx.Response(200, json={"workflow_runs": [{"status": "completed", "conclusion": "success"}]}))
    respx.get(f"{base}/pulls/1").mock(return_value=httpx.Response(200, json={"mergeable": True}))
    checks = (await github.list_pulls(project, "autodev"))[0]["checks"]
    assert checks == {"verdict": "failing", "total": 3, "failed": 1, "pending": 0}


@respx.mock
async def test_without_actions_permission_the_pull_request_still_shows_its_statuses_with_a_note(project, monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "t")
    project.pr.slug = "o/r"
    base = "https://api.github.com/repos/o/r"
    respx.get(f"{base}/pulls", params={"state": "all"}).mock(return_value=httpx.Response(200, json=[pr(1, "autodev/fix-a")]))
    respx.get(f"{base}/commits/abc/status").mock(return_value=httpx.Response(200, json={"statuses": [{"state": "success"}]}))
    respx.get(f"{base}/commits/abc/check-runs").mock(return_value=httpx.Response(403))
    respx.get(f"{base}/actions/runs").mock(return_value=httpx.Response(403))
    respx.get(f"{base}/pulls/1").mock(return_value=httpx.Response(200, json={"mergeable": True}))
    checks = (await github.list_pulls(project, "autodev"))[0]["checks"]
    assert checks["verdict"] == "passing" and "Actions" in checks["note"]


def remote_merge(project, tmp_path, branch):
    """Someone merges `branch` into main on the remote (as GitHub does) without touching the local checkout."""
    other = tmp_path / "other"
    subprocess.run(["git", "clone", "-q", str(tmp_path / "origin.git"), str(other)], check=True)
    for k, v in (("user.name", "o"), ("user.email", "o@o")):
        git(other, "config", k, v)
    git(other, "fetch", "-q", "origin", branch)
    git(other, "merge", "-q", "--no-ff", f"origin/{branch}", "-m", "merge via PR")
    git(other, "push", "-q", "origin", "main")


def test_after_a_merge_the_checkout_leaves_the_merged_branch_and_catches_up(project, tmp_path):
    agent_branch(project, "autodev/fix-a", "a = 1\n")
    git(project.local_path, "push", "-q", "origin", "autodev/fix-a")
    git(project.local_path, "checkout", "-q", "autodev/fix-a")
    remote_merge(project, tmp_path, "autodev/fix-a")
    assert repo.return_to_base_after_merge(project, "autodev/fix-a") == "main"
    assert git(project.local_path, "rev-parse", "--abbrev-ref", "HEAD") == "main"
    assert "merge via PR" in git(project.local_path, "log", "-1", "--format=%s")
    assert "autodev/fix-a" not in git(project.local_path, "branch")


def test_after_a_merge_nothing_is_touched_when_the_checkout_is_elsewhere_or_dirty(project, tmp_path):
    agent_branch(project, "autodev/fix-a", "a = 1\n")
    assert repo.return_to_base_after_merge(project, "autodev/fix-a") is None  # on main, not on the branch
    git(project.local_path, "checkout", "-q", "autodev/fix-a")
    (__import__("pathlib").Path(project.local_path) / "wip.txt").write_text("my work")
    assert repo.return_to_base_after_merge(project, "autodev/fix-a") is None
    assert git(project.local_path, "rev-parse", "--abbrev-ref", "HEAD") == "autodev/fix-a"


def test_going_back_to_the_base_branch_brings_it_up_to_date(project, tmp_path):
    agent_branch(project, "autodev/fix-a", "a = 1\n")
    git(project.local_path, "push", "-q", "origin", "autodev/fix-a")
    remote_merge(project, tmp_path, "autodev/fix-a")
    git(project.local_path, "checkout", "-q", "autodev/fix-a")
    repo.checkout(project, "main")
    assert "merge via PR" in git(project.local_path, "log", "-1", "--format=%s")


# ---- pushing the base branch after a local merge --------------------------------------------
def commit_on_main(cfg, name, body=""):
    path = __import__("pathlib").Path(cfg.local_path) / f"{name}.txt"
    path.write_text(name)
    git(cfg.local_path, "add", path.name)
    git(cfg.local_path, "commit", "-qm", f"{name}\n\n{body}".strip())
    return git(cfg.local_path, "rev-parse", "HEAD")


def remote_head(cfg):
    git(cfg.local_path, "fetch", "-q")
    return git(cfg.local_path, "rev-parse", "origin/main")


def test_the_push_plan_lists_what_would_go_out_and_marks_the_commits_that_are_not_autodevs(project):
    mine = commit_on_main(project, "mine")
    tip = commit_on_main(project, "fix: Bug", "Ticket: https://notion.so/x")
    plan = repo.push_plan(project, tip)
    assert [(c["subject"], c["autodev"]) for c in plan["commits"]] == [("mine", False), ("fix: Bug", True)]
    assert plan["own_count"] == 1 and plan["can_push"] and plan["target"] == tip
    assert mine[:8] == plan["commits"][0]["sha"]


def test_pushing_stops_at_the_autodev_commit_so_later_work_stays_local(project):
    tip = commit_on_main(project, "fix: Bug", "Ticket: https://notion.so/x")
    later = commit_on_main(project, "mine-after")
    plan = repo.push_base(project, tip)
    assert [c["subject"] for c in plan["commits"]] == ["fix: Bug"]
    assert remote_head(project) == tip and git(project.local_path, "rev-parse", "HEAD") == later


def test_commits_made_before_the_merge_cannot_be_left_behind(project):
    mine = commit_on_main(project, "mine-before")
    tip = commit_on_main(project, "fix: Bug", "Ticket: https://notion.so/x")
    repo.push_base(project, tip)
    assert remote_head(project) == tip and git(project.local_path, "merge-base", "--is-ancestor", mine, "origin/main") == ""


def test_nothing_is_pushed_when_origin_is_ahead_or_already_up_to_date(project, tmp_path):
    assert repo.push_plan(project)["can_push"] is False and "already on origin" in repo.push_plan(project)["reason"]
    other = tmp_path / "other"
    git(tmp_path, "clone", "-q", git(project.local_path, "remote", "get-url", "origin"), str(other))
    commit_on_main(type("C", (), {"local_path": str(other)}), "theirs")
    git(other, "push", "-q", "origin", "main")
    commit_on_main(project, "fix: Bug", "Ticket: https://notion.so/x")
    plan = repo.push_plan(project)
    assert plan["can_push"] is False and "pull" in plan["reason"]
    with pytest.raises(RepoError):
        repo.push_base(project)


def test_a_forgotten_tip_falls_back_to_the_whole_branch(project):
    commit_on_main(project, "fix: Bug", "Ticket: https://notion.so/x")
    assert repo.push_plan(project, "0" * 40)["target"] == git(project.local_path, "rev-parse", "main")
