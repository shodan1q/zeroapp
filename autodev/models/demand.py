"""Demand model -- represents a discovered app idea / requirement."""

from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import DateTime, Enum, Float, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from autodev.database import Base


class DemandStatus(str, enum.Enum):
    """Lifecycle status of a demand."""

    PENDING = "pending"
    EVALUATING = "evaluating"
    APPROVED = "approved"
    REJECTED = "rejected"
    GENERATING = "generating"
    GENERATED = "generated"
    BUILDING = "building"
    BUILT = "built"
    PUBLISHING = "publishing"
    PUBLISHED = "published"
    FAILED = "failed"


class Demand(Base):
    """A single app demand scraped from an external source."""

    __tablename__ = "demands"

    demand_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    category: Mapped[str | None] = mapped_column(String(128), nullable=True)
    target_users: Mapped[str | None] = mapped_column(Text, nullable=True)
    core_features: Mapped[str | None] = mapped_column(Text, nullable=True, doc="JSON array of feature strings")
    monetization: Mapped[str | None] = mapped_column(
        String(64), nullable=True, doc="free, freemium, paid, ads, subscription"
    )
    complexity: Mapped[str | None] = mapped_column(String(32), nullable=True, doc="low, medium, high")
    competition_score: Mapped[float | None] = mapped_column(Float, nullable=True, doc="0.0 (saturated) to 1.0 (blue ocean)")
    trend_score: Mapped[float | None] = mapped_column(Float, nullable=True, doc="0.0 to 1.0")
    feasibility_score: Mapped[float | None] = mapped_column(Float, nullable=True, doc="0.0 to 1.0")
    monetization_score: Mapped[float | None] = mapped_column(Float, nullable=True, doc="0.0 to 1.0")
    overall_score: Mapped[float | None] = mapped_column(Float, nullable=True, doc="Weighted composite score")
    source: Mapped[str | None] = mapped_column(String(64), nullable=True, doc="reddit, producthunt, appstore")
    source_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    status: Mapped[DemandStatus] = mapped_column(
        Enum(DemandStatus, name="demand_status"),
        nullable=False,
        default=DemandStatus.PENDING,
        server_default="pending",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    def __repr__(self) -> str:
        return f"<Demand {self.demand_id}: {self.title[:40]}... [{self.status.value}]>"
