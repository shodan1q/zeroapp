"""Celery tasks for monitoring and metrics collection.

Periodically collects pipeline health metrics: task counts, error rates,
build success rates, and stores them for the dashboard.

NOTE: This module is unchanged from the original -- it does not go through
the LangGraph pipeline since it is purely a monitoring / health-check concern.
"""

from __future__ import annotations

import asyncio
import datetime
import logging
from typing import Any, Dict

from autodev.celery_app import celery
from autodev.config import get_settings

logger = logging.getLogger(__name__)


def _run_async(coro):
    """Run an async coroutine from a sync Celery task."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures

            with concurrent.futures.ThreadPoolExecutor() as pool:
                return pool.submit(asyncio.run, coro).result()
        return loop.run_until_complete(coro)
    except RuntimeError:
        return asyncio.run(coro)


async def _collect_pipeline_metrics() -> Dict[str, Any]:
    """Gather metrics from the database and celery inspect."""
    metrics: Dict[str, Any] = {
        "timestamp": datetime.datetime.now(
            datetime.timezone.utc
        ).isoformat(),
        "demands": {},
        "builds": {},
        "tasks": {},
    }

    # Demand counts by status.
    try:
        from autodev.database import get_async_session

        async with get_async_session() as session:
            # TODO: Query actual counts from ORM.
            metrics["demands"] = {
                "total": 0,
                "pending": 0,
                "approved": 0,
                "rejected": 0,
                "review": 0,
                "generated": 0,
                "built": 0,
                "published": 0,
            }
    except Exception as exc:
        logger.warning("Failed to query demand metrics: %s", exc)

    # Celery worker stats.
    try:
        from autodev.celery_app import celery as celery_app

        inspect = celery_app.control.inspect()
        active = inspect.active() or {}
        reserved = inspect.reserved() or {}

        total_active = sum(len(tasks) for tasks in active.values())
        total_reserved = sum(len(tasks) for tasks in reserved.values())

        metrics["tasks"] = {
            "active_workers": len(active),
            "active_tasks": total_active,
            "reserved_tasks": total_reserved,
        }
    except Exception as exc:
        logger.warning("Failed to inspect Celery workers: %s", exc)

    return metrics


async def _store_metrics(metrics: Dict[str, Any]) -> None:
    """Persist metrics snapshot to the database or Redis."""
    try:
        import json

        import redis

        settings = get_settings()
        r = redis.from_url(settings.redis_url)
        key = f"autodev:metrics:{metrics['timestamp']}"
        r.setex(key, 86400, json.dumps(metrics))  # TTL 24h
        r.set("autodev:metrics:latest", json.dumps(metrics))
        logger.debug("Metrics stored: %s", key)
    except Exception as exc:
        logger.warning("Failed to store metrics in Redis: %s", exc)


@celery.task(name="autodev.tasks.monitor_tasks.collect_metrics")
def collect_metrics() -> dict:
    """Collect and store pipeline metrics.

    Runs every 15 minutes (configured in celery beat_schedule).
    Collects demand counts, build stats, and worker health.
    """
    logger.info("Collecting pipeline metrics.")

    try:
        metrics = _run_async(_collect_pipeline_metrics())
        _run_async(_store_metrics(metrics))

        logger.info(
            "Metrics collected: demands=%s tasks=%s",
            metrics.get("demands", {}),
            metrics.get("tasks", {}),
        )
        return {"status": "ok", "metrics": metrics}
    except Exception as exc:
        logger.exception("Metrics collection failed.")
        return {"status": "error", "error": str(exc)}


@celery.task(name="autodev.tasks.monitor_tasks.health_check")
def health_check() -> dict:
    """Quick health check: verify DB and Redis connectivity."""
    status: Dict[str, Any] = {
        "timestamp": datetime.datetime.now(
            datetime.timezone.utc
        ).isoformat(),
        "database": "unknown",
        "redis": "unknown",
        "flutter": "unknown",
    }

    # Database check.
    try:
        from autodev.database import get_sync_session

        session = get_sync_session()
        session.execute("SELECT 1")  # type: ignore[arg-type]
        session.close()
        status["database"] = "ok"
    except Exception as exc:
        status["database"] = f"error: {exc}"

    # Redis check.
    try:
        import redis

        settings = get_settings()
        r = redis.from_url(settings.redis_url)
        r.ping()
        status["redis"] = "ok"
    except Exception as exc:
        status["redis"] = f"error: {exc}"

    # Flutter check.
    try:
        import subprocess

        result = subprocess.run(
            ["flutter", "--version"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            version_line = result.stdout.splitlines()[0] if result.stdout else "ok"
            status["flutter"] = version_line
        else:
            status["flutter"] = f"error: rc={result.returncode}"
    except Exception as exc:
        status["flutter"] = f"error: {exc}"

    logger.info("Health check: %s", status)
    return status
