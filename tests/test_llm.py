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


# ── Claude Code identity injection (subscription OAuth) ──────────────


def test_inject_system_from_none() -> None:
    blocks = llm._inject_system(None)
    assert blocks == [{"type": "text", "text": llm._CLAUDE_CODE_IDENTITY}]


def test_inject_system_from_string() -> None:
    blocks = llm._inject_system("You are a helpful designer.")
    assert blocks[0]["text"] == llm._CLAUDE_CODE_IDENTITY
    assert blocks[1] == {"type": "text", "text": "You are a helpful designer."}


def test_inject_system_from_block_list() -> None:
    original = [{"type": "text", "text": "Reply with JSON only."}]
    blocks = llm._inject_system(original)
    assert blocks[0]["text"] == llm._CLAUDE_CODE_IDENTITY
    assert blocks[1:] == original


def test_oauth_client_injects_identity_on_create(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    class _FakeMessages:
        def create(self, **kwargs):
            captured.update(kwargs)
            return "ok"

    class _FakeClient:
        def __init__(self) -> None:
            self.messages = _FakeMessages()

    fake = _FakeClient()
    monkeypatch.setattr(llm.anthropic, "Anthropic", lambda **_: fake, raising=False)
    _patch_settings(monkeypatch, claude_oauth_token="oat-123")

    client = llm.get_claude_client()
    result = client.messages.create(model="m", system="custom prompt", messages=[])

    assert result == "ok"
    assert captured["system"][0]["text"] == llm._CLAUDE_CODE_IDENTITY
    assert captured["system"][1] == {"type": "text", "text": "custom prompt"}


def test_api_key_client_not_wrapped(monkeypatch: pytest.MonkeyPatch) -> None:
    sentinel = object()
    monkeypatch.setattr(llm.anthropic, "Anthropic", lambda **_: sentinel, raising=False)
    _patch_settings(monkeypatch, claude_api_key="sk-ant-456")

    assert llm.get_claude_client() is sentinel
