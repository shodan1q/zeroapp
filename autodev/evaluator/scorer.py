"""Weighted scorer -- combines all evaluation signals into a final score."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict

from autodev.evaluator.feasibility import FeasibilityResult
from autodev.evaluator.competition import CompetitionResult


# Scoring weights from requirements
WEIGHT_TREND = 0.30
WEIGHT_FEASIBILITY = 0.25
WEIGHT_LOW_COMPETITION = 0.25
WEIGHT_MONETIZATION = 0.20

# Aliases expected by tests
W_TREND = WEIGHT_TREND
W_FEASIBILITY = WEIGHT_FEASIBILITY
W_COMPETITION = WEIGHT_LOW_COMPETITION
W_MONETIZATION = WEIGHT_MONETIZATION

# Default monetization score for unknown categories
DEFAULT_MONETIZATION = 0.4

# Monetization potential by category
_MONETIZATION_MAP: Dict[str, float] = {
    "productivity": 0.7,
    "health": 0.7,
    "fitness": 0.7,
    "finance": 0.8,
    "education": 0.6,
    "entertainment": 0.5,
    "social": 0.4,
    "tools": 0.6,
    "lifestyle": 0.5,
    "business": 0.7,
    "music": 0.5,
    "games": 0.6,
    "shopping": 0.5,
    "travel": 0.5,
    "food": 0.5,
    "news": 0.3,
    "weather": 0.4,
    "sports": 0.4,
    "photo": 0.5,
    "video": 0.5,
}


@dataclass
class ScoreBreakdown:
    """Detailed score breakdown for a demand."""

    trend: float
    feasibility: float
    competition: float  # Higher = less competition = better
    monetization: float
    overall: float


class DemandScorer:
    """Compute weighted overall score for a demand."""

    def score(
        self,
        trend_score: float = 0.0,
        feasibility_score: float = 0.0,
        competition_score: float = 0.0,
        monetization_score: float = 0.0,
    ) -> ScoreBreakdown:
        """Calculate weighted score.

        All input scores should be in [0.0, 1.0].

        Returns:
            ScoreBreakdown with individual and overall scores.
        """
        overall = (
            WEIGHT_TREND * trend_score
            + WEIGHT_FEASIBILITY * feasibility_score
            + WEIGHT_LOW_COMPETITION * competition_score
            + WEIGHT_MONETIZATION * monetization_score
        )
        return ScoreBreakdown(
            trend=trend_score,
            feasibility=feasibility_score,
            competition=competition_score,
            monetization=monetization_score,
            overall=round(overall, 4),
        )


# ── Helper functions for test-friendly API ─────────────────────────


def _trend_score(demand: Dict[str, Any]) -> float:
    """Extract and clamp trend score from a demand dict."""
    raw = demand.get("trend_score")
    if not isinstance(raw, (int, float)):
        return 0.5
    return max(0.0, min(1.0, float(raw)))


def _monetization_score(demand: Dict[str, Any]) -> float:
    """Derive monetization score from category."""
    category = demand.get("category", "")
    if not isinstance(category, str) or not category:
        return DEFAULT_MONETIZATION
    return _MONETIZATION_MAP.get(category.lower(), DEFAULT_MONETIZATION)


def _feasibility_score(feasibility: FeasibilityResult) -> float:
    """Convert a FeasibilityResult into a 0-1 score.

    Scoring:
    - Infeasible -> 0.0
    - Start at 1.0, apply penalties:
      - complexity low: 0, medium: -0.25, high: -0.50
      - needs_backend: -0.20
      - needs_hardware: -0.30
      - needs_login: -0.10
      - page_count > 10: -0.15
    - Clamp to [0.0, 1.0]
    """
    if not feasibility.feasible:
        return 0.0

    score = 1.0

    complexity_penalties = {"low": 0.0, "medium": 0.25, "high": 0.50}
    score -= complexity_penalties.get(feasibility.complexity, 0.50)

    if feasibility.needs_backend:
        score -= 0.20
    if feasibility.needs_hardware:
        score -= 0.30
    if feasibility.needs_login:
        score -= 0.10
    if feasibility.page_count > 10:
        score -= 0.15

    return max(0.0, min(1.0, round(score, 4)))


def _competition_score(competition: CompetitionResult) -> float:
    """Convert CompetitionResult to a 0-1 score (higher = less competition = better)."""
    return max(0.0, min(1.0, 1.0 - competition.competition_score))


def calculate_score(
    demand: Dict[str, Any],
    feasibility: FeasibilityResult,
    competition: CompetitionResult,
) -> float:
    """Calculate the overall weighted score for a demand.

    Returns:
        Float in [0.0, 1.0].
    """
    t = _trend_score(demand)
    f = _feasibility_score(feasibility)
    c = _competition_score(competition)
    m = _monetization_score(demand)

    overall = W_TREND * t + W_FEASIBILITY * f + W_COMPETITION * c + W_MONETIZATION * m
    return max(0.0, min(1.0, round(overall, 4)))
