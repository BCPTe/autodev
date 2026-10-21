"""End-to-end run of the fix stage with a real agent on a tiny fixture project.

Costs real usage, so it only runs when RUN_AGENT_TESTS=1.
"""
import os

import pytest

from autodev.models import Status, Ticket
from autodev.pipeline import fix_ticket
from autodev.sandbox import workspace as wsmod

from tests.fixture_repo import make_project

pytestmark = pytest.mark.skipif(os.environ.get("RUN_AGENT_TESTS") != "1", reason="set RUN_AGENT_TESTS=1")


class FakeTracker:
    def __init__(self):
        self.statuses: list[Status] = []
        self.comments: list[str] = []
        self.fields: dict = {}

    async def bot_comments(self, ticket_id):
        return ["Triage: ready. Probabile causa: apply_discount in shop/pricing.py sottrae la percentuale invece di applicarla."]

    async def set_status(self, ticket_id, status):
        self.statuses.append(status)

    async def comment(self, ticket_id, text):
        self.comments.append(text)

    async def update(self, ticket_id, **kw):
        self.fields.update({k: v for k, v in kw.items() if v is not None})


async def test_agent_fixes_the_bug_with_a_failing_test_first(tmp_path, monkeypatch):
    monkeypatch.setattr(wsmod, "WORKSPACES", tmp_path / "workspaces")
    cfg = make_project(tmp_path)
    ticket = Ticket(
        id="abcdef12-1111-2222-3333-444444444444",
        title="The discount calculation is wrong",
        status=Status.IN_PROGRESS,
        kind="Bug",
        body="apply_discount(200, 25) returns 175 instead of 150: a 25% discount on 200 must give 150.",
    )
    tracker = FakeTracker()

    outcome = await fix_ticket(cfg, tracker, ticket)

    print("COST", outcome.cost_usd, [c.line() for c in outcome.checks], outcome.message)
    assert outcome.status == Status.REVIEW, tracker.comments
    assert all(c.ok for c in outcome.checks)
    assert any(c.name == "regression test" and c.ok for c in outcome.checks)
    assert tracker.fields["verification"] == "Passed"
