"""Is the project wired up? Notion reachable, columns present, tickets ready, GitHub usable."""
import httpx

from autodev import github
from autodev.config import ProjectConfig


async def check_setup(cfg: ProjectConfig, tracker) -> dict:
    out: dict = {"notion": {"ok": False}, "github": None}
    try:
        props = await tracker.verify()
        ready = await tracker.fetch_ready()
        out["notion"] = {"ok": True, "properties": len(props), "ready_tickets": [t.title for t in ready]}
    except httpx.HTTPStatusError as e:
        out["notion"] = {"ok": False, "error": f"Notion error {e.response.status_code}: {e.response.text}"}
    except Exception as e:
        out["notion"] = {"ok": False, "error": str(e)}
    out["github"] = await github.verify_access(cfg)
    return out
