"""Celery tasks for building and publishing Flutter apps.

Thin wrappers around the LangGraph pipeline.  Build and publish logic
is handled by the ``build``, ``assets``, and ``publish`` nodes in the
per-demand sub-graph.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict

from zerodev.celery_app import celery

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


@celery.task(
    name="zerodev.tasks.build_tasks.build_app",
    bind=True,
    max_retries=1,
    default_retry_delay=300,
    time_limit=3600,
    soft_time_limit=3300,
)
def build_app(self, demand_id: int) -> dict:
    """Build a Flutter app for a demand via the per-demand graph."""
    logger.info("Starting build for demand %d.", demand_id)

    try:
        from zerodev.pipeline import run_single_demand

        demand: Dict[str, Any] = {
            "id": demand_id,
            "title": "Placeholder",
            "description": "Placeholder demand.",
        }

        result = _run_async(run_single_demand(demand))

        logger.info(
            "Build for demand %d: stage=%s, artifacts=%s.",
            demand_id,
            result.get("stage"),
            list((result.get("build_artifacts") or {}).keys()),
        )
        return {
            "demand_id": demand_id,
            "stage": result.get("stage"),
            "artifacts": result.get("build_artifacts", {}),
            "failed": result.get("failed", False),
            "errors": result.get("errors", []),
        }
    except Exception as exc:
        logger.exception("Build failed for demand %d.", demand_id)
        raise self.retry(exc=exc)


@celery.task(
    name="zerodev.tasks.build_tasks.build_and_publish",
    bind=True,
    time_limit=7200,
    soft_time_limit=6900,
)
def build_and_publish(self, demand_id: int) -> dict:
    """Full pipeline: build, assets, and publish for a single demand."""
    logger.info("Starting build-and-publish for demand %d.", demand_id)

    try:
        from zerodev.pipeline import run_single_demand

        demand: Dict[str, Any] = {
            "id": demand_id,
            "title": "Placeholder",
            "description": "Placeholder demand.",
        }

        result = _run_async(run_single_demand(demand))

        return {
            "demand_id": demand_id,
            "stage": result.get("stage"),
            "artifacts": result.get("build_artifacts", {}),
            "publish_results": result.get("publish_results", {}),
            "failed": result.get("failed", False),
            "errors": result.get("errors", []),
        }
    except Exception as exc:
        logger.exception("Build-and-publish failed for demand %d.", demand_id)
        raise self.retry(exc=exc)


@celery.task(name="zerodev.tasks.build_tasks.build_pending")
def build_pending() -> dict:
    """Build all pending apps via a full pipeline run."""
    logger.info("Running pipeline for pending builds.")
    from zerodev.pipeline import run_pipeline

    summary = _run_async(run_pipeline())
    return {
        "run_id": summary.run_id,
        "built": summary.demands_built,
        "published": summary.demands_published,
    }
