"""Live control of one running agent: pause, talk to it, and answer its questions.

A run started by the dashboard server gets a `RunControl` (found by the agents through
`current_control`). Runs started from the CLI have none and behave exactly as before.

Talking to the agent is "interrupt, then instruct": the current action stops, the agent keeps its
whole context, and your message becomes its next turn. That keeps every turn well delimited.
"""
import asyncio
import json
import re
from contextvars import ContextVar
from typing import Any, Callable

from claude_agent_sdk import AssistantMessage, PermissionResultAllow, PermissionResultDeny, TextBlock

from autodev.db import Database, dumps, now
from autodev.jobs import add_event
from autodev.progress import describe_tool

current_control: ContextVar["RunControl | None"] = ContextVar("current_control", default=None)

DENIED_IN_AUTO = "Permission not granted: in Auto mode nobody answers requests. Find another way."


DENIED_DANGEROUS = "Permission not granted: this command can destroy work or leave the project, and nobody can approve it in Auto mode."

_DANGEROUS = [re.compile(p) for p in (
    r"\brm\s+(-\w*[rf]\w*|--recursive|--force)",
    r"\bsudo\b", r"\bsu\s", r"\b(dd|mkfs\w*|shutdown|reboot|halt|kill|killall|pkill)\b",
    r"\bgit\s+(push|reset\s+--hard|clean|checkout\s+--|checkout\s+-f|branch\s+-[dD]|rebase|stash\s+(drop|clear)|remote\s+(add|set-url))",
    r"\bchmod\s+-R|\bchown\b", r"(curl|wget)[^|;]*\|\s*(sudo\s+)?(ba|z)?sh",
    r"\b(npm|pnpm|yarn)\s+(publish|login)", r"\bpip\s+install\b.*--break-system",
    r"\bdocker\s+(rm|rmi|system|volume\s+(rm|prune)|compose\s+(down|rm))", r">\s*/(dev|etc|usr|var|boot)/",
    r"(\.ssh|\.aws|\.gnupg|/etc/(passwd|shadow))", r"\.env\b",
)]


def is_dangerous(tool: str, tool_input: dict[str, Any], cwd: str = "") -> bool:
    """Commands that never run without a human, whatever the policy: they destroy work or leave the project."""
    if tool == "Bash":
        command = str(tool_input.get("command", ""))
        return any(p.search(command) for p in _DANGEROUS)
    if tool in ("Edit", "Write"):
        path = str(tool_input.get("file_path", ""))
        return bool(path) and path.startswith("/") and not (path.startswith(cwd.rstrip("/") + "/") or path.startswith("/tmp/"))
    return False


def remember_key(tool: str, tool_input: dict[str, Any]) -> str:
    """What 'allow for this run' means: the tool, and for Bash the program (python3, sed, grep...)."""
    if tool == "Bash":
        words = str(tool_input.get("command", "")).split()
        return "Bash:" + (words[0] if words else "")
    return tool


class RunControl:
    def __init__(
        self, db: Database, mode: Callable[[], str], notify: Callable[[str, str], None] | None = None,
        policy: Callable[[], str] | None = None,
    ):
        self.db = db
        self.mode = mode
        self.policy = policy or (lambda: "ask")
        self.notify = notify or (lambda title, body: None)
        self.run_id: int | None = None
        self.client: Any = None
        self.cwd = "/"
        self.state = "running"  # running | waiting (paused, wants a message) | approval
        self._interrupt = False
        self._messages: asyncio.Queue[str] = asyncio.Queue()
        self._futures: dict[int, asyncio.Future] = {}
        self._remembered: set[str] = set()

    # ---- events --------------------------------------------------------------------------
    def event(self, type_: str, text: str = "", data: dict | None = None) -> None:
        if self.run_id is not None:
            add_event(self.db, self.run_id, type_, text, data)

    def narrate(self, message: AssistantMessage) -> None:
        for block in message.content:
            if isinstance(block, TextBlock) and block.text.strip():
                self.event("agent", block.text.strip()[:2000])

    # ---- pause and messages --------------------------------------------------------------
    async def _interrupt_now(self) -> None:
        self._interrupt = True
        if self.client is not None:
            await self.client.interrupt()

    async def pause(self) -> None:
        if self.state == "running":
            self.event("paused", "paused: write a message to make it continue")
            await self._interrupt_now()

    async def send(self, text: str) -> None:
        self._messages.put_nowait(text)
        if self.state == "running":
            await self._interrupt_now()

    def take_interrupt(self) -> bool:
        flagged, self._interrupt = self._interrupt, False
        return flagged

    def drop_pending(self) -> None:
        """The agent finished before the interruption took effect: say so instead of losing the message silently."""
        self._interrupt = False
        while not self._messages.empty():
            self.event("log", f"message not delivered (the agent had already finished): {self._messages.get_nowait()}")

    async def next_instruction(self) -> str:
        if self._messages.empty():
            self.state = "waiting"
        text = await self._messages.get()
        self.state = "running"
        self.event("user", text)
        return text

    # ---- questions to the human ----------------------------------------------------------
    async def ask(self, kind: str, title: str, detail: dict) -> tuple[bool, str, bool]:
        """Blocks until the human decides. Returns (allowed, note, remember_for_run)."""
        assert self.run_id is not None
        approval_id = self.db.execute(
            "INSERT INTO approvals(run_id, kind, title, detail, created_at) VALUES(?, ?, ?, ?, ?)",
            (self.run_id, kind, title, dumps(detail), now()),
        )
        future: asyncio.Future = asyncio.get_running_loop().create_future()
        self._futures[approval_id] = future
        previous, self.state = self.state, "approval"
        self.event(kind, title, {"approval_id": approval_id, **detail})
        self.notify("autodev is waiting for you" if kind == "permission" else "autodev: your approval is needed", title)
        try:
            return await future
        finally:
            self.state = previous
            self._futures.pop(approval_id, None)
            self.db.execute("UPDATE approvals SET status = 'expired', decided_at = ? WHERE id = ? AND status = 'pending'", (now(), approval_id))

    def decide(self, approval_id: int, decision: str, note: str = "") -> bool:
        future = self._futures.get(approval_id)
        if future is None or future.done():
            return False
        allowed = decision in ("allow", "allow_run")
        self.db.execute(
            "UPDATE approvals SET status = ?, decided_at = ?, note = ? WHERE id = ?",
            ("allowed" if allowed else "denied", now(), note or None, approval_id),
        )
        self.event("decision", ("Allowed" if allowed else "Denied") + (f": {note}" if note else ""), {"approval_id": approval_id})
        future.set_result((allowed, note, decision == "allow_run"))
        return True

    async def can_use_tool(self, tool: str, tool_input: dict[str, Any], context: Any):
        dangerous = is_dangerous(tool, tool_input, self.cwd)
        if self.policy() == "trusted" and not dangerous:
            return PermissionResultAllow(updated_input=tool_input)
        if self.mode() == "auto":
            return PermissionResultDeny(message=DENIED_DANGEROUS if dangerous else DENIED_IN_AUTO)
        key = remember_key(tool, tool_input)
        if key in self._remembered and not dangerous:
            return PermissionResultAllow(updated_input=tool_input)
        title = getattr(context, "title", None) or describe_tool(tool, tool_input, self.cwd)
        allowed, note, remember = await self.ask(
            "permission", title, {"tool": tool, "input": json.loads(json.dumps(tool_input, default=str))}
        )
        if not allowed:
            return PermissionResultDeny(message=note or "Denied by the user.")
        if remember:
            self._remembered.add(key)
        return PermissionResultAllow(updated_input=tool_input)


async def checkpoint(enabled: list[str], name: str, title: str, detail: dict) -> tuple[bool, str]:
    """Waits for a human at a named point of the pipeline. Passes straight through when nobody can answer."""
    control = current_control.get()
    if control is None or name not in enabled or control.mode() == "auto":
        return True, ""
    allowed, note, _ = await control.ask("checkpoint", title, {"name": name, **detail})
    return allowed, note
