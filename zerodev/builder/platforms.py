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


def get_runtime_platforms() -> list[str]:
    """Resolve the effective default build targets for a pipeline run.

    Priority: Dashboard-saved ``data/settings.json`` (``targetPlatforms``) >
    env config (``TARGET_PLATFORMS``) > built-in default. Invalid saved values
    are ignored in favor of the env config. This is the single source of truth
    used when no explicit ``--platform`` / argument is supplied, so the
    Dashboard "构建平台" selection actually drives the pipeline.
    """
    import json

    from zerodev.config import get_settings

    settings = get_settings()
    settings_file = settings.base_dir / "data" / "settings.json"
    if settings_file.exists():
        try:
            saved = json.loads(settings_file.read_text(encoding="utf-8")).get("targetPlatforms")
            if saved:
                return parse_platforms(saved)
        except (ValueError, OSError, json.JSONDecodeError):
            pass
    return parse_platforms(settings.target_platforms)
