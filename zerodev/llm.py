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
import re
import time
from dataclasses import dataclass, field
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
        raise LLMConfigError(
            "No Claude credentials configured. Set CLAUDE_OAUTH_TOKEN "
            "(from `claude setup-token`) or CLAUDE_API_KEY in your environment, "
            "or fill them in on the Dashboard settings page."
        )

    return kwargs


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


class LLMError(RuntimeError):
    """Raised for provider request failures on the OpenAI-compatible path.

    Subclasses ``RuntimeError`` for backwards compatibility. Call sites that
    implement per-item resilience should catch ``(anthropic.APIError, LLMError)``
    so both the Claude path and the compat path degrade the same way.
    """

    # Consumed by zerodev.pipeline.retry: a transient request failure is worth
    # another attempt.
    retryable = True


class LLMOverloadedError(LLMError):
    """The provider accepted the request but produced nothing usable.

    Relays under concurrent load answer with an empty SSE stream rather than a
    429, so this is what rate limiting actually looks like from the client side.
    It is retryable, but only after backing off far longer than a transient
    network blip -- retrying hard is what turned an overloaded provider into a
    collapsed batch.
    """

    backoff_multiplier = 6.0


class LLMConfigError(LLMError):
    """The provider is not configured well enough to make any request.

    Distinct from a request failure because no amount of retrying fixes a
    missing base URL or API key -- the pipeline should surface it immediately
    instead of burning the retry budget on a backoff schedule. Still an
    ``LLMError`` (and therefore a ``RuntimeError``) so every existing handler
    keeps working.
    """

    retryable = False


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
    **ignored: Any,
) -> dict[str, Any]:
    """Translate Anthropic-style kwargs into a Chat Completions payload."""
    if ignored:
        # Anthropic-only kwargs have no compat equivalent; surface the drop so
        # a future call site doesn't silently lose behavior on other providers.
        logger.warning("Dropping unsupported kwargs for %s: %s", spec.label, sorted(ignored))
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


def _extract_prefill(messages: list[dict[str, Any]]) -> str:
    """Return the assistant-prefill text when the last message is a prefill.

    Anthropic's prefill contract: a trailing assistant message is *continued*
    by the model and excluded from the response. Chat Completions endpoints
    have no such contract -- the model usually restarts from scratch. We keep
    sending the message as context and reconcile in :func:`_apply_prefill`.
    """
    if messages and messages[-1].get("role") == "assistant":
        content = messages[-1].get("content")
        if isinstance(content, str):
            return content
    return ""


def _apply_prefill(prefill: str, text: str) -> str:
    """Normalize a compat response to Anthropic prefill semantics.

    Callers reconstruct ``full = prefill + response_text``. If the model
    re-emitted the prefill at the start of its reply, strip it so the
    reconstruction doesn't duplicate it (``importimport ...``).
    """
    if prefill and text.startswith(prefill):
        return text[len(prefill):]
    return text


_THINK_BLOCK_RE = re.compile(r"^\s*<think>.*?</think>\s*", re.DOTALL)


def _parse_chat_response(data: dict[str, Any], provider_label: str) -> _CompatResponse:
    try:
        choice = data["choices"][0]
        text = choice["message"]["content"] or ""
    except (KeyError, IndexError, TypeError) as exc:
        raise LLMError(f"{provider_label} returned an unexpected response shape: {data}") from exc

    # Reasoning models (deepseek-r1 via Ollama, etc.) may inline a leading
    # <think>...</think> block; downstream JSON/code parsers must never see it.
    text = _THINK_BLOCK_RE.sub("", text, count=1)

    if not text.strip():
        finish = choice.get("finish_reason", "unknown")
        refusal = (choice.get("message") or {}).get("refusal")
        raise LLMError(
            f"{provider_label} returned empty content (finish_reason={finish!r}"
            + (f", refusal={refusal!r}" if refusal else "")
            + "). If finish_reason is 'length', raise max_tokens -- reasoning "
            "models spend part of the budget on hidden reasoning tokens."
        )
    return _CompatResponse(text, data.get("model", ""), data)


def _retry_delay(attempt: int, error: BaseException | None = None) -> float:
    """Backoff for one retry, stretched when the provider signals overload.

    A saturated relay answers with an empty stream rather than a 429, and
    retrying that on the ordinary schedule is what turns overload into a
    collapsed batch -- so those errors carry a multiplier.
    """
    multiplier = float(getattr(error, "backoff_multiplier", 1.0))
    return min((2.0**attempt + random.uniform(0, 1)) * multiplier, 120.0)


def _should_retry(status_code: int) -> bool:
    return status_code == 429 or status_code >= 500


# The output-token cap is spelled differently across OpenAI API generations:
# older chat models take ``max_tokens``, the GPT-5 series takes
# ``max_completion_tokens``. Relays and aggregators front a mix of both and the
# registry default cannot know which, so a rejection on this parameter is
# recovered by swapping the name once rather than failing the whole run.
_MAX_TOKENS_ALIASES: dict[str, str] = {
    "max_tokens": "max_completion_tokens",
    "max_completion_tokens": "max_tokens",
}


def _swap_max_tokens_param(payload: dict[str, Any], response_body: str) -> str | None:
    """Rewrite ``payload`` to use the other token-cap parameter name.

    Returns the new parameter name when the swap applies, ``None`` otherwise
    (so the caller can surface the original error untouched).
    """
    lowered = response_body.lower()
    if "max_tokens" not in lowered and "max_completion_tokens" not in lowered:
        return None
    for current, replacement in _MAX_TOKENS_ALIASES.items():
        if current in payload:
            payload[replacement] = payload.pop(current)
            return replacement
    return None


# Streaming is the default on this path, and that is a robustness decision
# rather than a UX one. Relays, API gateways and corporate proxies commonly
# buffer a non-streaming completion end to end, so nothing crosses the wire
# until the model has finished. Any idle timeout in that chain then kills the
# connection, and a long generation becomes a 502 or a hang that no retry can
# fix. An SSE stream keeps bytes flowing, so the same request completes.
# Measured against one relay: a 16k-token request hung past 400s unstreamed and
# finished in ~74s streamed.
_STREAM_BY_DEFAULT = True

_SSE_DONE = "[DONE]"

# Streaming timeouts are per-operation, not per-request: `read` bounds the gap
# between chunks, so a generation may run far longer than any single value here
# as long as it keeps producing output.
_STREAM_TIMEOUT = httpx.Timeout(connect=30.0, read=300.0, write=60.0, pool=30.0)

# Body markers that mean "this endpoint does not do SSE", so the client should
# drop back to a plain request instead of retrying the same way.
_NO_STREAM_MARKERS = ("stream", "sse", "not supported", "unsupported")


class _HTTPFailureError(Exception):
    """A non-2xx response, carried so the retry loop can inspect it."""

    def __init__(self, status: int, body: str) -> None:
        super().__init__(f"HTTP {status}")
        self.status = status
        self.body = body


class _StreamAccumulator:
    """Reassemble an SSE chat-completion stream into a single response."""

    def __init__(self) -> None:
        self._chunks: list[str] = []
        self.model = ""
        self.finish_reason = ""
        self.saw_chunk = False

    def feed(self, raw_line: str) -> bool:
        """Consume one SSE line; returns True once the stream is complete."""
        line = raw_line.strip()
        # Blank lines separate events and ``:`` lines are keep-alive comments.
        if not line or line.startswith(":") or not line.startswith("data:"):
            return False
        body = line[5:].strip()
        if body == _SSE_DONE:
            return True
        try:
            payload = json.loads(body)
        except json.JSONDecodeError:
            # A partial or vendor-specific frame is not worth failing the whole
            # generation over; the stream carries its own completion signal.
            logger.debug("Skipping unparseable SSE frame: %s", body[:120])
            return False

        self.saw_chunk = True
        if payload.get("model"):
            self.model = str(payload["model"])
        for choice in payload.get("choices") or []:
            delta = choice.get("delta") or {}
            text = delta.get("content")
            if isinstance(text, str):
                self._chunks.append(text)
            if choice.get("finish_reason"):
                self.finish_reason = str(choice["finish_reason"])
        return False

    def to_response(self, provider_label: str) -> _CompatResponse:
        text = "".join(self._chunks)
        if not text.strip():
            detail = "no frames received" if not self.saw_chunk else f"finish_reason={self.finish_reason or 'unset'}"
            # An empty completion is treated as a transport-level failure so the
            # retry loop gets a chance. Under concurrency this is how a relay
            # signals overload, so it backs off harder than a normal retry.
            raise LLMOverloadedError(f"{provider_label} returned an empty stream ({detail}).")
        return _CompatResponse(text, self.model, {"stream": True, "finish_reason": self.finish_reason})


def _stream_request_payload(payload: dict[str, Any]) -> dict[str, Any]:
    return {**payload, "stream": True}


def _looks_like_streaming_unsupported(status: int, body: str) -> bool:
    """Whether a rejection means the endpoint cannot stream at all."""
    if status not in (400, 404, 405, 501):
        return False
    lowered = body.lower()
    return any(marker in lowered for marker in _NO_STREAM_MARKERS)


class _CompatTransportMixin:
    """Retry/fallback policy shared by the sync and async compat clients."""

    _cfg: ResolvedLLM

    def _prepare(self, kwargs: dict[str, Any]) -> tuple[str, dict[str, str], dict[str, Any], str]:
        cfg = self._cfg
        prefill = _extract_prefill(kwargs.get("messages") or [])
        payload = _build_chat_payload(cfg.spec, **kwargs)
        url = f"{cfg.base_url.rstrip('/')}/chat/completions"
        headers = {"Content-Type": "application/json"}
        if cfg.api_key:
            headers["Authorization"] = f"Bearer {cfg.api_key}"
        return url, headers, payload, prefill

    def _handle_failure(self, exc: _HTTPFailureError, payload: dict[str, Any], state: dict[str, Any]) -> Exception:
        """Classify a non-2xx response, mutating ``payload``/``state`` to adapt.

        Returns the error to record for the retry loop, or raises when the
        failure is terminal.
        """
        label = self._cfg.spec.label
        if state["stream"] and _looks_like_streaming_unsupported(exc.status, exc.body):
            state["stream"] = False
            logger.info("%s rejected streaming (%d); falling back to a plain request.", label, exc.status)
            return LLMError(f"{label} rejected streaming ({exc.status})")

        if not _should_retry(exc.status):
            if not state["swapped"]:
                renamed = _swap_max_tokens_param(payload, exc.body)
                if renamed:
                    state["swapped"] = True
                    logger.info("%s rejected the token-cap parameter; retrying with %s.", label, renamed)
                    return LLMError(f"{label} rejected the token-cap parameter")
            raise LLMError(f"{label} request failed ({exc.status}): {exc.body[:500]}")

        return LLMError(f"{label} request failed ({exc.status}): {exc.body[:200]}")


class _CompatMessages(_CompatTransportMixin):
    """Sync ``messages`` facade over an OpenAI-compatible endpoint."""

    def __init__(self, cfg: ResolvedLLM) -> None:
        self._cfg = cfg

    def _send(self, url: str, headers: dict[str, str], payload: dict[str, Any], stream: bool) -> _CompatResponse:
        label = self._cfg.spec.label
        if not stream:
            resp = httpx.post(url, json=payload, headers=headers, timeout=_DEFAULT_TIMEOUT)
            if resp.status_code >= 400:
                raise _HTTPFailureError(resp.status_code, resp.text)
            try:
                data = resp.json()
            except json.JSONDecodeError as exc:
                # e.g. a proxy returning HTML with 200 -- retryable.
                raise LLMError(f"{label} returned non-JSON body: {exc}") from exc
            return _parse_chat_response(data, label)

        with httpx.stream(
            "POST", url, json=_stream_request_payload(payload), headers=headers, timeout=_STREAM_TIMEOUT
        ) as resp:
            if resp.status_code >= 400:
                resp.read()
                raise _HTTPFailureError(resp.status_code, resp.text)
            accumulator = _StreamAccumulator()
            for line in resp.iter_lines():
                if accumulator.feed(line):
                    break
        return accumulator.to_response(label)

    def create(self, **kwargs: Any) -> _CompatResponse:
        label = self._cfg.spec.label
        url, headers, payload, prefill = self._prepare(kwargs)
        state = {"stream": _STREAM_BY_DEFAULT, "swapped": False}

        last_error: Exception | None = None
        for attempt in range(_DEFAULT_MAX_RETRIES + 1):
            try:
                result = self._send(url, headers, payload, state["stream"])
            except _HTTPFailureError as exc:
                last_error = self._handle_failure(exc, payload, state)
            except (httpx.HTTPError, LLMError) as exc:
                last_error = exc
            else:
                result.content[0].text = _apply_prefill(prefill, result.content[0].text)
                return result

            if attempt < _DEFAULT_MAX_RETRIES:
                delay = _retry_delay(attempt, last_error)
                logger.warning("%s call failed (%s); retry %d in %.1fs", label, last_error, attempt + 1, delay)
                time.sleep(delay)
        raise LLMError(f"{label} request failed after retries") from last_error


class _CompatAsyncMessages(_CompatTransportMixin):
    """Async ``messages`` facade over an OpenAI-compatible endpoint."""

    def __init__(self, cfg: ResolvedLLM) -> None:
        self._cfg = cfg

    async def _send(
        self, url: str, headers: dict[str, str], payload: dict[str, Any], stream: bool
    ) -> _CompatResponse:
        label = self._cfg.spec.label
        if not stream:
            async with httpx.AsyncClient(timeout=_DEFAULT_TIMEOUT) as http:
                resp = await http.post(url, json=payload, headers=headers)
            if resp.status_code >= 400:
                raise _HTTPFailureError(resp.status_code, resp.text)
            try:
                data = resp.json()
            except json.JSONDecodeError as exc:
                raise LLMError(f"{label} returned non-JSON body: {exc}") from exc
            return _parse_chat_response(data, label)

        accumulator = _StreamAccumulator()
        async with httpx.AsyncClient(timeout=_STREAM_TIMEOUT) as http:
            async with http.stream(
                "POST", url, json=_stream_request_payload(payload), headers=headers
            ) as resp:
                if resp.status_code >= 400:
                    await resp.aread()
                    raise _HTTPFailureError(resp.status_code, resp.text)
                async for line in resp.aiter_lines():
                    if accumulator.feed(line):
                        break
        return accumulator.to_response(label)

    async def create(self, **kwargs: Any) -> _CompatResponse:
        import asyncio

        label = self._cfg.spec.label
        url, headers, payload, prefill = self._prepare(kwargs)
        state = {"stream": _STREAM_BY_DEFAULT, "swapped": False}

        last_error: Exception | None = None
        for attempt in range(_DEFAULT_MAX_RETRIES + 1):
            try:
                result = await self._send(url, headers, payload, state["stream"])
            except _HTTPFailureError as exc:
                last_error = self._handle_failure(exc, payload, state)
            except (httpx.HTTPError, LLMError) as exc:
                last_error = exc
            else:
                result.content[0].text = _apply_prefill(prefill, result.content[0].text)
                return result

            if attempt < _DEFAULT_MAX_RETRIES:
                delay = _retry_delay(attempt, last_error)
                logger.warning("%s call failed (%s); retry %d in %.1fs", label, last_error, attempt + 1, delay)
                await asyncio.sleep(delay)
        raise LLMError(f"{label} request failed after retries") from last_error


class _CompatClient:
    """Anthropic-shaped client backed by an OpenAI-compatible endpoint."""

    def __init__(self, cfg: ResolvedLLM, *, is_async: bool) -> None:
        for problem in describe_config_gaps(cfg):
            raise LLMConfigError(problem)
        self._cfg = cfg
        self.messages = _CompatAsyncMessages(cfg) if is_async else _CompatMessages(cfg)


def describe_config_gaps(cfg: ResolvedLLM) -> list[str]:
    """Return actionable messages for anything missing from ``cfg``.

    Providers with blank registry defaults (relays) need an explicit base URL
    and model, so failing here with a specific instruction beats a confusing
    404 or "model not found" from the far end.
    """
    prefix = cfg.provider.upper()
    gaps: list[str] = []

    if cfg.spec.kind == "anthropic":
        if not (cfg.api_key or cfg.oauth_token):
            gaps.append(
                "No Claude credential configured. Set CLAUDE_OAUTH_TOKEN (from `claude setup-token`, "
                "billed to a Pro/Max subscription) or CLAUDE_API_KEY (metered Anthropic API)."
            )
        return gaps

    if cfg.spec.requires_api_key and not cfg.api_key:
        gaps.append(
            f"No API key configured for {cfg.spec.label}. Set {prefix}_API_KEY in your "
            "environment or fill it in on the Dashboard settings page."
        )
    if not cfg.base_url:
        gaps.append(
            f"No base URL configured for {cfg.spec.label}. Set {prefix}_BASE_URL to the "
            "endpoint your provider documents (it must end in the OpenAI-compatible path, "
            "usually /v1)."
        )
    if not cfg.model:
        gaps.append(
            f"No model configured for {cfg.spec.label}. Set {prefix}_MODEL, or run "
            "`zerodev llm probe` to list the model names this endpoint actually serves."
        )
    return gaps


# ---------------------------------------------------------------------------
# Connectivity probe
# ---------------------------------------------------------------------------


@dataclass
class ProbeResult:
    """Outcome of checking that the configured provider actually answers."""

    provider: str
    label: str
    base_url: str
    model: str
    models_available: list[str] = field(default_factory=list)
    models_error: str = ""
    chat_ok: bool = False
    chat_reply: str = ""
    chat_error: str = ""
    config_gaps: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.chat_ok and not self.config_gaps

    def suggest_models(self, hint: str = "") -> list[str]:
        """Model ids from the endpoint that look like ``hint``, best first."""
        if not self.models_available:
            return []
        if not hint:
            return self.models_available[:20]
        needle = re.sub(r"[^a-z0-9.]", "", hint.lower())
        scored: list[tuple[int, str]] = []
        for name in self.models_available:
            flat = re.sub(r"[^a-z0-9.]", "", name.lower())
            if flat == needle:
                scored.append((0, name))
            elif needle and needle in flat:
                scored.append((1, name))
            elif flat and flat in needle:
                scored.append((2, name))
        return [name for _, name in sorted(scored)]


async def aprobe_provider(*, list_models: bool = True, smoke_test: bool = True) -> ProbeResult:
    """Check the configured provider end to end without running a pipeline.

    Lists the endpoint's models (so a relay's real aliases become visible) and
    sends a one-token chat request to prove the credential and model work.
    """
    cfg = resolve_llm_config()
    result = ProbeResult(
        provider=cfg.provider,
        label=cfg.spec.label,
        base_url=cfg.base_url or ("(official endpoint)" if cfg.spec.kind == "anthropic" else "(unset)"),
        model=cfg.model,
        config_gaps=describe_config_gaps(cfg),
    )

    if cfg.spec.kind == "openai_compat" and list_models and cfg.base_url:
        try:
            async with httpx.AsyncClient(timeout=30.0) as http:
                resp = await http.get(
                    f"{cfg.base_url.rstrip('/')}/models",
                    headers={"Authorization": f"Bearer {cfg.api_key}"} if cfg.api_key else {},
                )
            if resp.status_code >= 400:
                result.models_error = f"HTTP {resp.status_code}: {resp.text[:300]}"
            else:
                payload = resp.json()
                entries = payload.get("data", payload) if isinstance(payload, dict) else payload
                result.models_available = sorted(
                    str(item.get("id", "")) for item in entries if isinstance(item, dict) and item.get("id")
                )
        except (httpx.HTTPError, json.JSONDecodeError, AttributeError, TypeError) as exc:
            result.models_error = str(exc)

    if smoke_test and not result.config_gaps:
        try:
            reply = await acomplete(
                "Reply with the single word: ready",
                max_tokens=64,
                model=cfg.model or None,
            )
            result.chat_ok = bool(reply.strip())
            result.chat_reply = reply.strip()[:200]
        except (LLMError, RuntimeError, anthropic.APIError) as exc:
            result.chat_error = str(exc)[:500]

    return result


def probe_provider(*, list_models: bool = True, smoke_test: bool = True) -> ProbeResult:
    """Synchronous wrapper around :func:`aprobe_provider`."""
    import asyncio

    return asyncio.run(aprobe_provider(list_models=list_models, smoke_test=smoke_test))


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


def get_llm_model() -> str:
    """Return the effective model name for the configured provider.

    Call sites must use this instead of ``settings.claude_model`` so the
    model always matches the active provider (a DeepSeek client must not be
    asked for a Claude model, and vice versa).
    """
    return resolve_llm_config().model


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
