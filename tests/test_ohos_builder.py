"""Tests for HarmonyOS toolchain discovery, signing injection and artifact lookup."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from zerodev.builder import ohos_builder
from zerodev.builder.ohos_builder import (
    OhosSigningConfig,
    OhosToolchainError,
    _has_dependencies,
    apply_signing_config,
    extract_errors,
    find_hap,
    find_toolchain,
)


def _fake_deveco(root: Path) -> Path:
    """Create a directory tree shaped like a DevEco Studio installation."""
    home = root / "DevEco-Studio.app" / "Contents"
    (home / "sdk" / "default" / "openharmony" / "ets").mkdir(parents=True)
    (home / "tools" / "hvigor" / "bin").mkdir(parents=True)
    (home / "tools" / "ohpm" / "bin").mkdir(parents=True)
    (home / "tools" / "node" / "bin").mkdir(parents=True)
    (home / "tools" / "hvigor" / "bin" / "hvigorw").write_text("#!/bin/sh\n")
    (home / "tools" / "ohpm" / "bin" / "ohpm").write_text("#!/bin/sh\n")
    (home / "sdk" / "default" / "openharmony" / "ets" / "oh-uni-package.json").write_text(
        json.dumps({"apiVersion": "24", "version": "6.1.1.125"})
    )
    return home


# ── Discovery ───────────────────────────────────────────────────


def test_finds_toolchain_from_explicit_home(tmp_path: Path) -> None:
    home = _fake_deveco(tmp_path)
    toolchain = find_toolchain(home)
    assert toolchain.deveco_home == home
    assert toolchain.api_version == "24"


def test_accepts_sdk_home_and_steps_up(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    home = _fake_deveco(tmp_path)
    # DEVECO_SDK_HOME points at <deveco>/sdk, not the Contents directory.
    monkeypatch.setattr(ohos_builder, "_DEVECO_CANDIDATES", ())
    monkeypatch.setenv("DEVECO_SDK_HOME", str(home / "sdk"))
    monkeypatch.setattr(ohos_builder, "effective_setting", lambda key, env="", default="": env)
    assert find_toolchain().deveco_home == home


def test_missing_toolchain_raises_with_probe_list(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ohos_builder, "_DEVECO_CANDIDATES", (str(tmp_path / "nope"),))
    monkeypatch.setattr(ohos_builder, "effective_setting", lambda key, env="", default="": "")
    with pytest.raises(OhosToolchainError, match="Probed:"):
        find_toolchain()


def test_incomplete_install_is_not_accepted(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    home = _fake_deveco(tmp_path)
    (home / "tools" / "hvigor" / "bin" / "hvigorw").unlink()
    # Standard locations are blanked so the probe cannot fall back to a real
    # DevEco install on the developer's machine and mask the rejection.
    monkeypatch.setattr(ohos_builder, "_DEVECO_CANDIDATES", ())
    monkeypatch.setattr(ohos_builder, "effective_setting", lambda key, env="", default="": "")
    with pytest.raises(OhosToolchainError):
        find_toolchain(home)


def test_env_overlay_points_at_bundled_sdk_and_node(tmp_path: Path) -> None:
    toolchain = find_toolchain(_fake_deveco(tmp_path))
    env = toolchain.env()
    assert env["DEVECO_SDK_HOME"] == str(toolchain.sdk_home)
    assert str(toolchain.node_home / "bin") in env["PATH"]


# ── Signing ─────────────────────────────────────────────────────


def _signing(tmp_path: Path) -> OhosSigningConfig:
    for name in ("ks.p12", "cert.cer", "profile.p7b"):
        (tmp_path / name).write_bytes(b"x")
    return OhosSigningConfig(
        store_file=str(tmp_path / "ks.p12"),
        store_password="storepass",
        key_alias="release",
        key_password="keypass",
        cert_path=str(tmp_path / "cert.cer"),
        profile_path=str(tmp_path / "profile.p7b"),
    )


def test_signing_from_settings_returns_none_when_incomplete(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ohos_builder, "effective_setting", lambda key, env="", default="": "")
    assert OhosSigningConfig.from_settings() is None


def test_missing_files_detected(tmp_path: Path) -> None:
    signing = _signing(tmp_path)
    (tmp_path / "cert.cer").unlink()
    assert signing.missing_files() == [signing.cert_path]


def test_apply_signing_config_rewrites_build_profile(tmp_path: Path) -> None:
    project = tmp_path / "proj"
    project.mkdir()
    (project / "build-profile.json5").write_text(
        json.dumps({"app": {"signingConfigs": [], "products": [{"name": "default", "signingConfig": "default"}]}}),
        encoding="utf-8",
    )
    apply_signing_config(project, _signing(tmp_path))

    profile = json.loads((project / "build-profile.json5").read_text(encoding="utf-8"))
    material = profile["app"]["signingConfigs"][0]["material"]
    assert material["keyAlias"] == "release"
    assert material["signAlg"] == "SHA256withECDSA"
    assert profile["app"]["products"][0]["signingConfig"] == "default"


def test_apply_signing_config_leaves_json5_with_comments_alone(tmp_path: Path) -> None:
    project = tmp_path / "proj"
    project.mkdir()
    original = '{\n  // hand edited\n  "app": {}\n}'
    (project / "build-profile.json5").write_text(original, encoding="utf-8")
    apply_signing_config(project, _signing(tmp_path))
    # Corrupting a hand-maintained config would be worse than skipping.
    assert (project / "build-profile.json5").read_text(encoding="utf-8") == original


# ── Artifacts and diagnostics ───────────────────────────────────


def test_find_hap_prefers_signed(tmp_path: Path) -> None:
    out = tmp_path / "out"
    out.mkdir()
    (out / "entry-default-unsigned.hap").write_bytes(b"x")
    (out / "entry-default-signed.hap").write_bytes(b"x")
    assert find_hap(tmp_path).name == "entry-default-signed.hap"


def test_find_hap_returns_none_when_absent(tmp_path: Path) -> None:
    assert find_hap(tmp_path) is None


def test_extract_errors_strips_ansi_and_dedupes() -> None:
    output = (
        "> hvigor \x1b[31mERROR: Failed to compile ArkTS\x1b[0m\n"
        "> hvigor \x1b[31mERROR: Failed to compile ArkTS\x1b[0m\n"
        "ok line\n"
        "ArkTS:ERROR File: Index.ets:3:1 unknown identifier\n"
    )
    errors = extract_errors(output)
    assert len(errors) == 2
    assert all("\x1b" not in e for e in errors)


def test_has_dependencies_detects_declared_packages(tmp_path: Path) -> None:
    (tmp_path / "oh-package.json5").write_text('{"dependencies": {"@ohos/axios": "^2.0.0"}}', encoding="utf-8")
    assert _has_dependencies(tmp_path) is True


def test_has_dependencies_false_for_empty_block(tmp_path: Path) -> None:
    (tmp_path / "oh-package.json5").write_text('{"dependencies": {}}', encoding="utf-8")
    assert _has_dependencies(tmp_path) is False
