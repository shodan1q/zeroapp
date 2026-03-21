"""Retry utilities for LangGraph node functions.

Provides a decorator that wraps async node functions with configurable
exponential-backoff retry logic.  On each failure the wrapper updates the
state ``errors`` and ``retry_count`` fields before sleeping and re-trying.
After ``max_retries`` exhausted the node marks the state as failed and
returns so that the graph can continue along its failure edge.
"""

from __future__ import annotations

import asyncio
import functools
import logging
import traceback
from typing import Any, Awaitable, Callable, Dict

from zerodev.pipeline.state import RetryPolicy

logger = logging.getLogger(__name__)

# Type alias for a LangGraph node function: takes state dict, returns partial update dict.
NodeFn = Callable[[Dict[str, Any]], Awaitable[Dict[str, Any]]]


def with_retry(
    func: NodeFn | None = None,
    *,
    policy: RetryPolicy | None = None,
    node_name: str | None = None,
) -> NodeFn | Callable[[NodeFn], NodeFn]:
    """Decorator that adds retry-with-backoff to a LangGraph node function.

    Can be used with or without arguments::

        @with_retry
        async def my_node(state): ...

        @with_retry(policy=RetryPolicy(max_retries=5))
        async def my_node(state): ...

    On failure the returned partial-state update includes:
    - ``errors``: appended error message
    - ``retry_count``: incremented count
    - ``failed``: True when retries are exhausted
    """
    if policy is None:
        policy = RetryPolicy()

    def decorator(fn: NodeFn) -> NodeFn:
        name = node_name or fn.__name__

        @functools.wraps(fn)
        async def wrapper(state: Dict[str, Any]) -> Dict[str, Any]:
            errors: list[str] = list(state.get("errors") or [])
            retry_count: int = state.get("retry_count", 0)

            for attempt in range(policy.max_retries + 1):
                try:
                    result = await fn(state)
                    # Success -- reset retry_count for the next node.
                    result.setdefault("retry_count", 0)
                    return result
                except Exception as exc:
                    tb = traceback.format_exc()
                    error_msg = f"[{name}] attempt {attempt + 1}/{policy.max_retries + 1} failed: {exc}"
                    logger.warning(error_msg)
                    logger.debug("Traceback:\n%s", tb)
                    errors.append(error_msg)

                    if attempt < policy.max_retries:
                        delay = policy.delay_for_attempt(attempt)
                        logger.info(
                            "[%s] Retrying in %.1fs (attempt %d/%d).",
                            name,
                            delay,
                            attempt + 2,
                            policy.max_retries + 1,
                        )
                        await asyncio.sleep(delay)
                    else:
                        logger.error(
                            "[%s] All %d retries exhausted.",
                            name,
                            policy.max_retries + 1,
                        )

            # All retries failed.
            return {
                "errors": errors,
                "retry_count": retry_count + policy.max_retries + 1,
                "failed": True,
            }

        return wrapper

    # Allow bare @with_retry without parentheses.
    if func is not None:
        return decorator(func)
    return decorator
