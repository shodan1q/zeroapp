"""Celery tasks for code generation.

Takes approved demands and generates Flutter projects using the generator
layer (template selection, PRD, code generation, dependency fixing).
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, Optional

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


async def _generate_app_code(
    demand: Dict[str, Any],
) -> Dict[str, Any]:
    """Generate a complete Flutter project for *demand*.

    Returns a dict with ``project_path`` and ``status``.
    """
    result: Dict[str, Any] = {
        "project_path": None,
        "status": "failed",
        "errors": [],
    }

    try:
        from autodev.generator import (
            select_template,
            generate_prd,
            generate_project,
            check_and_fix_dependencies,
            auto_fix_project,
        )

        template = await select_template(demand)
        logger.info("Template: %s", template)

        prd = await generate_prd(demand)
        logger.info("PRD generated for %s.", demand.get("title"))

        project = await generate_project(prd, template=template)
        logger.info("Code generated at %s.", project.path)

        await check_and_fix_dependencies(project.path)

        fix_result = await auto_fix_project(project.path)
        if not fix_result.success:
            result["errors"] = fix_result.errors[:5]
            logger.warning("Auto-fix issues: %s", fix_result.errors[:3])

        result["project_path"] = project.path
        result["status"] = "success"

    except ImportError:
        # Generator not fully available; fall back to flutter create.
        logger.warning("Generator not available; using flutter create.")
        from autodev.builder.flutter_builder import FlutterBuilder

        builder = FlutterBuilder()
        build_result = await builder.create_project(
            str(demand.get("id", "unknown")),
            demand.get("title", "app"),
        )
        if build_result.success:
            result["project_path"] = build_result.artifact_path
            result["status"] = "success_fallback"
        else:
            result["errors"] = build_result.errors

    return result


async def _update_demand_project(
    demand_id: int, project_path: Optional[str], status: str
) -> None:
    """Update the demand record with the generated project path."""
    try:
        from autodev.database import get_async_session

        async with get_async_session() as session:
            logger.info(
                "Would update demand %d: project_path=%s status=%s",
                demand_id,
                project_path,
                status,
            )
            # TODO: Update ORM record.
    except Exception as exc:
        logger.error(
            "Failed to update demand %d project path: %s",
            demand_id,
            exc,
        )


@celery.task(
    name="autodev.tasks.gen_tasks.generate_app",
    bind=True,
    max_retries=1,
    default_retry_delay=120,
    time_limit=1800,
    soft_time_limit=1500,
)
def generate_app(self, demand_id: int) -> dict:
    """Generate Flutter app code for an approved demand.

    Fetches the demand from the database, runs the full generation
    pipeline, and records the project path.
    """
    logger.info("Starting code generation for demand %d.", demand_id)

    try:
        # TODO: Fetch demand from DB.
        demand: Dict[str, Any] = {
            "id": demand_id,
            "title": "Placeholder",
            "description": "Placeholder demand.",
            "core_features": "",
        }

        result = _run_async(_generate_app_code(demand))
        _run_async(
            _update_demand_project(
                demand_id, result.get("project_path"), result["status"]
            )
        )

        logger.info(
            "Code generation for demand %d: status=%s path=%s",
            demand_id,
            result["status"],
            result.get("project_path"),
        )
        return {
            "demand_id": demand_id,
            "status": result["status"],
            "project_path": result.get("project_path"),
            "errors": result.get("errors", []),
        }
    except Exception as exc:
        logger.exception(
            "Code generation failed for demand %d.", demand_id
        )
        raise self.retry(exc=exc)


@celery.task(name="autodev.tasks.gen_tasks.generate_pending")
def generate_pending() -> dict:
    """Generate code for all approved demands without generated code.

    Queries the database for approved demands that have not yet been
    generated, and dispatches individual generation tasks.
    """
    logger.info("Generating code for all pending approved demands.")

    # TODO: Query approved demands without project_path from DB.
    pending_ids: list[int] = []

    dispatched = 0
    for demand_id in pending_ids:
        generate_app.delay(demand_id)
        dispatched += 1

    logger.info("Dispatched %d generation tasks.", dispatched)
    return {"dispatched": dispatched}
