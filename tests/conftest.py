import pytest

from autodev import engine as engine_mod
from autodev import notify
from autodev.agents.learn import LearnOutcome


@pytest.fixture(autouse=True)
def desktop_notifications(monkeypatch):
    """No test may pop up a real desktop notification; the commands that would have run are collected."""
    sent: list[list[str]] = []
    monkeypatch.setattr(notify, "spawn", sent.append)
    monkeypatch.setattr(notify, "resolve_command", lambda configured: configured or notify.DEFAULT_COMMAND)
    return sent


@pytest.fixture(autouse=True)
def no_real_retrospective(monkeypatch):
    """The retrospective agent never runs for real in tests; the tickets it was asked about are collected."""
    asked: list[str] = []

    async def fake(cfg, tracker, db, project, ticket, report=None):
        asked.append(ticket.id)
        return LearnOutcome()

    monkeypatch.setattr(engine_mod, "learn_ticket", fake)
    return asked
