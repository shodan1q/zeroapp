"""Select the appropriate Flutter project template based on demand characteristics.

Uses Claude API to analyse the demand and pick the best-fitting template from a
fixed catalogue of six template types.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

from autodev.llm import get_claude_client

from autodev.config import get_settings

logger = logging.getLogger(__name__)

TEMPLATE_DIR = Path(__file__).parent / "templates"

VALID_TEMPLATES = [
    "single_page_tool",
    "list_display",
    "timer",
    "tracker",
    "info_aggregator",
    "mini_game",
]

TEMPLATE_DESCRIPTIONS: dict[str, str] = {
    "single_page_tool": (
        "A single-screen utility app (converter, calculator, generator, etc.). "
        "Minimal navigation, focused on one core interaction."
    ),
    "list_display": (
        "An app centred on displaying, filtering, and searching a list of items. "
        "Examples: recipe browser, todo list, bookmark manager."
    ),
    "timer": (
        "An app whose primary function revolves around time: countdown, stopwatch, "
        "Pomodoro, interval timer, alarm, or scheduling."
    ),
    "tracker": (
        "An app that tracks data over time: habit tracker, expense logger, "
        "mood journal, workout log, or any data-recording app."
    ),
    "info_aggregator": (
        "An app that pulls and presents information from APIs or local data: "
        "weather dashboard, news reader, price comparator, dashboard."
    ),
    "mini_game": (
        "A simple casual game: quiz, trivia, puzzle, memory match, "
        "clicker, or any entertainment-focused app."
    ),
}

SELECTION_PROMPT = """\
You are a senior Flutter architect selecting the best project template for a new app.

Available templates:
{template_list}

App demand:
  Title: {title}
  Description: {description}

Analyse the demand and select the SINGLE best-fitting template.
Reply ONLY with valid JSON (no markdown fences):

{{
  "template": "<template_name>",
  "reasoning": "<1-2 sentence explanation of why this template fits best>"
}}
"""


def _build_template_list() -> str:
    """Format template descriptions for the prompt."""
    return "\n".join(f"  - {name}: {desc}" for name, desc in TEMPLATE_DESCRIPTIONS.items())


def _parse_json_response(raw_text: str) -> dict[str, Any]:
    """Parse JSON from Claude's response, handling markdown fences."""
    try:
        return json.loads(raw_text)  # type: ignore[no-any-return]
    except json.JSONDecodeError:
        match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw_text, re.DOTALL)
        if match:
            return json.loads(match.group(1))  # type: ignore[no-any-return]
        raise ValueError(f"Could not parse JSON from response: {raw_text[:300]}")


class TemplateSelector:
    """Choose a Flutter project template based on app category and features.

    Uses Claude API to intelligently match a demand description to the most
    appropriate template type.
    """

    def __init__(self) -> None:
        settings = get_settings()
        self._client = get_claude_client()
        self._model = settings.claude_model

    # ------------------------------------------------------------------
    # Synchronous fallback (keyword-based)
    # ------------------------------------------------------------------

    def select(self, category: str | None, features: list[str] | None) -> Path:
        """Return path to the best matching template directory (sync fallback).

        Uses simple keyword heuristics. For Claude-powered selection, use
        :meth:`select_for_demand` instead.

        Args:
            category: App category (productivity, social, etc.).
            features: List of core feature strings.

        Returns:
            Path to the template directory.
        """
        template = self._keyword_match(category, features)
        return TEMPLATE_DIR / template

    @staticmethod
    def _keyword_match(category: str | None, features: list[str] | None) -> str:
        """Simple keyword-based template matching."""
        text = f"{category or ''} {' '.join(features or [])}".lower()

        keyword_map: dict[str, list[str]] = {
            "timer": ["timer", "countdown", "stopwatch", "pomodoro", "alarm", "clock"],
            "tracker": ["tracker", "habit", "log", "journal", "expense", "mood", "track"],
            "list_display": ["list", "browse", "catalog", "collection", "recipe", "bookmark", "todo"],
            "info_aggregator": ["weather", "news", "dashboard", "aggregate", "feed", "api", "price"],
            "mini_game": ["game", "quiz", "trivia", "puzzle", "match", "play", "score"],
        }

        for template, keywords in keyword_map.items():
            if any(kw in text for kw in keywords):
                return template

        return "single_page_tool"

    # ------------------------------------------------------------------
    # Claude-powered selection
    # ------------------------------------------------------------------

    async def select_for_demand(
        self,
        title: str,
        description: str,
    ) -> dict[str, str]:
        """Use Claude to select the best template for a demand.

        Args:
            title: The app demand title.
            description: The app demand description.

        Returns:
            Dict with ``template`` (template name) and ``reasoning``.
        """
        prompt = SELECTION_PROMPT.format(
            template_list=_build_template_list(),
            title=title,
            description=description,
        )

        logger.info("Selecting template for '%s' via Claude", title)

        try:
            response = self._client.messages.create(
                model=self._model,
                max_tokens=512,
                messages=[{"role": "user", "content": prompt}],
            )
        except anthropic.APIError:
            logger.exception("Claude API call failed during template selection")
            raise

        raw_text = response.content[0].text.strip()
        logger.debug("Claude template selection response: %s", raw_text)

        data = _parse_json_response(raw_text)

        template = str(data.get("template", "single_page_tool")).strip()
        if template not in VALID_TEMPLATES:
            logger.warning(
                "Claude selected unknown template '%s'; falling back to single_page_tool.",
                template,
            )
            template = "single_page_tool"

        reasoning = str(data.get("reasoning", ""))

        logger.info("Selected template '%s': %s", template, reasoning)
        return {"template": template, "reasoning": reasoning}
