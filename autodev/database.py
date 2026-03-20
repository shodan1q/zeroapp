"""SQLAlchemy engine, session factories, and base model."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from autodev.config import get_settings


# ── Declarative base ────────────────────────────────────────────
class Base(DeclarativeBase):
    """Base class for all ORM models."""
    pass


# ── Async engine + session (FastAPI, async tasks) ──────────────
def _build_async_engine():
    settings = get_settings()
    return create_async_engine(
        settings.database_url,
        echo=settings.log_level == "DEBUG",
        pool_size=10,
        max_overflow=20,
        pool_pre_ping=True,
    )


def _build_async_session_factory():
    return async_sessionmaker(
        bind=_build_async_engine(),
        class_=AsyncSession,
        expire_on_commit=False,
    )


async_engine = None
AsyncSessionFactory = None


def get_async_engine():
    global async_engine
    if async_engine is None:
        async_engine = _build_async_engine()
    return async_engine


def get_async_session_factory():
    global AsyncSessionFactory
    if AsyncSessionFactory is None:
        AsyncSessionFactory = async_sessionmaker(
            bind=get_async_engine(),
            class_=AsyncSession,
            expire_on_commit=False,
        )
    return AsyncSessionFactory


@asynccontextmanager
async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    """Provide a transactional async session scope."""
    factory = get_async_session_factory()
    session = factory()
    try:
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()


# ── Sync engine + session (Celery workers, Alembic) ────────────
def _build_sync_engine():
    settings = get_settings()
    return create_engine(
        settings.database_url_sync,
        echo=settings.log_level == "DEBUG",
        pool_size=5,
        max_overflow=10,
        pool_pre_ping=True,
    )


sync_engine = None
SyncSessionFactory = None


def get_sync_engine():
    global sync_engine
    if sync_engine is None:
        sync_engine = _build_sync_engine()
    return sync_engine


def get_sync_session_factory():
    global SyncSessionFactory
    if SyncSessionFactory is None:
        SyncSessionFactory = sessionmaker(
            bind=get_sync_engine(),
            class_=Session,
            expire_on_commit=False,
        )
    return SyncSessionFactory


def get_sync_session() -> Session:
    """Return a sync session (caller must manage commit/rollback/close)."""
    factory = get_sync_session_factory()
    return factory()


# ── Table creation helper (for dev/testing) ────────────────────
async def create_all_tables() -> None:
    """Create all tables in the database (async)."""
    engine = get_async_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def drop_all_tables() -> None:
    """Drop all tables in the database (async)."""
    engine = get_async_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
