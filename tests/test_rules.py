"""Tests for autodev.evaluator.rules -- the decision rules engine."""

from __future__ import annotations

from typing import Any, Dict

import pytest

from autodev.evaluator.competition import CompetitionResult
from autodev.evaluator.feasibility import FeasibilityResult
from autodev.evaluator.rules import decide


class TestAutoReject:
    def test_banned_category_rejected(
        self,
        simple_feasibility: FeasibilityResult,
        low_competition: CompetitionResult,
    ) -> None:
        demand: Dict[str, Any] = {"category": "gambling", "trend_score": 0.9}
        decision, reason = decide(demand, simple_feasibility, low_competition)
        assert decision == "reject"
        assert "banned category" in reason.lower()

    def test_needs_login_rejected(
        self,
        low_competition: CompetitionResult,
    ) -> None:
        feasibility = FeasibilityResult(
            feasible=True,
            complexity="low",
            page_count=3,
            needs_backend=False,
            needs_hardware=False,
            needs_login=True,
            reasoning="Requires auth.",
        )
        demand: Dict[str, Any] = {"category": "tools", "trend_score": 0.8}
        decision, reason = decide(demand, feasibility, low_competition)
        assert decision == "reject"
        assert "login" in reason.lower()

    def test_excessive_hours_rejected(
        self,
        complex_feasibility: FeasibilityResult,
        low_competition: CompetitionResult,
    ) -> None:
        demand: Dict[str, Any] = {"category": "tools", "trend_score": 0.5}
        decision, reason = decide(demand, complex_feasibility, low_competition)
        assert decision == "reject"
        assert "reject" in decision

    def test_infeasible_rejected(
        self,
        infeasible_result: FeasibilityResult,
        low_competition: CompetitionResult,
    ) -> None:
        demand: Dict[str, Any] = {"category": "tools", "trend_score": 0.8}
        decision, reason = decide(demand, infeasible_result, low_competition)
        assert decision == "reject"


class TestAutoApprove:
    def test_simple_app_approved(
        self,
        sample_demand: Dict[str, Any],
        simple_feasibility: FeasibilityResult,
        low_competition: CompetitionResult,
    ) -> None:
        decision, reason = decide(sample_demand, simple_feasibility, low_competition)
        assert decision == "approve"
        assert "approved" in reason.lower()


class TestManualReview:
    def test_medium_complexity_goes_to_review(
        self,
        low_competition: CompetitionResult,
    ) -> None:
        feasibility = FeasibilityResult(
            feasible=True,
            complexity="medium",
            page_count=4,
            needs_backend=False,
            needs_hardware=False,
            needs_login=False,
            reasoning="Moderate complexity.",
        )
        demand: Dict[str, Any] = {"category": "tools", "trend_score": 0.5}
        decision, reason = decide(demand, feasibility, low_competition)
        assert decision == "manual_review"
        assert "manual review" in reason.lower()

    def test_high_competition_goes_to_review(
        self,
        simple_feasibility: FeasibilityResult,
        high_competition: CompetitionResult,
    ) -> None:
        demand: Dict[str, Any] = {"category": "tools", "trend_score": 0.5}
        decision, reason = decide(demand, simple_feasibility, high_competition)
        assert decision == "manual_review"
