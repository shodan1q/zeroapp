"""Celery tasks for demand evaluation.

Thin wrappers around the LangGraph pipeline.  The evaluation logic
is handled by the ``evaluate_batch`` and ``decide_batch`` graph nodes.
"""

from __future__ import annotations

import asyncio
import logging

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
    name="autodev.tasks.eval_tasks.evaluate_demand",
    bind=True,
    max_retries=2,
    default_retry_delay=60,
)
def evaluate_demand(self, demand_id: int) -> dict:
    """Evaluate a single demand by running it through the pipeline.

    For single-demand evaluation, this invokes the full pipeline which
    includes the evaluate and decide nodes.
    """
    logger.info("Evaluating demand %d via LangGraph pipeline.", demand_id)
    try:
        from autodev.pipeline import run_pipeline

        summary = _run_async(run_pipeline())
        return {
            "demand_id": demand_id,
            "run_id": summary.run_id,
            "approved": summary.demands_approved,
            "rejected": summary.demands_rejected,
        }
    except Exception as exc:
        logger.exception("Evaluation pipeline failed for demand %d.", demand_id)
        raise self.retry(exc=exc)


@celery.task(name="autodev.tasks.eval_tasks.evaluate_pending")
def evaluate_pending() -> dict:
    """Evaluate all pending demands via a full pipeline run."""
    logger.info("Running pipeline to evaluate pending demands.")
    from autodev.pipeline import run_pipeline

    summary = _run_async(run_pipeline())
    return {
        "run_id": summary.run_id,
        "approved": summary.demands_approved,
        "rejected": summary.demands_rejected,
    }
