"""Checkpointer factory for LangGraph pipeline persistence.

Returns the appropriate LangGraph checkpointer based on settings:
- ``"memory"`` -- in-process ``MemorySaver`` (good for dev / tests)
- ``"sqlite"`` -- file-backed ``SqliteSaver`` (production MVP)

The backend is selected via ``Settings.pipeline_checkpoint_backend``.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

from zerodev.config import get_settings

logger = logging.getLogger(__name__)


@asynccontextmanager
async def get_checkpointer() -> AsyncIterator:
    """Create and yield a LangGraph checkpointer instance.

    Use as an async context manager::

        async with get_checkpointer() as saver:
            graph = build_main_graph(checkpointer=saver)

    Yields
    ------
    langgraph.checkpoint.base.BaseCheckpointSaver
        A MemorySaver or AsyncSqliteSaver depending on configuration.
    """
    settings = get_settings()
    backend = settings.pipeline_checkpoint_backend

    if backend == "memory":
        from langgraph.checkpoint.memory import MemorySaver

        logger.info("Using in-memory checkpointer (MemorySaver).")
        yield MemorySaver()
        return

    if backend == "sqlite":
        from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

        db_path = settings.pipeline_checkpoint_path
        # Ensure parent directory exists.
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        logger.info("Using SQLite checkpointer at %s.", db_path)
        async with AsyncSqliteSaver.from_conn_string(db_path) as saver:
            yield saver
        return

    raise ValueError(
        f"Unknown checkpoint backend {backend!r}. "
        "Supported values: 'memory', 'sqlite'."
    )
