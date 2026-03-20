"""Celery tasks for demand evaluation.

Runs feasibility and competition analysis on pending demands and
updates their scores in the database.
"""

from __future__ import annotations

import asyncio
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


async def _evaluate_single(demand: Dict[str, Any]) -> Dict[str, Any]:
    """Run feasibility + competition evaluation on a single demand."""
    from autodev.evaluator.feasibility import evaluate_feasibility
    from autodev.evaluator.competition import analyse_competition

    feasibility = await evaluate_feasibility(demand)
    competition = await analyse_competition(demand)

    # Compute composite score.
    comp_score = competition.competition_score
    opportunity = 1.0 - comp_score
    complexity_map = {"low": 0.3, "medium": 0.15, "high": 0.0}
    complexity_bonus = complexity_map.get(feasibility.complexity, 0.0)
    final_score = min(1.0, max(0.0, opportunity * 0.7 + complexity_bonus))

    settings = get_settings()
    if not feasibility.feasible:
        decision = "rejected"
    elif (
        feasibility.complexity == "high" and feasibility.needs_backend
    ):
        decision = "rejected"
    elif final_score >= settings.pipeline_auto_approve_threshold:
        decision = "approved"
    elif final_score <= settings.pipeline_auto_reject_threshold:
        decision = "rejected"
    else:
        decision = "review"

    return {
        "feasibility": feasibility.model_dump(),
        "competition": competition.model_dump(),
        "final_score": final_score,
        "decision": decision,
    }


async def _update_demand_evaluation(
    demand_id: int, evaluation: Dict[str, Any]
) -> None:
    """Persist evaluation results to the database."""
    try:
        from autodev.database import get_async_session

        async with get_async_session() as session:
            # TODO: Update the Demand ORM record with evaluation results.
            logger.info(
                "Would update demand %d: decision=%s score=%.3f",
                demand_id,
                evaluation.get("decision"),
                evaluation.get("final_score", 0),
            )
    except Exception as exc:
        logger.error(
            "Failed to persist evaluation for demand %d: %s",
            demand_id,
            exc,
        )


@celery.task(
    name="autodev.tasks.eval_tasks.evaluate_demand",
    bind=True,
    max_retries=2,
    default_retry_delay=60,
)
def evaluate_demand(self, demand_id: int) -> dict:
    """Evaluate a single demand by ID.

    Fetches the demand from the database, runs feasibility and
    competition analysis, computes a score, and updates the record.
    """
    logger.info("Evaluating demand %d.", demand_id)

    try:
        # TODO: Fetch demand from DB by demand_id.
        # For now, use a placeholder.
        demand = {
            "id": demand_id,
            "title": "Placeholder",
            "description": "Placeholder demand for evaluation.",
            "core_features": "",
        }

        evaluation = _run_async(_evaluate_single(demand))
        _run_async(_update_demand_evaluation(demand_id, evaluation))

        logger.info(
            "Demand %d evaluated: decision=%s score=%.3f",
            demand_id,
            evaluation["decision"],
            evaluation["final_score"],
        )
        return {
            "demand_id": demand_id,
            "decision": evaluation["decision"],
            "score": evaluation["final_score"],
        }
    except Exception as exc:
        logger.exception("Evaluation failed for demand %d.", demand_id)
        raise self.retry(exc=exc)


@celery.task(name="autodev.tasks.eval_tasks.evaluate_pending")
def evaluate_pending() -> dict:
    """Evaluate all pending (unevaluated) demands.

    Queries the database for demands with status 'pending', dispatches
    individual evaluation tasks for each.
    """
    logger.info("Evaluating all pending demands.")

    # TODO: Query pending demands from DB.
    # pending_ids = _run_async(_get_pending_demand_ids())
    pending_ids: list[int] = []

    dispatched = 0
    for demand_id in pending_ids:
        evaluate_demand.delay(demand_id)
        dispatched += 1

    logger.info("Dispatched %d evaluation tasks.", dispatched)
    return {"evaluated": dispatched}
