from pathlib import Path

import httpx
import pytest
import respx

from autodev.config import load_project
from autodev.github import verify_access

CFG = load_project(Path(__file__).parent.parent / "tests" / "fixtures" / "demo.yaml")
REPO = f"https://api.github.com/repos/{CFG.pr.slug}"


async def test_missing_token_is_reported(monkeypatch):
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    assert "GITHUB_TOKEN missing" in await verify_access(CFG)


@respx.mock
@pytest.mark.parametrize("status,expected", [(401, "invalid"), (404, "not visible")])
async def test_repo_errors_are_explained(monkeypatch, status, expected):
    monkeypatch.setenv("GITHUB_TOKEN", "x")
    respx.get(REPO).mock(return_value=httpx.Response(status))
    assert expected in await verify_access(CFG)


@respx.mock
async def test_token_without_pull_request_permission_is_explained(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "x")
    respx.get(REPO).mock(return_value=httpx.Response(200, json={}))
    respx.get(f"{REPO}/branches/{CFG.base_branch}").mock(return_value=httpx.Response(200, json={}))
    respx.get(f"{REPO}/pulls").mock(return_value=httpx.Response(403))
    assert "'Pull requests' permission" in await verify_access(CFG)


@respx.mock
async def test_working_token_is_confirmed(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "x")
    respx.get(REPO).mock(return_value=httpx.Response(200, json={}))
    respx.get(f"{REPO}/branches/{CFG.base_branch}").mock(return_value=httpx.Response(200, json={}))
    respx.get(f"{REPO}/pulls").mock(return_value=httpx.Response(200, json=[]))
    assert "GitHub OK" in await verify_access(CFG)


@respx.mock
async def test_a_token_that_cannot_read_contents_is_caught_before_the_first_pull_request(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "x")
    respx.get(REPO).mock(return_value=httpx.Response(200, json={}))
    respx.get(f"{REPO}/branches/{CFG.base_branch}").mock(return_value=httpx.Response(403, json={"message": "Resource not accessible by personal access token"}))
    assert "'Contents' permission" in await verify_access(CFG)


@respx.mock
async def test_a_refused_pull_request_says_why_and_hints_at_the_token(monkeypatch):
    from autodev.github import create_pull_request

    monkeypatch.setenv("GITHUB_TOKEN", "x")
    respx.post(f"{REPO}/pulls").mock(return_value=httpx.Response(
        422, json={"message": "Validation Failed", "errors": [{"resource": "PullRequest", "field": "head", "code": "invalid"}]}))
    with pytest.raises(RuntimeError, match=r"Validation Failed.*Contents: read and write"):
        await create_pull_request(CFG, "autodev/x", "t", "b")


@respx.mock
async def test_existing_pull_request_is_reused_instead_of_failing(monkeypatch):
    from autodev.github import create_pull_request

    monkeypatch.setenv("GITHUB_TOKEN", "x")
    respx.post(f"{REPO}/pulls").mock(return_value=httpx.Response(422, text='{"errors":[{"message":"A pull request already exists for x"}]}'))
    respx.get(f"{REPO}/pulls").mock(return_value=httpx.Response(200, json=[{"html_url": "https://github.com/o/r/pull/7"}]))
    assert await create_pull_request(CFG, "autodev/x", "t", "b") == "https://github.com/o/r/pull/7"


@respx.mock
async def test_a_token_that_cannot_read_commit_statuses_is_caught_by_the_check(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "x")
    respx.get(REPO).mock(return_value=httpx.Response(200, json={}))
    respx.get(f"{REPO}/branches/{CFG.base_branch}").mock(return_value=httpx.Response(200, json={"commit": {"sha": "abc"}}))
    respx.get(f"{REPO}/commits/abc/status").mock(return_value=httpx.Response(403))
    assert "'Commit statuses' permission" in await verify_access(CFG)


@respx.mock
async def test_readable_statuses_are_enough_even_without_check_runs(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "x")
    respx.get(REPO).mock(return_value=httpx.Response(200, json={}))
    respx.get(f"{REPO}/branches/{CFG.base_branch}").mock(return_value=httpx.Response(200, json={"commit": {"sha": "abc"}}))
    respx.get(f"{REPO}/commits/abc/status").mock(return_value=httpx.Response(200, json={"statuses": []}))
    respx.get(f"{REPO}/pulls").mock(return_value=httpx.Response(200, json=[]))
    assert "GitHub OK" in await verify_access(CFG)


@pytest.mark.asyncio
async def test_each_project_uses_the_token_named_in_its_config(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "default-account")
    monkeypatch.setenv("GITHUB_TOKEN_SHOP", "shop-account")
    shop = CFG.model_copy(update={"pr": CFG.pr.model_copy(update={"token_env": "GITHUB_TOKEN_SHOP"})})
    from autodev.github import _headers

    assert _headers(CFG)["Authorization"] == "Bearer default-account"
    assert _headers(shop)["Authorization"] == "Bearer shop-account"
    monkeypatch.delenv("GITHUB_TOKEN_SHOP")
    assert "GITHUB_TOKEN_SHOP missing" in await verify_access(shop)
