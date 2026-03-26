"""FastAPI application for the ZeroDev Agent dashboard."""

from __future__ import annotations

import logging
import pathlib
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from zerodev.config import get_settings
from zerodev.database import get_async_engine

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Startup / shutdown lifecycle handler.

    On startup we verify the database connection is reachable.
    On shutdown we dispose of the connection pool.
    """
    settings = get_settings()
    logger.info("Starting ZeroDev Dashboard API (log_level=%s)", settings.log_level)

    engine = get_async_engine()
    try:
        # Create tables if they don't exist
        from zerodev.database import Base
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("Database tables ensured.")
    except Exception:
        logger.warning(
            "Database is not reachable at startup. "
            "Endpoints requiring DB will fail until the database is available."
        )

    yield

    logger.info("Shutting down ZeroDev Dashboard API...")
    await engine.dispose()


def create_app() -> FastAPI:
    """Build and return the configured FastAPI application."""
    settings = get_settings()

    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    application = FastAPI(
        title="ZeroDev Agent Dashboard",
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
    from zerodev.api.routes import router

    application.include_router(router)

    # Include WebSocket routes
    from zerodev.api.websocket import router as ws_router

    application.include_router(ws_router)

    # Serve static files
    static_dir = pathlib.Path(__file__).resolve().parent.parent / "static"
    if static_dir.is_dir():
        application.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    # Root route redirects to the Next.js dashboard
    @application.get("/")
    async def root_redirect() -> RedirectResponse:
        return RedirectResponse(url="http://localhost:9717")

    return application


# Module-level application instance for ``uvicorn zerodev.api.app:app``
app = create_app()
