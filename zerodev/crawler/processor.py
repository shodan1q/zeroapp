"""Raw demand processor -- cleans data and uses LLM to extract structured demands."""

from __future__ import annotations

import json
from typing import Any

from zerodev.config import get_settings
from zerodev.crawler.base import RawDemand
from zerodev.llm import get_claude_client

EXTRACTION_PROMPT = """You are analyzing a post from {source} to determine if it describes a viable mobile app idea.

Post title: {title}
Post body: {body}

Extract the following as JSON (use null for fields you cannot determine):
{{
  "is_app_idea": true/false,
  "title": "concise app name/title",
  "description": "2-3 sentence description",
  "category": "one of: productivity, social, health, finance, education, entertainment, utility, lifestyle, travel, food",
  "target_users": "who would use this app",
  "core_features": ["feature1", "feature2", ...],
  "monetization": "one of: free, freemium, paid, ads, subscription",
  "complexity": "one of: low, medium, high"
}}

Respond ONLY with valid JSON."""


class DemandProcessor:
    """Process raw crawled data into structured demands using Claude."""

    def __init__(self) -> None:
        settings = get_settings()
        self._client = get_claude_client()
        self._model = settings.claude_model

    async def extract(self, raw: RawDemand) -> dict[str, Any] | None:
        """Use Claude to extract structured demand from raw post.

        Returns:
            Parsed dict if the post is a valid app idea, else None.
        """
        prompt = EXTRACTION_PROMPT.format(
            source=raw.source,
            title=raw.title,
            body=raw.body[:3000],
        )

        response = self._client.messages.create(
            model=self._model,
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )

        text = response.content[0].text.strip()
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            return None

        if not data.get("is_app_idea"):
            return None

        data["source"] = raw.source
        data["source_url"] = raw.source_url
        return data

    async def process_batch(self, raws: list[RawDemand]) -> list[dict[str, Any]]:
        """Process a batch of raw demands, filtering non-app-ideas."""
        results: list[dict[str, Any]] = []
        for raw in raws:
            extracted = await self.extract(raw)
            if extracted is not None:
                results.append(extracted)
        return results
