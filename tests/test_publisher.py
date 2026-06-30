"""Tests for the HarmonyOS publisher and platform-aware publish dispatch."""

from __future__ import annotations

import json

import pytest

from zerodev.builder.publisher import HarmonyOSPublisher, PublishResult

# ── HarmonyOSPublisher ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_harmonyos_missing_credentials() -> None:
    pub = HarmonyOSPublisher(client_id="", client_secret="")
    result = await pub.publish("/tmp/whatever", _app_info())
    assert result.success is False
    assert "credentials" in result.message.lower()


@pytest.mark.asyncio
async def test_harmonyos_hap_not_found(tmp_path) -> None:
    pub = HarmonyOSPublisher(client_id="cid", client_secret="sec")
    result = await pub.publish(str(tmp_path), _app_info())
    assert result.success is False
    assert ".hap" in result.message.lower() or "hap" in result.message.lower()


def test_harmonyos_locate_hap_prefers_signed(tmp_path) -> None:
    build = tmp_path / "ohos" / "build"
    build.mkdir(parents=True)
    (build / "entry-default-unsigned.hap").write_bytes(b"x")
    (build / "entry-default-signed.hap").write_bytes(b"x")

    located = HarmonyOSPublisher._locate_hap(str(tmp_path))
    assert located is not None
    assert "signed" in located.name.lower()


def _app_info():
    from zerodev.builder.publisher import AppInfo

    return AppInfo(package_name="com.zerodev.demo", app_name="Demo")


# ── get_runtime_platforms (settings.json override) ──────────────────


def test_get_runtime_platforms_reads_settings_json(tmp_path, monkeypatch) -> None:
    import zerodev.config as config
    from zerodev.builder.platforms import get_runtime_platforms
    from zerodev.config import Settings

    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "settings.json").write_text(
        json.dumps({"targetPlatforms": ["ohos"]}), encoding="utf-8"
    )
    monkeypatch.setattr(
        config, "get_settings", lambda: Settings(base_dir=tmp_path, target_platforms="android")
    )

    assert get_runtime_platforms() == ["ohos"]


def test_get_runtime_platforms_falls_back_to_env(tmp_path, monkeypatch) -> None:
    import zerodev.config as config
    from zerodev.builder.platforms import get_runtime_platforms
    from zerodev.config import Settings

    # No settings.json present -> use env config.
    monkeypatch.setattr(
        config, "get_settings", lambda: Settings(base_dir=tmp_path, target_platforms="android,ohos")
    )

    assert get_runtime_platforms() == ["android", "ohos"]


# ── node_publish platform-aware dispatch ────────────────────────────


class _RecordingPublisher:
    def __init__(self, name, registry):
        self._name = name
        self._registry = registry

    async def publish(self, project, app_info):
        self._registry.append(self._name)
        return PublishResult(success=True, store_url=f"https://store/{self._name}")


@pytest.mark.asyncio
async def test_node_publish_only_for_built_artifacts(monkeypatch) -> None:
    import zerodev.builder.publisher as pub
    from zerodev.pipeline.graph import node_publish

    called: list[str] = []
    monkeypatch.setattr(pub, "GooglePlayPublisher", lambda: _RecordingPublisher("gp", called))
    monkeypatch.setattr(pub, "AppStorePublisher", lambda: _RecordingPublisher("as", called))
    monkeypatch.setattr(pub, "HarmonyOSPublisher", lambda: _RecordingPublisher("hm", called))

    state = {
        "demand": {"title": "Demo"},
        "demand_id": "d1",
        "project_path": "/tmp/proj",
        "build_artifacts": {"hap": "/tmp/app.hap"},  # ohos only
    }
    result = await node_publish(state)

    assert called == ["hm"]  # google/appstore never invoked
    assert "appgallery_harmonyos" in result["publish_results"]
    assert "google_play" not in result["publish_results"]
