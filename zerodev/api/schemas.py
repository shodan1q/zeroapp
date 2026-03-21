"""Pydantic response/request schemas for the dashboard API."""

from __future__ import annotations

import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


# ── Dashboard ────────────────────────────────────────────────────


class DashboardSummary(BaseModel):
    total_apps: int = 0
    live_apps: int = 0
    reviewing_apps: int = 0
    developing_apps: int = 0
    total_demands: int = 0
    pending_demands: int = 0
    approved_today: int = 0
    rejected_today: int = 0
    builds_today: int = 0


# ── Demand ───────────────────────────────────────────────────────


class DemandOut(BaseModel):
    demand_id: int
    title: str
    description: str
    source: Optional[str] = None
    source_url: Optional[str] = None
    category: Optional[str] = None
    status: str
    overall_score: Optional[float] = None
    trend_score: Optional[float] = None
    created_at: datetime.datetime
    updated_at: datetime.datetime

    model_config = {"from_attributes": True}


class DemandDetail(DemandOut):
    target_users: Optional[str] = None
    core_features: Optional[str] = None
    monetization: Optional[str] = None
    complexity: Optional[str] = None
    competition_score: Optional[float] = None
    feasibility_score: Optional[float] = None
    monetization_score: Optional[float] = None


class DemandListResponse(BaseModel):
    items: List[DemandOut]
    total: int
    page: int
    page_size: int


# ── App ──────────────────────────────────────────────────────────


class BuildLogOut(BaseModel):
    build_id: int
    step: str
    status: str
    output: Optional[str] = None
    error_message: Optional[str] = None
    attempt: int = 1
    started_at: Optional[datetime.datetime] = None
    finished_at: Optional[datetime.datetime] = None
    created_at: datetime.datetime

    model_config = {"from_attributes": True}


class AppOut(BaseModel):
    app_id: int
    app_name: str
    package_name: str
    status: str
    category: Optional[str] = None
    google_play_url: Optional[str] = None
    total_downloads: int = 0
    revenue_usd: float = 0.0
    rating: Optional[float] = None
    created_at: datetime.datetime
    updated_at: datetime.datetime

    model_config = {"from_attributes": True}


class AppDetail(AppOut):
    demand_id: int
    description: str = ""
    flutter_version: Optional[str] = None
    project_path: Optional[str] = None
    build_attempts: int = 0
    fix_iterations: int = 0
    code_gen_cost_usd: float = 0.0
    published_at: Optional[datetime.datetime] = None
    build_logs: List[BuildLogOut] = Field(default_factory=list)


class AppListResponse(BaseModel):
    items: List[AppOut]
    total: int
    page: int
    page_size: int


# ── Builds ───────────────────────────────────────────────────────


class BuildListResponse(BaseModel):
    items: List[BuildLogOut]
    total: int


# ── Stats ────────────────────────────────────────────────────────


class DailyStat(BaseModel):
    date: datetime.date
    apps_created: int = 0
    revenue_usd: float = 0.0


class RatingBucket(BaseModel):
    rating_range: str
    count: int


class StatsResponse(BaseModel):
    apps_per_day: List[DailyStat] = Field(default_factory=list)
    total_revenue_usd: float = 0.0
    ratings_distribution: List[RatingBucket] = Field(default_factory=list)


# ── Pipeline ─────────────────────────────────────────────────────


class PipelineTriggerResponse(BaseModel):
    run_id: int
    status: str = "started"
    message: str = "Pipeline run triggered successfully."


class TopApp(BaseModel):
    app_id: int
    app_name: str
    package_name: Optional[str] = None
    value: float = 0.0


class PipelineStatus(BaseModel):
    runs_last_24h: int = 0
    last_run_status: Optional[str] = None
    last_run_at: Optional[datetime.datetime] = None


class TrendPoint(BaseModel):
    date: datetime.date
    apps_created: int = 0
    revenue_usd: float = 0.0
    total_downloads: int = 0


class MessageResponse(BaseModel):
    message: str
