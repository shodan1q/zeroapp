"""Application settings using pydantic-settings."""

from __future__ import annotations

from pathlib import Path
from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central configuration loaded from environment variables and .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Claude API ──────────────────────────────────────────────
    claude_mode: str = Field(
        default="api",
        description="'api' for Anthropic API, 'local' for Claude Max local proxy",
    )
    claude_api_key: str = Field(default="", description="Anthropic API key (required for 'api' mode)")
    claude_base_url: str = Field(
        default="http://127.0.0.1:3456",
        description="claude-max-api proxy URL (used in 'local' mode)",
    )
    claude_model: str = Field(default="claude-opus-4-6", description="Claude model to use")

    # ── Reddit API ──────────────────────────────────────────────
    reddit_client_id: str = Field(default="", description="Reddit OAuth client ID")
    reddit_client_secret: str = Field(default="", description="Reddit OAuth client secret")
    reddit_user_agent: str = Field(default="zerodev-agent/0.1", description="Reddit user agent string")

    # ── Database ────────────────────────────────────────────────
    database_url: str = Field(
        default="postgresql+asyncpg://zerodev:zerodev@localhost:5432/zerodev",
        description="Async database URL (asyncpg)",
    )
    database_url_sync: str = Field(
        default="postgresql+psycopg2://zerodev:zerodev@localhost:5432/zerodev",
        description="Sync database URL (psycopg2) for Alembic and Celery workers",
    )

    # ── Redis / Celery ──────────────────────────────────────────
    redis_url: str = Field(default="redis://localhost:6379/0")
    celery_broker_url: str = Field(default="redis://localhost:6379/1")
    celery_result_backend: str = Field(default="redis://localhost:6379/2")

    # ── DALL-E ──────────────────────────────────────────────────
    dalle_api_key: str = Field(default="", description="OpenAI API key for DALL-E icon generation")

    # ── Flutter ─────────────────────────────────────────────────
    flutter_sdk_path: Path = Field(default=Path("/usr/local/flutter"), description="Path to Flutter SDK")
    flutter_bin: str = Field(default="flutter", description="Flutter binary name or path")
    dart_bin: str = Field(default="dart", description="Dart binary name or path")

    # ── Workspace ───────────────────────────────────────────────
    workspace_dir: str = Field(default="workspace", description="Working directory for generated projects")

    # ── App Store Publishing ────────────────────────────────────
    google_play_json_key_path: str = Field(default="", description="Path to Google Play service account JSON key")
    apple_api_key_id: str = Field(default="")
    apple_api_issuer_id: str = Field(default="")
    apple_api_key_path: str = Field(default="")

    # ── Output / GitHub ────────────────────────────────────────
    output_dir: str = Field(default="/Users/shodan/project/zerodev", description="Output directory for generated app projects")
    github_org: str = Field(default="shodan1q", description="GitHub user/org that owns the zerogenerate monorepo")

    # ── Pipeline settings ───────────────────────────────────────
    pipeline_crawl_interval_hours: int = Field(default=6, description="Hours between crawl cycles")
    pipeline_max_concurrent_builds: int = Field(default=2, description="Max parallel Flutter builds")
    pipeline_auto_approve_threshold: float = Field(
        default=0.75, description="Score above which demands are auto-approved"
    )
    pipeline_auto_reject_threshold: float = Field(
        default=0.30, description="Score below which demands are auto-rejected"
    )

    # ── LangGraph pipeline checkpoint / retry ────────────────────
    pipeline_checkpoint_backend: str = Field(
        default="sqlite",
        description="Checkpoint backend: 'memory' (dev) or 'sqlite' (production)",
    )
    pipeline_checkpoint_path: str = Field(
        default="data/checkpoints.db",
        description="Path to SQLite checkpoint database (used when backend='sqlite')",
    )
    pipeline_max_retries: int = Field(
        default=3, description="Max retry attempts per pipeline node"
    )
    pipeline_retry_backoff_base: float = Field(
        default=2.0, description="Base seconds for exponential retry backoff"
    )
    pipeline_retry_backoff_max: float = Field(
        default=300.0, description="Maximum retry backoff delay in seconds"
    )

    # ── Logging ─────────────────────────────────────────────────
    log_level: str = Field(default="INFO")

    # ── Derived paths ───────────────────────────────────────────
    base_dir: Path = Field(default_factory=lambda: Path(__file__).resolve().parent.parent)

    @property
    def generated_apps_dir(self) -> Path:
        d = self.base_dir / "generated_apps"
        d.mkdir(parents=True, exist_ok=True)
        return d

    @property
    def builds_dir(self) -> Path:
        d = self.base_dir / "builds"
        d.mkdir(parents=True, exist_ok=True)
        return d


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached singleton Settings instance."""
    return Settings()


# Module-level convenience alias
settings = get_settings()
