"""Dashboard API route definitions."""

from __future__ import annotations

import datetime
import json
import logging
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import case, cast, Date, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from zerodev.api.deps import get_session
from zerodev.api.schemas import (
    AppDetail,
    AppListResponse,
    AppOut,
    BuildListResponse,
    BuildLogOut,
    DailyStat,
    DashboardSummary,
    DemandDetail,
    DemandListResponse,
    DemandOut,
    MessageResponse,
    PipelineTriggerResponse,
    RatingBucket,
    StatsResponse,
)
from zerodev.models import (
    AppMetric,
    AppRegistry,
    AppStatus,
    BuildLog,
    BuildStatus,
    Demand,
    DemandStatus,
    PipelineRun,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api")


# ── Dashboard ────────────────────────────────────────────────────


@router.get("/dashboard", response_model=DashboardSummary)
async def get_dashboard(session: AsyncSession = Depends(get_session)) -> DashboardSummary:
    """Return an overview of the current system state."""
    try:
        result = await _get_dashboard_impl(session)
    except Exception:
        logger.warning("Dashboard query failed (tables may not exist yet)")
        result = DashboardSummary(
            total_apps=0, live_apps=0, reviewing_apps=0, developing_apps=0,
            total_demands=0, pending_demands=0,
            approved_today=0, rejected_today=0, builds_today=0,
        )

    # Supplement with file system generated apps count
    try:
        from zerodev.config import get_settings
        from pathlib import Path
        output_dir = Path(get_settings().output_dir)
        if output_dir.exists():
            fs_apps = sum(1 for d in output_dir.iterdir() if d.is_dir() and (d / "pubspec.yaml").exists())
            result.total_apps = max(result.total_apps, fs_apps)
            result.developing_apps = max(result.developing_apps, fs_apps - result.live_apps)
    except Exception:
        pass

    # Supplement with runner stats
    try:
        from zerodev.pipeline.runner import PipelineRunner
        runner = PipelineRunner.get_instance()
        stats = runner.stats
        result.builds_today = max(result.builds_today, stats.get("apps_generated", 0))
    except Exception:
        pass

    return result


async def _get_dashboard_impl(session: AsyncSession) -> DashboardSummary:
    today_start = datetime.datetime.now(datetime.timezone.utc).replace(
        hour=0, minute=0, second=0, microsecond=0
    )

    # App counts by status
    app_counts = (
        await session.execute(
            select(AppRegistry.status, func.count(AppRegistry.app_id)).group_by(
                AppRegistry.status
            )
        )
    ).all()
    app_map = {
        str(row[0].value if hasattr(row[0], "value") else row[0]): row[1]
        for row in app_counts
    }

    # Total demands and pending
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

    # Today's approved / rejected
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

    # Builds today
    builds_today = (
        await session.execute(
            select(func.count(BuildLog.build_id)).where(
                BuildLog.created_at >= today_start
            )
        )
    ).scalar_one()

    total_apps = sum(app_map.values())

    return DashboardSummary(
        total_apps=total_apps,
        live_apps=app_map.get(AppStatus.LIVE.value, 0),
        reviewing_apps=app_map.get(AppStatus.CODE_GENERATED.value, 0),
        developing_apps=app_map.get(AppStatus.DRAFT.value, 0),
        total_demands=total_demands,
        pending_demands=pending_demands,
        approved_today=approved_today,
        rejected_today=rejected_today,
        builds_today=builds_today,
    )


# ── Demands ──────────────────────────────────────────────────────


@router.get("/demands", response_model=DemandListResponse)
async def list_demands(
    status: Optional[str] = Query(None, description="Filter by status"),
    source: Optional[str] = Query(None, description="Filter by source"),
    date_from: Optional[datetime.date] = Query(None, description="Start date"),
    date_to: Optional[datetime.date] = Query(None, description="End date"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
) -> DemandListResponse:
    """List demands with optional filters and pagination."""
    stmt = select(Demand)
    count_stmt = select(func.count(Demand.demand_id))

    if status:
        try:
            status_enum = DemandStatus(status)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid status: {status}")
        stmt = stmt.where(Demand.status == status_enum)
        count_stmt = count_stmt.where(Demand.status == status_enum)

    if source:
        stmt = stmt.where(Demand.source.ilike(f"%{source}%"))
        count_stmt = count_stmt.where(Demand.source.ilike(f"%{source}%"))

    if date_from:
        dt_from = datetime.datetime.combine(
            date_from, datetime.time.min, tzinfo=datetime.timezone.utc
        )
        stmt = stmt.where(Demand.created_at >= dt_from)
        count_stmt = count_stmt.where(Demand.created_at >= dt_from)

    if date_to:
        dt_to = datetime.datetime.combine(
            date_to, datetime.time.max, tzinfo=datetime.timezone.utc
        )
        stmt = stmt.where(Demand.created_at <= dt_to)
        count_stmt = count_stmt.where(Demand.created_at <= dt_to)

    total = (await session.execute(count_stmt)).scalar_one()

    stmt = stmt.order_by(Demand.created_at.desc())
    stmt = stmt.offset((page - 1) * page_size).limit(page_size)

    rows = (await session.execute(stmt)).scalars().all()

    return DemandListResponse(
        items=[DemandOut.model_validate(d) for d in rows],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/demands/{demand_id}", response_model=DemandDetail)
async def get_demand(
    demand_id: int,
    session: AsyncSession = Depends(get_session),
) -> DemandDetail:
    """Return full detail for a single demand."""
    demand = await session.get(Demand, demand_id)
    if demand is None:
        raise HTTPException(status_code=404, detail="Demand not found")
    return DemandDetail.model_validate(demand)


@router.post("/demands/{demand_id}/approve", response_model=MessageResponse)
async def approve_demand(
    demand_id: int,
    session: AsyncSession = Depends(get_session),
) -> MessageResponse:
    """Manually approve a demand."""
    demand = await session.get(Demand, demand_id)
    if demand is None:
        raise HTTPException(status_code=404, detail="Demand not found")

    if demand.status not in (DemandStatus.PENDING, DemandStatus.EVALUATING):
        raise HTTPException(
            status_code=400,
            detail=f"Cannot approve demand in status '{demand.status.value}'",
        )

    demand.status = DemandStatus.APPROVED
    await session.commit()
    logger.info("Demand %s manually approved.", demand_id)
    return MessageResponse(message=f"Demand {demand_id} approved.")


@router.post("/demands/{demand_id}/reject", response_model=MessageResponse)
async def reject_demand(
    demand_id: int,
    session: AsyncSession = Depends(get_session),
) -> MessageResponse:
    """Manually reject a demand."""
    demand = await session.get(Demand, demand_id)
    if demand is None:
        raise HTTPException(status_code=404, detail="Demand not found")

    if demand.status not in (DemandStatus.PENDING, DemandStatus.EVALUATING):
        raise HTTPException(
            status_code=400,
            detail=f"Cannot reject demand in status '{demand.status.value}'",
        )

    demand.status = DemandStatus.REJECTED
    await session.commit()
    logger.info("Demand %s manually rejected.", demand_id)
    return MessageResponse(message=f"Demand {demand_id} rejected.")


# ── Devices ──────────────────────────────────────────────────────


@router.get("/devices/status")
async def get_device_status():
    """Check which emulators/simulators are running."""
    from zerodev.api.device_manager import check_devices
    return await check_devices()


@router.post("/apps/run")
async def run_app_on_device(body: dict):
    """Run a generated app on a specific platform's emulator."""
    app_dir = body.get("app_dir", "")
    platform = body.get("platform", "")
    if not app_dir or not platform:
        raise HTTPException(status_code=400, detail="app_dir and platform are required")
    from zerodev.api.device_manager import start_run_on_device
    return await start_run_on_device(app_dir, platform)


# ── Apps ─────────────────────────────────────────────────────────


@router.get("/apps", response_model=AppListResponse)
async def list_apps(
    status: Optional[str] = Query(None, description="Filter by app status"),
    search: Optional[str] = Query(None, description="Search by name"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
) -> AppListResponse:
    """List all apps in the registry with optional filters."""
    stmt = select(AppRegistry)
    count_stmt = select(func.count(AppRegistry.app_id))

    if status:
        try:
            status_enum = AppStatus(status)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid status: {status}")
        stmt = stmt.where(AppRegistry.status == status_enum)
        count_stmt = count_stmt.where(AppRegistry.status == status_enum)

    if search:
        stmt = stmt.where(AppRegistry.app_name.ilike(f"%{search}%"))
        count_stmt = count_stmt.where(AppRegistry.app_name.ilike(f"%{search}%"))

    total = (await session.execute(count_stmt)).scalar_one()

    stmt = stmt.order_by(AppRegistry.created_at.desc())
    stmt = stmt.offset((page - 1) * page_size).limit(page_size)

    rows = (await session.execute(stmt)).scalars().all()

    return AppListResponse(
        items=[AppOut.model_validate(a) for a in rows],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/apps/{app_id}", response_model=AppDetail)
async def get_app(
    app_id: int,
    session: AsyncSession = Depends(get_session),
) -> AppDetail:
    """Return full detail for a single app including build logs."""
    stmt = (
        select(AppRegistry)
        .where(AppRegistry.app_id == app_id)
        .options(selectinload(AppRegistry.build_logs))
    )
    result = await session.execute(stmt)
    app = result.scalar_one_or_none()
    if app is None:
        raise HTTPException(status_code=404, detail="App not found")

    app_dict = {
        "app_id": app.app_id,
        "demand_id": app.demand_id,
        "app_name": app.app_name,
        "package_name": app.package_name,
        "description": app.description,
        "category": app.category,
        "flutter_version": app.flutter_version,
        "project_path": app.project_path,
        "status": app.status.value if hasattr(app.status, "value") else str(app.status),
        "google_play_url": app.google_play_url,
        "total_downloads": app.total_downloads,
        "revenue_usd": app.revenue_usd,
        "rating": app.rating,
        "build_attempts": app.build_attempts,
        "fix_iterations": app.fix_iterations,
        "code_gen_cost_usd": app.code_gen_cost_usd,
        "published_at": app.published_at,
        "created_at": app.created_at,
        "updated_at": app.updated_at,
        "build_logs": [BuildLogOut.model_validate(b) for b in app.build_logs],
    }
    return AppDetail(**app_dict)


@router.post("/apps/{app_id}/rebuild", response_model=MessageResponse)
async def rebuild_app(
    app_id: int,
    session: AsyncSession = Depends(get_session),
) -> MessageResponse:
    """Trigger a rebuild for an existing app."""
    app = await session.get(AppRegistry, app_id)
    if app is None:
        raise HTTPException(status_code=404, detail="App not found")

    from zerodev.models import BuildStep

    build = BuildLog(
        demand_id=app.demand_id,
        app_id=app_id,
        step=BuildStep.BUILD_APK,
        status=BuildStatus.PENDING,
    )
    session.add(build)
    app.build_attempts += 1
    await session.commit()

    logger.info("Rebuild queued for app %s (build %s).", app_id, build.build_id)
    return MessageResponse(
        message=f"Rebuild queued for app {app_id} (build {build.build_id})."
    )


# ── Builds ───────────────────────────────────────────────────────


@router.get("/builds", response_model=BuildListResponse)
async def list_builds(
    limit: int = Query(50, ge=1, le=200),
    session: AsyncSession = Depends(get_session),
) -> BuildListResponse:
    """Return recent build logs."""
    stmt = select(BuildLog).order_by(BuildLog.created_at.desc()).limit(limit)
    rows = (await session.execute(stmt)).scalars().all()
    total = (
        await session.execute(select(func.count(BuildLog.build_id)))
    ).scalar_one()
    return BuildListResponse(
        items=[BuildLogOut.model_validate(b) for b in rows],
        total=total,
    )


# ── Stats ────────────────────────────────────────────────────────


@router.get("/stats", response_model=StatsResponse)
async def get_stats(
    days: int = Query(30, ge=1, le=365),
    session: AsyncSession = Depends(get_session),
) -> StatsResponse:
    """Return statistics: apps per day, revenue, ratings distribution."""
    since = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=days)

    # Apps created per day
    apps_per_day_rows = (
        await session.execute(
            select(
                cast(AppRegistry.created_at, Date).label("date"),
                func.count(AppRegistry.app_id).label("count"),
            )
            .where(AppRegistry.created_at >= since)
            .group_by(cast(AppRegistry.created_at, Date))
            .order_by(cast(AppRegistry.created_at, Date))
        )
    ).all()

    apps_per_day = [
        DailyStat(date=row.date, apps_created=row.count) for row in apps_per_day_rows
    ]

    # Total revenue from AppMetric
    total_revenue = (
        await session.execute(
            select(func.coalesce(func.sum(AppMetric.revenue_usd), 0.0))
        )
    ).scalar_one()

    # Ratings distribution
    ratings_rows = (
        await session.execute(
            select(
                case(
                    (AppMetric.rating < 1.0, "0-1"),
                    (AppMetric.rating < 2.0, "1-2"),
                    (AppMetric.rating < 3.0, "2-3"),
                    (AppMetric.rating < 4.0, "3-4"),
                    else_="4-5",
                ).label("rating_range"),
                func.count(AppMetric.metric_id).label("count"),
            ).group_by("rating_range")
        )
    ).all()

    ratings_distribution = [
        RatingBucket(rating_range=row.rating_range, count=row.count)
        for row in ratings_rows
    ]

    return StatsResponse(
        apps_per_day=apps_per_day,
        total_revenue_usd=float(total_revenue),
        ratings_distribution=ratings_distribution,
    )


# ── Pipeline ─────────────────────────────────────────────────────


@router.get("/pipeline/status/{thread_id}")
async def get_pipeline_status(thread_id: str) -> dict:
    """Return the current LangGraph checkpoint state for a given pipeline run.

    If the checkpointer is not available or the thread has no state,
    returns a graceful fallback.
    """
    try:
        from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

        from zerodev.pipeline.graph import build_main_graph

        checkpointer = AsyncSqliteSaver.from_conn_string("checkpoints.db")
        graph = build_main_graph(checkpointer=checkpointer)
        config = {"configurable": {"thread_id": thread_id}}
        state = await graph.aget_state(config)
        if state and state.values:
            return {
                "thread_id": thread_id,
                "status": "found",
                "stage": state.values.get("stage", "unknown"),
                "values": {
                    k: v
                    for k, v in state.values.items()
                    if k
                    not in (
                        "demands_raw",
                        "demands_structured",
                        "demands_evaluated",
                    )
                },
            }
        return {"thread_id": thread_id, "status": "not_found", "values": {}}
    except Exception as exc:
        logger.warning("Could not fetch pipeline state for %s: %s", thread_id, exc)
        return {
            "thread_id": thread_id,
            "status": "error",
            "message": str(exc),
        }


@router.post("/pipeline/trigger", response_model=PipelineTriggerResponse)
async def trigger_pipeline(
    session: AsyncSession = Depends(get_session),
) -> PipelineTriggerResponse:
    """Trigger a full pipeline run (crawl -> evaluate -> build)."""
    run = PipelineRun(trigger="manual", status="running")
    session.add(run)
    await session.commit()
    await session.refresh(run)

    logger.info("Pipeline run %s triggered manually.", run.run_id)

    # In production this would dispatch Celery tasks; for now we just
    # record the run and return immediately.
    return PipelineTriggerResponse(
        run_id=run.run_id,
        status="started",
        message="Pipeline run triggered successfully.",
    )


# ── Pipeline Loop Control ────────────────────────────────────


@router.post("/pipeline/start")
async def start_pipeline_loop():
    from zerodev.pipeline.runner import PipelineRunner

    runner = PipelineRunner.get_instance()
    result = runner.start()
    return result


@router.post("/pipeline/stop")
async def stop_pipeline_loop():
    from zerodev.pipeline.runner import PipelineRunner

    runner = PipelineRunner.get_instance()
    result = runner.stop()
    return result


@router.get("/pipeline/runner-status")
async def get_runner_status():
    from zerodev.pipeline.runner import PipelineRunner

    runner = PipelineRunner.get_instance()
    return runner.stats


@router.post("/pipeline/generate-custom")
async def generate_custom_app(body: dict):
    """Generate an app from a user-specified theme/description."""
    theme = body.get("theme", "")
    if not theme:
        raise HTTPException(status_code=400, detail="theme is required")

    from zerodev.pipeline.runner import PipelineRunner
    runner = PipelineRunner.get_instance()
    result = await runner.start_custom(theme)
    return result


@router.post("/pipeline/generate-concurrent")
async def generate_concurrent_app(body: dict):
    """Generate an app concurrently (doesn't block other pipelines)."""
    theme = body.get("theme", "")
    if not theme:
        raise HTTPException(status_code=400, detail="theme is required")

    from zerodev.pipeline.runner import PipelineRunner
    runner = PipelineRunner.get_instance()
    result = await runner.start_concurrent(theme)
    return result


@router.get("/pipeline/logs")
async def get_pipeline_logs():
    from zerodev.pipeline.runner import PipelineRunner

    runner = PipelineRunner.get_instance()
    return {"logs": runner.stats.get("logs", [])}


# ── App Revision ─────────────────────────────────────────────────


@router.post("/generated-apps/revise")
async def revise_app(body: dict):
    """Revise an existing generated app."""
    app_dir = body.get("app_dir", "")
    instruction = body.get("instruction", "")

    if not app_dir or not instruction:
        raise HTTPException(status_code=400, detail="app_dir and instruction are required")

    from zerodev.pipeline.reviser import AppReviser

    reviser = AppReviser()
    result = await reviser.revise(app_dir, instruction)
    return result


# ── Settings ──────────────────────────────────────────────────────


SETTINGS_FILE = Path(__file__).resolve().parent.parent.parent / "data" / "settings.json"

_SENSITIVE_KEYWORDS = ("key", "secret", "password", "token")


def _mask_value(value: str) -> str:
    """Mask a sensitive string, showing only last 4 characters."""
    if not value or len(value) <= 4:
        return "****"
    return "*" * (len(value) - 4) + value[-4:]


def _is_sensitive(field_name: str) -> bool:
    """Return True if the field name suggests a sensitive value."""
    lower = field_name.lower()
    return any(kw in lower for kw in _SENSITIVE_KEYWORDS)


def _get_defaults() -> dict[str, Any]:
    """Build default settings dict from config.py Settings class."""
    from zerodev.config import get_settings

    cfg = get_settings()
    return {
        "claudeMode": cfg.claude_mode,
        "claudeApiKey": cfg.claude_api_key,
        "claudeModel": cfg.claude_model,
        "claudeBaseUrl": cfg.claude_base_url,
        "crawlInterval": str(cfg.pipeline_crawl_interval_hours),
        "maxConcurrent": str(cfg.pipeline_max_concurrent_builds),
        "autoApproveThreshold": str(cfg.pipeline_auto_approve_threshold),
        "maxRetries": str(cfg.pipeline_max_retries),
        "retryDelay": str(cfg.pipeline_retry_backoff_base),
        "enabledSources": {
            "reddit": True,
            "producthunt": True,
            "twitter": False,
            "hackernews": True,
        },
        "redditClientId": cfg.reddit_client_id,
        "redditClientSecret": cfg.reddit_client_secret,
        "googlePlayKeyPath": cfg.google_play_json_key_path,
        "appStoreKeyPath": cfg.apple_api_key_path,
        "huaweiKeyPath": "",
        "outputDir": cfg.output_dir,
        "githubOrg": cfg.github_org,
    }


def _load_settings_file() -> dict[str, Any]:
    """Load settings from the JSON file, returning empty dict if missing."""
    if SETTINGS_FILE.exists():
        try:
            return json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Failed to read settings file: %s", exc)
    return {}


def _save_settings_file(data: dict[str, Any]) -> None:
    """Write settings dict to the JSON file."""
    SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
    SETTINGS_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


@router.get("/settings")
async def get_settings_api() -> dict[str, Any]:
    """Return current settings (merge file + env defaults), with secrets masked."""
    defaults = _get_defaults()
    saved = _load_settings_file()
    merged = {**defaults, **saved}

    # Mask sensitive top-level string fields
    masked = {}
    for k, v in merged.items():
        if isinstance(v, str) and _is_sensitive(k) and v:
            masked[k] = _mask_value(v)
        else:
            masked[k] = v
    return masked


@router.post("/settings")
async def save_settings_api(body: dict[str, Any]) -> MessageResponse:
    """Save settings to data/settings.json."""
    # Strip out masked values -- don't overwrite real secrets with mask strings
    current = _load_settings_file()
    cleaned: dict[str, Any] = {}
    for k, v in body.items():
        if isinstance(v, str) and v.startswith("*"):
            # Keep existing value if the user didn't change a masked field
            if k in current:
                cleaned[k] = current[k]
            # else: skip, don't store the mask
        else:
            cleaned[k] = v

    _save_settings_file(cleaned)
    logger.info("Settings saved to %s", SETTINGS_FILE)
    return MessageResponse(message="Settings saved successfully.")


@router.get("/generated-apps")
async def list_generated_apps():
    """List all generated app directories."""
    from zerodev.config import get_settings
    from pathlib import Path

    settings = get_settings()
    output_dir = Path(settings.output_dir)

    if not output_dir.exists():
        return {"apps": []}

    apps = []
    for d in sorted(output_dir.iterdir()):
        if d.is_dir() and (d / "pubspec.yaml").exists():
            # Read pubspec for app name
            pubspec = (d / "pubspec.yaml").read_text(encoding="utf-8")
            name = d.name
            for line in pubspec.split("\n"):
                if line.startswith("description:"):
                    name = line.split(":", 1)[1].strip().strip('"').strip("'")
                    break

            apps.append({
                "id": d.name,
                "name": name,
                "path": str(d),
                "created_at": datetime.datetime.fromtimestamp(
                    d.stat().st_ctime
                ).isoformat(),
            })

    return {"apps": apps}
