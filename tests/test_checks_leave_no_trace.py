import subprocess

from autodev.checks import run_check
from autodev.config import Check
from tests.fixture_repo import make_project


def test_a_check_leaves_the_checkout_exactly_as_it_found_it(tmp_path):
    cfg = make_project(tmp_path)
    path = __import__("pathlib").Path(cfg.local_path)
    (path / ".gitignore").unlink()  # a project that does not ignore its bytecode
    subprocess.run(["git", "commit", "-qam", "no ignore file"], cwd=path, check=True)
    result = run_check(cfg, Check(name="tests", cmd="{python} -m pytest -q -p no:cacheprovider"), path)
    assert result.ok, result.output
    status = subprocess.run(["git", "status", "--porcelain"], cwd=path, capture_output=True, text=True).stdout
    assert status == "", status
