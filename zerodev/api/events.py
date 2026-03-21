"""Event emitter for pipeline nodes to push real-time updates.

Pipeline nodes call these helpers to broadcast progress to all
connected WebSocket clients via the ConnectionManager singleton.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


def _get_manager():
    """Lazy import to avoid circular dependencies."""
    from zerodev.api.websocket import manager
    return manager


def _fire_and_forget(coro):
    """Schedule a coroutine without awaiting it (best-effort delivery)."""
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(coro)
    except RuntimeError:
        # No running event loop – skip emission silently.
        pass


async def emit_stage_change(
    stage: str,
    demand_id: Optional[str] = None,
    status: str = "started",
    detail: Optional[Dict[str, Any]] = None,
) -> None:
    """Broadcast a pipeline stage transition.

    Parameters
    ----------
    stage : str
        Stage name (e.g. crawl, process, evaluate, decide, generate, build, assets, publish).
    demand_id : str, optional
        The demand being processed.
    status : str
        One of: started, completed, failed.
    detail : dict, optional
        Extra information about the stage.
    """
    try:
        data: Dict[str, Any] = {"stage": stage, "status": status}
        if demand_id:
            data["demand_id"] = demand_id
        if detail:
            data["detail"] = detail
        await _get_manager().broadcast("stage_change", data)
    except Exception:
        logger.debug("Failed to emit stage_change event.", exc_info=True)


async def emit_build_progress(
    demand_id: str,
    step: str,
    progress_pct: float,
    message: str = "",
) -> None:
    """Broadcast build progress for a specific demand.

    Parameters
    ----------
    demand_id : str
        Demand identifier.
    step : str
        Build step (e.g. pub_get, analyze, sign, build_apk, build_aab).
    progress_pct : float
        Completion percentage 0-100.
    message : str
        Human-readable status message.
    """
    try:
        await _get_manager().broadcast("build_update", {
            "demand_id": demand_id,
            "step": step,
            "progress_pct": progress_pct,
            "message": message,
        })
    except Exception:
        logger.debug("Failed to emit build_update event.", exc_info=True)


async def emit_pipeline_summary(
    run_id: str,
    stats: Dict[str, Any],
) -> None:
    """Broadcast a pipeline run summary.

    Parameters
    ----------
    run_id : str
        Pipeline run identifier.
    stats : dict
        Summary statistics (e.g. crawled, processed, approved, built, published counts).
    """
    try:
        await _get_manager().broadcast("pipeline_update", {
            "run_id": run_id,
            "stats": stats,
        })
    except Exception:
        logger.debug("Failed to emit pipeline_update event.", exc_info=True)


async def emit_error(source: str, message: str) -> None:
    """Broadcast an error event.

    Parameters
    ----------
    source : str
        Component that raised the error (e.g. node name).
    message : str
        Human-readable error description.
    """
    try:
        await _get_manager().broadcast("error", {
            "source": source,
            "message": message,
        })
    except Exception:
        logger.debug("Failed to emit error event.", exc_info=True)


async def emit_metrics_update(metrics: Dict[str, Any]) -> None:
    """Broadcast a metrics update (e.g. refreshed dashboard numbers).

    Parameters
    ----------
    metrics : dict
        Key-value pairs of metric names to values.
    """
    try:
        await _get_manager().broadcast("metrics_update", metrics)
    except Exception:
        logger.debug("Failed to emit metrics_update event.", exc_info=True)
