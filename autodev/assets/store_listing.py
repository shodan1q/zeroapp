"""Generate app store listing copy using Claude.

Produces ASO-optimised titles, descriptions, and privacy policies in both
English and Chinese.  All outputs are returned as a Pydantic model.
"""

from __future__ import annotations

import json
import logging
import re
from typing import List, Optional

import anthropic
from pydantic import BaseModel, Field

from autodev.config import get_settings

logger = logging.getLogger(__name__)


# ── Pydantic models ──────────────────────────────────────────────────


class LocalisedListing(BaseModel):
    """Store listing copy for a single locale."""

    locale: str = Field(
        description="BCP-47 locale code (e.g. en-US, zh-CN)"
    )
    title: str = Field(max_length=30, description="App title, ASO optimised")
    short_description: str = Field(
        max_length=80, description="Short promotional text"
    )
    full_description: str = Field(
        max_length=4000, description="Full store description"
    )
    whats_new: str = Field(default="Initial release.", max_length=500)
    keywords: List[str] = Field(
        default_factory=list, description="ASO keyword list"
    )


class StoreListing(BaseModel):
    """Complete store listing for all supported locales."""

    en: LocalisedListing
    zh: LocalisedListing
    privacy_policy_html: str = Field(
        description="Privacy policy as minimal HTML"
    )
    category_suggestion: str = Field(
        default="TOOLS",
        description="Suggested Google Play / App Store category",
    )


# ── Prompt templates ─────────────────────────────────────────────────

_LISTING_SYSTEM = (
    "You are an expert ASO (App Store Optimisation) copywriter who creates "
    "compelling mobile app store listings. You write concise, keyword-rich "
    "copy that maximises organic discovery and conversion. You are fluent "
    "in both English and Simplified Chinese."
)

_LISTING_USER = """\
Generate a complete app store listing for the following app.

App name: {app_name}
Description: {description}
Core features: {features}
Target audience: {audience}

Reply ONLY with valid JSON (no markdown fences) matching this exact schema:

{{
  "en": {{
    "locale": "en-US",
    "title": "<max 30 chars, ASO optimised>",
    "short_description": "<max 80 chars>",
    "full_description": "<max 4000 chars, use bullet points and line breaks>",
    "whats_new": "Initial release.",
    "keywords": ["keyword1", "keyword2", ...]
  }},
  "zh": {{
    "locale": "zh-CN",
    "title": "<max 30 chars, ASO optimised Chinese>",
    "short_description": "<max 80 chars Chinese>",
    "full_description": "<max 4000 chars Chinese>",
    "whats_new": "首次发布。",
    "keywords": ["关键词1", "关键词2", ...]
  }},
  "category_suggestion": "<Google Play category e.g. TOOLS, PRODUCTIVITY>"
}}
"""

_PRIVACY_SYSTEM = (
    "You are a privacy-law expert. Generate a concise, legally sound "
    "privacy policy in HTML format for a mobile application. The policy "
    "should cover: data collection, usage, storage, third-party sharing, "
    "user rights, and contact information. Use a generic developer/company "
    "placeholder that can be replaced later."
)

_PRIVACY_USER = """\
Generate a privacy policy HTML document for:

App name: {app_name}
Description: {description}
Data collected: {data_collected}
Third-party services: {third_party}

Reply with ONLY the HTML (starting with <!DOCTYPE html> or <html>), no \
markdown fences or extra text.  Include both English and Chinese sections \
(use <section lang="en"> and <section lang="zh-CN">)."""


class StoreListingGenerator:
    """Generate store listings and privacy policies via Claude."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
    ) -> None:
        settings = get_settings()
        self._api_key = api_key or settings.claude_api_key
        self._model = model or settings.claude_model

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def generate(
        self,
        app_name: str,
        description: str,
        features: str = "",
        audience: str = "general",
        data_collected: str = "None",
        third_party_services: str = "None",
    ) -> StoreListing:
        """Generate a complete :class:`StoreListing` for *app_name*.

        Makes two Claude API calls in sequence:
        1. Listing copy (title, descriptions, keywords) in EN + ZH.
        2. Bilingual privacy policy HTML.
        """
        listing_data = await self._generate_listing_copy(
            app_name, description, features, audience
        )
        privacy_html = await self._generate_privacy_policy(
            app_name, description, data_collected, third_party_services
        )

        return StoreListing(
            en=LocalisedListing(**listing_data["en"]),
            zh=LocalisedListing(**listing_data["zh"]),
            privacy_policy_html=privacy_html,
            category_suggestion=listing_data.get(
                "category_suggestion", "TOOLS"
            ),
        )

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    async def _call_claude(
        self,
        system: str,
        user_message: str,
        max_tokens: int = 4096,
    ) -> str:
        """Send a single message to Claude and return the text response."""
        client = anthropic.AsyncAnthropic(api_key=self._api_key)
        message = await client.messages.create(
            model=self._model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user_message}],
        )
        return message.content[0].text.strip()

    async def _generate_listing_copy(
        self,
        app_name: str,
        description: str,
        features: str,
        audience: str,
    ) -> dict:
        """Generate listing copy and parse the JSON response."""
        prompt = _LISTING_USER.format(
            app_name=app_name,
            description=description,
            features=features or "See description",
            audience=audience,
        )

        raw = await self._call_claude(_LISTING_SYSTEM, prompt)
        logger.debug("Listing raw response: %s", raw[:500])

        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            match = re.search(
                r"```(?:json)?\s*(\{.*\})\s*```", raw, re.DOTALL
            )
            if match:
                data = json.loads(match.group(1))
            else:
                raise ValueError(
                    f"Failed to parse listing JSON: {raw[:300]}"
                )

        if "en" not in data or "zh" not in data:
            raise ValueError("Listing response missing 'en' or 'zh' keys.")

        # Ensure locale fields and enforce store limits.
        data["en"].setdefault("locale", "en-US")
        data["zh"].setdefault("locale", "zh-CN")

        for lang in ("en", "zh"):
            d = data[lang]
            d["title"] = d.get("title", app_name)[:30]
            d["short_description"] = d.get("short_description", "")[:80]
            d["full_description"] = d.get("full_description", "")[:4000]
            d.setdefault(
                "whats_new",
                "Initial release." if lang == "en" else "首次发布。",
            )
            d.setdefault("keywords", [])

        return data

    async def _generate_privacy_policy(
        self,
        app_name: str,
        description: str,
        data_collected: str,
        third_party: str,
    ) -> str:
        """Generate a bilingual privacy policy HTML document."""
        prompt = _PRIVACY_USER.format(
            app_name=app_name,
            description=description,
            data_collected=data_collected,
            third_party=third_party,
        )

        raw = await self._call_claude(
            _PRIVACY_SYSTEM, prompt, max_tokens=8192
        )

        # Strip any markdown fences.
        if raw.startswith("```"):
            match = re.search(
                r"```(?:html)?\s*(.*)\s*```", raw, re.DOTALL
            )
            if match:
                raw = match.group(1).strip()

        return raw
