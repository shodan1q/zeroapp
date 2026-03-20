"""Celery tasks for crawling demands from external sources.

Periodic task ``crawl_all`` dispatches individual source crawlers
and persists results to the database.
"""

from __future__ import annotations

import asyncio
import datetime
import logging
from typing import Any, Dict, List

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


async def _crawl_source(source_name: str) -> List[Dict[str, Any]]:
    """Crawl a single source and return raw demand dicts."""
    results: List[Dict[str, Any]] = []

    if source_name == "reddit":
        from autodev.crawler.reddit import RedditCrawler

        crawler = RedditCrawler()
        demands = await crawler.crawl()
        results = [d.model_dump() for d in demands]

    elif source_name == "producthunt":
        from autodev.crawler.producthunt import ProductHuntCrawler

        crawler = ProductHuntCrawler()
        demands = await crawler.crawl()
        results = [d.model_dump() for d in demands]

    elif source_name == "appstore":
        try:
            from autodev.crawler.appstore import AppStoreCrawler

            crawler = AppStoreCrawler()
            demands = await crawler.crawl()
            results = [d.model_dump() for d in demands]
        except ImportError:
            logger.warning("AppStoreCrawler not available.")

    return results


async def _persist_demands(demands: List[Dict[str, Any]]) -> int:
    """Save crawled demands to the database. Returns count persisted."""
    try:
        from autodev.database import get_async_session

        saved = 0
        async with get_async_session() as session:
            for demand in demands:
                # TODO: Create ORM Demand model and insert.
                # For now, log the demand.
                logger.debug(
                    "Would persist demand: %s", demand.get("title", "?")
                )
                saved += 1
        return saved
    except Exception as exc:
        logger.error("Failed to persist demands: %s", exc)
        return 0


@celery.task(
    name="autodev.tasks.crawl_tasks.crawl_reddit",
    bind=True,
    max_retries=3,
    default_retry_delay=300,
)
def crawl_reddit(self) -> dict:
    """Crawl Reddit for new app demands."""
    logger.info("Starting Reddit crawl task.")
    try:
        demands = _run_async(_crawl_source("reddit"))
        saved = _run_async(_persist_demands(demands))
        logger.info("Reddit crawl complete: %d crawled, %d saved.", len(demands), saved)
        return {"source": "reddit", "crawled": len(demands), "saved": saved}
    except Exception as exc:
        logger.exception("Reddit crawl failed.")
        raise self.retry(exc=exc)


@celery.task(
    name="autodev.tasks.crawl_tasks.crawl_producthunt",
    bind=True,
    max_retries=3,
    default_retry_delay=300,
)
def crawl_producthunt(self) -> dict:
    """Crawl ProductHunt for new product launches."""
    logger.info("Starting ProductHunt crawl task.")
    try:
        demands = _run_async(_crawl_source("producthunt"))
        saved = _run_async(_persist_demands(demands))
        logger.info(
            "ProductHunt crawl complete: %d crawled, %d saved.",
            len(demands),
            saved,
        )
        return {
            "source": "producthunt",
            "crawled": len(demands),
            "saved": saved,
        }
    except Exception as exc:
        logger.exception("ProductHunt crawl failed.")
        raise self.retry(exc=exc)


@celery.task(name="autodev.tasks.crawl_tasks.crawl_all")
def crawl_all() -> dict:
    """Dispatch crawl tasks for all configured sources."""
    logger.info("Dispatching crawl tasks for all sources.")
    reddit_result = crawl_reddit.delay()
    ph_result = crawl_producthunt.delay()
    return {
        "dispatched": ["reddit", "producthunt"],
        "task_ids": {
            "reddit": reddit_result.id,
            "producthunt": ph_result.id,
        },
    }
