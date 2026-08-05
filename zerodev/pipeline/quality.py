"""Score a generated app, so the factory can decide instead of just shipping.

Without a score there is no supervision: every build that parses gets published,
and the only quality control is a human noticing something looks thin. This
module turns the signals the pipeline already collects into one number and a
verdict, which is what lets the graph choose between accepting an app, sending
it back for another attempt, or giving up on it.

The scoring is deliberately built on **objective, already-measured** signals --
did it run, how many views registered, how many records exist -- rather than
asking a model whether its own output is good. A self-assessment would agree
with itself; a boot that throws will not.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# Verdicts the supervisor acts on.
ACCEPT = "accept"
REWORK = "rework"
REJECT = "reject"

# Below this an app is not worth shipping; above it, publishing is reasonable.
ACCEPT_THRESHOLD = 70.0

# Below this the result is bad enough that another attempt is unlikely to be a
# small edit -- the whole app gets regenerated rather than patched.
REJECT_THRESHOLD = 25.0

# What "good" looks like for each measured dimension. Hitting the target earns
# full marks; falling short scales down linearly.
TARGETS: dict[str, tuple[int, float]] = {
    # dimension: (target value, weight)
    "views": (5, 12.0),
    "features": (8, 18.0),
    "charts": (3, 6.0),
    "records": (80, 18.0),
    "collections": (3, 6.0),
}

# Passing the runtime gate is most of the score, because an app that does not
# run is worth nothing regardless of how much content it contains.
RUNTIME_WEIGHT = 30.0
BUILD_WEIGHT = 10.0


@dataclass
class QualityScore:
    """One app's score, with the reasoning kept alongside the number."""

    total: float = 0.0
    verdict: str = REJECT
    breakdown: dict[str, float] = field(default_factory=dict)
    reasons: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return self.verdict == ACCEPT

    def render(self) -> str:
        parts = ", ".join(f"{k} {v:.0f}" for k, v in self.breakdown.items())
        return f"{self.total:.0f}/100 [{self.verdict}] ({parts})"

    def to_dict(self) -> dict[str, Any]:
        return {
            "total": round(self.total, 1),
            "verdict": self.verdict,
            "breakdown": {k: round(v, 1) for k, v in self.breakdown.items()},
            "reasons": self.reasons,
        }


def score_app(metrics: dict[str, Any], *, built: bool, build_required: bool = True) -> QualityScore:
    """Score one generated app from its measured metrics.

    ``metrics`` is what :func:`zerodev.pipeline.webview_app.create_webview_app`
    records: counts from the runtime harness plus whether it passed.
    """
    score = QualityScore()
    breakdown: dict[str, float] = {}
    reasons: list[str] = []

    # -- did it actually run -------------------------------------------------
    runtime_ok = metrics.get("runtime_ok")
    if runtime_ok is True:
        breakdown["runtime"] = RUNTIME_WEIGHT
    elif runtime_ok is None:
        # The gate was unavailable. Award partial credit rather than punishing
        # an app for the operator's missing toolchain, but say so.
        breakdown["runtime"] = RUNTIME_WEIGHT * 0.5
        reasons.append("runtime gate was unavailable, so the app was never executed")
    else:
        breakdown["runtime"] = 0.0
        reasons.append("the app failed the runtime check")

    # -- content and capability ---------------------------------------------
    for name, (target, weight) in TARGETS.items():
        value = _as_number(metrics.get(name))
        earned = weight * min(1.0, value / target) if target else 0.0
        breakdown[name] = earned
        if value < target * 0.6:
            reasons.append(f"{name}: {value:g} is well short of the {target} expected")

    # -- did it package ------------------------------------------------------
    if not build_required:
        breakdown["build"] = BUILD_WEIGHT
    elif built:
        breakdown["build"] = BUILD_WEIGHT
    else:
        breakdown["build"] = 0.0
        reasons.append("no .hap was produced")

    score.breakdown = breakdown
    score.total = sum(breakdown.values())
    score.reasons = reasons
    score.verdict = _verdict(score.total, runtime_ok)
    return score


def _verdict(total: float, runtime_ok: Any) -> str:
    # A failed runtime check is disqualifying on its own: shipping a blank
    # screen is worse than shipping nothing, however rich the data behind it.
    if runtime_ok is False:
        return REWORK if total >= REJECT_THRESHOLD else REJECT
    if total >= ACCEPT_THRESHOLD:
        return ACCEPT
    if total >= REJECT_THRESHOLD:
        return REWORK
    return REJECT


def _as_number(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def metrics_from_result(result: Any) -> dict[str, Any]:
    """Pull the scoreable metrics off a :class:`WebviewAppResult`."""
    return dict(getattr(result, "metrics", {}) or {})
