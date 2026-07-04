"""Runtime access to Dashboard-saved settings (data/settings.json).

The Dashboard settings page persists to ``data/settings.json``. Values saved
there must take effect at runtime without a restart, with env vars as the
fallback -- the same precedence the build-platform selection and the LLM
provider resolution already use:

    settings.json  >  environment (.env via zerodev.config)  >  code default

Use :func:`effective_setting` for that resolution, or
:func:`load_dashboard_settings` for raw access.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

SETTINGS_FILE = Path(__file__).resolve().parent.parent / "data" / "settings.json"


def load_dashboard_settings() -> dict[str, Any]:
    """Read ``data/settings.json``; returns {} when absent or unreadable."""
    if SETTINGS_FILE.exists():
        try:
            return json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Failed to read %s: %s", SETTINGS_FILE, exc)
    return {}


def _usable(value: Any) -> bool:
    """A usable saved string: non-blank and not a masked secret (****xxxx)."""
    return isinstance(value, str) and bool(value.strip()) and not value.strip().startswith("*")


def effective_setting(file_key: str, env_value: str = "", default: str = "") -> str:
    """Resolve one string setting: settings.json > env value > default."""
    saved = load_dashboard_settings().get(file_key)
    if _usable(saved):
        return str(saved).strip()
    if isinstance(env_value, str) and env_value.strip():
        return env_value.strip()
    return default


def effective_float(file_key: str, env_value: float, *, minimum: float | None = None) -> float:
    """Resolve a numeric setting saved as a string in settings.json."""
    saved = load_dashboard_settings().get(file_key)
    try:
        value = float(str(saved)) if saved not in (None, "") else float(env_value)
    except (TypeError, ValueError):
        value = float(env_value)
    if minimum is not None:
        value = max(minimum, value)
    return value


def effective_sources(default: dict[str, bool] | None = None) -> dict[str, bool]:
    """Resolve the enabled data-source toggles saved by the Dashboard."""
    defaults = default or {"reddit": True, "producthunt": True, "twitter": False, "hackernews": True}
    saved = load_dashboard_settings().get("enabledSources")
    if isinstance(saved, dict):
        return {**defaults, **{k: bool(v) for k, v in saved.items()}}
    return defaults
