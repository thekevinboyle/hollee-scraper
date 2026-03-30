"""FastAPI dependency injection providers.

Provides reusable dependencies for database sessions, settings,
and the Huey task queue instance.
"""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession

from og_scraper.config import Settings, get_settings
from og_scraper.database import get_db as _get_db
from og_scraper.worker import huey_app


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Dependency: yields an async database session."""
    async for session in _get_db():
        yield session


def get_settings_dep() -> Settings:
    """Dependency: returns application settings."""
    return get_settings()


def get_huey():
    """Dependency: returns the Huey task queue instance."""
    return huey_app
