"""Tests for demand processing with mocked Claude API calls.

Tests the feasibility evaluator and the end-to-end flow of
demand -> evaluation -> scoring -> decision.
"""

from __future__ import annotations

import json
from typing import Any, Dict
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from zerodev.evaluator.feasibility import FeasibilityResult, evaluate_feasibility
from zerodev.evaluator.competition import CompetitionResult
from zerodev.evaluator.scorer import calculate_score
from zerodev.evaluator.rules import decide


# ── Helpers ──────────────────────────────────────────────────────


def _make_claude_response(data: Dict[str, Any]) -> MagicMock:
    """Build a mock Anthropic message response containing JSON *data*."""
    content_block = MagicMock()
    content_block.text = json.dumps(data)
    message = MagicMock()
    message.content = [content_block]
    return message


# ── evaluate_feasibility with mocked Claude ──────────────────────


class TestEvaluateFeasibility:
    @pytest.mark.asyncio
    async def test_parses_valid_response(self) -> None:
        response_data = {
            "feasible": True,
            "complexity": "low",
            "page_count": 3,
            "needs_backend": False,
            "needs_hardware": False,
            "needs_login": False,
            "reasoning": "Simple timer app.",
        }
        mock_message = _make_claude_response(response_data)

        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(return_value=mock_message)

        with patch(
            "zerodev.evaluator.feasibility.anthropic.AsyncAnthropic",
            return_value=mock_client,
        ):
            result = await evaluate_feasibility(
                {
                    "title": "Timer",
                    "description": "A timer app",
                    "core_features": ["timer"],
                },
                api_key="test-key",
            )

        assert isinstance(result, FeasibilityResult)
        assert result.feasible is True
        assert result.complexity == "low"
        assert result.page_count == 3
        assert result.needs_backend is False

    @pytest.mark.asyncio
    async def test_handles_markdown_fenced_json(self) -> None:
        """Claude sometimes wraps JSON in markdown fences despite instructions."""
        raw_json = json.dumps(
            {
                "feasible": True,
                "complexity": "medium",
                "page_count": 5,
                "needs_backend": True,
                "needs_hardware": False,
                "needs_login": False,
                "reasoning": "Needs simple REST API.",
            }
        )
        fenced = f"```json\n{raw_json}\n```"

        content_block = MagicMock()
        content_block.text = fenced
        message = MagicMock()
        message.content = [content_block]

        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(return_value=message)

        with patch(
            "zerodev.evaluator.feasibility.anthropic.AsyncAnthropic",
            return_value=mock_client,
        ):
            result = await evaluate_feasibility(
                {
                    "title": "Notes App",
                    "description": "Cloud notes",
                    "core_features": ["sync"],
                },
                api_key="test-key",
            )

        assert result.feasible is True
        assert result.complexity == "medium"
        assert result.needs_backend is True

    @pytest.mark.asyncio
    async def test_normalises_unknown_complexity(self) -> None:
        """Unknown complexity values should default to 'high'."""
        response_data = {
            "feasible": True,
            "complexity": "extreme",
            "page_count": 2,
            "needs_backend": False,
            "needs_hardware": False,
            "needs_login": False,
            "reasoning": "ok",
        }
        mock_message = _make_claude_response(response_data)

        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(return_value=mock_message)

        with patch(
            "zerodev.evaluator.feasibility.anthropic.AsyncAnthropic",
            return_value=mock_client,
        ):
            result = await evaluate_feasibility(
                {"title": "Test", "description": "test", "core_features": []},
                api_key="test-key",
            )

        assert result.complexity == "high"

    @pytest.mark.asyncio
    async def test_raises_on_garbage_response(self) -> None:
        """Should raise ValueError when Claude returns non-JSON."""
        content_block = MagicMock()
        content_block.text = "I cannot evaluate this request."
        message = MagicMock()
        message.content = [content_block]

        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(return_value=message)

        with patch(
            "zerodev.evaluator.feasibility.anthropic.AsyncAnthropic",
            return_value=mock_client,
        ):
            with pytest.raises(ValueError, match="non-JSON"):
                await evaluate_feasibility(
                    {"title": "Bad", "description": "bad", "core_features": []},
                    api_key="test-key",
                )


# ── End-to-end pipeline: evaluate -> score -> decide ─────────────


class TestEndToEndProcessing:
    @pytest.mark.asyncio
    async def test_full_pipeline_approve(self) -> None:
        """A good demand should flow through evaluation, scoring, and approval."""
        response_data = {
            "feasible": True,
            "complexity": "low",
            "page_count": 3,
            "needs_backend": False,
            "needs_hardware": False,
            "needs_login": False,
            "reasoning": "Simple offline app.",
        }
        mock_message = _make_claude_response(response_data)

        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(return_value=mock_message)

        demand: Dict[str, Any] = {
            "title": "Meditation Timer",
            "description": "A minimal meditation timer with ambient sounds.",
            "core_features": ["timer", "sounds", "history"],
            "category": "health",
            "trend_score": 0.7,
        }

        # Step 1: Evaluate feasibility
        with patch(
            "zerodev.evaluator.feasibility.anthropic.AsyncAnthropic",
            return_value=mock_client,
        ):
            feasibility = await evaluate_feasibility(demand, api_key="test-key")

        # Step 2: Mock competition (low)
        competition = CompetitionResult(
            app_count=5, avg_rating=3.5, competition_score=0.3
        )

        # Step 3: Score
        score = calculate_score(demand, feasibility, competition)
        assert 0.6 <= score <= 1.0

        # Step 4: Decide
        decision, reason = decide(demand, feasibility, competition)
        assert decision == "approve"

    @pytest.mark.asyncio
    async def test_full_pipeline_reject_infeasible(self) -> None:
        """An infeasible demand should be rejected."""
        response_data = {
            "feasible": False,
            "complexity": "high",
            "page_count": 20,
            "needs_backend": True,
            "needs_hardware": True,
            "needs_login": True,
            "reasoning": "Requires custom hardware.",
        }
        mock_message = _make_claude_response(response_data)

        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(return_value=mock_message)

        demand: Dict[str, Any] = {
            "title": "IoT Controller",
            "description": "Control custom IoT devices via BLE.",
            "core_features": ["BLE", "device pairing", "firmware update"],
            "category": "tools",
            "trend_score": 0.3,
        }

        with patch(
            "zerodev.evaluator.feasibility.anthropic.AsyncAnthropic",
            return_value=mock_client,
        ):
            feasibility = await evaluate_feasibility(demand, api_key="test-key")

        competition = CompetitionResult(
            app_count=10, avg_rating=4.0, competition_score=0.5
        )

        score = calculate_score(demand, feasibility, competition)
        assert score < 0.5

        decision, _reason = decide(demand, feasibility, competition)
        assert decision == "reject"
