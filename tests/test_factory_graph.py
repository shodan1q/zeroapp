"""Tests for the LangGraph batch factory: fan-out, supervision and rework."""

from __future__ import annotations

import asyncio

import pytest

from zerodev.pipeline import factory_graph
from zerodev.pipeline.factory_graph import (
    after_supervise,
    build_factory_graph,
    fan_out,
    node_intake,
    node_supervise,
    run_factory_batch,
)
from zerodev.pipeline.quality import ACCEPT, REJECT, REWORK

BRIEFS = [
    {"app_name": "工具", "description": "d", "slug": "tool"},
    {"app_name": "内容", "description": "d", "slug": "content"},
    {"app_name": "互动", "description": "d", "slug": "play"},
]


class _FakeResult:
    def __init__(self, name: str, slug: str, metrics: dict, hap: str = "", error: str = "") -> None:
        self.metrics = metrics
        self.hap_path = hap
        # The real result always carries this; the supervisor reads it to tell a
        # generation failure apart from a merely thin app.
        self.error = error
        self._name = name
        self._slug = slug

    def to_dict(self) -> dict:
        return {"app_name": self._name, "slug": self._slug, "success": True, "metrics": self.metrics}


GOOD = {"views": 6, "features": 12, "charts": 4, "records": 120, "collections": 4, "runtime_ok": True}
THIN = {"views": 2, "features": 2, "charts": 0, "records": 8, "collections": 1, "runtime_ok": True}
BROKEN = {"views": 6, "features": 12, "charts": 4, "records": 120, "collections": 4, "runtime_ok": False}


def _install_builder(monkeypatch, metrics_by_name, tracker=None):
    async def _create(request, **kwargs):
        if tracker is not None:
            tracker["live"] += 1
            tracker["peak"] = max(tracker["peak"], tracker["live"])
            await asyncio.sleep(0.02)
            tracker["live"] -= 1
        metrics = metrics_by_name.get(request.app_name, GOOD)
        return _FakeResult(request.app_name, request.resolved_slug(), metrics, hap="/tmp/x.hap")

    monkeypatch.setattr(factory_graph, "create_webview_app", _create)


# ── Fan-out ─────────────────────────────────────────────────────


def test_fan_out_emits_one_branch_per_app() -> None:
    sends = fan_out({"pending": BRIEFS, "round": 1, "build": True})
    assert len(sends) == 3
    assert {s.node for s in sends} == {"build_app"}
    assert [s.arg["brief"]["app_name"] for s in sends] == ["工具", "内容", "互动"]


def test_fan_out_is_empty_when_nothing_pending() -> None:
    assert fan_out({"pending": []}) == []


def test_intake_rejects_an_empty_batch() -> None:
    with pytest.raises(ValueError, match="no usable briefs"):
        asyncio.run(node_intake({"briefs": []}))


def test_intake_drops_briefs_without_a_name() -> None:
    state = asyncio.run(node_intake({"briefs": [{"description": "x"}, BRIEFS[0]]}))
    assert [b["app_name"] for b in state["briefs"]] == ["工具"]


# ── Concurrency ─────────────────────────────────────────────────


def test_apps_are_built_concurrently(monkeypatch: pytest.MonkeyPatch) -> None:
    tracker = {"live": 0, "peak": 0}
    _install_builder(monkeypatch, {}, tracker)
    asyncio.run(run_factory_batch(BRIEFS, build=True, checkpointer=False))
    # Serial execution would never show more than one branch in flight.
    assert tracker["peak"] > 1


def test_concurrency_limit_is_respected(monkeypatch: pytest.MonkeyPatch) -> None:
    tracker = {"live": 0, "peak": 0}
    _install_builder(monkeypatch, {}, tracker)
    asyncio.run(run_factory_batch(BRIEFS, build=True, concurrency=1, checkpointer=False))
    assert tracker["peak"] == 1


# ── Supervision ─────────────────────────────────────────────────


def test_good_apps_are_accepted(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_builder(monkeypatch, {})
    report = asyncio.run(run_factory_batch(BRIEFS, build=True, checkpointer=False))
    assert report["accepted"] == 3
    assert report["rejected"] == 0
    assert all(a["verdict"] == ACCEPT for a in report["apps"])


def test_a_thin_app_is_reworked_then_filed(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_builder(monkeypatch, {"内容": THIN})
    report = asyncio.run(run_factory_batch(BRIEFS, build=True, max_rounds=2, checkpointer=False))
    # It stays thin on the retry, so it ends up rejected rather than shipped.
    assert report["attempts"] > len(BRIEFS)
    thin = next(a for a in report["apps"] if a["app_name"] == "内容")
    assert thin["verdict"] in (REWORK, REJECT)


def test_rework_is_bounded(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_builder(monkeypatch, dict.fromkeys(["工具", "内容", "互动"], THIN))
    report = asyncio.run(run_factory_batch(BRIEFS, build=True, max_rounds=2, checkpointer=False))
    # 3 apps x at most 2 rounds; the loop must terminate rather than spin.
    assert report["attempts"] <= len(BRIEFS) * 2
    assert report["accepted"] + report["rejected"] == len(BRIEFS)


def test_a_broken_app_never_gets_accepted(monkeypatch: pytest.MonkeyPatch) -> None:
    # Failing the runtime gate is disqualifying however rich the content is.
    _install_builder(monkeypatch, {"工具": BROKEN})
    report = asyncio.run(run_factory_batch(BRIEFS, build=True, max_rounds=1, checkpointer=False))
    broken = next(a for a in report["apps"] if a["app_name"] == "工具")
    assert broken["verdict"] != ACCEPT


def test_one_crashing_app_does_not_kill_the_batch(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _create(request, **kwargs):
        if request.app_name == "内容":
            raise RuntimeError("provider exploded")
        return _FakeResult(request.app_name, request.resolved_slug(), GOOD, hap="/tmp/x.hap")

    monkeypatch.setattr(factory_graph, "create_webview_app", _create)
    report = asyncio.run(run_factory_batch(BRIEFS, build=True, max_rounds=1, checkpointer=False))

    assert report["accepted"] == 2
    crashed = next(a for a in report["apps"] if a["app_name"] == "内容")
    assert crashed["verdict"] == REJECT
    assert "provider exploded" in crashed["error"]


# ── Routing ─────────────────────────────────────────────────────


def test_supervise_routes_back_only_while_work_remains() -> None:
    assert after_supervise({"pending": [BRIEFS[0]], "round": 2, "max_rounds": 2}) == "rework"
    assert after_supervise({"pending": [], "round": 2, "max_rounds": 2}) == "report"
    assert after_supervise({"pending": [BRIEFS[0]], "round": 3, "max_rounds": 2}) == "report"


def test_supervise_files_each_verdict() -> None:
    results = [
        {"app_name": "a", "round": 1, "score": {"verdict": ACCEPT}, "brief": {}},
        {"app_name": "b", "round": 1, "score": {"verdict": REWORK, "reasons": []}, "brief": BRIEFS[0]},
        {"app_name": "c", "round": 1, "score": {"verdict": REJECT, "reasons": []}, "brief": {}},
    ]
    out = asyncio.run(node_supervise({"results": results, "round": 1, "max_rounds": 2}))
    assert [a["app_name"] for a in out["accepted"]] == ["a"]
    assert [a["app_name"] for a in out["rejected"]] == ["c"]
    assert out["pending"] == [BRIEFS[0]]
    assert out["round"] == 2


def test_graph_topology_has_the_supervision_loop() -> None:
    graph = build_factory_graph().get_graph()
    edges = {(e.source, e.target) for e in graph.edges}
    assert ("intake", "build_app") in edges
    assert ("build_app", "supervise") in edges
    assert ("supervise", "build_app") in edges  # the rework loop
    assert ("supervise", "report") in edges


def test_a_generation_failure_is_retried_before_being_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    # A truncated response or a saturated provider produces no assets at all,
    # which scores near zero on every dimension. Rejecting that outright throws
    # away an app that a second attempt usually produces fine.
    attempts = {"n": 0}

    async def _create(request, **kwargs):
        attempts["n"] += 1
        if attempts["n"] == 1:
            result = _FakeResult(request.app_name, request.resolved_slug(), {})
            result.to_dict = lambda: {
                "app_name": request.app_name,
                "slug": request.resolved_slug(),
                "success": False,
                "error": "web asset generation failed: shard truncated",
                "metrics": {},
            }
            result.error = "web asset generation failed: shard truncated"
            return result
        good = _FakeResult(request.app_name, request.resolved_slug(), GOOD, hap="/tmp/x.hap")
        good.error = ""
        return good

    monkeypatch.setattr(factory_graph, "create_webview_app", _create)
    report = asyncio.run(run_factory_batch([BRIEFS[0]], build=True, max_rounds=2, checkpointer=False))
    assert attempts["n"] == 2
    assert report["accepted"] == 1


def test_report_shows_what_happened_not_what_the_scorer_preferred() -> None:
    # An app the scorer wanted reworked but that ran out of rounds is rejected;
    # the report must say rejected, not carry the scorer's unmet preference.
    results = [{"app_name": "a", "round": 1, "score": {"verdict": REWORK, "reasons": []}, "brief": {}}]
    out = asyncio.run(node_supervise({"results": results, "round": 1, "max_rounds": 1}))
    assert out["rejected"][0]["disposition"] == REJECT
    assert out["rejected"][0]["score"]["verdict"] == REWORK
