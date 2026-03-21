"""Auto-approve and auto-reject rules for demand evaluation."""

from __future__ import annotations

from typing import Any, Dict, Tuple

from zerodev.config import get_settings
from zerodev.evaluator.feasibility import FeasibilityResult
from zerodev.evaluator.competition import CompetitionResult
from zerodev.evaluator.scorer import calculate_score, _feasibility_score


# Categories that are automatically rejected
BANNED_CATEGORIES = {"gambling", "adult", "weapons", "drugs"}

# Maximum page count before auto-reject
MAX_PAGE_COUNT = 10

# Score thresholds
APPROVE_THRESHOLD = 0.60
REJECT_THRESHOLD = 0.40


class ApprovalRules:
    """Rule engine for automatic demand approval/rejection."""

    def __init__(self) -> None:
        settings = get_settings()
        self.auto_approve_threshold = settings.pipeline_auto_approve_threshold
        self.auto_reject_threshold = settings.pipeline_auto_reject_threshold

    def decide(self, overall_score: float, complexity: str | None = None) -> str:
        """Return 'approved', 'rejected', or 'manual_review'.

        Rules:
        - Score >= auto_approve_threshold AND complexity != 'high' -> approved
        - Score < auto_reject_threshold -> rejected
        - Otherwise -> manual_review (treated as approved for now)
        """
        if overall_score >= self.auto_approve_threshold and complexity != "high":
            return "approved"
        if overall_score < self.auto_reject_threshold:
            return "rejected"
        return "manual_review"


def decide(
    demand: Dict[str, Any],
    feasibility: FeasibilityResult,
    competition: CompetitionResult,
) -> Tuple[str, str]:
    """Evaluate a demand and return (decision, reason).

    Decision is one of: "approve", "reject", "manual_review".

    Rules (in priority order):
    1. Banned category -> reject
    2. needs_login -> reject
    3. Not feasible -> reject
    4. High complexity with page_count > MAX_PAGE_COUNT -> reject
    5. High complexity -> reject (excessive effort)
    6. Score >= APPROVE_THRESHOLD and low complexity -> approve
    7. Otherwise -> manual_review
    """
    category = demand.get("category", "").lower()

    # Rule 1: Banned category
    if category in BANNED_CATEGORIES:
        return ("reject", f"Banned category: {category}")

    # Rule 2: Needs login
    if feasibility.needs_login:
        return ("reject", "Requires login/auth which is out of scope.")

    # Rule 3: Not feasible
    if not feasibility.feasible:
        return ("reject", f"Not feasible: {feasibility.reasoning}")

    # Rule 4 & 5: High complexity
    if feasibility.complexity == "high":
        return ("reject", "Rejected: high complexity requires excessive development hours.")

    # Calculate score for threshold-based decisions
    score = calculate_score(demand, feasibility, competition)

    # Rule 6: Good score + manageable complexity -> approve
    if score >= APPROVE_THRESHOLD and feasibility.complexity == "low":
        return ("approve", f"Auto-approved with score {score:.2f}.")

    # Rule 7: Everything else -> manual review
    return ("manual_review", f"Sent to manual review with score {score:.2f}.")
