"""Celery application configuration."""

from __future__ import annotations

from celery import Celery
from celery.schedules import crontab

from autodev.config import get_settings

settings = get_settings()

celery = Celery(
    "autodev",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
)

celery.conf.update(
    # Serialization
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    # Timezone
    timezone="UTC",
    enable_utc=True,
    # Task behaviour
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    # Result expiry
    result_expires=3600 * 24,  # 24 hours
    # Concurrency
    worker_concurrency=4,
    # Task routes
    task_routes={
        "autodev.tasks.crawl_tasks.*": {"queue": "crawl"},
        "autodev.tasks.eval_tasks.*": {"queue": "eval"},
        "autodev.tasks.gen_tasks.*": {"queue": "gen"},
        "autodev.tasks.build_tasks.*": {"queue": "build"},
        "autodev.tasks.monitor_tasks.*": {"queue": "monitor"},
    },
    # Periodic tasks (celery beat)
    beat_schedule={
        "crawl-reddit-every-6h": {
            "task": "autodev.tasks.crawl_tasks.crawl_reddit",
            "schedule": crontab(minute=0, hour=f"*/{settings.pipeline_crawl_interval_hours}"),
        },
        "evaluate-pending-hourly": {
            "task": "autodev.tasks.eval_tasks.evaluate_pending",
            "schedule": crontab(minute=30),
        },
        "collect-metrics-every-15m": {
            "task": "autodev.tasks.monitor_tasks.collect_metrics",
            "schedule": crontab(minute="*/15"),
        },
    },
)

# Auto-discover tasks in the autodev.tasks package
celery.autodiscover_tasks(["autodev.tasks"])
