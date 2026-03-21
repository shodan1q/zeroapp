"""FastAPI application for the AutoDev Agent dashboard."""

from __future__ import annotations

import logging
import pathlib
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from autodev.config import get_settings
from autodev.database import get_async_engine

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Startup / shutdown lifecycle handler.

    On startup we verify the database connection is reachable.
    On shutdown we dispose of the connection pool.
    """
    settings = get_settings()
    logger.info("Starting AutoDev Dashboard API (log_level=%s)", settings.log_level)

    engine = get_async_engine()
    try:
        async with engine.connect() as conn:
            from sqlalchemy import text

            await conn.execute(text("SELECT 1"))
        logger.info("Database connection verified.")
    except Exception:
        logger.warning(
            "Database is not reachable at startup. "
            "Endpoints requiring DB will fail until the database is available."
        )

    yield

    logger.info("Shutting down AutoDev Dashboard API...")
    await engine.dispose()


def create_app() -> FastAPI:
    """Build and return the configured FastAPI application."""
    settings = get_settings()

    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    application = FastAPI(
        title="AutoDev Agent Dashboard",
        description="Dashboard API for the autonomous app development pipeline.",
        version="0.1.0",
        lifespan=lifespan,
    )

    # CORS - allow all origins in development; restrict in production via env
    application.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Health check
    @application.get("/health")
    async def health_check() -> dict[str, str]:
        return {"status": "ok"}

    # Include API routes
    from autodev.api.routes import router

    application.include_router(router)

    # Include WebSocket routes
    from autodev.api.websocket import router as ws_router

    application.include_router(ws_router)

    # Serve static files
    static_dir = pathlib.Path(__file__).resolve().parent.parent / "static"
    if static_dir.is_dir():
        application.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    # Root route serves the dashboard
    @application.get("/", response_class=HTMLResponse)
    async def serve_dashboard() -> HTMLResponse:
        index_path = static_dir / "index.html"
        if index_path.exists():
            return HTMLResponse(content=index_path.read_text(encoding="utf-8"))
        return HTMLResponse(
            content="<h1>Dashboard not found</h1><p>static/index.html is missing.</p>",
            status_code=404,
        )

    return application


# Module-level application instance for ``uvicorn autodev.api.app:app``
app = create_app()
