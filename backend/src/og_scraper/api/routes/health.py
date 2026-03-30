"""Health check endpoint."""

from typing import Annotated

import structlog
from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from og_scraper.database import get_db

logger = structlog.get_logger()

router = APIRouter(tags=["health"])

DbSession = Annotated[AsyncSession, Depends(get_db)]


@router.get("/health")
async def health_check(db: DbSession):
    """Health check endpoint.

    Returns the service status, database connectivity, and version.
    Used by Docker health checks and monitoring.
    """
    db_status = "disconnected"
    db_version = None
    postgis_version = None

    try:
        # Test database connection
        result = await db.execute(text("SELECT version()"))
        db_version = result.scalar()
        db_status = "connected"

        # Test PostGIS
        result = await db.execute(text("SELECT PostGIS_Version()"))
        postgis_version = result.scalar()
    except Exception as e:
        logger.error("Health check: database connection failed", error=str(e))
        db_status = f"error: {str(e)}"

    return {
        "status": "ok" if db_status == "connected" else "degraded",
        "version": "0.1.0",
        "db": db_status,
        "db_version": db_version,
        "postgis_version": postgis_version,
    }
