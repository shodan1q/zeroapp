"""Feasibility evaluator -- uses LLM to assess technical feasibility."""

from __future__ import annotations

import json

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
  "feasibility_score": 0.0 to 1.0,
  "reasoning": "brief explanation",
  "blockers": ["list of potential blockers"],
  "estimated_complexity": "low/medium/high"
}}"""


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
