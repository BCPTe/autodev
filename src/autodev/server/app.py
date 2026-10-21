import asyncio
import json
import time
from pathlib import Path
from typing import Any, Protocol

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel

from autodev.config import ProjectConfig
from autodev.db import Database
from autodev.jobs import daily_cap, mark_orphans, spent_today, start_of_today
from autodev.models import Comment, Status, Ticket
from autodev.server import auth as authmod
from autodev.server.auth import COOKIE, Auth
from autodev.server.repo import repo_state

ALLOWED_HOSTS = {"localhost", "127.0.0.1", "[::1]", "::1", "testserver"}
INBOX_STATES = {Status.NEEDS_INFO, Status.ANALYZED, Status.REVIEW, Status.ESCALATED}
TICKET_CACHE_SECONDS = 20
DIST = Path(__file__).resolve().parents[3] / "dashboard" / "dist"


def hostname(host_header: str) -> str:
    """'localhost:8765' -> 'localhost', '[::1]:8765' -> '[::1]'."""
    host = host_header.split("/", 1)[0]
    return host.split("]")[0] + "]" if host.startswith("[") else host.split(":")[0]


class TrackerLike(Protocol):
    async def list_all(self) -> list[Ticket]: ...
    async def detail(self, ticket_id: str) -> tuple[Ticket, list[Comment]]: ...


class Credentials(BaseModel):
    password: str


class Setup(BaseModel):
    password: str
    code: str


def create_app(cfg: ProjectConfig, project: str, db: Database, tracker: TrackerLike, *, static_dir: Path | None = DIST) -> FastAPI:
    app = FastAPI(title="autodev", docs_url=None, redoc_url=None, openapi_url=None)
    auth = Auth(db)
    app.state.auth = auth
    cache: dict[str, Any] = {"at": 0.0, "tickets": []}
    mark_orphans(db)

    @app.middleware("http")
    async def guard(request: Request, call_next):
        host = hostname(request.headers.get("host", ""))
        if host not in ALLOWED_HOSTS:
            return Response("host non consentito", status_code=400)
        if request.method not in ("GET", "HEAD", "OPTIONS"):
            origin = request.headers.get("origin")
            if origin and hostname(origin.split("://", 1)[-1]) not in ALLOWED_HOSTS:
                return Response("origine non consentita", status_code=403)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'"
        )
        return response

    def require_session(request: Request) -> None:
        if not auth.valid(request.cookies.get(COOKIE)):
            raise HTTPException(401, "non autenticato")

    def set_cookie(response: Response, token: str) -> None:
        response.set_cookie(COOKIE, token, max_age=authmod.SESSION_SECONDS, httponly=True, samesite="strict", path="/")

    # ---- auth ----------------------------------------------------------------------------
    @app.get("/api/auth/state")
    def auth_state(request: Request):
        return {"setup_required": not auth.configured, "authenticated": auth.valid(request.cookies.get(COOKIE))}

    @app.post("/api/auth/setup")
    def auth_setup(body: Setup, response: Response):
        try:
            auth.set_password(body.password, body.code)
        except PermissionError as e:
            raise HTTPException(403, str(e))
        except ValueError as e:
            raise HTTPException(422, str(e))
        set_cookie(response, auth.new_session())
        return {"ok": True}

    @app.post("/api/auth/login")
    def auth_login(body: Credentials, response: Response):
        wait = auth.retry_after()
        if wait:
            raise HTTPException(429, f"troppi tentativi, riprova tra {wait} secondi", headers={"Retry-After": str(wait)})
        token = auth.login(body.password)
        if not token:
            raise HTTPException(401, "password errata")
        set_cookie(response, token)
        return {"ok": True}

    @app.post("/api/auth/logout")
    def auth_logout(request: Request, response: Response):
        auth.logout(request.cookies.get(COOKIE))
        response.delete_cookie(COOKIE, path="/")
        return {"ok": True}

    # ---- data ----------------------------------------------------------------------------
    async def tickets(refresh: bool = False) -> list[Ticket]:
        if refresh or time.time() - cache["at"] > TICKET_CACHE_SECONDS:
            cache["tickets"] = await tracker.list_all()
            cache["at"] = time.time()
        return cache["tickets"]

    def run_row(r: dict) -> dict:
        r = dict(r)
        r["cancel_requested"] = bool(r["cancel_requested"])
        r["duration"] = (r["finished_at"] or time.time()) - r["started_at"]
        return r

    @app.get("/api/overview", dependencies=[Depends(require_session)])
    async def overview(refresh: bool = False):
        ts = await tickets(refresh)
        counts: dict[str, int] = {}
        for t in ts:
            counts[t.status.value] = counts.get(t.status.value, 0) + 1
        running = [run_row(r) for r in db.query("SELECT * FROM runs WHERE status = 'running' ORDER BY started_at")]
        problems = [
            run_row(r) for r in db.query(
                "SELECT * FROM runs WHERE status IN ('failed','cancelled') AND started_at >= ? ORDER BY started_at DESC",
                (time.time() - 24 * 3600,),
            )
        ]
        inbox = [
            {"kind": "ticket", "state": t.status.value, "ticket": t.model_dump(include={"id", "title", "status", "area", "priority", "risk", "url", "pr_url", "branch", "agent_note", "updated_at"})}
            for t in ts if t.status in INBOX_STATES
        ]
        return {
            "project": project,
            "spent_today": spent_today(db),
            "daily_cap": daily_cap(db, cfg.limits.daily_budget_usd),
            "ticket_cap": cfg.limits.budget_usd_per_ticket,
            "counts": counts,
            "running": running,
            "recent_problems": problems,
            "inbox": inbox,
            "repo": {k: v for k, v in repo_state(cfg).items() if k in {"branch", "clean", "on_agent_branch"}},
        }

    @app.get("/api/tickets", dependencies=[Depends(require_session)])
    async def list_tickets(refresh: bool = False):
        ts = await tickets(refresh)
        last = {
            r["ticket_id"]: r for r in db.query(
                "SELECT ticket_id, kind, status, outcome, started_at FROM runs WHERE id IN (SELECT MAX(id) FROM runs GROUP BY ticket_id)"
            )
        }
        out = []
        for t in ts:
            d = t.model_dump(exclude={"body", "comments"})
            d["last_run"] = last.get(t.id)
            out.append(d)
        return {"tickets": out, "fetched_at": cache["at"]}

    @app.get("/api/tickets/{ticket_id}", dependencies=[Depends(require_session)])
    async def ticket_detail(ticket_id: str):
        try:
            ticket, comments = await tracker.detail(ticket_id)
        except Exception as e:
            raise HTTPException(502, f"Notion non raggiungibile: {e}")
        runs = [run_row(r) for r in db.query("SELECT * FROM runs WHERE ticket_id = ? ORDER BY started_at DESC", (ticket_id,))]
        return {"ticket": ticket.model_dump(exclude={"comments"}), "comments": [c.model_dump() for c in comments], "runs": runs}

    @app.get("/api/runs", dependencies=[Depends(require_session)])
    def list_runs(limit: int = 50, ticket_id: str | None = None):
        limit = max(1, min(limit, 200))
        if ticket_id:
            rows = db.query("SELECT * FROM runs WHERE ticket_id = ? ORDER BY started_at DESC LIMIT ?", (ticket_id, limit))
        else:
            rows = db.query("SELECT * FROM runs ORDER BY started_at DESC LIMIT ?", (limit,))
        return {"runs": [run_row(r) for r in rows]}

    def events_for(run_id: int, after: int = 0) -> list[dict]:
        rows = db.query("SELECT id, ts, type, text, data FROM events WHERE run_id = ? AND id > ? ORDER BY id", (run_id, after))
        for r in rows:
            r["data"] = json.loads(r["data"]) if r["data"] else None
        return rows

    @app.get("/api/runs/{run_id}", dependencies=[Depends(require_session)])
    def run_detail(run_id: int):
        row = db.one("SELECT * FROM runs WHERE id = ?", (run_id,))
        if not row:
            raise HTTPException(404, "run non trovato")
        return {"run": run_row(row), "events": events_for(run_id)}

    @app.get("/api/runs/{run_id}/stream", dependencies=[Depends(require_session)])
    async def run_stream(run_id: int, request: Request):
        if not db.one("SELECT id FROM runs WHERE id = ?", (run_id,)):
            raise HTTPException(404, "run non trovato")

        async def gen():
            last = int(request.headers.get("last-event-id") or 0)
            while True:
                for ev in events_for(run_id, last):
                    last = ev["id"]
                    yield f"id: {ev['id']}\nevent: event\ndata: {json.dumps(ev, ensure_ascii=False)}\n\n"
                status = db.one("SELECT status FROM runs WHERE id = ?", (run_id,))["status"]
                if status != "running" and not events_for(run_id, last):
                    yield f"event: end\ndata: {json.dumps({'status': status})}\n\n"
                    return
                if await request.is_disconnected():
                    return
                yield ": keepalive\n\n"
                await asyncio.sleep(0.5)

        return StreamingResponse(gen(), media_type="text/event-stream", headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"})

    @app.get("/api/costs", dependencies=[Depends(require_session)])
    def costs():
        day = "strftime('%Y-%m-%d', started_at, 'unixepoch', 'localtime')"
        since = time.time() - 30 * 24 * 3600
        return {
            "today": spent_today(db),
            "daily_cap": daily_cap(db, cfg.limits.daily_budget_usd),
            "ticket_cap": cfg.limits.budget_usd_per_ticket,
            "total": (db.one("SELECT COALESCE(SUM(cost_usd),0) AS s FROM runs") or {"s": 0})["s"],
            "by_day": db.query(f"SELECT {day} AS day, SUM(cost_usd) AS cost, COUNT(*) AS runs FROM runs WHERE started_at >= ? GROUP BY day ORDER BY day", (since,)),
            "by_model": db.query("SELECT COALESCE(model, 'n/d') AS model, SUM(cost_usd) AS cost, COUNT(*) AS runs FROM runs GROUP BY model ORDER BY cost DESC"),
            "by_kind": db.query("SELECT kind, SUM(cost_usd) AS cost, COUNT(*) AS runs FROM runs GROUP BY kind"),
            "by_ticket": db.query("SELECT ticket_id, ticket_title AS title, SUM(cost_usd) AS cost, COUNT(*) AS runs FROM runs GROUP BY ticket_id ORDER BY cost DESC LIMIT 10"),
        }

    @app.get("/api/repo", dependencies=[Depends(require_session)])
    async def repo():
        state = await asyncio.to_thread(repo_state, cfg)
        state["busy"] = bool(db.one("SELECT id FROM runs WHERE status = 'running' AND kind = 'fix'"))
        return state

    @app.get("/api/config", dependencies=[Depends(require_session)])
    def config():
        return {
            "project": project,
            "repo": cfg.repo,
            "base_branch": cfg.base_branch,
            "local_path": cfg.local_path,
            "workspace_mode": cfg.workspace_mode,
            "limits": cfg.limits.model_dump(),
            "agents": {k: v.model_dump(include={"models", "max_turns"}) for k, v in cfg.agents.items()},
            "model_choices": cfg.model_choices,
            "pr_enabled": cfg.pr.create,
            "never_automerge": cfg.risk.never_automerge,
            "daily_cap_effective": daily_cap(db, cfg.limits.daily_budget_usd),
            "started_today": start_of_today(),
        }

    # ---- static frontend -----------------------------------------------------------------
    if static_dir and static_dir.is_dir():
        index = static_dir / "index.html"

        @app.get("/{path:path}", include_in_schema=False)
        def spa(path: str):
            if path.startswith("api/"):
                raise HTTPException(404)
            candidate = (static_dir / path).resolve()
            if path and candidate.is_file() and static_dir.resolve() in candidate.parents:
                return FileResponse(candidate)
            return FileResponse(index)

    return app
