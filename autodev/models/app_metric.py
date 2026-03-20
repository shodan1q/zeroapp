"""AppMetric model -- periodic metrics snapshots for each published app."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from autodev.database import Base


class AppMetric(Base):
    """A single metrics snapshot collected for an app."""

    __tablename__ = "app_metrics"

    metric_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    app_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("app_registry.app_id"), nullable=False, index=True
    )

    # Play Store
    downloads: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    rating: Mapped[float] = mapped_column(Float, nullable=False, default=0.0, server_default="0.0")
    review_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")

    # AdMob / Revenue
    revenue_usd: Mapped[float] = mapped_column(Float, nullable=False, default=0.0, server_default="0.0")
    ad_impressions: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    ad_clicks: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")

    # Firebase / Usage
    dau: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    mau: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    crash_rate: Mapped[float] = mapped_column(Float, nullable=False, default=0.0, server_default="0.0")

    collected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    # Relationships
    app = relationship("AppRegistry", backref="metrics", lazy="selectin")

    def __repr__(self) -> str:
        return f"<AppMetric {self.metric_id}: app={self.app_id} at {self.collected_at}>"
