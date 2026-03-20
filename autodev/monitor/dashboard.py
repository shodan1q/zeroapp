"""Dashboard data aggregation for the monitoring layer.

All functions accept an async SQLAlchemy session and return Pydantic models
suitable for direct serialisation in API responses.
"""

from __future__ import annotations

import datetime
import logging
from typing import List

from sqlalchemy import cast, Date, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from autodev.api.schemas import (
    DashboardSummary,
    PipelineStatus,
    TopApp,
    TrendPoint,
)
from autodev.models import (
    AppMetric,
    AppRegistry,
    AppStatus,
    BuildLog,
    Demand,
    DemandStatus,
    PipelineRun,
)

logger = logging.getLogger(__name__)


async def get_dashboard_summary(session: AsyncSession) -> DashboardSummary:
    """Return high-level counts for the dashboard overview card.

    Parameters
    ----------
    session:
        Active async database session.
    """
    today_start = datetime.datetime.now(datetime.timezone.utc).replace(
        hour=0, minute=0, second=0, microsecond=0
    )

    # App counts
    app_rows = (
        await session.execute(
            select(AppRegistry.status, func.count(AppRegistry.app_id)).group_by(
                AppRegistry.status
            )
        )
    ).all()
    app_map = {
        str(row[0].value if hasattr(row[0], "value") else row[0]): row[1]
        for row in app_rows
    }

    total_demands = (
        await session.execute(select(func.count(Demand.demand_id)))
    ).scalar_one()
    pending_demands = (
        await session.execute(
            select(func.count(Demand.demand_id)).where(
                Demand.status == DemandStatus.PENDING
            )
        )
    ).scalar_one()

    approved_today = (
        await session.execute(
            select(func.count(Demand.demand_id)).where(
                Demand.status == DemandStatus.APPROVED,
                Demand.updated_at >= today_start,
            )
        )
    ).scalar_one()
    rejected_today = (
        await session.execute(
            select(func.count(Demand.demand_id)).where(
                Demand.status == DemandStatus.REJECTED,
                Demand.updated_at >= today_start,
            )
        )
    ).scalar_one()

    builds_today = (
        await session.execute(
            select(func.count(BuildLog.build_id)).where(
                BuildLog.created_at >= today_start
            )
        )
    ).scalar_one()

    return DashboardSummary(
        total_apps=sum(app_map.values()),
        live_apps=app_map.get(AppStatus.LIVE.value, 0),
        reviewing_apps=app_map.get(AppStatus.CODE_GENERATED.value, 0),
        developing_apps=app_map.get(AppStatus.DRAFT.value, 0),
        total_demands=total_demands,
        pending_demands=pending_demands,
        approved_today=approved_today,
        rejected_today=rejected_today,
        builds_today=builds_today,
    )


async def get_top_apps(
    session: AsyncSession,
    by: str = "revenue",
    limit: int = 5,
) -> List[TopApp]:
    """Return the top-performing apps ranked by a given metric.

    Parameters
    ----------
    session:
        Active async database session.
    by:
        Metric to rank by.  One of ``"revenue"``, ``"downloads"``, ``"rating"``.
    limit:
        Maximum number of apps to return.
    """
    metric_col = {
        "revenue": AppMetric.revenue_usd,
        "downloads": AppMetric.downloads,
        "rating": AppMetric.rating,
    }.get(by, AppMetric.revenue_usd)

    stmt = (
        select(
            AppRegistry.app_id,
            AppRegistry.app_name,
            AppRegistry.package_name,
            func.coalesce(func.sum(metric_col), 0).label("value"),
        )
        .outerjoin(AppMetric, AppMetric.app_id == AppRegistry.app_id)
        .group_by(AppRegistry.app_id, AppRegistry.app_name, AppRegistry.package_name)
        .order_by(func.coalesce(func.sum(metric_col), 0).desc())
        .limit(limit)
    )

    rows = (await session.execute(stmt)).all()

    return [
        TopApp(
            app_id=row.app_id,
            app_name=row.app_name,
            package_name=row.package_name,
            value=float(row.value),
        )
        for row in rows
    ]


async def get_pipeline_status(session: AsyncSession) -> PipelineStatus:
    """Return a summary of pipeline activity in the last 24 hours.

    Parameters
    ----------
    session:
        Active async database session.
    """
    cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=24)

    runs_count = (
        await session.execute(
            select(func.count(PipelineRun.run_id)).where(
                PipelineRun.started_at >= cutoff
            )
        )
    ).scalar_one()

    last_run = (
        await session.execute(
            select(PipelineRun).order_by(PipelineRun.started_at.desc()).limit(1)
        )
    ).scalar_one_or_none()

    return PipelineStatus(
        runs_last_24h=runs_count,
        last_run_status=last_run.status if last_run else None,
        last_run_at=last_run.started_at if last_run else None,
    )


async def get_trend_data(
    session: AsyncSession,
    days: int = 30,
) -> List[TrendPoint]:
    """Return daily time-series data for dashboard charts.

    Parameters
    ----------
    session:
        Active async database session.
    days:
        Number of days of history to include.
    """
    since = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=days)

    # Apps created per day
    apps_stmt = (
        select(
            cast(AppRegistry.created_at, Date).label("date"),
            func.count(AppRegistry.app_id).label("apps_created"),
        )
        .where(AppRegistry.created_at >= since)
        .group_by(cast(AppRegistry.created_at, Date))
    )
    app_rows = {
        row.date: row.apps_created
        for row in (await session.execute(apps_stmt)).all()
    }

    # Revenue and downloads per day
    metrics_stmt = (
        select(
            cast(AppMetric.collected_at, Date).label("date"),
            func.coalesce(func.sum(AppMetric.revenue_usd), 0.0).label("revenue"),
            func.coalesce(func.sum(AppMetric.downloads), 0).label("downloads"),
        )
        .where(AppMetric.collected_at >= since)
        .group_by(cast(AppMetric.collected_at, Date))
    )
    metric_rows = {
        row.date: (float(row.revenue), int(row.downloads))
        for row in (await session.execute(metrics_stmt)).all()
    }

    all_dates = set(app_rows.keys()) | set(metric_rows.keys())
    if not all_dates:
        return []

    results: List[TrendPoint] = []
    for d in sorted(all_dates):
        rev, dl = metric_rows.get(d, (0.0, 0))
        results.append(
            TrendPoint(
                date=d,
                apps_created=app_rows.get(d, 0),
                revenue_usd=rev,
                total_downloads=dl,
            )
        )

    return results
