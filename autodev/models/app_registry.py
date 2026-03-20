"""AppRegistry model -- tracks generated apps through their lifecycle."""

from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import DateTime, Enum, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from autodev.database import Base


class AppStatus(str, enum.Enum):
    DRAFT = "draft"
    CODE_GENERATED = "code_generated"
    BUILD_SUCCESS = "build_success"
    BUILD_FAILED = "build_failed"
    PUBLISHED = "published"
    LIVE = "live"
    SUSPENDED = "suspended"


class AppRegistry(Base):
    """Registry of all generated applications."""

    __tablename__ = "app_registry"

    app_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    demand_id: Mapped[int] = mapped_column(Integer, ForeignKey("demands.demand_id"), nullable=False, index=True)
    app_name: Mapped[str] = mapped_column(String(256), nullable=False)
    package_name: Mapped[str] = mapped_column(String(256), nullable=False, unique=True)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    category: Mapped[str | None] = mapped_column(String(128), nullable=True)
    flutter_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    project_path: Mapped[str | None] = mapped_column(String(2048), nullable=True, doc="Path to generated Flutter project")
    apk_path: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    aab_path: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    ipa_path: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    icon_path: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    store_listing: Mapped[str | None] = mapped_column(Text, nullable=True, doc="JSON blob of store listing metadata")
    status: Mapped[AppStatus] = mapped_column(
        Enum(AppStatus, name="app_status"),
        nullable=False,
        default=AppStatus.DRAFT,
        server_default="draft",
    )
    google_play_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    apple_store_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    total_downloads: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    revenue_usd: Mapped[float] = mapped_column(Float, nullable=False, default=0.0, server_default="0.0")
    rating: Mapped[float | None] = mapped_column(Float, nullable=True)
    code_gen_tokens_used: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    code_gen_cost_usd: Mapped[float] = mapped_column(Float, nullable=False, default=0.0, server_default="0.0")
    build_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    fix_iterations: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    demand = relationship("Demand", backref="apps", lazy="selectin")

    def __repr__(self) -> str:
        return f"<AppRegistry {self.app_id}: {self.app_name} [{self.status.value}]>"
