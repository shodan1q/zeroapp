"""Weighted scorer -- combines all evaluation signals into a final score."""

from __future__ import annotations

from dataclasses import dataclass


# Scoring weights from requirements
WEIGHT_TREND = 0.30
WEIGHT_FEASIBILITY = 0.25
WEIGHT_LOW_COMPETITION = 0.25
WEIGHT_MONETIZATION = 0.20


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
