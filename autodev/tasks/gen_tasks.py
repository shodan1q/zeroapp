"""Celery tasks for code generation.

Thin wrappers around the LangGraph pipeline.  Code generation is handled
by the ``generate`` node in the per-demand sub-graph.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict

from autodev.celery_app import celery

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
    name="autodev.tasks.gen_tasks.generate_app",
    bind=True,
    max_retries=1,
    default_retry_delay=120,
    time_limit=1800,
    soft_time_limit=1500,
)
def generate_app(self, demand_id: int) -> dict:
    """Generate Flutter app code for a demand via the per-demand graph.

    Invokes the LangGraph per-demand pipeline (generate -> build -> assets -> publish)
    for the specified demand.
    """
    logger.info("Starting code generation for demand %d.", demand_id)

    try:
        from autodev.pipeline import run_single_demand

        # Construct a minimal demand dict (in production, fetch from DB).
        demand: Dict[str, Any] = {
            "id": demand_id,
            "title": "Placeholder",
            "description": "Placeholder demand.",
            "core_features": "",
        }

        result = _run_async(run_single_demand(demand))

        logger.info(
            "Generation for demand %d complete: stage=%s, failed=%s.",
            demand_id,
            result.get("stage"),
            result.get("failed", False),
        )
        return {
            "demand_id": demand_id,
            "stage": result.get("stage"),
            "project_path": result.get("project_path"),
            "failed": result.get("failed", False),
            "errors": result.get("errors", []),
        }
    except Exception as exc:
        logger.exception("Code generation failed for demand %d.", demand_id)
        raise self.retry(exc=exc)


@celery.task(name="autodev.tasks.gen_tasks.generate_pending")
def generate_pending() -> dict:
    """Generate code for all pending approved demands via a full pipeline run."""
    logger.info("Running pipeline for pending code generation.")
    from autodev.pipeline import run_pipeline

    summary = _run_async(run_pipeline())
    return {
        "run_id": summary.run_id,
        "built": summary.demands_built,
        "published": summary.demands_published,
    }
