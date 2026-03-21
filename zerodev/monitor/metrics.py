"""Metrics collection stubs for Play Store, AdMob, and Firebase.

Each collection function returns realistic-looking stub data.  Replace with
real API integrations when credentials and SDKs are available.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from zerodev.models import AppMetric, AppRegistry, AppStatus

logger = logging.getLogger(__name__)


# ── Play Store ───────────────────────────────────────────────────


async def collect_play_store_metrics(package_name: str) -> Dict[str, Any]:
    """Collect download, rating, and review count from the Play Store.

    Parameters
    ----------
    package_name:
        Android package name, e.g. ``com.example.myapp``.

    Returns
    -------
    dict with keys ``downloads``, ``rating``, ``review_count``.
    """
    logger.info("Collecting Play Store metrics for %s (stub)", package_name)

    # TODO: Replace with google-play-scraper or Play Developer API call.
    return {
        "downloads": 0,
        "rating": 0.0,
        "review_count": 0,
    }


# ── AdMob / Revenue ─────────────────────────────────────────────


async def collect_admob_metrics(app_id: str) -> Dict[str, Any]:
    """Collect ad revenue metrics from AdMob.

    Parameters
    ----------
    app_id:
        AdMob app ID.

    Returns
    -------
    dict with keys ``revenue_usd``, ``impressions``, ``clicks``.
    """
    logger.info("Collecting AdMob metrics for %s (stub)", app_id)

    # TODO: Replace with AdMob Reporting API integration.
    return {
        "revenue_usd": 0.0,
        "impressions": 0,
        "clicks": 0,
    }


# ── Firebase ─────────────────────────────────────────────────────


async def collect_firebase_metrics(app_id: str) -> Dict[str, Any]:
    """Collect usage and stability metrics from Firebase.

    Parameters
    ----------
    app_id:
        Firebase project / app ID.

    Returns
    -------
    dict with keys ``dau``, ``mau``, ``crash_rate``.
    """
    logger.info("Collecting Firebase metrics for %s (stub)", app_id)

    # TODO: Replace with Firebase Analytics / Crashlytics API.
    return {
        "dau": 0,
        "mau": 0,
        "crash_rate": 0.0,
    }


# ── Aggregation ──────────────────────────────────────────────────


async def aggregate_daily_metrics(session: AsyncSession) -> List[AppMetric]:
    """Collect and persist metrics for all live apps.

    Iterates over every app with ``status == LIVE``, calls each metrics
    source, and writes a combined :class:`AppMetric` row.

    Parameters
    ----------
    session:
        Active async database session.

    Returns
    -------
    List of newly created :class:`AppMetric` instances.
    """
    stmt = select(AppRegistry).where(AppRegistry.status == AppStatus.LIVE)
    apps = (await session.execute(stmt)).scalars().all()

    logger.info("Aggregating daily metrics for %d live apps.", len(apps))

    new_metrics: List[AppMetric] = []

    for app in apps:
        try:
            play = await collect_play_store_metrics(app.package_name or "")
            admob = await collect_admob_metrics(str(app.app_id))
            firebase = await collect_firebase_metrics(str(app.app_id))

            metric = AppMetric(
                app_id=app.app_id,
                downloads=play.get("downloads", 0),
                rating=play.get("rating", 0.0),
                review_count=play.get("review_count", 0),
                revenue_usd=admob.get("revenue_usd", 0.0),
                ad_impressions=admob.get("impressions", 0),
                ad_clicks=admob.get("clicks", 0),
                dau=firebase.get("dau", 0),
                mau=firebase.get("mau", 0),
                crash_rate=firebase.get("crash_rate", 0.0),
            )
            session.add(metric)
            new_metrics.append(metric)

        except Exception:
            logger.exception(
                "Failed to collect metrics for app %s (%s)",
                app.app_name,
                app.app_id,
            )

    await session.flush()
    logger.info("Persisted %d metric records.", len(new_metrics))
    return new_metrics
