import httpx
import pytest
import respx
import yaml
from fastapi.testclient import TestClient

from autodev import onboarding
from autodev.config import load_project
from autodev.db import Database
from autodev.server.app import build_app
from tests.fixture_repo import make_project

PASSWORD = "una-password-lunga-1"


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.delenv("NOTION_TOKEN", raising=False)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    cfg = make_project(tmp_path)
    projects, dotenv = tmp_path / "projects", tmp_path / ".env"
    app = build_app(Database(tmp_path / "s.db"), [], static_dir=None, projects_dir=projects, env_path=dotenv)
    c = TestClient(app)
    c.post("/api/auth/setup", json={"password": PASSWORD, "code": app.state.auth.setup_code})
    return c, cfg, projects, dotenv


def test_setup_needs_a_session(tmp_path):
    app = build_app(Database(tmp_path / "s.db"), [], static_dir=None)
    assert TestClient(app).post("/api/setup/repo", json={"path": "/tmp"}).status_code == 401


def test_inspect_repo_reads_remote_branch_and_state(env, tmp_path):
    c, cfg, *_ = env
    out = c.post("/api/setup/repo", json={"path": cfg.local_path}).json()
    assert out["ok"] and out["base_branch"] == cfg.base_branch and out["clean"] and out["remote"]
    assert c.post("/api/setup/repo", json={"path": str(tmp_path / "nope")}).json()["ok"] is False
    (tmp_path / "plain").mkdir()
    assert "not a git repository" in c.post("/api/setup/repo", json={"path": str(tmp_path / "plain")}).json()["error"]


def test_checks_are_suggested_from_the_project_files(tmp_path):
    (tmp_path / "pyproject.toml").write_text("[tool.pytest.ini_options]\n")
    web = tmp_path / "web"
    web.mkdir()
    (web / "package.json").write_text('{"scripts": {"test": "vitest", "lint": "eslint ."}}')
    (web / "tsconfig.json").write_text("{}")
    names = [(c["name"], c["cwd"]) for c in onboarding._checks(tmp_path, None)]
    assert names == [("Python tests", "."), ("JS tests (web)", "web"), ("Typecheck (web)", "web"), ("Lint (web)", "web")]


def test_env_file_is_updated_in_place_and_private(tmp_path, monkeypatch):
    f = tmp_path / ".env"
    f.write_text("OTHER=1\nNOTION_TOKEN=old\n")
    onboarding.write_env(f, {"NOTION_TOKEN": "new", "GITHUB_TOKEN": "gh"})
    assert f.read_text().splitlines() == ["OTHER=1", "NOTION_TOKEN=new", "GITHUB_TOKEN=gh"]
    assert oct(f.stat().st_mode & 0o777) == "0o600"
    with pytest.raises(ValueError):
        onboarding.write_env(f, {"bad key": "x"})
    monkeypatch.delenv("NOTION_TOKEN")
    monkeypatch.delenv("GITHUB_TOKEN")


@respx.mock
def test_pages_lists_only_pages_that_can_hold_a_database(env):
    c, *_ = env
    respx.post("https://api.notion.com/v1/search").mock(return_value=httpx.Response(200, json={"results": [
        {"id": "p1", "url": "u1", "parent": {"type": "workspace"}, "properties": {"title": {"type": "title", "title": [{"plain_text": "test"}]}}},
        {"id": "row", "parent": {"type": "data_source_id"}, "properties": {"Title": {"type": "title", "title": [{"plain_text": "a ticket"}]}}},
    ]}))
    assert c.post("/api/setup/notion/pages", json={"token": "t"}).json()["pages"] == [{"id": "p1", "title": "test", "url": "u1"}]
    assert c.post("/api/setup/notion/pages", json={}).status_code == 422


def project_body(cfg, **kw):
    return {"name": "shop", "path": cfg.local_path, "repo": cfg.repo, "base_branch": cfg.base_branch, "token": "ntn_x",
            "database_id": "d" * 32, "data_source_id": "s" * 32, "preset": "balanced", "checks": [{"name": "t", "cmd": "pytest", "cwd": "."}],
            "areas": {"Backend": ["src/"]}, **kw}


def test_creating_the_project_writes_files_secrets_and_links_it(env, monkeypatch):
    c, cfg, projects, dotenv = env
    monkeypatch.setenv("NOTION_TOKEN", "")
    r = c.post("/api/setup/project", json=project_body(cfg))
    assert r.status_code == 200, r.text
    assert r.json()["warnings"] == []
    written = yaml.safe_load((projects / "shop.yaml").read_text())
    assert written["autonomy"]["default_mode"] == "supervised" and written["area_map"] == "shop.area_map.md"
    assert written["tracker"]["status_map"]["needs_info"] == "Needs info"
    assert load_project(projects / "shop.yaml").area_map_text.startswith("# Code map")
    assert "NOTION_TOKEN=ntn_x" in dotenv.read_text()
    assert c.get("/api/projects").json()["default"] == "shop"
    assert c.post("/api/setup/project", json=project_body(cfg)).status_code == 409


def test_a_bad_project_is_rejected_and_leaves_nothing_behind(env):
    c, cfg, projects, dotenv = env
    assert c.post("/api/setup/project", json=project_body(cfg, name="Bad Name")).status_code == 422
    assert c.post("/api/setup/project", json=project_body(cfg, preset="reckless")).status_code == 422
    assert not list(projects.glob("*")) and not dotenv.exists()


def test_browse_lists_visible_folders_and_flags_git_checkouts(env, tmp_path):
    c, cfg, *_ = env
    (tmp_path / "plain").mkdir()
    (tmp_path / ".hidden").mkdir()
    (tmp_path / "a-file.txt").write_text("x")
    out = c.get("/api/setup/browse", params={"path": str(tmp_path)}).json()
    names = {f["name"]: f["git"] for f in out["folders"]}
    assert out["ok"] and out["parent"] == str(tmp_path.parent)
    assert names["plain"] is False and ".hidden" not in names and "a-file.txt" not in names
    inside = c.get("/api/setup/browse", params={"path": cfg.local_path}).json()
    assert inside["git"] is True
    assert c.get("/api/setup/browse", params={"path": str(tmp_path / "missing")}).json()["ok"] is False
    assert c.get("/api/setup/browse").json()["path"]  # no path: the home folder


def test_pull_requests_are_only_turned_on_when_the_token_can_see_the_repository(env, monkeypatch):
    from autodev import github

    c, cfg, projects, _ = env

    async def blind(token, slug):
        return f"the token cannot see {slug}"

    async def sighted(token, slug):
        return None

    monkeypatch.setattr(github, "can_see", blind)
    r = c.post("/api/setup/project", json=project_body(cfg, name="a", github_token="ghp_x", github_slug="o/r"))
    assert r.json()["warnings"] == ["Pull requests are off: the token cannot see o/r."]
    assert yaml.safe_load((projects / "a.yaml").read_text())["pr"] == {"create": False}

    monkeypatch.setattr(github, "can_see", sighted)
    r = c.post("/api/setup/project", json=project_body(cfg, name="b", github_token="ghp_x", github_slug="o/r"))
    assert r.json()["warnings"] == []
    assert yaml.safe_load((projects / "b.yaml").read_text())["pr"] == {"create": True, "slug": "o/r", "token_env": "GITHUB_TOKEN_B"}
    assert "GITHUB_TOKEN_B=ghp_x" in (projects.parent / ".env").read_text()   # its own variable: other projects keep theirs

    # no token given in the wizard: pull requests stay off, and nothing blames a token nobody gave,
    # even if another project's token sits in the environment
    monkeypatch.setenv("GITHUB_TOKEN", "another-account")
    r = c.post("/api/setup/project", json=project_body(cfg, name="c", github_slug="o/r"))
    assert r.json()["warnings"] == []
    assert yaml.safe_load((projects / "c.yaml").read_text())["pr"] == {"create": False}


def test_git_access_reports_whether_origin_can_be_read(env):
    c, cfg, *_ = env
    ok = c.post("/api/setup/git", json={"path": cfg.local_path}).json()
    assert ok["ok"] is True and ok["error"] is None


def test_an_https_remote_that_fails_is_offered_the_ssh_address(env, monkeypatch):
    c, cfg, *_ = env
    from autodev import onboarding

    calls = []

    def fake(target, cwd, env):
        calls.append(target)
        address = onboarding._git(cwd, "remote", "get-url", "origin") if target == "origin" else target
        return None if address.startswith("git@") else "could not read Username for 'https://github.com'"

    monkeypatch.setattr(onboarding, "_ls_remote", fake)
    onboarding._git(onboarding.Path(cfg.local_path), "remote", "set-url", "origin", "https://github.com/o/r.git")
    out = c.post("/api/setup/git", json={"path": cfg.local_path}).json()
    assert out["ok"] is False and out["ssh_url"] == "git@github.com:o/r.git"
    fixed = c.post("/api/setup/git/ssh", json={"path": cfg.local_path})
    assert fixed.status_code == 200 and fixed.json()["remote"] == "git@github.com:o/r.git" and fixed.json()["ok"] is True


def test_nothing_is_changed_when_ssh_does_not_answer(env, monkeypatch):
    c, cfg, *_ = env
    from autodev import onboarding

    monkeypatch.setattr(onboarding, "_ls_remote", lambda *a: "denied")
    onboarding._git(onboarding.Path(cfg.local_path), "remote", "set-url", "origin", "https://github.com/o/r.git")
    assert c.post("/api/setup/git/ssh", json={"path": cfg.local_path}).status_code == 409
    assert onboarding._git(onboarding.Path(cfg.local_path), "remote", "get-url", "origin") == "https://github.com/o/r.git"


def test_the_github_token_check_names_the_account_and_the_problem(env, monkeypatch):
    from autodev import github

    c, *_ = env

    async def who(token):
        return "BCPTe" if token == "good" else None

    async def sees(token, slug):
        return None

    monkeypatch.setattr(github, "whoami", who)
    monkeypatch.setattr(github, "can_see", sees)
    assert c.post("/api/setup/github", json={"slug": "o/r", "token": "good"}).json() == {"ok": True, "login": "BCPTe", "problem": None}
    bad = c.post("/api/setup/github", json={"slug": "o/r", "token": "bad"}).json()
    assert bad["ok"] is False and bad["login"] is None


# ---- the one-button GitHub connection ---------------------------------------------------------
def plan_env(monkeypatch, *, git_ok=True, ssh=None, accounts=None, working=(), token_sees=None):
    """Fakes the outside world of `/github/plan`: git, the `gh` accounts and what GitHub says about each token."""
    from autodev import github, onboarding

    monkeypatch.setattr(onboarding, "git_access", lambda path, token=None: {"ok": git_ok or bool(token), "remote": "r", "error": None if git_ok else "denied", "ssh_url": ssh})
    monkeypatch.setattr(onboarding, "gh_accounts", lambda: accounts)
    monkeypatch.setattr(onboarding, "gh_token", lambda login: f"tok-{login}")

    async def sees(token, slug):
        return None if token in {f"tok-{w}" for w in working} or token == token_sees else "cannot see it"

    async def who(token):
        return token.removeprefix("tok-")

    monkeypatch.setattr(github, "can_see", sees)
    monkeypatch.setattr(github, "whoami", who)


def plan(c, cfg, **kw):
    return c.post("/api/setup/github/plan", json={"path": cfg.local_path, "slug": "o/r", **kw}).json()


def test_the_plan_picks_the_shortest_action(env, monkeypatch):
    c, cfg, *_ = env
    plan_env(monkeypatch, git_ok=True, accounts=["BCPTe"], working=["BCPTe"])
    assert plan(c, cfg)["action"] == "gh_use" and plan(c, cfg)["gh_account"] == "BCPTe"          # one click covers git and pull requests

    plan_env(monkeypatch, git_ok=False, ssh="git@github.com:o/r.git", accounts=["other"], working=[])
    assert plan(c, cfg)["action"] == "ssh"                                                        # git works over SSH; no account sees the repo

    plan_env(monkeypatch, git_ok=True, accounts=[], working=[])
    assert plan(c, cfg)["action"] == "gh_login"                                                   # gh installed, nobody signed in

    plan_env(monkeypatch, git_ok=True, accounts=None, working=[])
    assert plan(c, cfg)["action"] == "token"                                                      # no gh at all

    plan_env(monkeypatch, git_ok=True, accounts=[], token_sees="pasted")
    done = plan(c, cfg, token="pasted")
    assert done["action"] == "done" and done["pr"]["on"] is True

    out = c.post("/api/setup/github/plan", json={"path": cfg.local_path}).json()                  # not a GitHub remote
    assert out["action"] == "done" and out["pr"]["on"] is False


def test_using_a_gh_account_keeps_its_token_on_the_server_and_turns_pull_requests_on(env, monkeypatch):
    c, cfg, projects, dotenv = env
    plan_env(monkeypatch, accounts=["BCPTe"], working=["BCPTe"])
    assert c.post("/api/setup/github/use-gh", json={"slug": "o/r", "login": "BCPTe"}).json() == {"ok": True, "login": "BCPTe"}
    r = c.post("/api/setup/project", json=project_body(cfg, name="viagh", github_slug="o/r"))   # no token in the request
    assert r.status_code == 200 and r.json()["warnings"] == []
    assert yaml.safe_load((projects / "viagh.yaml").read_text())["pr"] == {"create": True, "slug": "o/r", "token_env": "GITHUB_TOKEN_VIAGH"}
    assert "GITHUB_TOKEN_VIAGH=tok-BCPTe" in dotenv.read_text()


def test_a_gh_account_that_cannot_see_the_repo_is_refused(env, monkeypatch):
    c, cfg, *_ = env
    plan_env(monkeypatch, accounts=["engfill"], working=[])
    assert c.post("/api/setup/github/use-gh", json={"slug": "o/r", "login": "engfill"}).status_code == 409


@pytest.mark.asyncio
async def test_the_gh_login_reads_the_code_and_the_address_and_ends_with_the_exit_status():
    import sys
    from autodev.onboarding import GhLogin

    script = "print('! One-time code (37E9-CD52) copied to clipboard'); print('Open this URL to continue in your web browser: https://github.com/login/device')"
    login = GhLogin([sys.executable, "-c", script])
    login.start()
    await login._task
    assert login.state() == {"code": "37E9-CD52", "url": "https://github.com/login/device", "done": True, "ok": True, "error": None}
    failing = GhLogin([sys.executable, "-c", "import sys; sys.exit(1)"])
    failing.start()
    await failing._task
    assert failing.state()["ok"] is False and failing.state()["error"]
