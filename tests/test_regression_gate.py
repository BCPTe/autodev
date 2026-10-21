import pytest

from autodev.checks import regression_gate, run_checks
from autodev.models import Status, Ticket
from autodev.sandbox import workspace as wsmod
from autodev.sandbox.workspace import Workspace

from tests.fixture_repo import PRICING_FIXED, make_project

REGRESSION_TEST = '''from shop.pricing import apply_discount


def test_percent_discount_is_a_percentage_of_the_price():
    assert apply_discount(200, 25) == 150
'''
TEST_THAT_NEVER_FAILS = '''from shop.pricing import apply_discount


def test_zero_discount_is_identity_again():
    assert apply_discount(50, 0) == 50
'''


@pytest.fixture
def setup(tmp_path, monkeypatch):
    monkeypatch.setattr(wsmod, "WORKSPACES", tmp_path / "workspaces")
    cfg = make_project(tmp_path)
    ticket = Ticket(id="abcdef12-0000-0000-0000-000000000000", title="Discount is wrong", status=Status.NEW)
    return cfg, Workspace.create(cfg, ticket)


def test_workspace_branches_from_remote_base_not_local_changes(tmp_path, monkeypatch):
    monkeypatch.setattr(wsmod, "WORKSPACES", tmp_path / "workspaces")
    cfg = make_project(tmp_path)
    (tmp_path / "local" / "shop" / "pricing.py").write_text("# local uncommitted work\n")
    ws = Workspace.create(cfg, Ticket(id="11111111-aaaa", title="x", status=Status.NEW))
    assert "local uncommitted" not in (ws.path / "shop" / "pricing.py").read_text()
    assert ws.branch.startswith("autodev/x-")


def test_gate_passes_when_new_test_fails_without_fix_and_passes_with_it(setup):
    cfg, ws = setup
    (ws.path / "tests" / "test_discount_regression.py").write_text(REGRESSION_TEST)
    (ws.path / "shop" / "pricing.py").write_text(PRICING_FIXED)
    ws.commit("fix")
    result = regression_gate(cfg, ws)
    assert result.ok, result.output
    assert (ws.path / "shop" / "pricing.py").read_text() == PRICING_FIXED
    assert all(c.ok for c in run_checks(cfg, ws))


def test_gate_rejects_a_test_that_passes_without_the_fix(setup):
    cfg, ws = setup
    (ws.path / "tests" / "test_identity.py").write_text(TEST_THAT_NEVER_FAILS)
    (ws.path / "shop" / "pricing.py").write_text(PRICING_FIXED)
    ws.commit("fix")
    result = regression_gate(cfg, ws)
    assert not result.ok
    assert "prove nothing" in result.output


def test_gate_rejects_a_fix_without_any_new_test(setup):
    cfg, ws = setup
    (ws.path / "shop" / "pricing.py").write_text(PRICING_FIXED)
    ws.commit("fix")
    result = regression_gate(cfg, ws)
    assert not result.ok
    assert "no new test" in result.output


def test_gate_rejects_edits_to_existing_tests_as_the_only_test_change(setup):
    cfg, ws = setup
    (ws.path / "tests" / "test_pricing.py").write_text(REGRESSION_TEST)
    (ws.path / "shop" / "pricing.py").write_text(PRICING_FIXED)
    ws.commit("fix")
    assert not regression_gate(cfg, ws).ok
    assert ws.modified_existing() == ["shop/pricing.py", "tests/test_pricing.py"]


def test_gate_fails_when_the_new_test_still_fails_with_the_fix(setup):
    cfg, ws = setup
    (ws.path / "tests" / "test_discount_regression.py").write_text(REGRESSION_TEST)
    (ws.path / "shop" / "pricing.py").write_text("def apply_discount(price, percent):\n    return price\n")
    ws.commit("wrong fix")
    result = regression_gate(cfg, ws)
    assert not result.ok
    assert "fail with the fix" in result.output


SECOND_TEST = '''from shop.pricing import apply_discount


def test_discount_above_100_percent_never_goes_negative():
    assert apply_discount(100, 150) == 0
'''
SECOND_FIX = '''def apply_discount(price: float, percent: float) -> float:
    return max(0.0, price * (1 - percent / 100))
'''


def _first_run_committed(cfg, tmp_path):
    ticket = Ticket(id="abcdef12-0000-0000-0000-000000000000", title="Discount is wrong", status=Status.NEW)
    ws = Workspace.create(cfg, ticket)
    (ws.path / "tests" / "test_discount_regression.py").write_text(REGRESSION_TEST)
    (ws.path / "shop" / "pricing.py").write_text(PRICING_FIXED)
    ws.commit("first run")
    return ticket, ws


def test_second_run_resumes_the_same_branch_and_drops_leftovers(setup, tmp_path):
    cfg, _ = setup
    ticket, ws1 = _first_run_committed(cfg, tmp_path)
    (ws1.path / "shop" / "leftover.py").write_text("junk = 1\n")
    (ws1.path / "shop" / "pricing.py").write_text("# half-done edit\n")

    ws2 = Workspace.create(cfg, ticket)

    assert ws2.resumed and ws2.path == ws1.path and ws2.branch == ws1.branch
    assert not (ws2.path / "shop" / "leftover.py").exists()
    assert (ws2.path / "shop" / "pricing.py").read_text() == PRICING_FIXED
    assert ws2.start_ref != ws2.base_ref
    assert ws2.changed_files() == []
    assert "first run" in ws2.history()


def test_resumed_run_is_judged_only_on_its_own_changes(setup, tmp_path):
    cfg, _ = setup
    ticket, _ = _first_run_committed(cfg, tmp_path)
    ws = Workspace.create(cfg, ticket)
    (ws.path / "tests" / "test_discount_cap.py").write_text(SECOND_TEST)
    (ws.path / "shop" / "pricing.py").write_text(SECOND_FIX)
    ws.commit("second run")

    assert ws.changed_files() == ["shop/pricing.py", "tests/test_discount_cap.py"]
    assert "tests/test_discount_regression.py" in ws.changed_files(ws.base_ref)
    assert regression_gate(cfg, ws).ok


def test_resumed_run_without_a_new_test_is_rejected_even_though_earlier_tests_exist(setup, tmp_path):
    cfg, _ = setup
    ticket, _ = _first_run_committed(cfg, tmp_path)
    ws = Workspace.create(cfg, ticket)
    (ws.path / "shop" / "pricing.py").write_text(SECOND_FIX)
    ws.commit("second run, no test")
    result = regression_gate(cfg, ws)
    assert not result.ok and "no new test" in result.output


def test_failed_verification_rolls_back_only_the_current_run(setup, tmp_path):
    from autodev.pipeline import git_soft_reset

    cfg, _ = setup
    ticket, _ = _first_run_committed(cfg, tmp_path)
    ws = Workspace.create(cfg, ticket)
    (ws.path / "shop" / "pricing.py").write_text(SECOND_FIX)
    ws.commit("second run")
    git_soft_reset(ws)
    assert "first run" in ws.history()
    assert ws.changed_files() == ["shop/pricing.py"]


def test_discard_changes_saves_a_patch_and_restores_the_tree(setup):
    cfg, ws = setup
    (ws.path / "shop" / "pricing.py").write_text("# untested edit\n")
    patch = ws.discard_changes()
    assert patch is not None and "untested edit" in patch.read_text()
    assert ws.changed_files() == []
    assert ws.discard_changes() is None


def test_gate_handles_several_suites_and_paths_with_shell_characters(setup):
    from autodev.config import Regression

    cfg, ws = setup
    cfg.regressions = [
        *cfg.regressions,
        Regression(test_globs=["web/*.py"], cmd="{python} -m pytest -q -p no:cacheprovider {tests}"),
    ]
    tricky = ws.path / "web" / "(dashboard)" / "new page"
    tricky.mkdir(parents=True)
    (tricky / "test_discount_page.py").write_text(REGRESSION_TEST.replace("def test_percent", "def test_page_percent"))
    (ws.path / "tests" / "test_discount_regression.py").write_text(REGRESSION_TEST)
    (ws.path / "shop" / "pricing.py").write_text(PRICING_FIXED)
    ws.commit("fix")
    result = regression_gate(cfg, ws)
    assert result.ok, result.output
    assert "2 suite(s)" in result.output


def test_gate_names_the_suite_whose_new_test_proves_nothing(setup):
    from autodev.config import Regression

    cfg, ws = setup
    cfg.regressions = [
        *cfg.regressions,
        Regression(test_globs=["web/*.py"], cmd="{python} -m pytest -q -p no:cacheprovider {tests}"),
    ]
    (ws.path / "web").mkdir()
    (ws.path / "web" / "test_always_green.py").write_text("def test_nothing():\n    assert True\n")
    (ws.path / "tests" / "test_discount_regression.py").write_text(REGRESSION_TEST)
    (ws.path / "shop" / "pricing.py").write_text(PRICING_FIXED)
    ws.commit("fix")
    result = regression_gate(cfg, ws)
    assert not result.ok
    assert "web/test_always_green.py" in result.output and "prove nothing" in result.output


def _advance_remote_base(tmp_path, name, content):
    import subprocess

    other = tmp_path / "other"
    if not other.exists():
        subprocess.run(["git", "clone", "-q", str(tmp_path / "origin.git"), str(other)], check=True, capture_output=True)
        for k, v in (("user.name", "t"), ("user.email", "t@t")):
            subprocess.run(["git", "config", k, v], cwd=other, check=True)
    (other / name).write_text(content)
    subprocess.run(["git", "add", "-A"], cwd=other, check=True)
    subprocess.run(["git", "commit", "-q", "-m", f"add {name}"], cwd=other, check=True)
    subprocess.run(["git", "push", "-q", "origin", "main"], cwd=other, check=True)


def test_resume_brings_in_changes_that_landed_on_the_base_branch(setup, tmp_path):
    cfg, _ = setup
    ticket, _ = _first_run_committed(cfg, tmp_path)
    _advance_remote_base(tmp_path, "newtool.cfg", "vitest = true\n")

    ws = Workspace.create(cfg, ticket)

    assert (ws.path / "newtool.cfg").read_text() == "vitest = true\n"
    assert "first run" in ws.history()
    assert ws.changed_files() == []


def test_resume_reports_a_conflicting_base_instead_of_losing_work(setup, tmp_path):
    cfg, _ = setup
    ticket, ws1 = _first_run_committed(cfg, tmp_path)
    _advance_remote_base(tmp_path, "shop/pricing.py", "def apply_discount(price, percent):\n    return 0\n")
    with pytest.raises(RuntimeError, match="conflicts"):
        Workspace.create(cfg, ticket)
    assert (ws1.path / "shop" / "pricing.py").read_text() == PRICING_FIXED


def _branches(path) -> list[str]:
    import subprocess

    out = subprocess.run(["git", "branch", "--format=%(refname:short)"], cwd=path, capture_output=True, text=True, check=True)
    return out.stdout.split()


def test_publish_local_makes_the_branch_visible_in_the_users_checkout(setup, tmp_path):
    cfg, _ = setup
    ticket, ws = _first_run_committed(cfg, tmp_path)
    assert ws.branch not in _branches(cfg.local_path)

    ws.publish_local(cfg.local_path)
    assert ws.branch in _branches(cfg.local_path)
    assert (tmp_path / "local" / "shop" / "pricing.py").read_text() != PRICING_FIXED  # working tree untouched

    ws2 = Workspace.create(cfg, ticket)
    (ws2.path / "shop" / "extra.py").write_text("X = 1\n")
    ws2.commit("second run")
    ws2.publish_local(cfg.local_path)  # fast-forwards the published branch


def test_publish_local_reports_when_the_branch_is_checked_out_there(setup, tmp_path):
    import subprocess

    cfg, _ = setup
    _, ws = _first_run_committed(cfg, tmp_path)
    ws.publish_local(cfg.local_path)
    subprocess.run(["git", "checkout", "-q", ws.branch], cwd=cfg.local_path, check=True)
    (ws.path / "shop" / "more.py").write_text("Y = 2\n")
    ws.commit("more")
    with pytest.raises(RuntimeError):
        ws.publish_local(cfg.local_path)
    assert ws.has_commits()
