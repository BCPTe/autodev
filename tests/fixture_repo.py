import subprocess
import sys
from pathlib import Path

from autodev.config import AgentConfig, Check, ProjectConfig, Regression, TrackerConfig
from autodev.models import Status

PRICING_BUG = '''def apply_discount(price: float, percent: float) -> float:
    return price - percent
'''
PRICING_FIXED = '''def apply_discount(price: float, percent: float) -> float:
    return price * (1 - percent / 100)
'''
EXISTING_TEST = '''from shop.pricing import apply_discount


def test_zero_discount_keeps_price():
    assert apply_discount(100, 0) == 100
'''
CLAUDE_MD = """# Shop
Run tests with `python -m pytest -q`. Bug fixes need a regression test in tests/ that fails before the fix.
"""


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


def make_project(root: Path) -> ProjectConfig:
    """Tiny project: bare 'remote', local checkout, one bug in shop/pricing.py."""
    origin = root / "origin.git"
    local = root / "local"
    _git(root, "init", "--bare", "--initial-branch=main", str(origin))
    _git(root, "clone", "--quiet", str(origin), str(local))
    (local / "shop").mkdir()
    (local / "tests").mkdir()
    (local / "shop" / "__init__.py").write_text("")
    (local / "shop" / "pricing.py").write_text(PRICING_BUG)
    (local / "tests" / "test_pricing.py").write_text(EXISTING_TEST)
    (local / "CLAUDE.md").write_text(CLAUDE_MD)
    for k, v in (("user.name", "t"), ("user.email", "t@t")):
        _git(local, "config", k, v)
    _git(local, "add", "-A")
    _git(local, "commit", "-q", "-m", "init")
    _git(local, "push", "-q", "origin", "main")

    return ProjectConfig(
        repo=str(origin),
        base_branch="main",
        local_path=str(local),
        tracker=TrackerConfig(type="notion", database_id="x", data_source_id="x", status_map={s: s.value for s in Status}),
        python=sys.executable,
        checks=[Check(name="tests", cmd="{python} -m pytest -q -p no:cacheprovider")],
        regressions=[Regression(test_globs=["tests/*.py"], cmd="{python} -m pytest -q -p no:cacheprovider {tests}")],
        agents={
            "fix": AgentConfig(
                models=["claude-haiku-5-5"],
                max_turns=25,
                allowed_bash=["{python} -m pytest", "python -m pytest", "git status", "git diff", "git log", "tail", "head", "grep"],
            )
        },
    )
