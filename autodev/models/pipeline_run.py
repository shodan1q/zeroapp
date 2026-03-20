"""PipelineRun model -- records each execution of the full pipeline."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from autodev.database import Base


class PipelineRun(Base):
    """A single execution of the crawl -> evaluate -> build pipeline."""

    __tablename__ = "pipeline_runs"

    run_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    trigger: Mapped[str] = mapped_column(
        String(50), nullable=False, default="scheduled", server_default="scheduled"
    )
    demands_crawled: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    demands_approved: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    demands_rejected: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    builds_triggered: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="running", server_default="running"
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    def __repr__(self) -> str:
        return f"<PipelineRun {self.run_id}: {self.trigger} [{self.status}]>"
