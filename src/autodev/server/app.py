import asyncio
import json
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, Protocol

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request, Response
import httpx
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel

from autodev.config import ProjectConfig
from autodev.db import Database
from autodev.engine import Engine, Refused
from autodev.jobs import daily_cap, mark_orphans, spent_today, start_of_today
from autodev.models import Comment, Status, Ticket
from autodev.server import auth as authmod
from autodev.server.auth import COOKIE, Auth
from autodev import costs as costs_mod, github, knowledge
from autodev.server import repo as repomod
from autodev.sandbox.workspace import identity_flags
from autodev.server.repo import RepoError, repo_state

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


class Control(BaseModel):
    mode: str | None = None
    my_turn: bool | None = None
    daily_budget_usd: float | None = None
    quiet_hours: str | None = None
    notifications: bool | None = None
    permission_policy: str | None = None


class TicketEdit(BaseModel):
    status: Status | None = None
    authorized: bool | None = None
    model: str | None = None
    attempts: int | None = None


class Checkout(BaseModel):
    branch: str


class Cleanup(BaseModel):
    names: list[str] | None = None
    remote: bool = False


class Merge(BaseModel):
    confirm: bool = False
    method: Literal["squash", "merge", "rebase"] = "squash"
    delete_branch: bool = True


class Decision(BaseModel):
    decision: Literal["allow", "allow_run", "deny"]
    note: str = ""


class LearningEdit(BaseModel):
    category: Literal["where", "domain", "gotcha", "command"] | None = None
    text: str | None = None
    area: str | None = None
    paths: list[str] | None = None


class Message(BaseModel):
    text: str


class StartJob(BaseModel):
    kind: Literal["triage", "fix", "publish", "learn"]


class CommentBody(BaseModel):
    text: str


class Credentials(BaseModel):
    password: str


class Setup(BaseModel):
    password: str
    code: str


@dataclass
class Ctx:
    """Everything one project needs: its config, tracker, engine and caches."""

    cfg: ProjectConfig
    project: str
    db: Database
    tracker: Any
    engine: Engine
    cache: dict[str, Any] = field(default_factory=lambda: {"at": 0.0, "tickets": [], "prs_at": 0.0, "prs": []})

    def __post_init__(self) -> None:
        self.engine.on_change = lambda: self.cache.update(at=0.0)


def project_router(ctx: Ctx, require_session) -> APIRouter:
    """All the routes that belong to one project; mounted once per project (see create_app)."""
    cfg, project, db, tracker, engine, cache = ctx.cfg, ctx.project, ctx.db, ctx.tracker, ctx.engine, ctx.cache
    r = APIRouter()

    # ---- data ----------------------------------------------------------------------------
    async def tickets(refresh: bool = False) -> list[Ticket]:
        if refresh or time.time() - cache["at"] > TICKET_CACHE_SECONDS:
            cache["tickets"] = await tracker.list_all()
            cache["at"] = time.time()
        return cache["tickets"]

    def pending_approvals(run_id: int | None = None) -> list[dict]:
        sql = (
            "SELECT a.id, a.run_id, a.kind, a.title, a.detail, a.created_at, r.ticket_id, r.ticket_title, r.kind AS run_kind "
            "FROM approvals a JOIN runs r ON r.id = a.run_id WHERE a.status = 'pending' AND r.project = ?"
        )
        rows = db.query(sql + (" AND a.run_id = ?" if run_id else "") + " ORDER BY a.id", (project, run_id) if run_id else (project,))
        for r in rows:
            r["detail"] = json.loads(r["detail"]) if r["detail"] else {}
        return rows

    def run_row(r: dict) -> dict:
        r = dict(r)
        r["cancel_requested"] = bool(r["cancel_requested"])
        r["duration"] = (r["finished_at"] or time.time()) - r["started_at"]
        r["sessions"] = costs_mod.sessions_of(r)
        r.pop("usage", None)
        return r

    @r.get("/overview", dependencies=[Depends(require_session)])
    async def overview(refresh: bool = False):
        ts = await tickets(refresh)
        counts: dict[str, int] = {}
        for t in ts:
            counts[t.status.value] = counts.get(t.status.value, 0) + 1
        running = [run_row(r) for r in db.query("SELECT * FROM runs WHERE status = 'running' AND project = ? ORDER BY started_at", (project,))]
        # A failed or stopped run needs you only while it is the latest word on its ticket: once the ticket was
        # run again, closed, sent to review or deleted, or you dismissed the run, it is no longer a problem.
        waiting = {t.id for t in ts if t.status not in (Status.CLOSED, Status.REVIEW)}
        problems = [
            run_row(r) for r in db.query(
                "SELECT * FROM runs WHERE status IN ('failed','cancelled') AND dismissed = 0 AND project = ? AND started_at >= ? "
                "AND id = (SELECT MAX(id) FROM runs x WHERE x.ticket_id = runs.ticket_id AND x.project = runs.project) "
                "ORDER BY started_at DESC",
                (project, time.time() - 24 * 3600),
            ) if r["ticket_id"] in waiting or r["ticket_id"] == "repo"
        ]
        inbox = [
            {"kind": "ticket", "state": t.status.value, "ticket": t.model_dump(include={"id", "title", "status", "area", "priority", "risk", "url", "pr_url", "branch", "agent_note", "updated_at"})}
            for t in ts if t.status in INBOX_STATES
        ]
        return {
            "project": project,
            "spent_today": spent_today(db, project),
            "daily_cap": daily_cap(db, cfg.limits.daily_budget_usd, project),
            "ticket_cap": cfg.limits.budget_usd_per_ticket,
            "counts": counts,
            "running": running,
            "recent_problems": problems,
            "inbox": inbox,
            "repo": {k: v for k, v in repo_state(cfg).items() if k in {"branch", "clean", "on_agent_branch"}},
            "control": engine.state(),
            "approvals": pending_approvals(),
        }

    @r.get("/tickets", dependencies=[Depends(require_session)])
    async def list_tickets(refresh: bool = False):
        ts = await tickets(refresh)
        last = {
            r["ticket_id"]: r for r in db.query(
                "SELECT ticket_id, kind, status, outcome, started_at FROM runs WHERE id IN (SELECT MAX(id) FROM runs WHERE project = ? GROUP BY ticket_id)", (project,)
            )
        }
        out = []
        for t in ts:
            d = t.model_dump(exclude={"body", "comments"})
            d["last_run"] = last.get(t.id)
            out.append(d)
        return {"tickets": out, "fetched_at": cache["at"]}

    @r.get("/tickets/{ticket_id}", dependencies=[Depends(require_session)])
    async def ticket_detail(ticket_id: str):
        try:
            ticket, comments = await tracker.detail(ticket_id)
        except Exception as e:
            raise HTTPException(502, f"Notion is unreachable: {e}")
        runs = [run_row(r) for r in db.query("SELECT * FROM runs WHERE ticket_id = ? AND project = ? ORDER BY started_at DESC", (ticket_id, project))]
        actions = db.query("SELECT ts, actor, action, detail FROM actions WHERE ticket_id = ? ORDER BY id DESC LIMIT 30", (ticket_id,))
        return {"ticket": ticket.model_dump(exclude={"comments"}), "comments": [c.model_dump() for c in comments], "runs": runs, "actions": actions}

    @r.get("/runs", dependencies=[Depends(require_session)])
    def list_runs(limit: int = 50, ticket_id: str | None = None):
        limit = max(1, min(limit, 200))
        if ticket_id:
            rows = db.query("SELECT * FROM runs WHERE ticket_id = ? AND project = ? ORDER BY started_at DESC LIMIT ?", (ticket_id, project, limit))
        else:
            rows = db.query("SELECT * FROM runs WHERE project = ? ORDER BY started_at DESC LIMIT ?", (project, limit))
        return {"runs": [run_row(r) for r in rows]}

    def events_for(run_id: int, after: int = 0) -> list[dict]:
        rows = db.query("SELECT id, ts, type, text, data FROM events WHERE run_id = ? AND id > ? ORDER BY id", (run_id, after))
        for r in rows:
            r["data"] = json.loads(r["data"]) if r["data"] else None
        return rows

    @r.get("/runs/{run_id}", dependencies=[Depends(require_session)])
    def run_detail(run_id: int):
        row = db.one("SELECT * FROM runs WHERE id = ? AND project = ?", (run_id, project))
        if not row:
            raise HTTPException(404, "run not found")
        control = engine.controls.get(run_id)
        interactive = {"live": control is not None, "state": control.state if control else None, "approvals": pending_approvals(run_id)}
        return {"run": run_row(row), "events": events_for(run_id), "interactive": interactive}

    @r.get("/runs/{run_id}/stream", dependencies=[Depends(require_session)])
    async def run_stream(run_id: int, request: Request):
        if not db.one("SELECT id FROM runs WHERE id = ? AND project = ?", (run_id, project)):
            raise HTTPException(404, "run not found")

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

    # ---- controls ------------------------------------------------------------------------
    @r.get("/control", dependencies=[Depends(require_session)])
    def control_state():
        return engine.state()

    @r.put("/control", dependencies=[Depends(require_session)])
    def control_update(body: Control):
        try:
            if body.mode is not None:
                engine.set_mode(body.mode)
            if body.my_turn is not None:
                engine.set_my_turn(body.my_turn)
            if body.daily_budget_usd is not None:
                engine.set_daily_cap(body.daily_budget_usd)
            if body.quiet_hours is not None:
                engine.set_quiet_hours(body.quiet_hours.strip())
            if body.notifications is not None:
                engine.set_notifications(body.notifications)
            if body.permission_policy is not None:
                engine.set_permission_policy(body.permission_policy)
        except ValueError as e:
            raise HTTPException(422, str(e))
        return engine.state()

    @r.post("/control/check-now", dependencies=[Depends(require_session)])
    def check_now():
        engine.check_now()
        return {"ok": True}

    @r.post("/control/stop-all", dependencies=[Depends(require_session)])
    def stop_all():
        return {"stopped": engine.stop()}

    @r.post("/runs/{run_id}/dismiss", dependencies=[Depends(require_session)])
    def dismiss_run(run_id: int):
        if not db.one("SELECT id FROM runs WHERE id = ? AND project = ?", (run_id, project)):
            raise HTTPException(404, "run not found")
        db.execute("UPDATE runs SET dismissed = 1 WHERE id = ?", (run_id,))
        return {"ok": True}

    @r.post("/runs/{run_id}/cancel", dependencies=[Depends(require_session)])
    def cancel_run(run_id: int):
        row = db.one("SELECT status FROM runs WHERE id = ? AND project = ?", (run_id, project))
        if not row:
            raise HTTPException(404, "run not found")
        if row["status"] != "running":
            raise HTTPException(409, "the run has already finished")
        engine.stop(run_id)
        return {"ok": True}

    def live_control(run_id: int):
        control = engine.controls.get(run_id)
        if control is None:
            raise HTTPException(409, "this run is not interactive (it has finished or was started from the terminal)")
        return control

    @r.post("/runs/{run_id}/message", dependencies=[Depends(require_session)])
    async def message_run(run_id: int, body: Message):
        text = body.text.strip()
        if not text:
            raise HTTPException(422, "the message is empty")
        await live_control(run_id).send(text)
        row = db.one("SELECT ticket_id FROM runs WHERE id = ? AND project = ?", (run_id, project))
        db.audit("user", "message", row["ticket_id"], text[:200])
        return {"ok": True}

    @r.post("/runs/{run_id}/pause", dependencies=[Depends(require_session)])
    async def pause_run(run_id: int):
        await live_control(run_id).pause()
        return {"ok": True}

    @r.get("/approvals", dependencies=[Depends(require_session)])
    def list_approvals():
        return {"approvals": pending_approvals()}

    @r.post("/approvals/{approval_id}", dependencies=[Depends(require_session)])
    def decide_approval(approval_id: int, body: Decision):
        row = db.one("SELECT a.run_id, a.status, r.ticket_id FROM approvals a JOIN runs r ON r.id = a.run_id WHERE a.id = ? AND r.project = ?", (approval_id, project))
        if not row:
            raise HTTPException(404, "request not found")
        control = engine.controls.get(row["run_id"])
        if row["status"] != "pending" or control is None or not control.decide(approval_id, body.decision, body.note):
            raise HTTPException(409, "the request is no longer pending")
        db.audit("user", "approval", row["ticket_id"], body.decision)
        return {"ok": True}

    @r.post("/tickets/{ticket_id}/start", dependencies=[Depends(require_session)])
    async def start_job(ticket_id: str, body: StartJob):
        try:
            await engine.start(ticket_id, body.kind)
        except Refused as e:
            raise HTTPException(409, str(e))
        except Exception as e:
            raise HTTPException(502, f"Notion is unreachable: {e}")
        cache["at"] = 0.0
        return {"ok": True}

    @r.patch("/tickets/{ticket_id}", dependencies=[Depends(require_session)])
    async def edit_ticket(ticket_id: str, body: TicketEdit):
        changes = body.model_dump(exclude_none=True)
        if not changes:
            raise HTTPException(422, "no changes")
        if "model" in changes and changes["model"] != "Auto" and changes["model"] not in cfg.model_choices:
            raise HTTPException(422, f"unknown model: {changes['model']}")
        if changes.get("attempts", 0) < 0:
            raise HTTPException(422, "attempts cannot be negative")
        try:
            if "status" in changes:
                await tracker.set_status(ticket_id, changes.pop("status"))
            if changes:
                await tracker.update(ticket_id, **changes)
        except Exception as e:
            raise HTTPException(502, f"Notion did not accept the change: {e}")
        db.audit("user", "edit", ticket_id, json.dumps(body.model_dump(exclude_none=True), default=str))
        cache["at"] = 0.0
        return {"ok": True}

    def comment_author() -> str | None:
        """Notion shows comments posted through an integration under its name; this label says who really wrote it."""
        if cfg.autonomy.comment_author:
            return cfg.autonomy.comment_author
        try:
            return identity_flags(cfg)[1].split("=", 1)[1]
        except RuntimeError:
            return None

    @r.post("/tickets/{ticket_id}/comment", dependencies=[Depends(require_session)])
    async def add_comment(ticket_id: str, body: CommentBody):
        text = body.text.strip()
        if not text:
            raise HTTPException(422, "the comment is empty")
        try:
            await tracker.comment(ticket_id, text, as_human=True, author=comment_author())
        except Exception as e:
            raise HTTPException(502, f"Notion did not accept the comment: {e}")
        db.audit("user", "comment", ticket_id, text[:200])
        return {"ok": True}

    @r.get("/costs", dependencies=[Depends(require_session)])
    def costs():
        day = "strftime('%Y-%m-%d', started_at, 'unixepoch', 'localtime')"
        since = time.time() - 30 * 24 * 3600
        return {
            "today": spent_today(db, project),
            "daily_cap": daily_cap(db, cfg.limits.daily_budget_usd, project),
            "ticket_cap": cfg.limits.budget_usd_per_ticket,
            "total": (db.one("SELECT COALESCE(SUM(cost_usd),0) AS s FROM runs WHERE project = ?", (project,)) or {"s": 0})["s"],
            "by_day": db.query(f"SELECT {day} AS day, SUM(cost_usd) AS cost, COUNT(*) AS runs FROM runs WHERE project = ? AND started_at >= ? GROUP BY day ORDER BY day", (project, since)),
            "by_model": db.query("SELECT COALESCE(model, 'n/d') AS model, SUM(cost_usd) AS cost, COUNT(*) AS runs FROM runs WHERE project = ? GROUP BY model ORDER BY cost DESC", (project,)),
            "by_kind": db.query("SELECT kind, SUM(cost_usd) AS cost, COUNT(*) AS runs FROM runs WHERE project = ? GROUP BY kind", (project,)),
            "by_ticket": db.query("SELECT ticket_id, ticket_title AS title, SUM(cost_usd) AS cost, COUNT(*) AS runs FROM runs WHERE project = ? GROUP BY ticket_id ORDER BY cost DESC LIMIT 10", (project,)),
            "by_stage_model": costs_mod.by_stage_model(db, project),
            "by_area": costs_mod.by_area(db, project),
            "by_outcome": costs_mod.by_outcome(db, project),
        }

    # ---- playbook ------------------------------------------------------------------------
    @r.get("/knowledge", dependencies=[Depends(require_session)])
    def knowledge_state():
        _, entries = knowledge.load(cfg)
        usage = knowledge.usage_stats(db, project)
        proposals = knowledge.list_proposals(db, project)
        for p in proposals:
            p["missing_paths"] = knowledge.missing_paths(cfg, p["paths"])
        return {
            "enabled": knowledge.enabled(cfg),
            "file": Path(cfg.knowledge_path).name if cfg.knowledge_path else None,
            "max_chars": cfg.knowledge.max_chars,
            "auto_propose_on_close": cfg.knowledge.auto_propose_on_close,
            "chars": sum(len(e.prompt_line()) + 1 for e in entries),
            "entries": [
                {**knowledge.entry_dict(e), "missing_paths": knowledge.missing_paths(cfg, e.paths), **usage.get(e.id, {"uses": 0, "cited": 0, "last_used": None})}
                for e in entries
            ],
            "proposals": proposals,
            "metrics": knowledge.metrics(db, project),
        }

    @r.post("/learnings/{learning_id}/accept", dependencies=[Depends(require_session)])
    def accept_learning(learning_id: int, body: LearningEdit | None = None):
        if not knowledge.enabled(cfg):
            raise HTTPException(409, "the playbook is turned off for this project")
        try:
            entry = knowledge.accept(db, cfg, project, learning_id, body.model_dump() if body else None)
        except LookupError as e:
            raise HTTPException(404, str(e))
        except ValueError as e:
            raise HTTPException(422, str(e))
        db.audit("user", "learning_accept", None, entry.text[:200])
        return {"ok": True, "entry": knowledge.entry_dict(entry)}

    @r.post("/learnings/{learning_id}/reject", dependencies=[Depends(require_session)])
    def reject_learning(learning_id: int):
        try:
            knowledge.reject(db, project, learning_id)
        except LookupError as e:
            raise HTTPException(404, str(e))
        except ValueError as e:
            raise HTTPException(422, str(e))
        db.audit("user", "learning_reject", None, str(learning_id))
        return {"ok": True}

    @r.delete("/knowledge/entries/{entry_id}", dependencies=[Depends(require_session)])
    def delete_entry(entry_id: str):
        if not knowledge.delete_entry(cfg, entry_id):
            raise HTTPException(404, "entry not found")
        db.audit("user", "knowledge_delete", None, entry_id)
        return {"ok": True}

    async def pulls(refresh: bool = False) -> list[dict]:
        if not cfg.pr.slug:
            return []
        if refresh or time.time() - cache["prs_at"] > 30:
            try:
                cache["prs"] = await github.list_pulls(cfg, cfg.branch_prefix)
            except Exception as e:
                raise HTTPException(502, f"GitHub is unreachable: {e}")
            cache["prs_at"] = time.time()
        return cache["prs"]

    async def merged_heads() -> set[str]:
        try:
            return {p["branch"] for p in await pulls() if p["state"] == "merged"}
        except HTTPException:
            return set()

    @r.get("/prs", dependencies=[Depends(require_session)])
    async def list_prs(refresh: bool = False):
        prs = await pulls(refresh)
        by_url = {t.pr_url: t for t in await tickets() if t.pr_url}
        out = []
        for p in prs:
            t = by_url.get(p["url"])
            out.append({**p, "ticket": t.model_dump(include={"id", "title", "risk", "verification", "agent_note", "status"}) if t else None})
        return {"enabled": True, "prs": out}

    @r.post("/prs/{number}/merge", dependencies=[Depends(require_session)])
    async def merge_pr(number: int, body: Merge):
        if not body.confirm:
            raise HTTPException(422, "explicit confirmation is required")
        pr = next((p for p in await pulls(True) if p["number"] == number), None)
        if not pr or pr["state"] != "open":
            raise HTTPException(409, "the pull request is not open")
        if pr["draft"]:
            raise HTTPException(409, "the pull request is a draft")
        if pr["checks"] and pr["checks"]["verdict"] == "unknown":
            raise HTTPException(409, "the checks on GitHub cannot be read with this token, so they cannot be verified here: merge on GitHub or give the token 'Checks' and 'Commit statuses' (read)")
        if pr["checks"] and pr["checks"]["verdict"] in ("failing", "pending"):
            raise HTTPException(409, "the checks on GitHub have not passed: wait or fix them")
        if pr["mergeable"] is False:
            raise HTTPException(409, "there are conflicts with the base branch")
        ticket = next((t for t in await tickets() if t.pr_url == pr["url"]), None)
        if ticket and ticket.risk == "High":
            raise HTTPException(403, "High risk: merge it by hand on GitHub after reading it")
        try:
            await github.merge_pull(cfg, number, body.method)
            if body.delete_branch:
                await github.delete_remote_branch(cfg, pr["branch"])
        except Exception as e:
            raise HTTPException(502, f"GitHub refused the merge: {e}")
        if ticket:
            await tracker.set_status(ticket.id, Status.CLOSED)
            engine.after_close(ticket)
        db.audit("user", "merge", ticket.id if ticket else None, f"PR {number} ({body.method})")
        cache["prs_at"] = 0.0
        cache["at"] = 0.0
        back_on = None
        if not engine.busy():
            back_on = await asyncio.to_thread(repomod.return_to_base_after_merge, cfg, pr["branch"])
        return {"ok": True, "back_on": back_on}

    def checkout_guard() -> None:
        if engine.busy():
            raise HTTPException(409, "an agent is working on the checkout")

    @r.get("/repo/diff", dependencies=[Depends(require_session)])
    async def repo_diff(branch: str | None = None):
        try:
            return await asyncio.to_thread(repomod.diff, cfg, branch)
        except RepoError as e:
            raise HTTPException(404, str(e))

    @r.post("/repo/checkout", dependencies=[Depends(require_session)])
    async def repo_checkout(body: Checkout):
        checkout_guard()
        try:
            await asyncio.to_thread(repomod.checkout, cfg, body.branch)
        except RepoError as e:
            raise HTTPException(409, str(e))
        db.audit("user", "checkout", None, body.branch)
        return {"ok": True}

    @r.post("/repo/cleanup", dependencies=[Depends(require_session)])
    async def repo_cleanup(body: Cleanup):
        checkout_guard()
        pr_merged = await merged_heads()
        names = body.names if body.names is not None else await asyncio.to_thread(repomod.removable_branches, cfg, pr_merged)
        try:
            deleted = await asyncio.to_thread(repomod.delete_branches, cfg, names, pr_merged)
        except RepoError as e:
            raise HTTPException(409, str(e))
        remote_deleted = []
        if body.remote:
            for name in deleted:
                try:
                    if await github.delete_remote_branch(cfg, name):
                        remote_deleted.append(name)
                except Exception:
                    pass
        db.audit("user", "cleanup", None, ", ".join(deleted))
        return {"deleted": deleted, "remote_deleted": remote_deleted}

    @r.post("/repo/checks", dependencies=[Depends(require_session)])
    async def repo_checks():
        try:
            await engine.start_checks()
        except Refused as e:
            raise HTTPException(409, str(e))
        return {"ok": True}

    @r.get("/repo", dependencies=[Depends(require_session)])
    async def repo():
        state = await asyncio.to_thread(repo_state, cfg, await merged_heads())
        state["busy"] = engine.busy()
        return state

    @r.get("/config", dependencies=[Depends(require_session)])
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
            "has_checks": bool(cfg.checks),
            "never_automerge": cfg.risk.never_automerge,
            "daily_cap_effective": daily_cap(db, cfg.limits.daily_budget_usd, project),
            "autonomy": cfg.autonomy.model_dump(),
            "statuses": {k.value: v for k, v in cfg.tracker.status_map.items()},
            "started_today": start_of_today(),
        }


    return r


def create_app(
    cfg: ProjectConfig, project: str, db: Database, tracker: TrackerLike, *,
    static_dir: Path | None = DIST, engine: Engine | None = None, run_loop: bool = False,
    others: list[Ctx] | None = None,
) -> FastAPI:
    """One dashboard for one or more projects.

    The first project is also served at /api/...; every project (that one included) lives at
    /api/p/<name>/..., which is what the dashboard uses once it knows the project list.
    """
    engine = engine or Engine(cfg, project, db, tracker)
    contexts = [Ctx(cfg, project, db, tracker, engine), *(others or [])]

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        loops = [asyncio.ensure_future(c.engine.run_forever()) for c in contexts] if run_loop else []
        yield
        for loop in loops:
            loop.cancel()

    app = FastAPI(title="autodev", docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)

    @app.exception_handler(httpx.HTTPStatusError)
    async def tracker_error(request: Request, e: httpx.HTTPStatusError):
        """A tracker or GitHub call refused (missing access, wrong id): say so instead of a bare 500."""
        try:
            detail = e.response.json().get("message") or e.response.text
        except ValueError:
            detail = e.response.text
        host = e.request.url.host
        hint = " Share the database with the integration (Notion: ⋯ > Connections)." if "notion" in host and e.response.status_code in (401, 403, 404) else ""
        return JSONResponse({"detail": f"{host} answered {e.response.status_code}: {detail}{hint}"}, status_code=502)
    auth = Auth(db)
    app.state.auth = auth
    app.state.engine = engine
    mark_orphans(db)

    @app.middleware("http")
    async def guard(request: Request, call_next):
        host = hostname(request.headers.get("host", ""))
        if host not in ALLOWED_HOSTS:
            return Response("host not allowed", status_code=400)
        if request.method not in ("GET", "HEAD", "OPTIONS"):
            origin = request.headers.get("origin")
            if origin and hostname(origin.split("://", 1)[-1]) not in ALLOWED_HOSTS:
                return Response("origin not allowed", status_code=403)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; font-src 'self' data:; connect-src 'self'; frame-ancestors 'none'"
        )
        return response

    def require_session(request: Request) -> None:
        if not auth.valid(request.cookies.get(COOKIE)):
            raise HTTPException(401, "not authenticated")

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
            raise HTTPException(429, f"too many attempts, try again in {wait} seconds", headers={"Retry-After": str(wait)})
        token = auth.login(body.password)
        if not token:
            raise HTTPException(401, "wrong password")
        set_cookie(response, token)
        return {"ok": True}

    @app.post("/api/auth/logout")
    def auth_logout(request: Request, response: Response):
        auth.logout(request.cookies.get(COOKIE))
        response.delete_cookie(COOKIE, path="/")
        return {"ok": True}

    # ---- projects ------------------------------------------------------------------------
    for c in contexts:
        app.include_router(project_router(c, require_session), prefix=f"/api/p/{c.project}")
    app.include_router(project_router(contexts[0], require_session), prefix="/api")

    @app.get("/api/projects", dependencies=[Depends(require_session)])
    def list_projects():
        def count(sql: str, name: str) -> int:
            return db.one(sql, (name,))["n"]

        return {
            "default": project,
            "projects": [
                {
                    "name": c.project,
                    "repo": c.cfg.repo,
                    "mode": c.engine.mode,
                    "running": count("SELECT COUNT(*) AS n FROM runs WHERE status = 'running' AND project = ?", c.project),
                    "waiting": count("SELECT COUNT(*) AS n FROM approvals a JOIN runs r ON r.id = a.run_id WHERE a.status = 'pending' AND r.project = ?", c.project),
                }
                for c in contexts
            ],
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
