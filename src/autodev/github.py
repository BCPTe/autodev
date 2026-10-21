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
        return "pr.slug non configurato"
    if not token:
        return "GITHUB_TOKEN mancante in .env"
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"}
    async with httpx.AsyncClient(timeout=30) as client:
        repo = await client.get(f"https://api.github.com/repos/{cfg.pr.slug}", headers=headers)
        if repo.status_code in (401, 403):
            return f"token non valido o non autorizzato ({repo.status_code}): controlla scadenza e che l'organizzazione lo abbia approvato"
        if repo.status_code == 404:
            return f"repository {cfg.pr.slug} non visibile al token: scegli la repository nei permessi del token"
        prs = await client.get(f"https://api.github.com/repos/{cfg.pr.slug}/pulls", headers=headers, params={"per_page": 1})
        if prs.status_code != 200:
            return f"il token vede la repository ma non può leggere le pull request ({prs.status_code}): serve il permesso 'Pull requests'"
    return f"GitHub OK: {cfg.pr.slug} raggiungibile e pull request leggibili (il permesso di scrittura si vede solo aprendo la prima PR)"
