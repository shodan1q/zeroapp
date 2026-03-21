"""BuildLog model -- records each step of the build pipeline."""

from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from zerodev.database import Base


class BuildStep(str, enum.Enum):
    CODE_GEN = "code_gen"
    DART_ANALYZE = "dart_analyze"
    AUTO_FIX = "auto_fix"
    BUILD_APK = "build_apk"
    BUILD_AAB = "build_aab"
    BUILD_IPA = "build_ipa"
    SIGN = "sign"
    PUBLISH_GOOGLE = "publish_google"
    PUBLISH_APPLE = "publish_apple"
    ICON_GEN = "icon_gen"
    SCREENSHOT_GEN = "screenshot_gen"
    STORE_LISTING = "store_listing"


class BuildStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"


class BuildLog(Base):
    """Log entry for a single build pipeline step."""

    __tablename__ = "build_logs"

    build_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    demand_id: Mapped[int] = mapped_column(Integer, ForeignKey("demands.demand_id"), nullable=False, index=True)
    app_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("app_registry.app_id"), nullable=True, index=True)
    step: Mapped[BuildStep] = mapped_column(Enum(BuildStep, name="build_step"), nullable=False)
    status: Mapped[BuildStatus] = mapped_column(
        Enum(BuildStatus, name="build_status"),
        nullable=False,
        default=BuildStatus.PENDING,
        server_default="pending",
    )
    output: Mapped[str | None] = mapped_column(Text, nullable=True, doc="stdout/stderr or LLM response")
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    attempt: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    # Relationships
    demand = relationship("Demand", backref="build_logs", lazy="selectin")
    app = relationship("AppRegistry", backref="build_logs", lazy="selectin")

    def __repr__(self) -> str:
        return f"<BuildLog {self.build_id}: demand={self.demand_id} step={self.step.value} [{self.status.value}]>"
