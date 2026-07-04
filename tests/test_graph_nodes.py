"""Tests for the main-pipeline LangGraph nodes and orchestrator auto-resume.

Covers the batch-pipeline bug fixes:
- crawler construction driven by Dashboard source toggles + credentials
- RawDemand dataclass serialisation (dataclasses.asdict, not model_dump)
- node_process reconstructing RawDemand and calling DemandProcessor.extract
- analyse_competition heuristic stub
- decide thresholds resolved through settings_store
- run_pipeline auto-resuming past the fan_out_approved interrupt
"""

from __future__ import annotations

import dataclasses
from contextlib import asynccontextmanager
from typing import Any, Dict, List

import pytest

from zerodev.crawler.base import RawDemand
from zerodev.crawler.producthunt import ProductHuntCrawler
from zerodev.crawler.reddit import RedditCrawler
from zerodev.evaluator.competition import CompetitionResult, analyse_competition
from zerodev.evaluator.feasibility import FeasibilityResult
from zerodev.pipeline import graph as graph_mod


def _raw(title: str = "Idea", **overrides: Any) -> Dict[str, Any]:
    demand = RawDemand(
        title=title,
        body="body text",
        source="reddit",
        source_url="https://reddit.com/x",
    )
    data = dataclasses.asdict(demand)
    data.update(overrides)
    return data


# ── analyse_competition ───────────────────────────────────────────


async def test_analyse_competition_returns_neutral_placeholder():
    result = await analyse_competition({"title": "Pomodoro Timer"})
    assert isinstance(result, CompetitionResult)
    assert result.competition_score == 0.5
    assert result.notes  # explains it is a placeholder
    # Must serialise as a dataclass (graph nodes rely on asdict).
    data = dataclasses.asdict(result)
    assert data["competition_score"] == 0.5


# ── _build_crawlers ───────────────────────────────────────────────


def test_build_crawlers_all_sources_disabled(monkeypatch):
    monkeypatch.setattr(
        "zerodev.settings_store.load_dashboard_settings",
        lambda: {"enabledSources": {"reddit": False, "producthunt": False}},
    )
    assert graph_mod._build_crawlers() == []


def test_build_crawlers_reddit_skipped_without_credentials(monkeypatch):
    monkeypatch.setattr(
        "zerodev.settings_store.load_dashboard_settings",
        lambda: {"enabledSources": {"reddit": True, "producthunt": False}},
    )
    settings = graph_mod.get_settings()
    monkeypatch.setattr(settings, "reddit_client_id", "")
    monkeypatch.setattr(settings, "reddit_client_secret", "")

    assert graph_mod._build_crawlers() == []


def test_build_crawlers_reddit_uses_dashboard_credentials(monkeypatch):
    monkeypatch.setattr(
        "zerodev.settings_store.load_dashboard_settings",
        lambda: {
            "enabledSources": {"reddit": True, "producthunt": False},
            "redditClientId": "dash-id",
            "redditClientSecret": "dash-secret",
        },
    )
    crawlers = graph_mod._build_crawlers()
    assert len(crawlers) == 1
    assert isinstance(crawlers[0], RedditCrawler)
    assert crawlers[0]._client_id == "dash-id"
    assert crawlers[0]._client_secret == "dash-secret"


def test_build_crawlers_includes_producthunt_stub_when_enabled(monkeypatch):
    monkeypatch.setattr(
        "zerodev.settings_store.load_dashboard_settings",
        lambda: {"enabledSources": {"reddit": False, "producthunt": True}},
    )
    crawlers = graph_mod._build_crawlers()
    assert len(crawlers) == 1
    assert isinstance(crawlers[0], ProductHuntCrawler)


# ── node_crawl ────────────────────────────────────────────────────


class _FakeCrawler:
    async def crawl(self, limit: int = 50) -> List[RawDemand]:
        return [
            RawDemand(
                title="Habit tracker",
                body="I wish there was a simple habit tracker.",
                source="reddit",
                source_url="https://reddit.com/r/AppIdeas/1",
                upvotes=42,
            )
        ]

    def source_name(self) -> str:
        return "fake"


async def test_node_crawl_serialises_dataclasses_and_skips_stubs(monkeypatch):
    # A working crawler plus the NotImplementedError stub: the stub must be
    # skipped quietly without failing the node or triggering retries.
    monkeypatch.setattr(
        graph_mod, "_build_crawlers", lambda: [_FakeCrawler(), ProductHuntCrawler()]
    )

    result = await graph_mod.node_crawl({})

    assert result["demands_crawled_count"] == 1
    assert result["stage"] == "crawl"
    demand = result["demands_raw"][0]
    assert isinstance(demand, dict)
    assert demand["title"] == "Habit tracker"
    assert demand["upvotes"] == 42


# ── node_process ──────────────────────────────────────────────────


class _FakeProcessor:
    """Stands in for DemandProcessor: asserts it receives RawDemand objects."""

    def __init__(self) -> None:
        pass

    async def extract(self, raw: RawDemand) -> Dict[str, Any] | None:
        assert isinstance(raw, RawDemand)
        if raw.title == "not-an-idea":
            return None
        if raw.title == "boom":
            raise RuntimeError("LLM exploded")
        return {"title": raw.title, "description": raw.body, "source": raw.source}


async def test_node_process_reconstructs_rawdemand_and_filters(monkeypatch):
    monkeypatch.setattr("zerodev.crawler.processor.DemandProcessor", _FakeProcessor)

    state = {
        "demands_raw": [
            _raw("Good idea", unknown_extra_key="ignored"),  # extra keys filtered
            _raw("not-an-idea"),  # extract returns None -> skipped
            _raw("boom"),  # extract raises -> logged, skipped
        ]
    }
    result = await graph_mod.node_process(state)

    structured = result["demands_structured"]
    assert len(structured) == 1
    assert structured[0]["title"] == "Good idea"
    assert structured[0]["id"]  # id assigned for downstream nodes
    assert result["stage"] == "process"


# ── node_evaluate_batch ───────────────────────────────────────────


async def test_node_evaluate_batch_serialises_dataclass_results(monkeypatch):
    async def fake_feasibility(demand: Dict[str, Any]) -> FeasibilityResult:
        return FeasibilityResult(
            feasible=True,
            complexity="low",
            page_count=3,
            needs_backend=False,
            needs_hardware=False,
            needs_login=False,
            reasoning="simple",
        )

    monkeypatch.setattr(
        "zerodev.evaluator.feasibility.evaluate_feasibility", fake_feasibility
    )

    state = {"demands_structured": [{"id": "d1", "title": "Timer"}]}
    result = await graph_mod.node_evaluate_batch(state)

    assert len(result["demands_evaluated"]) == 1
    evaluation = result["demands_evaluated"][0]["evaluation"]
    assert evaluation["feasibility"]["feasible"] is True
    assert evaluation["competition"]["competition_score"] == 0.5
    assert result["errors"] == []


# ── node_decide_batch ─────────────────────────────────────────────


async def test_node_decide_batch_reads_dashboard_approve_threshold(monkeypatch):
    calls: List[Any] = []

    def fake_effective_float(file_key: str, env_value: float, *, minimum=None) -> float:
        calls.append((file_key, env_value))
        return 0.9

    monkeypatch.setattr("zerodev.settings_store.effective_float", fake_effective_float)

    demand = {
        "id": "d1",
        "evaluation": {
            "feasibility": {"feasible": True, "complexity": "low", "needs_backend": False},
            "competition": {"competition_score": 0.5},
        },
    }
    result = await graph_mod.node_decide_batch({"demands_evaluated": [demand]})

    settings = graph_mod.get_settings()
    assert ("autoApproveThreshold", settings.pipeline_auto_approve_threshold) in calls
    # score = 0.5 * 0.7 + 0.3 = 0.65 -> below approve(0.9), above reject -> review/approved
    assert result["demands_approved_count"] == 1
    assert result["demands_rejected_count"] == 0


async def test_node_decide_batch_rejects_infeasible():
    demand = {
        "id": "d2",
        "evaluation": {
            "feasibility": {"feasible": False, "complexity": "high"},
            "competition": {"competition_score": 0.5},
        },
    }
    result = await graph_mod.node_decide_batch({"demands_evaluated": [demand]})
    assert result["demands_approved_count"] == 0
    assert result["demands_rejected_count"] == 1


# ── orchestrator: auto-resume past the interrupt ──────────────────


class _FakeSnapshot:
    def __init__(self, next_steps: tuple) -> None:
        self.next = next_steps


class _FakeGraph:
    """Simulates a compiled graph with interrupt_before=['fan_out_approved']."""

    def __init__(self) -> None:
        self.invocations: List[Any] = []
        self._paused = False

    async def ainvoke(self, initial_input: Any, config: Any = None) -> Dict[str, Any]:
        self.invocations.append(initial_input)
        if initial_input is not None:
            self._paused = True  # first invoke stops at the interrupt
            return {"stage": "decide", "demands_approved_count": 2}
        self._paused = False  # resume completes the run
        return {
            "stage": "done",
            "demands_approved_count": 2,
            "demands_built_count": 2,
            "demands_published_count": 1,
        }

    async def aget_state(self, config: Any) -> _FakeSnapshot:
        return _FakeSnapshot(("fan_out_approved",) if self._paused else ())


@pytest.fixture
def orchestrator_with_fake_graph(monkeypatch):
    from zerodev.pipeline import orchestrator

    fake = _FakeGraph()

    @asynccontextmanager
    async def fake_checkpointer():
        yield None

    async def no_persist(summary) -> None:
        return None

    monkeypatch.setattr(orchestrator, "get_checkpointer", fake_checkpointer)
    monkeypatch.setattr(orchestrator, "build_main_graph", lambda checkpointer=None: fake)
    monkeypatch.setattr(orchestrator, "_persist_run", no_persist)
    return orchestrator, fake


async def test_run_pipeline_auto_resumes_interrupt(orchestrator_with_fake_graph):
    orchestrator, fake = orchestrator_with_fake_graph

    summary = await orchestrator.run_pipeline()

    # Two invocations: the initial run, then the automatic resume (None input).
    assert len(fake.invocations) == 2
    assert fake.invocations[1] is None
    assert summary.demands_built == 2
    assert summary.demands_published == 1
    assert summary.final_state["stage"] == "done"


async def test_run_pipeline_human_review_keeps_pause(orchestrator_with_fake_graph):
    orchestrator, fake = orchestrator_with_fake_graph

    summary = await orchestrator.run_pipeline(human_review=True)

    # Only the initial invocation; the run stays paused for manual review.
    assert fake.invocations == [fake.invocations[0]]
    assert fake.invocations[0] is not None
    assert summary.demands_built == 0
    assert summary.final_state["stage"] == "decide"
