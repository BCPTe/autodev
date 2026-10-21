from pathlib import Path

import pytest

from autodev.agents import triage
from autodev.agents.triage import RunInfo, TriageResult, run_triage
from autodev.config import load_project
from autodev.models import Status, Ticket
from autodev.pipeline import prefilter

CFG = load_project(Path(__file__).parent.parent / "projects" / "demo.yaml")


def _ticket(body: str) -> Ticket:
    return Ticket(id="t1", title="x", status=Status.NEW, body=body)


def _result(confidence: str) -> TriageResult:
    return TriageResult(verdict="ready", confidence=confidence, risk="Basso", analysis="a")


def test_prefilter_rejects_short_body():
    assert prefilter(CFG, _ticket("non va")) is not None
    assert prefilter(CFG, _ticket("x" * 100)) is None


def test_area_map_loaded_into_config():
    assert "Export PDF" in CFG.area_map_text


async def test_cascade_stops_at_haiku_when_confident(monkeypatch):
    calls = []

    async def fake(cfg, ticket, model, progress=None, budget=None):
        calls.append(model)
        return _result("high"), RunInfo(model, 0.05, 4)

    monkeypatch.setattr(triage, "_run", fake)
    _, runs = await run_triage(CFG, _ticket("x" * 100))
    assert calls == ["claude-haiku-5-5"]
    assert not runs[0].escalated


async def test_cascade_escalates_on_low_confidence(monkeypatch):
    async def fake(cfg, ticket, model, progress=None, budget=None):
        return _result("low" if "haiku" in model else "high"), RunInfo(model, 0.1, 5)

    monkeypatch.setattr(triage, "_run", fake)
    result, runs = await run_triage(CFG, _ticket("x" * 100))
    assert [r.model for r in runs] == ["claude-haiku-5-5", "claude-sonnet-5-5"]
    assert runs[1].escalated and result.confidence == "high"


async def test_cascade_raises_when_all_models_fail(monkeypatch):
    async def fake(cfg, ticket, model, progress=None, budget=None):
        raise RuntimeError("boom")

    monkeypatch.setattr(triage, "_run", fake)
    with pytest.raises(RuntimeError):
        await run_triage(CFG, _ticket("x" * 100))


async def test_cascade_reports_progress_lines(monkeypatch):
    async def fake(cfg, ticket, model, progress=None, budget=None):
        return _result("low" if "haiku" in model else "high"), RunInfo(model, 0.1, 5)

    monkeypatch.setattr(triage, "_run", fake)
    lines: list[str] = []
    await run_triage(CFG, _ticket("x" * 100), report=lines.append)
    assert any("avvio analisi" in l for l in lines)
    assert any("confidenza bassa, passo al modello successivo" in l for l in lines)
    assert sum("fine: ready" in l for l in lines) == 2


def test_follow_up_comments_reach_the_triage_prompt():
    from autodev.agents.triage import _prompt

    t = _ticket("x" * 100)
    t.comments = ["Solo scia_sue_calabria", "Entrambi obbligatori"]
    prompt = _prompt(t)
    assert "- Solo scia_sue_calabria" in prompt and "- Entrambi obbligatori" in prompt


def test_ready_verdict_never_carries_open_questions():
    from autodev.agents.triage import normalize
    from autodev.pipeline import format_comment

    raw = TriageResult(
        verdict="ready", confidence="high", risk="Basso", analysis="a",
        questions=["Confermi X?"], assumptions=["Y"],
    )
    fixed = normalize(raw)
    assert fixed.questions == [] and fixed.assumptions == ["Y", "Confermi X?"]
    comment = format_comment(fixed, "Basso", [])
    assert "Domande" not in comment
    assert "Assunzioni da confermare in review (non bloccanti):" in comment and "- Confermi X?" in comment


def test_needs_info_keeps_its_questions():
    from autodev.agents.triage import normalize

    raw = TriageResult(verdict="needs_info", confidence="high", risk="Basso", analysis="a", questions=["Quale file?"])
    assert normalize(raw).questions == ["Quale file?"]
