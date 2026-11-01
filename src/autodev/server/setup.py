"""The setup wizard's API: look at the checkout, prepare Notion, then write the project and link it."""
import asyncio
import os
from pathlib import Path
from typing import Callable

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from autodev import github, onboarding
from autodev.config import load_project
from autodev.engine import Engine
from autodev.trackers import notion_schema
from autodev.trackers.notion import NotionTracker


class RepoBody(BaseModel):
    path: str


class PlanBody(BaseModel):
    path: str
    slug: str | None = None
    token: str | None = None


class UseGhBody(BaseModel):
    slug: str
    login: str


class GitBody(BaseModel):
    path: str
    token: str | None = None


class GithubBody(BaseModel):
    slug: str
    token: str


class NotionBody(BaseModel):
    token: str | None = None


class DatabaseBody(NotionBody):
    parent_page_id: str
    title: str = "autodev tickets"
    areas: list[str] = []


class AttachBody(NotionBody):
    database_id: str
    add_missing: bool = False


class ProjectBody(NotionBody):
    name: str
    path: str
    repo: str
    base_branch: str
    database_id: str
    data_source_id: str
    language: str = "English"
    python: str | None = None
    workspace_mode: str = "inplace"
    preset: str = "careful"
    daily_budget_usd: float = 20.0
    quiet_hours: str | None = None
    checks: list[dict] = []
    areas: dict[str, list[str]] = {}
    github_token: str | None = None
    github_slug: str | None = None


def setup_router(require_session, *, db, projects_dir: Path, env_path: Path, link: Callable) -> APIRouter:
    r = APIRouter(prefix="/setup", dependencies=[Depends(require_session)])
    # a GitHub token taken from `gh` stays here, on the server, until the project is created
    staged: dict[str, str] = {}
    login: dict[str, onboarding.GhLogin | None] = {"current": None}

    def notion_token(body: NotionBody) -> str:
        token = body.token or os.environ.get("NOTION_TOKEN")
        if not token:
            raise HTTPException(422, "Paste the Notion integration token first")
        return token

    @r.get("/state")
    def state():
        return {"has_notion_token": bool(os.environ.get("NOTION_TOKEN")), "has_github_token": bool(os.environ.get("GITHUB_TOKEN"))}

    @r.get("/claude")
    async def claude():
        return await asyncio.to_thread(onboarding.claude_status)

    @r.get("/browse")
    async def browse(path: str | None = None):
        return await asyncio.to_thread(onboarding.list_folders, path)

    @r.post("/repo")
    async def repo(body: RepoBody):
        return await asyncio.to_thread(onboarding.inspect_repo, body.path)

    @r.post("/git")
    async def git(body: GitBody):
        return await asyncio.to_thread(onboarding.git_access, body.path, body.token)

    @r.post("/git/ssh")
    async def git_ssh(body: GitBody):
        try:
            return await asyncio.to_thread(onboarding.use_ssh, body.path)
        except ValueError as e:
            raise HTTPException(409, str(e))

    @r.post("/github/plan")
    async def github_plan(body: PlanBody):
        """Where the GitHub connection stands and the ONE next action that gets it furthest with the fewest steps."""
        token = body.token or staged.get("github_token")
        git = await asyncio.to_thread(onboarding.git_access, body.path, token)
        accounts = await asyncio.to_thread(onboarding.gh_accounts)
        pr = {"on": False, "login": None, "problem": None}
        if body.slug and token:
            try:
                pr["login"] = await github.whoami(token)
                pr["problem"] = await github.can_see(token, body.slug) if pr["login"] else "GitHub does not accept this token"
            except httpx.HTTPError as e:
                pr["problem"] = f"GitHub could not be reached ({e})"
            pr["on"] = pr["problem"] is None
        candidate = None
        if body.slug and not pr["on"]:
            for name in accounts or []:
                t = await asyncio.to_thread(onboarding.gh_token, name)
                if t and await github.can_see(t, body.slug) is None:
                    candidate = name
                    break
        if git["ok"] and (pr["on"] or not body.slug):
            action = "done"
        elif not body.slug:
            action = "recheck"
        elif candidate:
            action = "gh_use"
        elif not git["ok"] and git["ssh_url"]:
            action = "ssh"
        elif accounts is not None:
            action = "gh_login"
        else:
            action = "token"
        return {"git": git, "pr": pr, "action": action, "gh_account": candidate, "can_continue": git["ok"]}

    @r.post("/github/use-gh")
    async def github_use_gh(body: UseGhBody):
        token = await asyncio.to_thread(onboarding.gh_token, body.login)
        if not token:
            raise HTTPException(409, f"`gh` has no token for {body.login}")
        problem = await github.can_see(token, body.slug)
        if problem:
            raise HTTPException(409, problem)
        staged["github_token"] = token
        return {"ok": True, "login": body.login}

    @r.post("/github/login")
    async def github_login_start():
        if login["current"]:
            login["current"].stop()
        login["current"] = onboarding.GhLogin()
        login["current"].start()
        for _ in range(100):  # the code appears within a moment
            if login["current"].code or login["current"].done:
                break
            await asyncio.sleep(0.1)
        return login["current"].state()

    @r.get("/github/login")
    async def github_login_state():
        return login["current"].state() if login["current"] else {"code": None, "url": None, "done": True, "ok": False, "error": "not started"}

    @r.post("/github")
    async def github_token(body: GithubBody):
        try:
            login = await github.whoami(body.token)
            problem = await github.can_see(body.token, body.slug) if login else "GitHub does not accept this token"
        except httpx.HTTPError as e:
            raise HTTPException(502, f"GitHub could not be reached: {e}")
        return {"ok": problem is None, "login": login, "problem": problem}

    @r.post("/notion/pages")
    async def pages(body: NotionBody):
        return {"pages": await notion_schema.shared_pages(notion_token(body))}

    @r.post("/notion/database")
    async def create_database(body: DatabaseBody):
        return await notion_schema.create_database(notion_token(body), body.parent_page_id, body.title, body.areas or None, list(onboarding.MODELS))

    @r.post("/notion/attach")
    async def attach(body: AttachBody):
        token = notion_token(body)
        data_source_id = await notion_schema.data_source_of(token, body.database_id)
        missing = await notion_schema.missing_properties(token, data_source_id)
        if body.add_missing:
            await notion_schema.rename_legacy(token, data_source_id)
            missing = await notion_schema.missing_properties(token, data_source_id)
            if missing:
                await notion_schema.add_properties(token, data_source_id, missing)
            await notion_schema.refresh_properties(token, data_source_id)
            await notion_schema.arrange_views(token, data_source_id)
        return {"database_id": body.database_id.replace("-", ""), "data_source_id": data_source_id,
                "missing": [] if body.add_missing else sorted(missing), "added": sorted(missing) if body.add_missing else []}

    @r.post("/project")
    async def project(body: ProjectBody, request: Request):
        if body.preset not in onboarding.PRESETS:
            raise HTTPException(422, f"unknown preset: {body.preset}")
        token = notion_token(body)
        warnings: list[str] = []
        github_slug = None
        # Only a token given here counts. One found in the environment may belong to another account or project:
        # using it would open pull requests with the wrong identity (and blame a token the user never gave).
        chosen = body.github_token or staged.get("github_token")
        token_env = onboarding.token_env_for(body.name) if chosen else "GITHUB_TOKEN"
        if body.github_slug and chosen:
            try:
                problem = await github.can_see(chosen, body.github_slug)
            except httpx.HTTPError as e:
                problem = f"GitHub could not be reached ({e})"
            if problem:
                warnings.append(f"Pull requests are off: {problem}.")
            else:
                github_slug = body.github_slug
        area_file = f"{body.name}.area_map.md" if body.areas else None
        try:
            cfg = onboarding.project_dict(
                name=body.name, repo=body.repo, base_branch=body.base_branch, local_path=body.path, language=body.language,
                database_id=body.database_id, data_source_id=body.data_source_id, python=body.python,
                workspace_mode=body.workspace_mode, preset=body.preset, daily_budget_usd=body.daily_budget_usd,
                quiet_hours=body.quiet_hours, checks=body.checks, github_slug=github_slug, github_token_env=token_env,
                area_map_file=area_file,
            )
            secrets = {"NOTION_TOKEN": token, **({token_env: chosen} if chosen else {})}
            target = onboarding.write_project(projects_dir, body.name, cfg, body.areas or None)
        except FileExistsError as e:
            raise HTTPException(409, str(e))
        except ValueError as e:
            raise HTTPException(422, str(e))
        try:
            onboarding.write_env(env_path, secrets)
            loaded = load_project(target)
            tracker = NotionTracker(loaded.tracker, token)
            link(request.app, loaded, body.name, tracker, Engine(loaded, body.name, db, tracker))
        except Exception as e:
            target.unlink(missing_ok=True)
            (projects_dir / f"{body.name}.area_map.md").unlink(missing_ok=True)
            raise HTTPException(500, f"project not linked: {e}")
        staged.pop("github_token", None)
        db.audit("user", "project_added", None, body.name)
        return {"name": body.name, "warnings": warnings}

    return r
