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
"""

from __future__ import annotations

import logging
from typing import Any

from zerodev.config import get_settings

logger = logging.getLogger(__name__)

# Beta header required when calling the official API with a Claude Code /
# subscription OAuth token instead of an API key.
_OAUTH_BETA_HEADER = "oauth-2025-04-20"

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


def get_claude_client():
    """Return a sync ``anthropic.Anthropic`` client."""
    import anthropic

    return anthropic.Anthropic(**_build_client_kwargs())


def get_claude_async_client():
    """Return an async ``anthropic.AsyncAnthropic`` client."""
    import anthropic

    return anthropic.AsyncAnthropic(**_build_client_kwargs())
