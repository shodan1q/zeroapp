"""Tests for the WebView app factory pipeline and the unattended daemon."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from zerodev.builder.publisher import AppInfo, HarmonyOSPublisher
from zerodev.pipeline import webview_app
from zerodev.pipeline.daemon import (
    AppFactoryDaemon,
    DaemonConfig,
    FactoryState,
    _json_list,
    _parse_idea_array,
    read_state,
    write_queue,
)
from zerodev.pipeline.webview_app import (
    WebviewAppRequest,
    create_webview_app,
    load_requests,
    request_from_demand,
)

MINIMAL_ASSETS = {
    "index.html": '<!doctype html><meta name="viewport" content="viewport-fit=cover"><body></body>',
    "styles.css": ":root{}",
    "data.js": "window.APP_DATA={};",
    "app.js": "(function(){window.APP_DATA;})();",
}


class _StubGenerator:
    """Stands in for the LLM-backed generator."""

    def __init__(self, assets: dict[str, str] | None = None, error: Exception | None = None) -> None:
        self._assets = assets or MINIMAL_ASSETS
        self._error = error
        self.calls: list[str] = []

    async def generate(self, spec) -> dict[str, str]:
        self.calls.append(spec.app_name)
        if self._error:
            raise self._error
        return dict(self._assets)


# ── Request handling ────────────────────────────────────────────


def test_slug_is_stable_for_cjk_names() -> None:
    # hash() is salted per process; the slug must not be, or every restart would
    # build the same app into a different workspace directory.
    request = WebviewAppRequest(app_name="静心冥想", description="x")
    assert request.resolved_slug() == WebviewAppRequest(app_name="静心冥想", description="y").resolved_slug()
    assert request.resolved_slug().startswith("app")


def test_slug_derived_from_latin_name() -> None:
    assert WebviewAppRequest(app_name="Habit Tracker", description="x").resolved_slug() == "habit_tracker"


def test_explicit_slug_wins() -> None:
    assert WebviewAppRequest(app_name="静心冥想", description="x", slug="Mindful App").resolved_slug() == "mindful_app"


def test_request_from_demand_maps_fields() -> None:
    request = request_from_demand(
        {"title": "记账本", "description": "记录开销", "features": ["记录"], "target_users": "上班族"}
    )
    assert request.app_name == "记账本"
    assert request.features == ["记录"]


def test_load_requests_ignores_unknown_keys(tmp_path: Path) -> None:
    path = tmp_path / "queue.json"
    path.write_text(json.dumps([{"app_name": "A", "description": "d", "bogus_key": 1}]), encoding="utf-8")
    requests = load_requests(path)
    assert len(requests) == 1 and requests[0].app_name == "A"


# ── Factory stages ──────────────────────────────────────────────


def test_factory_generates_and_scaffolds_without_building(tmp_path: Path) -> None:
    generator = _StubGenerator()
    result = asyncio.run(
        create_webview_app(
            WebviewAppRequest(app_name="记账本", description="记录开销", slug="ledger"),
            workspace=tmp_path,
            build=False,
            generator=generator,
        )
    )
    assert result.success
    assert [s.name for s in result.stages] == ["generate", "scaffold"]
    assert (Path(result.project_path) / "entry/src/main/resources/rawfile/index.html").exists()
    assert generator.calls == ["记账本"]


def test_factory_records_failed_stage_on_generation_error(tmp_path: Path) -> None:
    generator = _StubGenerator(error=RuntimeError("provider down"))
    result = asyncio.run(
        create_webview_app(
            WebviewAppRequest(app_name="X", description="d", slug="x"),
            workspace=tmp_path,
            build=False,
            generator=generator,
        )
    )
    assert not result.success
    assert result.failed_stage == "generate"
    assert "provider down" in result.error


def test_result_serialises_for_the_dashboard(tmp_path: Path) -> None:
    result = asyncio.run(
        create_webview_app(
            WebviewAppRequest(app_name="记账本", description="d", slug="ledger"),
            workspace=tmp_path,
            build=False,
            generator=_StubGenerator(),
        )
    )
    payload = result.to_dict()
    assert payload["success"] is True
    assert payload["slug"] == "ledger"
    assert {"generate", "scaffold"} == {s["name"] for s in payload["stages"]}
    json.dumps(payload)  # must stay JSON-serialisable


# ── Daemon ──────────────────────────────────────────────────────


def _daemon(tmp_path: Path, **config) -> AppFactoryDaemon:
    return AppFactoryDaemon(
        DaemonConfig(
            workspace=tmp_path / "workspace",
            state_dir=tmp_path / "state",
            build=False,
            **config,
        )
    )


def test_queue_is_drained_and_archived(tmp_path: Path) -> None:
    daemon = _daemon(tmp_path)
    write_queue([{"app_name": "A", "description": "d", "slug": "a"}], state_dir=tmp_path / "state")

    requests = daemon._drain_queue()
    assert [r.app_name for r in requests] == ["A"]
    # Re-reading must not hand out the same brief twice.
    assert daemon._drain_queue() == []
    assert (tmp_path / "state" / "queue-consumed.json").exists()


def test_unreadable_queue_is_ignored_not_fatal(tmp_path: Path) -> None:
    daemon = _daemon(tmp_path)
    (tmp_path / "state" / "queue.json").write_text("{ not json", encoding="utf-8")
    assert daemon._drain_queue() == []


def test_daemon_survives_a_crashing_build(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    daemon = _daemon(tmp_path)

    async def _boom(*args, **kwargs):
        raise ValueError("exploded")

    monkeypatch.setattr(webview_app, "create_webview_app", _boom)
    monkeypatch.setattr("zerodev.pipeline.daemon.create_webview_app", _boom)

    result = asyncio.run(daemon._build_one(WebviewAppRequest(app_name="A", description="d", slug="a")))
    assert not result.success
    assert "exploded" in result.error
    assert daemon.state.apps_failed == 1
    assert daemon.state.consecutive_failures == 1


def test_state_survives_a_restart(tmp_path: Path) -> None:
    daemon = _daemon(tmp_path)
    daemon.state.apps_built = 7
    daemon.state.built_names = ["记账本"]
    daemon._save_state()

    reloaded = FactoryState.load(tmp_path / "state" / "state.json")
    assert reloaded.apps_built == 7
    assert reloaded.built_names == ["记账本"]


def test_backoff_grows_with_consecutive_failures(tmp_path: Path) -> None:
    daemon = _daemon(tmp_path)
    delays = []
    for failures in (1, 2, 3, 10):
        daemon.state.consecutive_failures = failures
        delays.append(daemon._backoff_delay())
    assert delays == sorted(delays)
    assert delays[0] < delays[-1]


def test_max_apps_stops_the_loop(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    daemon = _daemon(tmp_path, max_apps=2)

    async def _next_requests():
        return [WebviewAppRequest(app_name=f"App{i}", description="d", slug=f"a{i}") for i in range(5)]

    monkeypatch.setattr(daemon, "next_requests", _next_requests)

    async def _fake_create(request, **kwargs):
        import datetime

        return webview_app.WebviewAppResult(
            request=request,
            started_at=datetime.datetime.now(datetime.UTC),
            stages=[webview_app.StageRecord("generate", True, 0.0)],
        )

    monkeypatch.setattr("zerodev.pipeline.daemon.create_webview_app", _fake_create)

    state = asyncio.run(daemon.run_forever())
    assert state.apps_built == 2


def test_read_state_reports_liveness_from_heartbeat(tmp_path: Path) -> None:
    daemon = _daemon(tmp_path)
    daemon._save_state()
    daemon._beat()
    state = read_state(tmp_path / "state")
    assert state["alive"] is True
    assert state["heartbeat_age_seconds"] < 60


def test_idea_array_parsing_tolerates_fences_and_prose() -> None:
    raw = 'Sure:\n```json\n[{"app_name": "A", "slug": "a"}]\n```\n'
    assert _parse_idea_array(raw) == [{"app_name": "A", "slug": "a"}]


def test_idea_array_parsing_returns_empty_on_garbage() -> None:
    assert _parse_idea_array("I cannot do that") == []


def test_json_list_handles_all_column_shapes() -> None:
    assert _json_list('["a","b"]') == ["a", "b"]
    assert _json_list("a, b") == ["a", "b"]
    assert _json_list(["a"]) == ["a"]
    assert _json_list(None) == []


# ── Publisher preflight ─────────────────────────────────────────


def test_publish_blocked_without_credentials(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("zerodev.builder.publisher.effective_setting", lambda key, env="", default="": "")
    (tmp_path / "entry-default-signed.hap").write_bytes(b"x")

    publisher = HarmonyOSPublisher()
    result = asyncio.run(publisher.publish(str(tmp_path), AppInfo(package_name="com.a.b", app_name="A")))
    assert not result.success
    assert "credentials not configured" in result.message


def test_publish_blocked_on_unsigned_artifact(tmp_path: Path) -> None:
    (tmp_path / "entry-default-unsigned.hap").write_bytes(b"x")
    publisher = HarmonyOSPublisher(client_id="id", client_secret="secret", app_id="123")

    _, problems = publisher.preflight(str(tmp_path))
    assert any("unsigned" in p for p in problems)


def test_preflight_reports_missing_artifact(tmp_path: Path) -> None:
    publisher = HarmonyOSPublisher(client_id="id", client_secret="secret", app_id="123")
    hap, problems = publisher.preflight(str(tmp_path))
    assert hap is None
    assert any("No .hap found" in p for p in problems)


def test_auto_submit_can_be_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("zerodev.builder.publisher.effective_setting", lambda key, env="", default="": "false")
    assert HarmonyOSPublisher().auto_submit is False
