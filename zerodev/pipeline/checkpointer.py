"""Checkpointer factory for LangGraph pipeline persistence.

Returns the appropriate LangGraph checkpointer based on settings:
- ``"memory"`` -- in-process ``MemorySaver`` (good for dev / tests)
- ``"sqlite"`` -- file-backed ``SqliteSaver`` (production MVP)

The backend is selected via ``Settings.pipeline_checkpoint_backend``.
"""

from __future__ import annotations

import logging
from pathlib import Path

from zerodev.config import get_settings

logger = logging.getLogger(__name__)


def get_checkpointer():
    """Create and return a LangGraph checkpointer instance.

    Returns
    -------
    langgraph.checkpoint.base.BaseCheckpointSaver
        A MemorySaver or SqliteSaver depending on configuration.
    """
    settings = get_settings()
    backend = settings.pipeline_checkpoint_backend

    if backend == "memory":
        from langgraph.checkpoint.memory import MemorySaver

        logger.info("Using in-memory checkpointer (MemorySaver).")
        return MemorySaver()

    if backend == "sqlite":
        from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

        db_path = settings.pipeline_checkpoint_path
        # Ensure parent directory exists.
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        logger.info("Using SQLite checkpointer at %s.", db_path)
        return AsyncSqliteSaver.from_conn_string(db_path)

    raise ValueError(
        f"Unknown checkpoint backend {backend!r}. "
        "Supported values: 'memory', 'sqlite'."
    )
