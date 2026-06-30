"""Tests for target platform parsing and per-platform build dispatch."""

from __future__ import annotations

import pytest

from zerodev.builder.platforms import (
    DEFAULT_PLATFORMS,
    SUPPORTED_PLATFORMS,
    parse_platforms,
)


def test_parse_csv_string() -> None:
    assert parse_platforms("android,ohos") == ["android", "ohos"]


def test_parse_normalizes_case_and_whitespace() -> None:
    assert parse_platforms("  OHOS , Android ") == ["android", "ohos"]


def test_parse_orders_by_canonical_not_input() -> None:
    # Input reversed -> output still android, ios, ohos order.
    assert parse_platforms("ohos,ios,android") == list(SUPPORTED_PLATFORMS)


def test_parse_dedupes() -> None:
    assert parse_platforms("ohos,ohos,android") == ["android", "ohos"]


def test_parse_list_input() -> None:
    assert parse_platforms(["ios", "android"]) == ["android", "ios"]


def test_parse_none_uses_default() -> None:
    assert parse_platforms(None) == list(DEFAULT_PLATFORMS)


def test_parse_empty_uses_default() -> None:
    assert parse_platforms("") == list(DEFAULT_PLATFORMS)
    assert parse_platforms("  , ") == list(DEFAULT_PLATFORMS)


def test_parse_custom_default() -> None:
    assert parse_platforms(None, default=["ohos"]) == ["ohos"]


def test_parse_unknown_raises() -> None:
    with pytest.raises(ValueError, match="Unsupported platform"):
        parse_platforms("android,windows")


# ── node_build per-platform dispatch ────────────────────────────────


class _FakeBuilder:
    """Records which build methods get invoked."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    async def _ok(self, name: str, artifact: str):
        from zerodev.builder.flutter_builder import BuildResult

        self.calls.append(name)
        return BuildResult(success=True, artifact_path=artifact)

    async def pub_get(self, project):
        from zerodev.builder.flutter_builder import BuildResult

        return BuildResult(success=True)

    async def analyze(self, project):
        from zerodev.builder.flutter_builder import BuildResult

        return BuildResult(success=True)

    async def build_apk(self, project):
        return await self._ok("apk", "/tmp/app.apk")

    async def build_appbundle(self, project):
        return await self._ok("aab", "/tmp/app.aab")

    async def build_ipa(self, project):
        return await self._ok("ipa", "/tmp/app.ipa")

    async def build_ohos(self, project):
        return await self._ok("hap", "/tmp/app.hap")


class _FakeSigner:
    async def generate_keystore(self, *a, **k):
        return None

    def configure_gradle_signing(self, *a, **k):
        return None


@pytest.mark.asyncio
async def test_node_build_ohos_only(monkeypatch: pytest.MonkeyPatch) -> None:
    import zerodev.builder.flutter_builder as fb
    import zerodev.builder.signer as sg
    from zerodev.pipeline.graph import node_build

    fake = _FakeBuilder()
    monkeypatch.setattr(fb, "FlutterBuilder", lambda *a, **k: fake)
    monkeypatch.setattr(sg, "SigningManager", lambda *a, **k: _FakeSigner())

    state = {
        "demand": {"title": "Demo"},
        "demand_id": "d1",
        "project_path": "/tmp/proj",
        "target_platforms": ["ohos"],
    }
    result = await node_build(state)

    assert result["build_artifacts"] == {"hap": "/tmp/app.hap"}
    assert fake.calls == ["hap"]  # android/ios builders never invoked


@pytest.mark.asyncio
async def test_node_build_android_and_ohos(monkeypatch: pytest.MonkeyPatch) -> None:
    import zerodev.builder.flutter_builder as fb
    import zerodev.builder.signer as sg
    from zerodev.pipeline.graph import node_build

    fake = _FakeBuilder()
    monkeypatch.setattr(fb, "FlutterBuilder", lambda *a, **k: fake)
    monkeypatch.setattr(sg, "SigningManager", lambda *a, **k: _FakeSigner())

    state = {
        "demand": {"title": "Demo"},
        "demand_id": "d1",
        "project_path": "/tmp/proj",
        "target_platforms": ["android", "ohos"],
    }
    result = await node_build(state)

    assert set(result["build_artifacts"]) == {"apk", "aab", "hap"}
    assert "ipa" not in fake.calls


@pytest.mark.asyncio
async def test_node_build_falls_back_to_runtime_platforms(monkeypatch: pytest.MonkeyPatch) -> None:
    """With no target_platforms in state, node_build uses get_runtime_platforms()."""
    import zerodev.builder.flutter_builder as fb
    import zerodev.builder.platforms as platforms
    import zerodev.builder.signer as sg
    import zerodev.pipeline.graph as graph

    fake = _FakeBuilder()
    monkeypatch.setattr(fb, "FlutterBuilder", lambda *a, **k: fake)
    monkeypatch.setattr(sg, "SigningManager", lambda *a, **k: _FakeSigner())
    monkeypatch.setattr(platforms, "get_runtime_platforms", lambda: ["ohos"])

    state = {
        "demand": {"title": "Demo"},
        "demand_id": "d1",
        "project_path": "/tmp/proj",
        # no target_platforms -> must fall back to get_runtime_platforms()
    }
    result = await graph.node_build(state)

    assert result["build_artifacts"] == {"hap": "/tmp/app.hap"}
    assert fake.calls == ["hap"]
