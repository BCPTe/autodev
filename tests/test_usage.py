import json
from types import SimpleNamespace

import pytest
from claude_agent_sdk import AssistantMessage, ClaudeAgentOptions, ResultMessage, TextBlock, ToolResultBlock, ToolUseBlock, UserMessage

from autodev import pipeline
from autodev.agents import learn, session, triage
from autodev.agents.fix import FixResult
from autodev.agents.session import isolation, run_session
from autodev.agents.usage import SessionUsage, last_session_id, usage_log
from autodev.db import Database
from autodev.jobs import RunSummary, run_tracked
from autodev.models import Comment, Status, Ticket
from tests.fixture_repo import PRICING_FIXED
from tests.test_review_feedback import REGRESSION_TEST, decisions, run  # noqa: F401
from tests.test_server import client, env, seed_run  # noqa: F401

USAGE = {"input_tokens": 4, "output_tokens": 300, "cache_read_input_tokens": 9000, "cache_creation_input_tokens": 1200}


def result(cost=0.25, sid="s1") -> ResultMessage:
    return ResultMessage(
        subtype="success", duration_ms=4000, duration_api_ms=3000, is_error=False, num_turns=3, session_id=sid,
        total_cost_usd=cost, usage=USAGE, structured_output={"ok": True}, permission_denials=[{"tool": "Bash"}],
    )


def conversation(sid="s1"):
    return [
        AssistantMessage(content=[TextBlock("looking"), ToolUseBlock("1", "Grep", {})], model="m"),
        UserMessage(content=[ToolResultBlock("1", "x" * 500)]),
        AssistantMessage(content=[ToolUseBlock("2", "Read", {}), ToolUseBlock("3", "Read", {})], model="m", usage={"input_tokens": 3, "cache_read_input_tokens": 120000, "cache_creation_input_tokens": 500}),
        UserMessage(content=[ToolResultBlock("2", [{"type": "text", "text": "y" * 7000}]), ToolResultBlock("3", "z")]),
        result(sid=sid),
    ]


@pytest.fixture
def fake_query(monkeypatch):
    seen = {}

    async def query(prompt, options):
        seen["options"] = options
        for m in conversation():
            yield m

    monkeypatch.setattr(session, "query", query)
    return seen


async def test_a_session_reports_tokens_cost_and_tool_calls_to_the_run_log(fake_query):
    log: list[SessionUsage] = []
    usage_log.set(log)
    await run_session("go", ClaudeAgentOptions(model="claude-haiku-5-5"), lambda m: None, "triage")
    [u] = log
    assert (u.stage, u.model, u.session_id, u.turns, u.cost_usd) == ("triage", "claude-haiku-5-5", "s1", 3, 0.25)
    assert (u.input, u.output, u.cache_read, u.cache_write) == (4, 300, 9000, 1200)
    assert u.tools == {"Grep": 1, "Read": 2} and u.tool_result_chars == 7501
    assert u.largest_result_chars == 7000 and u.denials == 1 and not u.resumed and u.peak_context == 120503
    assert last_session_id("triage") == "s1" and last_session_id("fix") is None


def test_unattended_sessions_do_not_load_the_users_connectors_or_memory():
    assert isolation()["strict_mcp_config"] is True
    assert isolation()["env"]["CLAUDE_CODE_DISABLE_AUTO_MEMORY"] == "1"
    assert isolation(user_mcp=True)["strict_mcp_config"] is False


async def test_every_agent_stage_passes_the_isolation_options(tmp_path, monkeypatch):
    from tests.test_knowledge import BASE, FakeSession, ticket

    fake = FakeSession({"verdict": "ready", "confidence": "high", "risk": "Low", "analysis": "a"})
    monkeypatch.setattr(triage, "run_session", fake)
    cfg = BASE.model_copy(deep=True)
    cfg.knowledge_path = str(tmp_path / "k.md")
    await triage._run(cfg, ticket(), "claude-haiku-5-5")
    assert fake.options.strict_mcp_config is True and fake.options.env["CLAUDE_CODE_DISABLE_AUTO_MEMORY"] == "1"
    cfg.agents["triage"].user_mcp = True
    await triage._run(cfg, ticket(), "claude-haiku-5-5")
    assert fake.options.strict_mcp_config is False


async def test_a_tracked_run_stores_its_sessions_and_a_failed_run_still_books_its_cost(tmp_path, fake_query):
    db = Database(tmp_path / "u.db")
    t = Ticket(id="t1", title="T", status=Status.NEW, area="Autofill")

    async def ok(report):
        await run_session("go", ClaudeAgentOptions(model="claude-haiku-5-5"), lambda m: None, "triage")
        return 1

    await run_tracked(db, project="p", ticket=t, kind="triage", work=ok, summarize=lambda r: RunSummary(outcome="analyzed", cost_usd=0.25), daily_cap_usd=10)
    row = db.one("SELECT * FROM runs")
    assert json.loads(row["usage"])[0]["cache_read"] == 9000 and row["turns"] == 3 and row["model"] == "claude-haiku-5-5"

    async def boom(report):
        await run_session("go", ClaudeAgentOptions(model="claude-sonnet-5-5"), lambda m: None, "fix")
        raise RuntimeError("verification exploded")

    with pytest.raises(RuntimeError):
        await run_tracked(db, project="p", ticket=t, kind="fix", work=boom, summarize=lambda r: RunSummary(), daily_cap_usd=10)
    failed = db.one("SELECT * FROM runs WHERE status = 'failed'")
    assert failed["cost_usd"] == pytest.approx(0.25) and failed["model"] == "claude-sonnet-5-5"


def test_costs_break_down_by_stage_model_area_and_outcome(client, env):
    c, (_, db, *_) = client, env
    sessions = [
        {"stage": "triage", "model": "claude-haiku-5-5", "turns": 5, "input": 10, "output": 100, "cache_read": 1000, "cache_write": 200, "cost_usd": 0.1, "peak_context": 30000},
        {"stage": "triage", "model": "claude-sonnet-5-5", "turns": 4, "input": 8, "output": 50, "cache_read": 500, "cache_write": 100, "cost_usd": 0.3, "peak_context": 130000},
    ]
    seed_run(db, cost_usd=0.4, kind="triage", area="Autofill", usage=json.dumps(sessions))
    seed_run(db, cost_usd=1.0, kind="fix", area="Autofill", outcome="escalated", model="claude-sonnet-5-5")
    seed_run(db, cost_usd=0.5, kind="fix", area="Autofill", outcome="review", model="claude-opus-5-5")
    body = c.get("/api/costs").json()
    rows = {(r["kind"], r["model"]): r for r in body["by_stage_model"]}
    assert rows[("triage", "claude-sonnet-5-5")]["long_context"] == 1 and rows[("triage", "claude-haiku-5-5")]["long_context"] == 0
    assert rows[("triage", "claude-haiku-5-5")]["cache_read"] == 1000 and rows[("triage", "claude-sonnet-5-5")]["cost"] == pytest.approx(0.3)
    assert rows[("fix", "claude-sonnet-5-5")]["untracked"] == 1 and rows[("fix", "claude-sonnet-5-5")]["cost"] == pytest.approx(1.0)
    fix_area = next(a for a in body["by_area"] if a["kind"] == "fix")
    assert fix_area["area"] == "Autofill" and fix_area["avg_cost"] == pytest.approx(0.75)
    assert {o["outcome"] for o in body["by_outcome"]["runs"] if o["kind"] == "fix"} == {"escalated", "review"}
    assert body["by_outcome"]["tickets"] == [{"outcome": "review", "tickets": 1, "cost": pytest.approx(1.9), "avg_cost": pytest.approx(1.9)}]
    run = c.get("/api/runs/1").json()["run"]
    assert run["sessions"][0]["cache_read"] == 1000 and "usage" not in run


# ---- the retrospective is not paid for when nothing happened ---------------------------------
def test_a_smooth_ticket_is_uneventful_and_comments_retries_or_notes_make_it_eventful():
    fix = {"kind": "fix"}
    bot, person = Comment(author="autodev", is_bot=True, text="Triage"), Comment(author="Ana", text="only SCIA counts")
    assert not learn.eventful([bot], [{"kind": "triage"}, fix], [{"status": "allowed", "note": None}])
    assert learn.eventful([bot, person], [fix], [])
    assert learn.eventful([bot], [fix, fix], [])
    assert learn.eventful([bot], [fix], [{"status": "denied", "note": None}])
    assert learn.eventful([bot], [fix], [{"status": "allowed", "note": "use the helper"}])


async def test_the_automatic_retrospective_skips_a_smooth_ticket_but_a_manual_one_runs(tmp_path, monkeypatch):
    calls = []

    async def fake_run_learn(cfg, evidence, current, report=None):
        calls.append(1)
        return learn.LearnResult(), 0.05, 2, "claude-haiku-5-5"

    class T:
        async def detail(self, ticket_id):
            t = Ticket(id="t1", title="T", status=Status.CLOSED)
            return t, [Comment(author="autodev", is_bot=True, text="Triage")]

    from tests.test_knowledge import BASE

    cfg = BASE.model_copy(deep=True)
    cfg.knowledge_path = str(tmp_path / "k.md")
    monkeypatch.setattr(learn, "run_learn", fake_run_learn)
    db = Database(tmp_path / "l.db")
    t = Ticket(id="t1", title="T", status=Status.CLOSED)
    out = await learn.learn_ticket(cfg, T(), db, "demo", t, skip_uneventful=True)
    assert out.skipped and calls == [] and out.cost_usd == 0
    out = await learn.learn_ticket(cfg, T(), db, "demo", t)
    assert not out.skipped and calls == [1]


# ---- retries can continue the previous session ------------------------------------------------
@pytest.mark.parametrize("enabled, expected", [(False, [None, None]), (True, [None, "s1"])])
async def test_a_retry_resumes_the_previous_fix_session_only_when_enabled(run, enabled, expected):  # noqa: F811
    cfg, ticket, tracker, calls, mp = run
    resumes = []

    async def fake_run_fix(cfg, ticket, ws, notes, previous_failure=None, resume=None, **kw):
        resumes.append(resume)
        usage_log.get().append(SessionUsage(stage="fix", model="m", session_id=f"s{len(resumes)}"))
        (ws.path / "shop" / "pricing.py").write_text(PRICING_FIXED)
        (ws.path / "tests" / "test_discount.py").write_text(REGRESSION_TEST)
        return FixResult(outcome="fixed", summary="done"), 0.1, 3

    mp.setattr(pipeline, "run_fix", fake_run_fix)
    usage_log.set([])
    cfg.agents["fix"].resume_retries = enabled
    decisions(mp, (True, ""), (False, "add a docstring"), (True, ""), (True, ""))
    await pipeline.fix_ticket(cfg, tracker, ticket)
    assert resumes == expected


# ---- a session that fails still costs money ---------------------------------------------------
async def test_a_cheap_triage_that_hits_the_turn_cap_is_booked_before_the_next_model_starts(monkeypatch):
    from tests.test_knowledge import BASE, ticket

    answers = iter([
        SimpleNamespace(is_error=True, structured_output=None, total_cost_usd=0.4, num_turns=15, subtype="error_max_turns", errors=["Reached maximum number of turns (15)"], result=""),
        SimpleNamespace(is_error=False, structured_output={"verdict": "ready", "confidence": "high", "risk": "Low", "analysis": "a"}, total_cost_usd=0.9, num_turns=9, subtype="", errors=None, result=""),
    ])

    async def session(prompt, options, on_message, stage="agent"):
        return next(answers)

    monkeypatch.setattr(triage, "run_session", session)
    cfg = BASE.model_copy(deep=True)
    _, runs = await triage.run_triage(cfg, ticket(), budget_usd=5)
    assert [(r.model, r.failed, r.cost_usd) for r in runs] == [("claude-haiku-5-5", True, 0.4), ("claude-sonnet-5-5", False, 0.9)]
    from autodev.pipeline import format_comment

    assert "failed" in format_comment(triage.TriageResult(verdict="ready", confidence="high", risk="Low", analysis="a"), "Low", runs)
