"""Shared Claude client factory.

Supports two modes:
- "api": Standard Anthropic API with API key
- "local": Claude Max local proxy via claude-max-api (OpenAI-compatible endpoint)

In "local" mode, we wrap the OpenAI-compatible endpoint at localhost:3456
to match the Anthropic SDK interface so all calling code works unchanged.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

import httpx

from autodev.config import get_settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Response shim: makes OpenAI responses look like Anthropic responses
# ---------------------------------------------------------------------------


@dataclass
class _TextBlock:
    text: str
    type: str = "text"


@dataclass
class _ShimResponse:
    """Mimics anthropic.types.Message just enough for our call sites."""
    content: list[_TextBlock] = field(default_factory=list)
    model: str = ""
    stop_reason: str = "end_turn"


# ---------------------------------------------------------------------------
# Local proxy client (sync) — wraps OpenAI-compatible chat/completions
# ---------------------------------------------------------------------------


class _LocalMessages:
    """Drop-in replacement for ``anthropic.Anthropic().messages``."""

    def __init__(self, base_url: str) -> None:
        self._url = f"{base_url.rstrip('/')}/v1/chat/completions"

    def create(
        self,
        *,
        model: str,
        max_tokens: int = 4096,
        messages: list[dict[str, Any]],
        system: str | None = None,
        **kwargs: Any,
    ) -> _ShimResponse:
        # Prepend system message in OpenAI format
        oai_messages: list[dict[str, str]] = []
        if system:
            oai_messages.append({"role": "system", "content": system})
        for m in messages:
            oai_messages.append({"role": m["role"], "content": m["content"]})

        payload = {
            "model": model,
            "max_tokens": max_tokens,
            "messages": oai_messages,
        }

        resp = httpx.post(
            self._url,
            json=payload,
            timeout=300.0,
        )
        resp.raise_for_status()
        data = resp.json()

        text = data["choices"][0]["message"]["content"]
        return _ShimResponse(
            content=[_TextBlock(text=text)],
            model=data.get("model", model),
        )


class _LocalAsyncMessages:
    """Async version of the local proxy wrapper."""

    def __init__(self, base_url: str) -> None:
        self._url = f"{base_url.rstrip('/')}/v1/chat/completions"

    async def create(
        self,
        *,
        model: str,
        max_tokens: int = 4096,
        messages: list[dict[str, Any]],
        system: str | None = None,
        **kwargs: Any,
    ) -> _ShimResponse:
        oai_messages: list[dict[str, str]] = []
        if system:
            oai_messages.append({"role": "system", "content": system})
        for m in messages:
            oai_messages.append({"role": m["role"], "content": m["content"]})

        payload = {
            "model": model,
            "max_tokens": max_tokens,
            "messages": oai_messages,
        }

        async with httpx.AsyncClient(timeout=300.0) as client:
            resp = await client.post(self._url, json=payload)
            resp.raise_for_status()
            data = resp.json()

        text = data["choices"][0]["message"]["content"]
        return _ShimResponse(
            content=[_TextBlock(text=text)],
            model=data.get("model", model),
        )


class _LocalClient:
    """Sync client that mimics ``anthropic.Anthropic`` interface."""

    def __init__(self, base_url: str) -> None:
        self.messages = _LocalMessages(base_url)


class _LocalAsyncClient:
    """Async client that mimics ``anthropic.AsyncAnthropic`` interface."""

    def __init__(self, base_url: str) -> None:
        self.messages = _LocalAsyncMessages(base_url)


# ---------------------------------------------------------------------------
# Public factory functions
# ---------------------------------------------------------------------------

_DEFAULT_LOCAL_URL = "http://127.0.0.1:3456"


def get_claude_client():
    """Return a sync client (Anthropic SDK or local proxy shim)."""
    settings = get_settings()

    if settings.claude_mode == "local":
        url = settings.claude_base_url or _DEFAULT_LOCAL_URL
        logger.info("Using Claude Max local proxy (sync) at %s", url)
        return _LocalClient(url)

    import anthropic
    return anthropic.Anthropic(api_key=settings.claude_api_key)


def get_claude_async_client():
    """Return an async client (Anthropic SDK or local proxy shim)."""
    settings = get_settings()

    if settings.claude_mode == "local":
        url = settings.claude_base_url or _DEFAULT_LOCAL_URL
        logger.info("Using Claude Max local proxy (async) at %s", url)
        return _LocalAsyncClient(url)

    import anthropic
    return anthropic.AsyncAnthropic(api_key=settings.claude_api_key)
