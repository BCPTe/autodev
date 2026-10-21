import os

import httpx

from autodev.config import ProjectConfig


async def create_pull_request(cfg: ProjectConfig, branch: str, title: str, body: str) -> str:
    token = os.environ.get("GITHUB_TOKEN")
    if not token or not cfg.pr.slug:
        raise RuntimeError("GITHUB_TOKEN and pr.slug are required to open pull requests")
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(
            f"https://api.github.com/repos/{cfg.pr.slug}/pulls",
            headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
            json={"title": title, "head": branch, "base": cfg.base_branch, "body": body, "draft": False},
        )
        if r.status_code == 422 and "already exists" in r.text:
            owner = cfg.pr.slug.split("/")[0]
            existing = await client.get(
                f"https://api.github.com/repos/{cfg.pr.slug}/pulls",
                headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
                params={"head": f"{owner}:{branch}", "state": "open"},
            )
            existing.raise_for_status()
            return existing.json()[0]["html_url"]
        r.raise_for_status()
        return r.json()["html_url"]


async def verify_access(cfg: ProjectConfig) -> str:
    """Human-readable diagnosis of the GitHub setup (token present, repo reachable, PRs readable)."""
    token = os.environ.get("GITHUB_TOKEN")
    if not cfg.pr.slug:
        return "pr.slug is not configured"
    if not token:
        return "GITHUB_TOKEN missing in .env"
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"}
    async with httpx.AsyncClient(timeout=30) as client:
        repo = await client.get(f"https://api.github.com/repos/{cfg.pr.slug}", headers=headers)
        if repo.status_code in (401, 403):
            return f"token invalid or not authorised ({repo.status_code}): check its expiry and that the organisation approved it"
        if repo.status_code == 404:
            return f"repository {cfg.pr.slug} is not visible to the token: select the repository in the token's permissions"
        prs = await client.get(f"https://api.github.com/repos/{cfg.pr.slug}/pulls", headers=headers, params={"per_page": 1})
        if prs.status_code != 200:
            return f"the token sees the repository but cannot read pull requests ({prs.status_code}): it needs the 'Pull requests' permission"
    return f"GitHub OK: {cfg.pr.slug} reachable and pull requests readable (write permission only shows when the first PR is opened)"


def _headers() -> dict[str, str]:
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        raise RuntimeError("GITHUB_TOKEN missing in .env")
    return {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"}


def _api(cfg: ProjectConfig, path: str) -> str:
    if not cfg.pr.slug:
        raise RuntimeError("pr.slug is not configured")
    return f"https://api.github.com/repos/{cfg.pr.slug}{path}"


def _checks_summary(runs: list[dict], statuses: list[dict]) -> dict:
    """Collapses check runs and legacy commit statuses into counts and one verdict."""
    states = [(r["conclusion"] if r["status"] == "completed" else "pending") for r in runs] + [s["state"] for s in statuses]
    failed = sum(s in ("failure", "timed_out", "cancelled", "error", "action_required") for s in states)
    pending = sum(s in ("pending", "queued", "in_progress", None) for s in states)
    verdict = "none" if not states else "failing" if failed else "pending" if pending else "passing"
    return {"verdict": verdict, "total": len(states), "failed": failed, "pending": pending}


async def list_pulls(cfg: ProjectConfig, branch_prefix: str, limit: int = 30) -> list[dict]:
    """Recent pull requests whose branch starts with `branch_prefix`, with check status for the open ones."""
    async with httpx.AsyncClient(timeout=30, headers=_headers()) as client:
        r = await client.get(_api(cfg, "/pulls"), params={"state": "all", "sort": "updated", "direction": "desc", "per_page": 50})
        r.raise_for_status()
        out = []
        for pr in r.json():
            if not pr["head"]["ref"].startswith(branch_prefix + "/") or len(out) >= limit:
                continue
            item = {
                "number": pr["number"], "title": pr["title"], "url": pr["html_url"], "branch": pr["head"]["ref"],
                "state": "merged" if pr.get("merged_at") else pr["state"], "draft": pr.get("draft", False),
                "body": pr.get("body") or "", "updated_at": pr["updated_at"], "author": pr["user"]["login"],
                "checks": None, "mergeable": None,
            }
            if pr["state"] == "open":
                sha = pr["head"]["sha"]
                runs = await client.get(_api(cfg, f"/commits/{sha}/check-runs"), params={"per_page": 50})
                status = await client.get(_api(cfg, f"/commits/{sha}/status"))
                item["checks"] = _checks_summary(
                    runs.json().get("check_runs", []) if runs.status_code == 200 else [],
                    status.json().get("statuses", []) if status.status_code == 200 else [],
                )
                detail = await client.get(_api(cfg, f"/pulls/{pr['number']}"))
                if detail.status_code == 200:
                    item["mergeable"] = detail.json().get("mergeable")
            out.append(item)
        return out


async def merge_pull(cfg: ProjectConfig, number: int, method: str = "squash") -> str:
    async with httpx.AsyncClient(timeout=30, headers=_headers()) as client:
        r = await client.put(_api(cfg, f"/pulls/{number}/merge"), json={"merge_method": method})
        if r.status_code >= 400:
            raise RuntimeError(r.json().get("message", r.text))
        return r.json().get("sha", "")


async def delete_remote_branch(cfg: ProjectConfig, branch: str) -> bool:
    async with httpx.AsyncClient(timeout=30, headers=_headers()) as client:
        r = await client.delete(_api(cfg, f"/git/refs/heads/{branch}"))
        return r.status_code in (204, 422)  # 422: already gone
