"""Shared pytest fixtures for the ZeroDev test suite."""

from __future__ import annotations

import pytest
from typing import Any, Dict

from zerodev.evaluator.feasibility import FeasibilityResult
from zerodev.evaluator.competition import CompetitionResult


# ── Sample data factories ────────────────────────────────────────


@pytest.fixture
def sample_demand() -> Dict[str, Any]:
    """Return a minimal demand dict suitable for scorer / rules tests."""
    return {
        "title": "Pomodoro Timer",
        "description": "A simple pomodoro timer app with task tracking.",
        "core_features": ["timer", "task list", "statistics"],
        "category": "productivity",
        "trend_score": 0.7,
    }


@pytest.fixture
def simple_feasibility() -> FeasibilityResult:
    """Return a feasibility result for a simple, feasible app."""
    return FeasibilityResult(
        feasible=True,
        complexity="low",
        page_count=3,
        needs_backend=False,
        needs_hardware=False,
        needs_login=False,
        reasoning="Simple standalone timer app, easily built with Flutter.",
    )


@pytest.fixture
def complex_feasibility() -> FeasibilityResult:
    """Return a feasibility result for a complex app."""
    return FeasibilityResult(
        feasible=True,
        complexity="high",
        page_count=15,
        needs_backend=True,
        needs_hardware=False,
        needs_login=True,
        reasoning="Social network with real-time messaging requires backend and auth.",
    )


@pytest.fixture
def infeasible_result() -> FeasibilityResult:
    """Return a feasibility result for an infeasible app."""
    return FeasibilityResult(
        feasible=False,
        complexity="high",
        page_count=20,
        needs_backend=True,
        needs_hardware=True,
        needs_login=True,
        reasoning="Requires custom BLE hardware pairing which is infeasible.",
    )


@pytest.fixture
def low_competition() -> CompetitionResult:
    """Return a competition result indicating a low-competition niche."""
    return CompetitionResult(
        app_count=3,
        avg_rating=3.2,
        competition_score=0.25,
    )


@pytest.fixture
def high_competition() -> CompetitionResult:
    """Return a competition result indicating a saturated market."""
    return CompetitionResult(
        app_count=45,
        avg_rating=4.5,
        competition_score=0.85,
    )
