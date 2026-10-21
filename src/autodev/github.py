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
