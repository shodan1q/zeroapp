"""Feasibility evaluator -- uses LLM to assess technical feasibility."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Dict

import anthropic

from autodev.config import get_settings
from autodev.llm import get_claude_client

FEASIBILITY_PROMPT = """Evaluate the technical feasibility of building this mobile app as a Flutter application.

App: {title}
Description: {description}
Core features: {features}

Consider:
1. Can this be built with Flutter and common pub.dev packages?
2. Does it require complex native integrations?
3. Can a single developer build an MVP in under 2 weeks?
4. Are there API dependencies that could block development?

Respond with JSON:
{{
  "feasible": true/false,
  "complexity": "low/medium/high",
  "page_count": integer,
  "needs_backend": true/false,
  "needs_hardware": true/false,
  "needs_login": true/false,
  "reasoning": "brief explanation"
}}"""

_VALID_COMPLEXITIES = {"low", "medium", "high"}


@dataclass
class FeasibilityResult:
    """Structured feasibility assessment result."""

    feasible: bool
    complexity: str
    page_count: int
    needs_backend: bool
    needs_hardware: bool
    needs_login: bool
    reasoning: str


class FeasibilityEvaluator:
    """Evaluate whether a demand can be realistically built."""

    def __init__(self) -> None:
        settings = get_settings()
        self._client = get_claude_client()
        self._model = settings.claude_model

    async def evaluate(self, title: str, description: str, features: list[str]) -> dict:
        """Return feasibility assessment for a demand.

        Returns:
            Dict with feasibility_score, reasoning, blockers, estimated_complexity.
        """
        prompt = FEASIBILITY_PROMPT.format(
            title=title,
            description=description,
            features=", ".join(features) if features else "not specified",
        )

        response = self._client.messages.create(
            model=self._model,
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )

        text = response.content[0].text.strip()
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return {"feasibility_score": 0.5, "reasoning": "Failed to parse LLM response", "blockers": [], "estimated_complexity": "medium"}


def _strip_markdown_fences(text: str) -> str:
    """Remove markdown code fences from LLM output."""
    text = text.strip()
    match = re.match(r"^```(?:json)?\s*\n(.*?)\n```$", text, re.DOTALL)
    if match:
        return match.group(1).strip()
    return text


async def evaluate_feasibility(
    demand: Dict[str, Any],
    *,
    api_key: str = "",
) -> FeasibilityResult:
    """Convenience async function to evaluate feasibility via Claude.

    Args:
        demand: Dict with title, description, core_features keys.
        api_key: Anthropic API key.

    Returns:
        FeasibilityResult dataclass.

    Raises:
        ValueError: If Claude returns non-JSON.
    """
    client = anthropic.AsyncAnthropic(api_key=api_key)
    settings = get_settings()

    title = demand.get("title", "")
    description = demand.get("description", "")
    features = demand.get("core_features", [])

    prompt = FEASIBILITY_PROMPT.format(
        title=title,
        description=description,
        features=", ".join(features) if features else "not specified",
    )

    response = await client.messages.create(
        model=settings.claude_model,
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
    )

    raw_text = response.content[0].text.strip()
    text = _strip_markdown_fences(raw_text)

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        raise ValueError(f"Claude returned non-JSON response: {raw_text[:200]}")

    # Normalise complexity
    complexity = data.get("complexity", "high")
    if complexity not in _VALID_COMPLEXITIES:
        complexity = "high"

    return FeasibilityResult(
        feasible=bool(data.get("feasible", False)),
        complexity=complexity,
        page_count=int(data.get("page_count", 0)),
        needs_backend=bool(data.get("needs_backend", False)),
        needs_hardware=bool(data.get("needs_hardware", False)),
        needs_login=bool(data.get("needs_login", False)),
        reasoning=data.get("reasoning", ""),
    )
