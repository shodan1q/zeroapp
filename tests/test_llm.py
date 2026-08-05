"""Tests for Claude client authentication resolution."""

from __future__ import annotations

import pytest

import zerodev.llm as llm
from zerodev.config import Settings


def _patch_settings(monkeypatch: pytest.MonkeyPatch, **overrides) -> None:
    """Replace llm.get_settings with one returning a custom Settings.

    ``_env_file=None`` stops pydantic-settings from reading the developer's real
    ``.env``; without it a machine configured for a different provider (or with
    a real API key on disk) silently changes what these tests assert.
    Also isolates tests from any real data/settings.json on the machine.
    """
    settings = Settings(_env_file=None, **overrides)
    monkeypatch.setattr(llm, "get_settings", lambda: settings)
    monkeypatch.setattr(llm, "_load_dashboard_settings", lambda: {})


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


# ── complete() / acomplete() helpers ────────────────────────────────


class _FakeBlock:
    def __init__(self, text):
        self.text = text


class _FakeResp:
    def __init__(self, text):
        self.content = [_FakeBlock(text)]


class _FakeMessages:
    def __init__(self, captured):
        self._captured = captured

    def create(self, **kwargs):
        self._captured.update(kwargs)
        return _FakeResp("hello")


class _FakeAsyncMessages:
    def __init__(self, captured):
        self._captured = captured

    async def create(self, **kwargs):
        self._captured.update(kwargs)
        return _FakeResp("hi")


class _FakeClient:
    def __init__(self, captured, is_async):
        self.messages = (
            _FakeAsyncMessages(captured) if is_async else _FakeMessages(captured)
        )


def test_complete_builds_single_user_message(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_settings(monkeypatch, claude_api_key="sk-ant-1", claude_model="m-default")
    cap: dict = {}
    out = llm.complete("hi there", max_tokens=123, client=_FakeClient(cap, is_async=False))

    assert out == "hello"
    assert cap["model"] == "m-default"
    assert cap["max_tokens"] == 123
    assert cap["messages"] == [{"role": "user", "content": "hi there"}]
    assert "system" not in cap  # omitted when None


@pytest.mark.asyncio
async def test_acomplete_passes_system_and_model(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_settings(monkeypatch, claude_api_key="sk-ant-1", claude_model="m-default")
    cap: dict = {}
    out = await llm.acomplete(
        "q", system="be brief", model="m-override", client=_FakeClient(cap, is_async=True)
    )

    assert out == "hi"
    assert cap["model"] == "m-override"
    assert cap["system"] == "be brief"


def test_complete_requires_prompt_or_messages(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_settings(monkeypatch, claude_api_key="sk-ant-1")
    with pytest.raises(ValueError, match="prompt.*messages"):
        llm.complete(client=_FakeClient({}, is_async=False))


# ── Multi-provider support ──────────────────────────────────────────


def test_resolve_defaults_to_claude(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_settings(monkeypatch, claude_api_key="sk-ant-1", claude_model="m-x")
    monkeypatch.setattr(llm, "_load_dashboard_settings", lambda: {})
    cfg = llm.resolve_llm_config()

    assert cfg.provider == "claude"
    assert cfg.model == "m-x"
    assert cfg.api_key == "sk-ant-1"


def test_resolve_provider_from_dashboard_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_settings(monkeypatch)
    monkeypatch.setattr(
        llm,
        "_load_dashboard_settings",
        lambda: {"llmProvider": "deepseek", "deepseekApiKey": "sk-ds-1"},
    )
    cfg = llm.resolve_llm_config()

    assert cfg.provider == "deepseek"
    assert cfg.api_key == "sk-ds-1"
    assert cfg.model == "deepseek-chat"  # registry default
    assert cfg.base_url == "https://api.deepseek.com/v1"


def test_resolve_env_fallback_for_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_settings(monkeypatch, llm_provider="openai", openai_api_key="sk-oa-1", openai_model="gpt-x")
    monkeypatch.setattr(llm, "_load_dashboard_settings", lambda: {})
    cfg = llm.resolve_llm_config()

    assert cfg.provider == "openai"
    assert cfg.api_key == "sk-oa-1"
    assert cfg.model == "gpt-x"


def test_resolve_unknown_provider_falls_back(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_settings(monkeypatch, llm_provider="nonsense", claude_api_key="sk-ant-1")
    monkeypatch.setattr(llm, "_load_dashboard_settings", lambda: {})
    assert llm.resolve_llm_config().provider == "claude"


def test_masked_dashboard_secret_ignored(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_settings(monkeypatch, claude_api_key="sk-env-real")
    monkeypatch.setattr(llm, "_load_dashboard_settings", lambda: {"claudeApiKey": "****abcd"})
    assert llm.resolve_llm_config().api_key == "sk-env-real"


def test_compat_payload_translates_anthropic_kwargs() -> None:
    from zerodev.providers import PROVIDERS

    payload = llm._build_chat_payload(
        PROVIDERS["deepseek"],
        model="deepseek-chat",
        max_tokens=256,
        system="be terse",
        messages=[{"role": "user", "content": "hi"}],
    )

    assert payload["messages"][0] == {"role": "system", "content": "be terse"}
    assert payload["messages"][1] == {"role": "user", "content": "hi"}
    assert payload["max_tokens"] == 256


def test_compat_payload_uses_openai_token_param() -> None:
    from zerodev.providers import PROVIDERS

    payload = llm._build_chat_payload(
        PROVIDERS["openai"], model="gpt-5.1", max_tokens=128, messages=[{"role": "user", "content": "q"}]
    )
    assert payload["max_completion_tokens"] == 128
    assert "max_tokens" not in payload


def test_compat_client_requires_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_settings(monkeypatch)
    monkeypatch.setattr(llm, "_load_dashboard_settings", lambda: {"llmProvider": "openai"})
    with pytest.raises(RuntimeError, match="No API key configured"):
        llm.get_llm_client()


def test_ollama_needs_no_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_settings(monkeypatch)
    monkeypatch.setattr(llm, "_load_dashboard_settings", lambda: {"llmProvider": "ollama"})
    client = llm.get_llm_client()

    assert isinstance(client, llm._CompatClient)
    assert client._cfg.base_url == "http://localhost:11434/v1"


def test_compat_response_shape() -> None:
    data = {"model": "m", "choices": [{"message": {"role": "assistant", "content": "out"}}]}
    resp = llm._parse_chat_response(data, "X")
    assert resp.content[0].text == "out"


# ── Compat response handling ────────────────────────────────────────


def _chat_data(text, finish="stop"):
    return {"model": "m", "choices": [{"message": {"role": "assistant", "content": text}, "finish_reason": finish}]}


def test_parse_strips_leading_think_block() -> None:
    resp = llm._parse_chat_response(_chat_data("<think>chain of thought</think>\n{\"a\": 1}"), "X")
    assert resp.content[0].text == '{"a": 1}'


def test_parse_raises_on_empty_content() -> None:
    with pytest.raises(llm.LLMError, match="empty content"):
        llm._parse_chat_response(_chat_data("", finish="length"), "X")


def test_parse_raises_on_null_content() -> None:
    data = {"model": "m", "choices": [{"message": {"role": "assistant", "content": None}, "finish_reason": "stop"}]}
    with pytest.raises(llm.LLMError):
        llm._parse_chat_response(data, "X")


def test_prefill_extracted_from_trailing_assistant_message() -> None:
    msgs = [{"role": "user", "content": "write main.dart"}, {"role": "assistant", "content": "import"}]
    assert llm._extract_prefill(msgs) == "import"
    assert llm._extract_prefill([{"role": "user", "content": "hi"}]) == ""


def test_prefill_duplicate_prefix_stripped() -> None:
    # Compat model restarted the file including the prefill: strip it so the
    # caller's `prefill + response` reconstruction has no duplication.
    assert llm._apply_prefill("import", "import 'package:flutter/material.dart';") == " 'package:flutter/material.dart';"
    # Model behaved like a continuation: leave untouched.
    assert llm._apply_prefill("import", " 'dart:async';") == " 'dart:async';"
    assert llm._apply_prefill("", "anything") == "anything"


def test_llm_error_is_runtime_error() -> None:
    assert issubclass(llm.LLMError, RuntimeError)
