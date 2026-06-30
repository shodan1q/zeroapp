"""Shared Claude client factory.

Uses the official Anthropic SDK natively. Two user-supplied authentication
methods are supported:

- API Key (``CLAUDE_API_KEY``): standard Anthropic API, billed per token.
- OAuth Token (``CLAUDE_OAUTH_TOKEN``): a Claude Pro/Max subscription token
  (obtained via ``claude setup-token``), sent as a Bearer token directly to
  the official API at no extra per-token cost.

OAuth Token takes priority when both are configured. An optional
``CLAUDE_BASE_URL`` may point at a custom gateway; it defaults to the official
Anthropic endpoint.

Subscription OAuth tokens are only accepted by the Messages API when the first
``system`` block is the Claude Code identity string. To keep every call site
unchanged, the OAuth clients transparently prepend that block on each request;
API-key clients pass requests through untouched.
"""

from __future__ import annotations

import logging
from typing import Any

import anthropic

from zerodev.config import get_settings

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


def _build_client_kwargs() -> dict[str, Any]:
    """Resolve authentication and shared client options from settings.

    OAuth token is preferred over API key. Raises a clear error when neither
    credential is configured.
    """
    settings = get_settings()

    kwargs: dict[str, Any] = {
        "max_retries": _DEFAULT_MAX_RETRIES,
        "timeout": _DEFAULT_TIMEOUT,
    }

    if settings.claude_base_url:
        kwargs["base_url"] = settings.claude_base_url

    oauth_token = settings.claude_oauth_token.strip()
    api_key = settings.claude_api_key.strip()

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
            "(from `claude setup-token`) or CLAUDE_API_KEY in your environment."
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


# ---------------------------------------------------------------------------
# OAuth wrappers: transparently inject the identity system block
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Public factory functions
# ---------------------------------------------------------------------------


def get_claude_client():
    """Return a sync ``anthropic.Anthropic`` client (OAuth-wrapped if needed)."""
    client = anthropic.Anthropic(**_build_client_kwargs())
    if _is_oauth_mode():
        return _OAuthClient(client, is_async=False)
    return client


def get_claude_async_client():
    """Return an async ``anthropic.AsyncAnthropic`` client (OAuth-wrapped if needed)."""
    client = anthropic.AsyncAnthropic(**_build_client_kwargs())
    if _is_oauth_mode():
        return _OAuthClient(client, is_async=True)
    return client
