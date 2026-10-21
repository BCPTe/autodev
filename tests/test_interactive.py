import asyncio
import time
from types import SimpleNamespace

import pytest
from claude_agent_sdk import ClaudeAgentOptions, ResultMessage

from autodev.agents import session
from autodev.control import DENIED_IN_AUTO, RunControl, checkpoint, current_control
from autodev.db import Database


def result(*, final: bool, cost: float = 0.1) -> ResultMessage:
    return ResultMessage(
        subtype="success" if final else "error_during_execution", duration_ms=1, duration_api_ms=1,
        is_error=not final, num_turns=1, session_id="s", total_cost_usd=cost,
        structured_output={"ok": True} if final else None,
    )


class FakeClient:
    """Turn 1 runs until interrupted; the next turn finishes. `during_turn` may call into the agent's hooks."""

    last: "FakeClient"
    during_turn = None

    def __init__(self, options):
        self.options, self.sent, self.interrupted = options, [], asyncio.Event()
        self.turn = 0
        self.started = asyncio.Event()
        FakeClient.last = self

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def query(self, text):
        self.sent.append(text)

    async def interrupt(self):
        self.interrupted.set()

    async def receive_response(self):
        self.turn += 1
        if FakeClient.during_turn:
            await FakeClient.during_turn(self)
        if self.turn == 1 and not FakeClient.during_turn:
            self.started.set()
            await self.interrupted.wait()
            yield result(final=False)
        else:
            yield result(final=True)


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(session, "ClaudeSDKClient", FakeClient)
    FakeClient.during_turn = None
    db = Database(tmp_path / "i.db")
    run_id = db.execute("INSERT INTO runs(project, ticket_id, ticket_title, kind, status, started_at) VALUES('p','t','T','fix','running',?)", (time.time(),))
    control = RunControl(db, lambda: "supervised")
    control.run_id = run_id
    current_control.set(control)
    yield control, db
    current_control.set(None)


def events(db, type_):
    return [e["text"] for e in db.query("SELECT text FROM events WHERE type = ? ORDER BY id", (type_,))]


async def start(prompt="fai il fix"):
    task = asyncio.ensure_future(session.run_session(prompt, ClaudeAgentOptions(cwd="/tmp"), lambda m: None))
    await asyncio.sleep(0.05)
    return task


async def test_a_message_interrupts_the_agent_and_becomes_its_next_turn(env):
    control, db = env
    task = await start()
    await asyncio.wait_for(FakeClient.last.started.wait(), 2)
    await control.send("usa un altro file")
    final = await asyncio.wait_for(task, 2)
    assert final.structured_output == {"ok": True}
    assert FakeClient.last.sent == ["fai il fix", "usa un altro file"]
    assert events(db, "user") == ["usa un altro file"]
    assert FakeClient.last.options.permission_mode == "default"
    assert FakeClient.last.options.can_use_tool == control.can_use_tool


async def test_pause_waits_for_a_message_before_going_on(env):
    control, db = env
    task = await start()
    await asyncio.wait_for(FakeClient.last.started.wait(), 2)
    await control.pause()
    await asyncio.sleep(0.05)
    assert control.state == "waiting" and not task.done()
    await control.send("continua pure")
    await asyncio.wait_for(task, 2)
    assert FakeClient.last.sent[-1] == "continua pure"
    assert events(db, "paused")


async def test_a_message_sent_after_the_agent_finished_is_reported_not_lost(env):
    control, db = env

    async def finish_at_once(client):
        await control.send("troppo tardi")

    FakeClient.during_turn = finish_at_once
    final = await asyncio.wait_for(await start(), 2)
    assert final.structured_output == {"ok": True}
    assert any("troppo tardi" in t for t in events(db, "log"))


async def test_permission_request_waits_for_the_human_and_can_be_denied_with_a_reason(env):
    control, db = env
    ctx = SimpleNamespace(title=None)
    pending = asyncio.ensure_future(control.can_use_tool("Bash", {"command": "docker ps"}, ctx))
    await asyncio.sleep(0.05)
    row = db.one("SELECT id, status, kind FROM approvals")
    assert (row["status"], row["kind"]) == ("pending", "permission") and control.state == "approval"
    assert control.decide(row["id"], "deny", "no, usa i test")
    outcome = await pending
    assert (outcome.behavior, outcome.message) == ("deny", "no, usa i test")
    assert db.one("SELECT status, note FROM approvals") == {"status": "denied", "note": "no, usa i test"}
    assert control.state == "running"
    assert not control.decide(row["id"], "allow")


async def test_allow_for_the_run_is_remembered_for_the_same_command_only(env):
    control, db = env
    ctx = SimpleNamespace(title=None)
    first = asyncio.ensure_future(control.can_use_tool("Bash", {"command": "git status -s"}, ctx))
    await asyncio.sleep(0.05)
    control.decide(db.one("SELECT id FROM approvals")["id"], "allow_run")
    assert (await first).behavior == "allow"
    assert (await control.can_use_tool("Bash", {"command": "git status"}, ctx)).behavior == "allow"
    other = asyncio.ensure_future(control.can_use_tool("Bash", {"command": "git push origin main"}, ctx))
    await asyncio.sleep(0.05)
    assert len(db.query("SELECT id FROM approvals")) == 2 and not other.done()
    other.cancel()


async def test_auto_mode_never_asks_anyone(env):
    control, db = env
    control.mode = lambda: "auto"
    outcome = await control.can_use_tool("Bash", {"command": "rm -rf /"}, SimpleNamespace(title=None))
    assert (outcome.behavior, outcome.message) == ("deny", DENIED_IN_AUTO)
    assert db.query("SELECT id FROM approvals") == []


async def test_a_cancelled_run_leaves_no_pending_approval(env):
    control, db = env
    pending = asyncio.ensure_future(control.can_use_tool("Edit", {"file_path": "/x"}, SimpleNamespace(title="Modifica x")))
    await asyncio.sleep(0.05)
    pending.cancel()
    await asyncio.gather(pending, return_exceptions=True)
    assert db.one("SELECT status FROM approvals")["status"] == "expired"


async def test_checkpoint_passes_when_nobody_can_answer_and_waits_otherwise(env):
    control, db = env
    assert await checkpoint([], "before_pr", "t", {}) == (True, "")  # not enabled
    current_control.set(None)
    assert await checkpoint(["before_pr"], "before_pr", "t", {}) == (True, "")  # CLI run
    current_control.set(control)
    control.mode = lambda: "auto"
    assert await checkpoint(["before_pr"], "before_pr", "t", {}) == (True, "")
    control.mode = lambda: "manual"
    waiting = asyncio.ensure_future(checkpoint(["before_pr"], "before_pr", "Apro la PR?", {"files": ["a.py"]}))
    await asyncio.sleep(0.05)
    row = db.one("SELECT id, kind FROM approvals")
    assert row["kind"] == "checkpoint"
    control.decide(row["id"], "deny", "aspetta")
    assert await waiting == (False, "aspetta")
