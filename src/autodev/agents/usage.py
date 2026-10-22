"""What every agent session consumed: tokens by kind, cost, and which tools it called.

`run_session` appends one `SessionUsage` per session to the log of the tracked run it belongs to
(`usage_log`), so a run that chains several sessions (triage cascade, fix attempts) reports each one
and a run that fails halfway still books what it spent.
"""
from collections import Counter
from contextvars import ContextVar
from dataclasses import asdict, dataclass, field
from typing import Any

from claude_agent_sdk import AssistantMessage, ResultMessage, ToolResultBlock, ToolUseBlock, UserMessage


@dataclass
class SessionUsage:
    stage: str
    model: str
    session_id: str = ""
    turns: int = 0
    input: int = 0
    output: int = 0
    cache_read: int = 0
    cache_write: int = 0
    cost_usd: float = 0.0
    duration_s: float = 0.0
    tools: dict[str, int] = field(default_factory=dict)
    tool_result_chars: int = 0
    largest_result_chars: int = 0
    peak_context: int = 0
    denials: int = 0
    resumed: bool = False
    error: bool = False

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


usage_log: ContextVar[list[SessionUsage] | None] = ContextVar("usage_log", default=None)


class Meter:
    """Counts the tool calls and tool output sizes seen while a session streams."""

    def __init__(self) -> None:
        self.tools: Counter[str] = Counter()
        self.chars = 0
        self.largest = 0
        self.peak = 0

    def feed(self, message: Any) -> None:
        if isinstance(message, AssistantMessage):
            for block in message.content:
                if isinstance(block, ToolUseBlock):
                    self.tools[block.name] += 1
            u = message.usage or {}
            self.peak = max(self.peak, sum(u.get(k, 0) or 0 for k in ("input_tokens", "cache_read_input_tokens", "cache_creation_input_tokens")))
        elif isinstance(message, UserMessage) and isinstance(message.content, list):
            for block in message.content:
                if isinstance(block, ToolResultBlock):
                    n = _size(block.content)
                    self.chars += n
                    self.largest = max(self.largest, n)


def _size(content: Any) -> int:
    if isinstance(content, str):
        return len(content)
    if isinstance(content, list):
        return sum(len(str(part.get("text", ""))) if isinstance(part, dict) else 0 for part in content)
    return 0


def from_result(stage: str, model: str, result: ResultMessage, meter: Meter, resumed: bool = False) -> SessionUsage:
    u = result.usage or {}
    return SessionUsage(
        stage=stage, model=model, session_id=result.session_id or "", turns=result.num_turns or 0,
        input=u.get("input_tokens", 0) or 0, output=u.get("output_tokens", 0) or 0,
        cache_read=u.get("cache_read_input_tokens", 0) or 0, cache_write=u.get("cache_creation_input_tokens", 0) or 0,
        cost_usd=result.total_cost_usd or 0.0, duration_s=round((result.duration_ms or 0) / 1000, 1),
        tools=dict(meter.tools), tool_result_chars=meter.chars, largest_result_chars=meter.largest, peak_context=meter.peak,
        denials=len(result.permission_denials or []), resumed=resumed, error=bool(result.is_error),
    )


def record(session: SessionUsage) -> None:
    log = usage_log.get()
    if log is not None:
        log.append(session)


def last_session_id(stage: str) -> str | None:
    log = usage_log.get() or []
    return next((s.session_id for s in reversed(log) if s.stage == stage and s.session_id), None)


def total(sessions: list[SessionUsage]) -> float:
    return sum(s.cost_usd for s in sessions)
