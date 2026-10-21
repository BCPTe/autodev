from pathlib import Path

import httpx
import pytest
import respx

from autodev.config import load_project
from autodev.github import verify_access

CFG = load_project(Path(__file__).parent.parent / "projects" / "demo.yaml")
REPO = f"https://api.github.com/repos/{CFG.pr.slug}"


async def test_missing_token_is_reported(monkeypatch):
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    assert "GITHUB_TOKEN mancante" in await verify_access(CFG)


@respx.mock
@pytest.mark.parametrize("status,expected", [(401, "non valido"), (404, "non visibile")])
async def test_repo_errors_are_explained(monkeypatch, status, expected):
    monkeypatch.setenv("GITHUB_TOKEN", "x")
    respx.get(REPO).mock(return_value=httpx.Response(status))
    assert expected in await verify_access(CFG)


@respx.mock
async def test_token_without_pull_request_permission_is_explained(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "x")
    respx.get(REPO).mock(return_value=httpx.Response(200, json={}))
    respx.get(f"{REPO}/pulls").mock(return_value=httpx.Response(403))
    assert "permesso 'Pull requests'" in await verify_access(CFG)


@respx.mock
async def test_working_token_is_confirmed(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "x")
    respx.get(REPO).mock(return_value=httpx.Response(200, json={}))
    respx.get(f"{REPO}/pulls").mock(return_value=httpx.Response(200, json=[]))
    assert "GitHub OK" in await verify_access(CFG)


@respx.mock
async def test_existing_pull_request_is_reused_instead_of_failing(monkeypatch):
    from autodev.github import create_pull_request

    monkeypatch.setenv("GITHUB_TOKEN", "x")
    respx.post(f"{REPO}/pulls").mock(return_value=httpx.Response(422, text='{"errors":[{"message":"A pull request already exists for x"}]}'))
    respx.get(f"{REPO}/pulls").mock(return_value=httpx.Response(200, json=[{"html_url": "https://github.com/o/r/pull/7"}]))
    assert await create_pull_request(CFG, "autodev/x", "t", "b") == "https://github.com/o/r/pull/7"
