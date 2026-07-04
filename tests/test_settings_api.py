"""Tests for the Dashboard settings API (masking, persistence, wiring)."""

from __future__ import annotations

import json

import pytest

from zerodev.api import routes


# ── _is_sensitive / mask helpers ─────────────────────────────────


def test_path_fields_are_not_sensitive() -> None:
    assert routes._is_sensitive("googlePlayKeyPath") is False
    assert routes._is_sensitive("appStoreKeyPath") is False
    assert routes._is_sensitive("huaweiKeyPath") is False


def test_secret_fields_are_sensitive() -> None:
    assert routes._is_sensitive("claudeApiKey") is True
    assert routes._is_sensitive("claudeOauthToken") is True
    assert routes._is_sensitive("huaweiAgcClientSecret") is True
    assert routes._is_sensitive("redditClientSecret") is True


def test_plain_fields_are_not_sensitive() -> None:
    assert routes._is_sensitive("outputDir") is False
    assert routes._is_sensitive("claudeModel") is False


def test_mask_value_output_matches_mask_pattern() -> None:
    assert routes._MASK_PATTERN.fullmatch(routes._mask_value("sk-abcdef123456"))
    assert routes._MASK_PATTERN.fullmatch(routes._mask_value("ab"))  # "****"


def test_mask_pattern_rejects_star_prefixed_real_values() -> None:
    # A real value that merely starts with "*" must not be treated as a mask.
    assert routes._MASK_PATTERN.fullmatch("*special-value") is None
    assert routes._MASK_PATTERN.fullmatch("*a/very/long/path") is None


# ── GET /api/settings ────────────────────────────────────────────


@pytest.fixture
def fake_defaults(monkeypatch, tmp_path):
    """Point routes at a temp settings file and deterministic defaults."""
    settings_file = tmp_path / "settings.json"
    monkeypatch.setattr(routes, "SETTINGS_FILE", settings_file)
    monkeypatch.setattr(
        routes,
        "_get_defaults",
        lambda: {
            "claudeApiKey": "sk-abcdef123456",
            "claudeModel": "model-from-env",
            "googlePlayKeyPath": "/keys/google-play.json",
            "appStoreKeyPath": "/keys/appstore.p8",
            "huaweiAgcClientSecret": "topsecretvalue",
            "outputDir": "/workspace",
        },
    )
    return settings_file


async def test_get_settings_masks_secrets_but_not_paths(fake_defaults) -> None:
    result = await routes.get_settings_api()

    # Path fields must be returned raw so the UI can show/edit them.
    assert result["googlePlayKeyPath"] == "/keys/google-play.json"
    assert result["appStoreKeyPath"] == "/keys/appstore.p8"

    # Secrets stay masked.
    assert result["claudeApiKey"].startswith("*")
    assert result["claudeApiKey"].endswith("3456")
    assert result["huaweiAgcClientSecret"].startswith("*")

    # Non-sensitive fields untouched.
    assert result["outputDir"] == "/workspace"
    assert result["claudeModel"] == "model-from-env"


# ── POST /api/settings ───────────────────────────────────────────


async def test_save_settings_does_not_freeze_env_defaults(fake_defaults) -> None:
    # Frontend posts back the full merged form; unchanged defaults must
    # NOT be persisted (otherwise later .env changes are shadowed).
    await routes.save_settings_api(
        {"claudeModel": "model-from-env", "outputDir": "/custom"}
    )
    saved = json.loads(fake_defaults.read_text(encoding="utf-8"))
    assert "claudeModel" not in saved
    assert saved["outputDir"] == "/custom"


async def test_save_settings_persists_default_if_previously_customized(
    fake_defaults,
) -> None:
    # An explicit change back to the default value still persists when the
    # key was previously customized in the file.
    fake_defaults.write_text(
        json.dumps({"claudeModel": "my-custom-model"}), encoding="utf-8"
    )
    await routes.save_settings_api({"claudeModel": "model-from-env"})
    saved = json.loads(fake_defaults.read_text(encoding="utf-8"))
    assert saved["claudeModel"] == "model-from-env"


async def test_save_settings_keeps_stored_secret_when_mask_round_trips(
    fake_defaults,
) -> None:
    fake_defaults.write_text(
        json.dumps({"claudeApiKey": "sk-stored-real-key"}), encoding="utf-8"
    )
    await routes.save_settings_api({"claudeApiKey": "**************-key"})
    saved = json.loads(fake_defaults.read_text(encoding="utf-8"))
    assert saved["claudeApiKey"] == "sk-stored-real-key"


async def test_save_settings_drops_mask_of_env_derived_secret(fake_defaults) -> None:
    # Mask of an env-derived secret (not in the file) must not be stored.
    await routes.save_settings_api({"claudeApiKey": "***********3456"})
    saved = json.loads(fake_defaults.read_text(encoding="utf-8"))
    assert "claudeApiKey" not in saved


async def test_save_settings_stores_star_prefixed_real_value(fake_defaults) -> None:
    # Not mask-shaped (more than 4 chars after the asterisks) -> store as-is.
    await routes.save_settings_api({"claudeApiKey": "*not-actually-a-mask"})
    saved = json.loads(fake_defaults.read_text(encoding="utf-8"))
    assert saved["claudeApiKey"] == "*not-actually-a-mask"


async def test_save_settings_persists_new_secret(fake_defaults) -> None:
    await routes.save_settings_api({"claudeApiKey": "sk-brand-new-key"})
    saved = json.loads(fake_defaults.read_text(encoding="utf-8"))
    assert saved["claudeApiKey"] == "sk-brand-new-key"


# ── Publisher consumes Dashboard-saved credentials ───────────────


def test_harmonyos_publisher_uses_dashboard_settings(monkeypatch) -> None:
    import zerodev.settings_store as settings_store
    from zerodev.builder.publisher import HarmonyOSPublisher

    monkeypatch.setattr(
        settings_store,
        "load_dashboard_settings",
        lambda: {
            "huaweiAgcClientId": "dash-client-id",
            "huaweiAgcClientSecret": "dash-client-secret",
            "huaweiAgcAppId": "dash-app-id",
        },
    )
    pub = HarmonyOSPublisher()
    assert pub.client_id == "dash-client-id"
    assert pub.client_secret == "dash-client-secret"
    assert pub.app_id == "dash-app-id"


def test_harmonyos_publisher_explicit_args_win(monkeypatch) -> None:
    import zerodev.settings_store as settings_store
    from zerodev.builder.publisher import HarmonyOSPublisher

    monkeypatch.setattr(
        settings_store,
        "load_dashboard_settings",
        lambda: {"huaweiAgcClientId": "dash-client-id"},
    )
    pub = HarmonyOSPublisher(client_id="explicit-id")
    assert pub.client_id == "explicit-id"
