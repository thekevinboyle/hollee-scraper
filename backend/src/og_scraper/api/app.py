"""FastAPI application factory.

Creates and configures the FastAPI app with:
- Lifespan management (startup/shutdown)
- CORS middleware for frontend access
- Health check endpoint (root level)
- API v1 router prefix (for future endpoints)
- Automatic OpenAPI documentation at /docs
"""

from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from og_scraper.api.routes import api_v1_router
from og_scraper.api.routes.health import router as health_router
from og_scraper.config import get_settings
from og_scraper.logging_config import setup_logging

logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager.

    Handles startup and shutdown events:
    - Startup: configure logging, verify database connection
    - Shutdown: clean up resources
    """
    settings = get_settings()
    setup_logging(settings.log_level)
    logger.info(
        "Starting Oil & Gas Document Scraper API",
        version=settings.app_version,
        environment=settings.environment,
    )
    yield
    logger.info("Shutting down Oil & Gas Document Scraper API")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application.

    This is the app factory function. Uvicorn calls this via:
        uvicorn og_scraper.api.app:create_app --factory
    """
    settings = get_settings()

    app = FastAPI(
        title=settings.app_title,
        version=settings.app_version,
        description="API for the Oil & Gas Document Scraper. "
        "Scrapes regulatory documents from 10 US state agencies, "
        "extracts structured data, and provides searchable access.",
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
    )

    # CORS middleware -- allow frontend at localhost:3000
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            settings.frontend_url,
            "http://localhost:3000",
            "http://127.0.0.1:3000",
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Include routers
    app.include_router(health_router)  # /health (root level)
    app.include_router(api_v1_router)  # /api/v1/* (versioned)

    return app
