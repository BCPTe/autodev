from pathlib import Path

import pytest

from autodev.agents.fix import pick_model
from autodev.config import load_project
from autodev.models import Status, Ticket

CFG = load_project(Path(__file__).parent.parent / "projects" / "demo.yaml")


def ticket(model):
    return Ticket(id="t", title="x", status=Status.IN_PROGRESS, model=model)


@pytest.mark.parametrize("label,expected", [
    ("Haiku", "claude-haiku-5-5"), ("Sonnet", "claude-sonnet-5-5"),
    ("Opus", "claude-opus-5-5"), ("Fable", "claude-fable-5-1"),
])
def test_explicit_choice_wins_on_every_attempt(label, expected):
    assert [pick_model(CFG, ticket(label), a) for a in (1, 2, 3)] == [expected] * 3


@pytest.mark.parametrize("label", [None, "Auto"])
def test_auto_starts_cheap_and_escalates_on_retry(label):
    assert [pick_model(CFG, ticket(label), a) for a in (1, 2, 3)] == [
        "claude-sonnet-5-5", "claude-opus-5-5", "claude-opus-5-5",
    ]


def test_unknown_choice_is_an_error_not_a_silent_default():
    with pytest.raises(RuntimeError, match="unknown model choice"):
        pick_model(CFG, ticket("Gemini"), 1)


def test_progress_describes_tool_calls_compactly():
    from autodev.progress import describe_tool

    cwd = "/work/repo"
    assert describe_tool("Read", {"file_path": "/work/repo/app/x.py"}, cwd) == "reads app/x.py"
    assert describe_tool("Grep", {"pattern": "required", "path": "/work/repo/app"}, cwd) == "searches 'required' in app"
    assert describe_tool("Bash", {"command": "pytest   -q\n tests/"}, cwd) == "runs pytest -q tests/"
    assert describe_tool("Weird", {}, cwd) == "Weird"


async def test_triage_runs_do_not_consume_fix_attempts(monkeypatch):
    from autodev import pipeline
    from autodev.agents.triage import RunInfo, TriageResult

    async def fake_run_triage(cfg, ticket, report=None, budget_usd=None):
        return TriageResult(verdict="ready", confidence="high", risk="Low", analysis="a"), [RunInfo("m", 0.2, 3)]

    monkeypatch.setattr(pipeline, "run_triage", fake_run_triage)

    class T:
        updates: list = []

        async def comment(self, *a): ...
        async def set_status(self, *a): ...
        async def update(self, ticket_id, **kw):
            self.updates.append(kw)

    t = T()
    ticket = Ticket(id="t", title="x", status=Status.NEW, body="x" * 100, attempts=2, cost_usd=0.5)
    await pipeline.triage_ticket(CFG, t, ticket)
    assert all("attempts" not in u for u in t.updates)
    assert t.updates[-1]["cost_usd"] == pytest.approx(0.7)


def test_budget_is_cumulative_over_everything_booked_on_the_ticket():
    from autodev.pipeline import budget_message, remaining_budget

    assert CFG.limits.budget_usd_per_ticket == 6.0
    t = Ticket(id="t", title="x", status=Status.IN_PROGRESS, cost_usd=2.5)
    assert remaining_budget(CFG, t) == pytest.approx(3.5)
    assert remaining_budget(CFG, t, spent_now=1.0) == pytest.approx(2.5)
    assert "$3.50 of $6.00" in budget_message(CFG, t, spent_now=1.0)


async def test_exhausted_budget_stops_before_any_agent_runs(monkeypatch):
    from autodev import pipeline

    async def boom(*a, **k):
        raise AssertionError("agent must not run")

    monkeypatch.setattr(pipeline, "run_triage", boom)

    class T:
        notes: list = []
        status = None

        async def comment(self, *a): ...
        async def set_status(self, _id, status):
            self.status = status
        async def update(self, _id, **kw):
            self.notes.append(kw)

    t = T()
    ticket = Ticket(id="t", title="x", status=Status.NEW, body="x" * 100, cost_usd=5.9)
    status, runs, comment = await pipeline.triage_ticket(CFG, t, ticket)
    assert status == Status.ESCALATED and runs == [] and "spending cap" in comment
    assert t.status == Status.ESCALATED
