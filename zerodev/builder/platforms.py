"""Target platform parsing and validation.

A single source of truth for the set of build targets the pipeline supports and
how a user-supplied selection (CLI flag, env config, or Dashboard setting) is
normalized into a clean ordered list.
"""

from __future__ import annotations

from collections.abc import Iterable

# Canonical build targets, in their natural display / build order.
SUPPORTED_PLATFORMS: tuple[str, ...] = ("android", "ios", "ohos")

# Fallback when nothing is configured -- preserves historical behavior
# (only Android artifacts were built before per-platform selection existed).
DEFAULT_PLATFORMS: tuple[str, ...] = ("android",)


def parse_platforms(
    raw: str | Iterable[str] | None,
    *,
    default: Iterable[str] = DEFAULT_PLATFORMS,
) -> list[str]:
    """Normalize a platform selection into a validated, deduped, ordered list.

    Accepts a comma-separated string (e.g. ``"android,ohos"``), an iterable of
    strings, or ``None``/empty. Values are lowercased and trimmed. Unknown
    platforms raise ``ValueError``. The result is ordered by
    ``SUPPORTED_PLATFORMS`` regardless of input order.
    """
    if raw is None:
        tokens: list[str] = []
    elif isinstance(raw, str):
        tokens = [t.strip().lower() for t in raw.split(",")]
    else:
        tokens = [str(t).strip().lower() for t in raw]

    selected = {t for t in tokens if t}

    if not selected:
        selected = {p.lower() for p in default}

    unknown = selected - set(SUPPORTED_PLATFORMS)
    if unknown:
        raise ValueError(
            f"Unsupported platform(s): {', '.join(sorted(unknown))}. "
            f"Supported: {', '.join(SUPPORTED_PLATFORMS)}."
        )

    # Return in canonical order, not input/set order.
    return [p for p in SUPPORTED_PLATFORMS if p in selected]
