"""Unified LLM client factory with multi-provider support.

Every call site in the codebase uses the Anthropic Messages shape::

    client = get_llm_client()          # or get_llm_async_client()
    resp = client.messages.create(model=..., max_tokens=..., system=..., messages=[...])
    text = resp.content[0].text

This module keeps that contract while supporting multiple AI providers:

- **Claude** (default): official Anthropic SDK. Two authentication methods:
  ``CLAUDE_API_KEY`` (per-token billing) or ``CLAUDE_OAUTH_TOKEN`` (Pro/Max
  subscription token from ``claude setup-token``; OAuth wins when both are
  set). Subscription tokens require the first ``system`` block to be the
  Claude Code identity string -- the OAuth wrappers inject it transparently.
- **OpenAI / Gemini / DeepSeek / Qwen / Zhipu GLM / Moonshot Kimi / Ollama**:
  each vendor's officially documented OpenAI-compatible endpoint, driven by a
  thin httpx client that mimics the Anthropic response shape. See
  ``zerodev/providers.py`` for the registry.

Provider selection order (mirrors the build-platform pattern):
Dashboard settings (``data/settings.json`` -> ``llmProvider``) >
env ``LLM_PROVIDER`` > default ``claude``. Credentials and model follow the
same file > env > registry-default resolution, so keys entered in the
Dashboard take effect without restarting with new env vars.
"""

from __future__ import annotations

import json
import logging
import random
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import anthropic
import httpx

from zerodev.config import get_settings
from zerodev.providers import DEFAULT_PROVIDER, PROVIDERS, ProviderSpec

logger = logging.getLogger(__name__)

# Beta header required when calling the official API with a Claude Code /
# subscription OAuth token instead of an API key.
_OAUTH_BETA_HEADER = "oauth-2025-04-20"

# Required first system block when authenticating with a subscription OAuth
# token; without it the Messages API rejects the credential.
_CLAUDE_CODE_IDENTITY = "You are Claude Code, Anthropic's official CLI for Claude."

# Default robustness settings applied to every client.
_DEFAULT_MAX_RETRIES = 3
_DEFAULT_TIMEOUT = 600.0

_SETTINGS_FILE = Path(__file__).resolve().parent.parent / "data" / "settings.json"


# ---------------------------------------------------------------------------
# Runtime configuration resolution (settings.json > env > registry default)
# ---------------------------------------------------------------------------


def _load_dashboard_settings() -> dict[str, Any]:
    """Read ``data/settings.json`` (Dashboard-saved settings); {} if absent."""
    if _SETTINGS_FILE.exists():
        try:
            return json.loads(_SETTINGS_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Failed to read %s: %s", _SETTINGS_FILE, exc)
    return {}


def _clean(value: Any) -> str:
    """Return a usable string setting, dropping blanks and masked secrets."""
    if not isinstance(value, str):
        return ""
    value = value.strip()
    # GET /api/settings masks secrets as "****xxxx"; never treat one as real.
    if value.startswith("*"):
        return ""
    return value


@dataclass(frozen=True)
class ResolvedLLM:
    """Effective LLM configuration after merging all sources."""

    provider: str
    spec: ProviderSpec
    api_key: str
    oauth_token: str  # Claude only
    base_url: str
    model: str


def resolve_llm_config() -> ResolvedLLM:
    """Merge Dashboard settings, env vars and registry defaults."""
    settings = get_settings()
    saved = _load_dashboard_settings()

    provider = (_clean(saved.get("llmProvider")) or settings.llm_provider or DEFAULT_PROVIDER).lower()
    if provider not in PROVIDERS:
        logger.warning("Unknown LLM provider %r; falling back to %s", provider, DEFAULT_PROVIDER)
        provider = DEFAULT_PROVIDER
    spec = PROVIDERS[provider]

    if provider == "claude":
        return ResolvedLLM(
            provider=provider,
            spec=spec,
            api_key=_clean(saved.get("claudeApiKey")) or settings.claude_api_key.strip(),
            oauth_token=_clean(saved.get("claudeOauthToken")) or settings.claude_oauth_token.strip(),
            base_url=_clean(saved.get("claudeBaseUrl")) or settings.claude_base_url.strip(),
            model=_clean(saved.get("claudeModel")) or settings.claude_model or spec.default_model,
        )

    def env(attr: str) -> str:
        return str(getattr(settings, f"{provider}_{attr}", "") or "").strip()

    return ResolvedLLM(
        provider=provider,
        spec=spec,
        api_key=_clean(saved.get(f"{provider}ApiKey")) or env("api_key"),
        oauth_token="",
        base_url=_clean(saved.get(f"{provider}BaseUrl")) or env("base_url") or spec.default_base_url,
        model=_clean(saved.get(f"{provider}Model")) or env("model") or spec.default_model,
    )


# ---------------------------------------------------------------------------
# Claude (official Anthropic SDK)
# ---------------------------------------------------------------------------


def _build_client_kwargs(resolved: ResolvedLLM | None = None) -> dict[str, Any]:
    """Resolve authentication and shared client options for Claude.

    OAuth token is preferred over API key. Raises a clear error when neither
    credential is configured. Without ``resolved``, falls back to env-only
    settings (kept for backwards compatibility and tests).
    """
    settings = get_settings()

    kwargs: dict[str, Any] = {
        "max_retries": _DEFAULT_MAX_RETRIES,
        "timeout": _DEFAULT_TIMEOUT,
    }

    base_url = resolved.base_url if resolved else settings.claude_base_url
    oauth_token = resolved.oauth_token if resolved else settings.claude_oauth_token.strip()
    api_key = resolved.api_key if resolved else settings.claude_api_key.strip()

    if base_url:
        kwargs["base_url"] = base_url

    if oauth_token:
        logger.info("Using Claude OAuth token authentication")
        kwargs["auth_token"] = oauth_token
        kwargs["default_headers"] = {"anthropic-beta": _OAUTH_BETA_HEADER}
    elif api_key:
        logger.info("Using Claude API key authentication")
        kwargs["api_key"] = api_key
    else:
        raise RuntimeError(
            "No Claude credentials configured. Set CLAUDE_OAUTH_TOKEN "
            "(from `claude setup-token`) or CLAUDE_API_KEY in your environment, "
            "or fill them in on the Dashboard settings page."
        )

    return kwargs


def _is_oauth_mode() -> bool:
    """Return True when OAuth token authentication is active."""
    return bool(get_settings().claude_oauth_token.strip())


def _inject_system(system: Any) -> list[dict[str, str]]:
    """Prepend the Claude Code identity block to a ``system`` argument.

    Accepts the call-site ``system`` value in any accepted form (omitted,
    string, or a list of content blocks) and returns a normalized block list
    whose first element is the required identity block.
    """
    identity = {"type": "text", "text": _CLAUDE_CODE_IDENTITY}

    if not system:  # None, "", or anthropic.NOT_GIVEN
        return [identity]
    if isinstance(system, str):
        return [identity, {"type": "text", "text": system}]
    if isinstance(system, list):
        return [identity, *system]
    # Unexpected shape -- stringify defensively rather than fail the request.
    return [identity, {"type": "text", "text": str(system)}]


class _OAuthMessages:
    """Sync ``messages`` proxy that injects the identity system block."""

    def __init__(self, real_messages: Any) -> None:
        self._real = real_messages

    def create(self, **kwargs: Any) -> Any:
        kwargs["system"] = _inject_system(kwargs.get("system"))
        return self._real.create(**kwargs)


class _OAuthAsyncMessages:
    """Async ``messages`` proxy that injects the identity system block."""

    def __init__(self, real_messages: Any) -> None:
        self._real = real_messages

    async def create(self, **kwargs: Any) -> Any:
        kwargs["system"] = _inject_system(kwargs.get("system"))
        return await self._real.create(**kwargs)


class _OAuthClient:
    """Wraps an Anthropic client, exposing ``messages`` with system injection."""

    def __init__(self, client: Any, *, is_async: bool) -> None:
        self._client = client
        self.messages = (
            _OAuthAsyncMessages(client.messages) if is_async else _OAuthMessages(client.messages)
        )

    def __getattr__(self, name: str) -> Any:
        # Delegate any other attribute access to the underlying client.
        return getattr(self._client, name)


def _claude_client(resolved: ResolvedLLM | None, *, is_async: bool) -> Any:
    kwargs = _build_client_kwargs(resolved)
    client = anthropic.AsyncAnthropic(**kwargs) if is_async else anthropic.Anthropic(**kwargs)
    oauth = resolved.oauth_token if resolved else get_settings().claude_oauth_token.strip()
    if oauth:
        return _OAuthClient(client, is_async=is_async)
    return client


# ---------------------------------------------------------------------------
# OpenAI-compatible providers (OpenAI / Gemini / DeepSeek / Qwen / GLM / Kimi / Ollama)
# ---------------------------------------------------------------------------


class _CompatTextBlock:
    """Mimics an Anthropic text content block (``.text``)."""

    __slots__ = ("text", "type")

    def __init__(self, text: str) -> None:
        self.type = "text"
        self.text = text


class _CompatResponse:
    """Mimics an Anthropic ``Message`` (``.content[0].text``)."""

    __slots__ = ("content", "model", "raw")

    def __init__(self, text: str, model: str, raw: dict[str, Any]) -> None:
        self.content = [_CompatTextBlock(text)]
        self.model = model
        self.raw = raw


def _system_to_text(system: Any) -> str:
    """Flatten an Anthropic-style ``system`` value into one string."""
    if system is None:
        return ""
    if isinstance(system, str):
        return system
    if isinstance(system, list):
        parts = []
        for block in system:
            if isinstance(block, dict):
                parts.append(str(block.get("text", "")))
            else:
                parts.append(str(getattr(block, "text", block)))
        return "\n\n".join(p for p in parts if p)
    return str(system)


def _build_chat_payload(
    spec: ProviderSpec,
    *,
    model: str,
    max_tokens: int,
    messages: list[dict[str, Any]],
    system: Any = None,
    **_ignored: Any,
) -> dict[str, Any]:
    """Translate Anthropic-style kwargs into a Chat Completions payload."""
    chat_messages: list[dict[str, Any]] = []
    system_text = _system_to_text(system)
    if system_text:
        chat_messages.append({"role": "system", "content": system_text})
    chat_messages.extend(messages)

    return {
        "model": model,
        "messages": chat_messages,
        spec.max_tokens_param: max_tokens,
    }


def _parse_chat_response(data: dict[str, Any], provider_label: str) -> _CompatResponse:
    try:
        choice = data["choices"][0]
        text = choice["message"]["content"] or ""
    except (KeyError, IndexError, TypeError) as exc:
        raise RuntimeError(f"{provider_label} returned an unexpected response shape: {data}") from exc
    return _CompatResponse(text, data.get("model", ""), data)


def _retry_delay(attempt: int) -> float:
    return min(2.0 ** attempt + random.uniform(0, 1), 30.0)


def _should_retry(status_code: int) -> bool:
    return status_code == 429 or status_code >= 500


class _CompatMessages:
    """Sync ``messages`` facade over an OpenAI-compatible endpoint."""

    def __init__(self, cfg: ResolvedLLM) -> None:
        self._cfg = cfg

    def create(self, **kwargs: Any) -> _CompatResponse:
        cfg = self._cfg
        payload = _build_chat_payload(cfg.spec, **kwargs)
        url = f"{cfg.base_url.rstrip('/')}/chat/completions"
        headers = {"Content-Type": "application/json"}
        if cfg.api_key:
            headers["Authorization"] = f"Bearer {cfg.api_key}"

        last_error: Exception | None = None
        for attempt in range(_DEFAULT_MAX_RETRIES + 1):
            try:
                resp = httpx.post(url, json=payload, headers=headers, timeout=_DEFAULT_TIMEOUT)
            except httpx.HTTPError as exc:
                last_error = exc
            else:
                if resp.status_code < 400:
                    return _parse_chat_response(resp.json(), cfg.spec.label)
                if not _should_retry(resp.status_code):
                    raise RuntimeError(
                        f"{cfg.spec.label} request failed ({resp.status_code}): {resp.text[:500]}"
                    )
                last_error = RuntimeError(
                    f"{cfg.spec.label} request failed ({resp.status_code}): {resp.text[:200]}"
                )
            if attempt < _DEFAULT_MAX_RETRIES:
                delay = _retry_delay(attempt)
                logger.warning("%s call failed (%s); retry %d in %.1fs", cfg.spec.label, last_error, attempt + 1, delay)
                time.sleep(delay)
        raise RuntimeError(f"{cfg.spec.label} request failed after retries") from last_error


class _CompatAsyncMessages:
    """Async ``messages`` facade over an OpenAI-compatible endpoint."""

    def __init__(self, cfg: ResolvedLLM) -> None:
        self._cfg = cfg

    async def create(self, **kwargs: Any) -> _CompatResponse:
        import asyncio

        cfg = self._cfg
        payload = _build_chat_payload(cfg.spec, **kwargs)
        url = f"{cfg.base_url.rstrip('/')}/chat/completions"
        headers = {"Content-Type": "application/json"}
        if cfg.api_key:
            headers["Authorization"] = f"Bearer {cfg.api_key}"

        last_error: Exception | None = None
        for attempt in range(_DEFAULT_MAX_RETRIES + 1):
            try:
                async with httpx.AsyncClient(timeout=_DEFAULT_TIMEOUT) as http:
                    resp = await http.post(url, json=payload, headers=headers)
            except httpx.HTTPError as exc:
                last_error = exc
            else:
                if resp.status_code < 400:
                    return _parse_chat_response(resp.json(), cfg.spec.label)
                if not _should_retry(resp.status_code):
                    raise RuntimeError(
                        f"{cfg.spec.label} request failed ({resp.status_code}): {resp.text[:500]}"
                    )
                last_error = RuntimeError(
                    f"{cfg.spec.label} request failed ({resp.status_code}): {resp.text[:200]}"
                )
            if attempt < _DEFAULT_MAX_RETRIES:
                delay = _retry_delay(attempt)
                logger.warning("%s call failed (%s); retry %d in %.1fs", cfg.spec.label, last_error, attempt + 1, delay)
                await asyncio.sleep(delay)
        raise RuntimeError(f"{cfg.spec.label} request failed after retries") from last_error


class _CompatClient:
    """Anthropic-shaped client backed by an OpenAI-compatible endpoint."""

    def __init__(self, cfg: ResolvedLLM, *, is_async: bool) -> None:
        if cfg.spec.requires_api_key and not cfg.api_key:
            raise RuntimeError(
                f"No API key configured for {cfg.spec.label}. Set {cfg.provider.upper()}_API_KEY "
                "in your environment or fill it in on the Dashboard settings page."
            )
        self._cfg = cfg
        self.messages = _CompatAsyncMessages(cfg) if is_async else _CompatMessages(cfg)


# ---------------------------------------------------------------------------
# Public factory functions
# ---------------------------------------------------------------------------


def get_llm_client():
    """Return a sync client for the configured provider (Anthropic-shaped)."""
    cfg = resolve_llm_config()
    if cfg.provider == "claude":
        return _claude_client(cfg, is_async=False)
    logger.info("Using LLM provider %s (model %s)", cfg.spec.label, cfg.model)
    return _CompatClient(cfg, is_async=False)


def get_llm_async_client():
    """Return an async client for the configured provider (Anthropic-shaped)."""
    cfg = resolve_llm_config()
    if cfg.provider == "claude":
        return _claude_client(cfg, is_async=True)
    logger.info("Using LLM provider %s (model %s)", cfg.spec.label, cfg.model)
    return _CompatClient(cfg, is_async=True)


# Backwards-compatible aliases -- existing call sites keep working unchanged.
def get_claude_client():
    """Deprecated alias of :func:`get_llm_client`."""
    return get_llm_client()


def get_claude_async_client():
    """Deprecated alias of :func:`get_llm_async_client`."""
    return get_llm_async_client()


def _build_messages_kwargs(
    prompt: str | None,
    messages: list[dict[str, Any]] | None,
    system: str | None,
    max_tokens: int,
    model: str | None,
) -> dict[str, Any]:
    """Assemble kwargs for ``messages.create`` shared by sync/async helpers."""
    if messages is None:
        if prompt is None:
            raise ValueError("complete() requires either `prompt` or `messages`.")
        messages = [{"role": "user", "content": prompt}]

    kwargs: dict[str, Any] = {
        "model": model or resolve_llm_config().model,
        "max_tokens": max_tokens,
        "messages": messages,
    }
    if system is not None:
        kwargs["system"] = system
    return kwargs


async def acomplete(
    prompt: str | None = None,
    *,
    system: str | None = None,
    messages: list[dict[str, Any]] | None = None,
    max_tokens: int = 4096,
    model: str | None = None,
    client: Any = None,
) -> str:
    """Run one async LLM completion and return the response text.

    Centralizes the ``messages.create(...) -> content[0].text`` pattern used
    across the codebase. Pass ``prompt`` for a single user turn or ``messages``
    for a full list; ``model`` defaults to the configured provider's model.
    """
    if client is None:
        client = get_llm_async_client()
    resp = await client.messages.create(
        **_build_messages_kwargs(prompt, messages, system, max_tokens, model)
    )
    return resp.content[0].text


def complete(
    prompt: str | None = None,
    *,
    system: str | None = None,
    messages: list[dict[str, Any]] | None = None,
    max_tokens: int = 4096,
    model: str | None = None,
    client: Any = None,
) -> str:
    """Synchronous counterpart of :func:`acomplete`."""
    if client is None:
        client = get_llm_client()
    resp = client.messages.create(
        **_build_messages_kwargs(prompt, messages, system, max_tokens, model)
    )
    return resp.content[0].text
