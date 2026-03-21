"""Main pipeline orchestrator: crawl -> evaluate -> generate -> build -> publish.

Chains together every layer of the AutoDev Agent using LangGraph:
  crawl -> process -> evaluate -> decide -> generate -> build -> assets -> publish

Supports:
- One-shot execution of a full pipeline cycle
- Resuming from the last checkpoint after a crash
- Continuous loop mode with configurable interval
- Both batch processing (multiple demands) and single-demand graphs

Persistence is handled by a configurable LangGraph checkpointer (in-memory
for development, SQLite for production MVP).
"""

from __future__ import annotations

import asyncio
import datetime
import logging
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from autodev.config import get_settings
from autodev.pipeline.checkpointer import get_checkpointer
from autodev.pipeline.graph import build_demand_graph, build_main_graph
from autodev.pipeline.state import DemandState, PipelineState

logger = logging.getLogger(__name__)


# ── Pipeline run summary ─────────────────────────────────────────────────


@dataclass
class PipelineRunSummary:
    """Summary of a completed (or failed) pipeline run."""

    run_id: str
    thread_id: str
    started_at: datetime.datetime
    finished_at: Optional[datetime.datetime] = None
    demands_crawled: int = 0
    demands_approved: int = 0
    demands_rejected: int = 0
    demands_built: int = 0
    demands_published: int = 0
    errors: List[str] = field(default_factory=list)
    final_state: Optional[Dict[str, Any]] = None
    resumed: bool = False


# ── Public API ────────────────────────────────────────────────────────────


async def run_pipeline(
    *,
    thread_id: str | None = None,
) -> PipelineRunSummary:
    """Execute one full pipeline cycle and return a summary.

    Parameters
    ----------
    thread_id : str, optional
        Identifier for checkpoint persistence.  If omitted a new UUID is
        generated.  Pass an existing ``thread_id`` to resume from the last
        checkpoint.

    Returns
    -------
    PipelineRunSummary
    """
    settings = get_settings()
    checkpointer = get_checkpointer()

    if thread_id is None:
        thread_id = f"run-{uuid.uuid4().hex[:12]}"
        resumed = False
    else:
        resumed = True

    run_id = thread_id
    summary = PipelineRunSummary(
        run_id=run_id,
        thread_id=thread_id,
        started_at=datetime.datetime.now(datetime.timezone.utc),
        resumed=resumed,
    )

    logger.info(
        "Pipeline %s started (thread_id=%s, resumed=%s).",
        run_id,
        thread_id,
        resumed,
    )

    graph = build_main_graph(checkpointer=checkpointer)
    config = {"configurable": {"thread_id": thread_id}}

    try:
        # When resuming, pass None so LangGraph loads from checkpoint.
        # For a fresh run, supply the initial state.
        if resumed:
            initial_input = None
            logger.info("Resuming pipeline from checkpoint (thread_id=%s).", thread_id)
        else:
            initial_input: dict[str, Any] | None = {
                "demands_raw": [],
                "demands_structured": [],
                "demands_evaluated": [],
                "demands_approved": [],
                "demands_rejected": [],
                "demand_results": [],
                "stage": "init",
                "errors": [],
                "retry_count": 0,
                "run_id": run_id,
                "demands_crawled_count": 0,
                "demands_approved_count": 0,
                "demands_rejected_count": 0,
                "demands_built_count": 0,
                "demands_published_count": 0,
            }

        final_state = await graph.ainvoke(initial_input, config=config)

        # Extract summary from final state.
        summary.demands_crawled = final_state.get("demands_crawled_count", 0)
        summary.demands_approved = final_state.get("demands_approved_count", 0)
        summary.demands_rejected = final_state.get("demands_rejected_count", 0)
        summary.demands_built = final_state.get("demands_built_count", 0)
        summary.demands_published = final_state.get("demands_published_count", 0)
        summary.errors = final_state.get("errors", [])
        summary.final_state = final_state

    except Exception as exc:
        logger.exception("Pipeline run %s failed.", run_id)
        summary.errors.append(f"Pipeline error: {exc}")

    summary.finished_at = datetime.datetime.now(datetime.timezone.utc)

    logger.info(
        "Pipeline %s finished. crawled=%d approved=%d built=%d published=%d errors=%d",
        run_id,
        summary.demands_crawled,
        summary.demands_approved,
        summary.demands_built,
        summary.demands_published,
        len(summary.errors),
    )

    # Persist run summary to database (best-effort).
    await _persist_run(summary)

    return summary


async def resume_pipeline(thread_id: str) -> PipelineRunSummary:
    """Resume a pipeline run from its last checkpoint.

    Parameters
    ----------
    thread_id : str
        The thread_id of the run to resume.

    Returns
    -------
    PipelineRunSummary
    """
    return await run_pipeline(thread_id=thread_id)


async def run_single_demand(
    demand: Dict[str, Any],
    *,
    thread_id: str | None = None,
) -> Dict[str, Any]:
    """Process a single demand through generate -> build -> assets -> publish.

    Parameters
    ----------
    demand : dict
        The structured demand dict.
    thread_id : str, optional
        For checkpoint persistence.

    Returns
    -------
    dict
        The final DemandState dict.
    """
    checkpointer = get_checkpointer()
    graph = build_demand_graph(checkpointer=checkpointer)

    if thread_id is None:
        thread_id = f"demand-{uuid.uuid4().hex[:12]}"

    demand_id = demand.get("id", uuid.uuid4().hex[:12])
    initial_state: Dict[str, Any] = {
        "demand_id": demand_id,
        "demand": demand,
        "project_path": None,
        "build_artifacts": {},
        "assets": {},
        "publish_results": {},
        "stage": "generate",
        "errors": [],
        "retry_count": 0,
        "failed": False,
    }

    config = {"configurable": {"thread_id": thread_id}}
    result = await graph.ainvoke(initial_state, config=config)
    return result


async def run_loop(
    *,
    interval_hours: int | None = None,
) -> None:
    """Run the pipeline in a continuous loop.

    Sleeps for ``interval_hours`` between cycles (defaults to settings).
    Cancel the awaited task to stop the loop.
    """
    settings = get_settings()
    interval = (interval_hours or settings.pipeline_crawl_interval_hours) * 3600

    logger.info(
        "Starting continuous pipeline loop (interval=%dh).",
        interval // 3600,
    )

    while True:
        try:
            summary = await run_pipeline()
            logger.info(
                "Loop cycle %s complete. Next run in %ds.",
                summary.run_id,
                interval,
            )
        except Exception:
            logger.exception("Pipeline cycle failed; will retry next cycle.")

        try:
            await asyncio.sleep(interval)
        except asyncio.CancelledError:
            logger.info("Pipeline loop cancelled.")
            break


async def get_pipeline_status(thread_id: str) -> Dict[str, Any]:
    """Query the checkpoint state for a given pipeline run.

    Parameters
    ----------
    thread_id : str
        The thread_id to look up.

    Returns
    -------
    dict
        The stored state, or a status dict indicating not found.
    """
    checkpointer = get_checkpointer()
    config = {"configurable": {"thread_id": thread_id}}

    try:
        # Build the graph to access the checkpointer through it.
        graph = build_main_graph(checkpointer=checkpointer)
        state = await graph.aget_state(config)
        if state and state.values:
            return {
                "thread_id": thread_id,
                "found": True,
                "stage": state.values.get("stage", "unknown"),
                "errors": state.values.get("errors", []),
                "demands_crawled": state.values.get("demands_crawled_count", 0),
                "demands_approved": state.values.get("demands_approved_count", 0),
                "demands_built": state.values.get("demands_built_count", 0),
                "demands_published": state.values.get("demands_published_count", 0),
                "next_steps": list(state.next) if state.next else [],
            }
        return {"thread_id": thread_id, "found": False}
    except Exception as exc:
        logger.warning("Failed to get pipeline status for %s: %s", thread_id, exc)
        return {"thread_id": thread_id, "found": False, "error": str(exc)}


# ── Legacy compatibility ─────────────────────────────────────────────────


class PipelineOrchestrator:
    """Legacy wrapper for backward compatibility.

    New code should use the module-level async functions directly:
    ``run_pipeline()``, ``resume_pipeline()``, ``run_loop()``.
    """

    def __init__(self) -> None:
        self._settings = get_settings()

    async def run_once(self) -> PipelineRunSummary:
        """Execute one full pipeline cycle."""
        return await run_pipeline()

    async def run_forever(self) -> None:
        """Run the pipeline in a continuous loop."""
        await run_loop()

    def stop(self) -> None:
        """No-op for backward compatibility (cancel the task instead)."""
        logger.info("PipelineOrchestrator.stop() called -- cancel the async task to stop.")


# ── Persistence ──────────────────────────────────────────────────────────


async def _persist_run(summary: PipelineRunSummary) -> None:
    """Log the pipeline run summary to the database (best-effort)."""
    try:
        from autodev.database import get_async_session

        async with get_async_session() as session:
            logger.info(
                "Persisting pipeline run %s: crawled=%d approved=%d built=%d published=%d.",
                summary.run_id,
                summary.demands_crawled,
                summary.demands_approved,
                summary.demands_built,
                summary.demands_published,
            )
            # TODO: Insert PipelineRun ORM record.
    except Exception as exc:
        logger.warning("Failed to persist pipeline run to DB: %s", exc)
