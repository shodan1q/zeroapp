"""State type definitions for the LangGraph pipeline.

Defines the TypedDict schemas used as graph state for both the
batch pipeline and the per-demand processing sub-graph.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, TypedDict


class PipelineState(TypedDict, total=False):
    """State for the main (batch) pipeline graph.

    All fields are optional so that node functions can return partial
    updates -- LangGraph merges the returned dict into the current state.
    """

    # Crawl / process
    demands_raw: List[Dict[str, Any]]
    demands_structured: List[Dict[str, Any]]

    # Evaluate / decide
    demands_evaluated: List[Dict[str, Any]]
    demands_approved: List[Dict[str, Any]]
    demands_rejected: List[Dict[str, Any]]

    # Per-demand processing results (list of DemandState dicts)
    demand_results: List[Dict[str, Any]]

    # Metadata
    stage: str
    errors: List[str]
    retry_count: int
    run_id: str

    # Stats
    demands_crawled_count: int
    demands_approved_count: int
    demands_rejected_count: int
    demands_built_count: int
    demands_published_count: int


class DemandState(TypedDict, total=False):
    """State for the per-demand processing graph.

    Tracks a single demand through: generate -> build -> assets -> publish.
    """

    # Identity
    demand_id: str
    demand: Dict[str, Any]

    # Generation
    project_path: Optional[str]

    # Build
    build_artifacts: Dict[str, str]

    # Assets
    assets: Dict[str, Any]

    # Publish
    publish_results: Dict[str, Any]

    # Control
    stage: str
    errors: List[str]
    retry_count: int
    failed: bool


@dataclass(frozen=True)
class RetryPolicy:
    """Configuration for exponential-backoff retries at each graph node."""

    max_retries: int = 3
    backoff_base: float = 2.0
    backoff_max: float = 300.0

    def delay_for_attempt(self, attempt: int) -> float:
        """Return the delay in seconds for the given attempt (0-indexed)."""
        return min(self.backoff_base * (2 ** attempt), self.backoff_max)
