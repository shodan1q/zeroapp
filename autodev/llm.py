"""Shared Claude client factory.

Supports two modes:
- "api": Standard Anthropic API with API key
- "local": Claude Max local proxy (custom base_url, no API key required)
"""

from __future__ import annotations

import logging

import anthropic

from autodev.config import get_settings

logger = logging.getLogger(__name__)


def get_claude_client() -> anthropic.Anthropic:
    """Return a sync Anthropic client based on configured mode."""
    settings = get_settings()

    if settings.claude_mode == "local":
        logger.info("Using Claude local proxy at %s", settings.claude_base_url)
        return anthropic.Anthropic(
            base_url=settings.claude_base_url or "http://localhost:8012/v1",
            api_key=settings.claude_api_key or "not-needed",
        )

    # Default: standard API mode
    return anthropic.Anthropic(api_key=settings.claude_api_key)


def get_claude_async_client() -> anthropic.AsyncAnthropic:
    """Return an async Anthropic client based on configured mode."""
    settings = get_settings()

    if settings.claude_mode == "local":
        logger.info("Using Claude local async proxy at %s", settings.claude_base_url)
        return anthropic.AsyncAnthropic(
            base_url=settings.claude_base_url or "http://localhost:8012/v1",
            api_key=settings.claude_api_key or "not-needed",
        )

    # Default: standard API mode
    return anthropic.AsyncAnthropic(api_key=settings.claude_api_key)
