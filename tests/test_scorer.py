"""Tests for zerodev.evaluator.scorer -- the weighted scoring system."""

from __future__ import annotations

from typing import Any, Dict

import pytest

from zerodev.evaluator.competition import CompetitionResult
from zerodev.evaluator.feasibility import FeasibilityResult
from zerodev.evaluator.scorer import (
    W_COMPETITION,
    W_FEASIBILITY,
    W_MONETIZATION,
    W_TREND,
    _feasibility_score,
    _monetization_score,
    _trend_score,
    calculate_score,
)


# ── _trend_score ─────────────────────────────────────────────────


class TestTrendScore:
    def test_returns_value_when_present(self) -> None:
        assert _trend_score({"trend_score": 0.8}) == 0.8

    def test_clamps_above_one(self) -> None:
        assert _trend_score({"trend_score": 1.5}) == 1.0

    def test_clamps_below_zero(self) -> None:
        assert _trend_score({"trend_score": -0.3}) == 0.0

    def test_defaults_to_half_when_missing(self) -> None:
        assert _trend_score({}) == 0.5

    def test_defaults_to_half_on_bad_type(self) -> None:
        assert _trend_score({"trend_score": "not-a-number"}) == 0.5


# ── _monetization_score ──────────────────────────────────────────


class TestMonetizationScore:
    def test_known_category(self) -> None:
        assert _monetization_score({"category": "productivity"}) == 0.7

    def test_case_insensitive(self) -> None:
        assert _monetization_score({"category": "Productivity"}) == 0.7

    def test_unknown_category_returns_default(self) -> None:
        score = _monetization_score({"category": "obscure_cat"})
        assert score == 0.4  # DEFAULT_MONETIZATION

    def test_missing_category(self) -> None:
        assert _monetization_score({}) == 0.4


# ── _feasibility_score ───────────────────────────────────────────


class TestFeasibilityScore:
    def test_perfect_score(self, simple_feasibility: FeasibilityResult) -> None:
        score = _feasibility_score(simple_feasibility)
        assert score == 1.0

    def test_infeasible_returns_zero(self, infeasible_result: FeasibilityResult) -> None:
        assert _feasibility_score(infeasible_result) == 0.0

    def test_medium_complexity_penalty(self) -> None:
        result = FeasibilityResult(
            feasible=True,
            complexity="medium",
            page_count=3,
            needs_backend=False,
            needs_hardware=False,
            needs_login=False,
            reasoning="ok",
        )
        assert _feasibility_score(result) == pytest.approx(0.75, abs=0.01)

    def test_all_penalties_accumulate(
        self, complex_feasibility: FeasibilityResult
    ) -> None:
        score = _feasibility_score(complex_feasibility)
        # high complexity (-0.50), backend (-0.20), login (-0.10), >10 pages (-0.15)
        assert score == pytest.approx(0.05, abs=0.01)


# ── calculate_score (integration) ────────────────────────────────


class TestCalculateScore:
    def test_weights_sum_to_one(self) -> None:
        total = W_TREND + W_FEASIBILITY + W_COMPETITION + W_MONETIZATION
        assert total == pytest.approx(1.0)

    def test_ideal_demand_scores_high(
        self,
        sample_demand: Dict[str, Any],
        simple_feasibility: FeasibilityResult,
        low_competition: CompetitionResult,
    ) -> None:
        score = calculate_score(sample_demand, simple_feasibility, low_competition)
        assert 0.7 <= score <= 1.0

    def test_bad_demand_scores_low(
        self,
        infeasible_result: FeasibilityResult,
        high_competition: CompetitionResult,
    ) -> None:
        demand: Dict[str, Any] = {"trend_score": 0.1, "category": "social"}
        score = calculate_score(demand, infeasible_result, high_competition)
        assert score < 0.3

    def test_score_bounded_zero_one(
        self,
        sample_demand: Dict[str, Any],
        simple_feasibility: FeasibilityResult,
        low_competition: CompetitionResult,
    ) -> None:
        score = calculate_score(sample_demand, simple_feasibility, low_competition)
        assert 0.0 <= score <= 1.0
