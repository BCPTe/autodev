"""Desktop notifications for things that need a human (a request, a finished or failed run).

The server runs on the user's machine, so it can use the desktop's own notifier even when the
dashboard tab is closed. The command is configurable (`autonomy.notify_command`, with {title} and
{body} placeholders); by default `notify-send` is used when it exists.
"""
import shutil
import subprocess

DEFAULT_COMMAND = ["notify-send", "--app-name=autodev", "{title}", "{body}"]


def resolve_command(configured: list[str] | None) -> list[str] | None:
    if configured:
        return configured
    return DEFAULT_COMMAND if shutil.which(DEFAULT_COMMAND[0]) else None


def spawn(cmd: list[str]) -> None:
    subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL)


def send(command: list[str] | None, title: str, body: str) -> bool:
    """Fire and forget; a missing or failing notifier must never disturb a run."""
    if not command:
        return False
    try:
        spawn([part.replace("{title}", title).replace("{body}", body) for part in command])
    except OSError:
        return False
    return True
