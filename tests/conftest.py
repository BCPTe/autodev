import pytest

from autodev import notify


@pytest.fixture(autouse=True)
def desktop_notifications(monkeypatch):
    """No test may pop up a real desktop notification; the commands that would have run are collected."""
    sent: list[list[str]] = []
    monkeypatch.setattr(notify, "spawn", sent.append)
    monkeypatch.setattr(notify, "resolve_command", lambda configured: configured or notify.DEFAULT_COMMAND)
    return sent
