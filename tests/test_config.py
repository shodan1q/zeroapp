"""Tests for configuration module."""

from autodev.config import Settings


def test_settings_defaults():
    """Verify default settings are populated."""
    settings = Settings()
    assert settings.claude_model == "claude-sonnet-4-20250514"
    assert settings.pipeline_auto_approve_threshold == 0.75
    assert settings.pipeline_auto_reject_threshold == 0.30
    assert settings.pipeline_crawl_interval_hours == 6
    assert settings.log_level == "INFO"
