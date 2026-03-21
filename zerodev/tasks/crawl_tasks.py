"""Celery tasks for crawling demands.

These are thin wrappers that invoke the LangGraph pipeline.
Celery Beat schedules these periodically; the actual crawling logic
lives in the pipeline graph nodes.
"""

from __future__ import annotations

import asyncio
import logging

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
    name="zerodev.tasks.crawl_tasks.crawl_reddit",
    bind=True,
    max_retries=3,
    default_retry_delay=300,
)
def crawl_reddit(self) -> dict:
    """Crawl Reddit for new app demands via the LangGraph pipeline."""
    logger.info("Starting Reddit crawl task (LangGraph pipeline).")
    try:
        from zerodev.pipeline import run_pipeline

        summary = _run_async(run_pipeline())
        logger.info(
            "Pipeline crawl complete: crawled=%d approved=%d.",
            summary.demands_crawled,
            summary.demands_approved,
        )
        return {
            "source": "reddit",
            "run_id": summary.run_id,
            "crawled": summary.demands_crawled,
            "approved": summary.demands_approved,
        }
    except Exception as exc:
        logger.exception("Reddit crawl pipeline failed.")
        raise self.retry(exc=exc)


@celery.task(name="zerodev.tasks.crawl_tasks.crawl_all")
def crawl_all() -> dict:
    """Run a full pipeline cycle (crawl all sources)."""
    logger.info("Running full pipeline cycle via crawl_all.")
    from zerodev.pipeline import run_pipeline

    summary = _run_async(run_pipeline())
    return {
        "run_id": summary.run_id,
        "crawled": summary.demands_crawled,
        "approved": summary.demands_approved,
        "built": summary.demands_built,
        "published": summary.demands_published,
        "errors": len(summary.errors),
    }
