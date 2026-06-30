"""Tests for Claude client authentication resolution."""

from __future__ import annotations

import pytest

import zerodev.llm as llm
from zerodev.config import Settings


def _patch_settings(monkeypatch: pytest.MonkeyPatch, **overrides) -> None:
    """Replace llm.get_settings with one returning a custom Settings."""
    settings = Settings(**overrides)
    monkeypatch.setattr(llm, "get_settings", lambda: settings)


def test_oauth_token_preferred_over_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_settings(monkeypatch, claude_oauth_token="oat-123", claude_api_key="sk-ant-456")
    kwargs = llm._build_client_kwargs()

    assert kwargs["auth_token"] == "oat-123"
    assert "api_key" not in kwargs
    assert kwargs["default_headers"]["anthropic-beta"] == llm._OAUTH_BETA_HEADER


def test_api_key_used_when_no_oauth_token(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_settings(monkeypatch, claude_oauth_token="", claude_api_key="sk-ant-456")
    kwargs = llm._build_client_kwargs()

    assert kwargs["api_key"] == "sk-ant-456"
    assert "auth_token" not in kwargs
    assert "default_headers" not in kwargs


def test_missing_credentials_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_settings(monkeypatch, claude_oauth_token="", claude_api_key="")
    with pytest.raises(RuntimeError, match="No Claude credentials"):
        llm._build_client_kwargs()


def test_base_url_override_applied(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_settings(
        monkeypatch,
        claude_api_key="sk-ant-456",
        claude_base_url="https://gateway.example.com",
    )
    kwargs = llm._build_client_kwargs()

    assert kwargs["base_url"] == "https://gateway.example.com"


def test_default_robustness_options(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_settings(monkeypatch, claude_api_key="sk-ant-456")
    kwargs = llm._build_client_kwargs()

    assert kwargs["max_retries"] == llm._DEFAULT_MAX_RETRIES
    assert kwargs["timeout"] == llm._DEFAULT_TIMEOUT
