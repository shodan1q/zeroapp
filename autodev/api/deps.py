"""FastAPI dependency injection helpers."""

from __future__ import annotations

from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession

from autodev.database import get_async_session_factory


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Yield a transactional async session for a single request."""
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
