"""Auto-approve and auto-reject rules for demand evaluation."""

from __future__ import annotations

from autodev.config import get_settings


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
