import os
import time
from typing import Any, Callable

Report = Callable[[str], None]


def describe_tool(name: str, tool_input: dict[str, Any], cwd: str) -> str:
    def rel(path: str) -> str:
        return os.path.relpath(path, cwd) if os.path.isabs(path) and path.startswith(cwd) else path

    if name == "Read":
        return f"reads {rel(tool_input.get('file_path', '?'))}"
    if name == "Grep":
        where = tool_input.get("path")
        return f"searches '{tool_input.get('pattern', '?')}'" + (f" in {rel(where)}" if where else "")
    if name == "Glob":
        return f"lists {tool_input.get('pattern', '?')}"
    if name in ("Edit", "Write"):
        verb = "edits" if name == "Edit" else "writes"
        return f"{verb} {rel(tool_input.get('file_path', '?'))}"
    if name == "Bash":
        cmd = " ".join(str(tool_input.get("command", "?")).split())
        return f"runs {cmd[:90]}"
    return name


class Progress:
    """One-line-per-action live view of an agent run, sent to ``emit`` (e.g. print)."""

    def __init__(self, label: str, emit: Report):
        self._label = label
        self._emit = emit
        self._start = time.monotonic()
        self.turns = 0

    def __call__(self, line: str) -> None:
        elapsed = int(time.monotonic() - self._start)
        self._emit(f"[{elapsed // 60}:{elapsed % 60:02d}] {self._label}: {line}")

    def tool(self, name: str, tool_input: dict[str, Any], cwd: str) -> None:
        self.turns += 1
        self(f"{self.turns:>2}. {describe_tool(name, tool_input, cwd)}")
