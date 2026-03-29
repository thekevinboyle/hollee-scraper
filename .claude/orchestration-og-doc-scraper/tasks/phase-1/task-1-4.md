# Task 1.4: FastAPI Skeleton

## Objective

Create the FastAPI application with app factory pattern, database connection via async SQLAlchemy dependency injection, health check endpoint, CORS configuration for the frontend, Huey task queue initialization with SQLite backend, pydantic-settings configuration, and structlog JSON logging. This is the API server skeleton that all subsequent API endpoints (Phase 3) will be added to.

## Context

Task 1.2 created the database models and Alembic migrations. This task creates the FastAPI application that wraps those models with HTTP endpoints. Only the health check endpoint is implemented here -- the actual API endpoints (wells, documents, scrape, review, map, stats, export) come in Phase 3. The goal is to get a running FastAPI server that connects to PostgreSQL, initializes Huey, and responds to health checks.

Key constraints from DISCOVERY.md:
- No authentication (D7) -- CORS is the only security concern (frontend at localhost:3000)
- Huey with SQLite backend, NOT Redis (from architecture decisions)
- FastAPI with automatic OpenAPI docs at /docs
- Pydantic-settings for configuration from environment variables
- structlog for JSON-formatted logging

## Dependencies

- Task 1.2 - Database models, async engine, session factory

## Blocked By

- Task 1.2

## Research Findings

Key findings from research files relevant to this task:

- From `fastapi-backend` skill: App factory pattern with lifespan context manager for startup/shutdown. `get_db()` dependency yields AsyncSession with auto-commit/rollback. Huey uses `SqliteHuey("og-scraper", filename="data/huey.db")`. CORS allows `http://localhost:3000`.
- From `docker-local-deployment` skill: Backend environment variables: DATABASE_URL, SYNC_DATABASE_URL, DATA_DIR, HUEY_DB_PATH, DOCUMENTS_DIR, LOG_LEVEL, ENVIRONMENT. Health check endpoint at `/health`.
- From `backend-schema-implementation.md`: FastAPI serves at port 8000. Base URL for API routes: `/api/v1`. Health endpoint at root level (not under /api/v1).

## Implementation Plan

### Step 1: Create Pydantic Settings Configuration

Create `backend/src/og_scraper/config.py`:

```python
"""Application configuration via pydantic-settings.

Settings are loaded from environment variables with sensible defaults
for local development. In Docker, these are set via docker-compose.yml.
"""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # Database
    database_url: str = "postgresql+asyncpg://ogdocs:ogdocs_dev@localhost:5432/ogdocs"
    sync_database_url: str = "postgresql://ogdocs:ogdocs_dev@localhost:5432/ogdocs"

    # Huey task queue
    huey_db_path: str = "data/huey.db"

    # File storage
    data_dir: str = "data"
    documents_dir: str = "data/documents"

    # Server
    environment: str = "development"
    log_level: str = "debug"
    debug: bool = True

    # CORS
    frontend_url: str = "http://localhost:3000"

    # OCR
    ocr_confidence_threshold: float = 0.80

    # API
    api_v1_prefix: str = "/api/v1"
    app_version: str = "0.1.0"
    app_title: str = "Oil & Gas Document Scraper API"

    @property
    def huey_db_dir(self) -> Path:
        """Ensure parent directory for Huey SQLite DB exists."""
        path = Path(self.huey_db_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        return path


def get_settings() -> Settings:
    """Create and return Settings instance."""
    return Settings()
```

### Step 2: Create Database Module

Update `backend/src/og_scraper/database.py` (created in Task 1.2, now refactored to use settings):

```python
"""Async database engine and session factory.

Uses SQLAlchemy 2.0 async with asyncpg driver.
"""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from og_scraper.config import get_settings

settings = get_settings()

engine = create_async_engine(
    settings.database_url,
    pool_size=20,
    max_overflow=10,
    pool_pre_ping=True,
    echo=settings.log_level.lower() == "trace",
)

async_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency that yields an async database session.

    Auto-commits on success, auto-rollbacks on exception.
    """
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
```

### Step 3: Create Huey Worker Instance

Create `backend/src/og_scraper/worker.py`:

```python
"""Huey task queue instance with SQLite backend.

This module provides the Huey instance shared between the API server
(for enqueuing tasks) and the worker process (for executing tasks).

Per DISCOVERY.md: no Redis. Huey uses a local SQLite file.
"""

from huey import SqliteHuey

from og_scraper.config import get_settings

settings = get_settings()

# Ensure the data directory exists
settings.huey_db_dir

huey_app = SqliteHuey(
    "og-scraper",
    filename=settings.huey_db_path,
)
```

### Step 4: Create Structlog Configuration

Create `backend/src/og_scraper/logging_config.py`:

```python
"""Structured logging configuration using structlog."""

import logging
import sys

import structlog


def setup_logging(log_level: str = "INFO") -> None:
    """Configure structlog for JSON logging.

    Args:
        log_level: Log level string (DEBUG, INFO, WARNING, ERROR, CRITICAL)
    """
    # Configure standard library logging
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=getattr(logging, log_level.upper(), logging.INFO),
    )

    # Configure structlog
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.StackInfoRenderer(),
            structlog.dev.set_exc_info,
            structlog.processors.TimeStamper(fmt="iso"),
            # In development, use console renderer; in production, use JSON
            structlog.dev.ConsoleRenderer()
            if log_level.upper() == "DEBUG"
            else structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, log_level.upper(), logging.INFO)
        ),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )
```

### Step 5: Create Health Check Router

Create `backend/src/og_scraper/api/routes/health.py`:

```python
"""Health check endpoint."""

import structlog
from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from og_scraper.database import get_db

logger = structlog.get_logger()

router = APIRouter(tags=["health"])


@router.get("/health")
async def health_check(db: AsyncSession = Depends(get_db)):
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
```

### Step 6: Create API Router Aggregation

Update `backend/src/og_scraper/api/routes/__init__.py`:

```python
"""API route aggregation.

Collects all routers and provides a single router for the app to include.
"""

from fastapi import APIRouter

from .health import router as health_router

# API v1 router -- all versioned endpoints go here
api_v1_router = APIRouter(prefix="/api/v1")

# Health is at root level (not versioned)
# API endpoints will be added to api_v1_router in Phase 3
```

### Step 7: Create FastAPI Application Factory

Create `backend/src/og_scraper/api/app.py`:

```python
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

from og_scraper.config import get_settings
from og_scraper.logging_config import setup_logging
from og_scraper.api.routes import api_v1_router
from og_scraper.api.routes.health import router as health_router

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
```

### Step 8: Create API Dependencies Module

Create `backend/src/og_scraper/api/deps.py`:

```python
"""FastAPI dependency injection providers.

Provides reusable dependencies for database sessions, settings,
and the Huey task queue instance.
"""

from collections.abc import AsyncGenerator

from fastapi import Depends
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
```

### Step 9: Create Tests

Create `backend/tests/api/__init__.py` (empty).

Create `backend/tests/api/test_health.py`:

```python
"""Tests for the health check endpoint."""

import pytest
from httpx import ASGITransport, AsyncClient

from og_scraper.api.app import create_app


@pytest.fixture
def app():
    return create_app()


@pytest.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.mark.asyncio
async def test_health_returns_200(client):
    """Health endpoint returns 200 status code."""
    response = await client.get("/health")
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_health_response_shape(client):
    """Health response has expected fields."""
    response = await client.get("/health")
    data = response.json()
    assert "status" in data
    assert "version" in data
    assert "db" in data
    assert data["version"] == "0.1.0"


@pytest.mark.asyncio
async def test_health_db_connected(client):
    """Health check reports database as connected when DB is up.

    Note: This test requires PostgreSQL to be running.
    Mark as integration test if running without Docker.
    """
    response = await client.get("/health")
    data = response.json()
    # In test environment without DB, this may show 'disconnected'
    # When DB is available, it should show 'connected'
    assert data["db"] in ("connected", "disconnected") or data["db"].startswith("error:")
```

Create `backend/tests/api/test_cors.py`:

```python
"""Tests for CORS configuration."""

import pytest
from httpx import ASGITransport, AsyncClient

from og_scraper.api.app import create_app


@pytest.fixture
def app():
    return create_app()


@pytest.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.mark.asyncio
async def test_cors_allows_frontend_origin(client):
    """CORS headers allow the frontend origin."""
    response = await client.options(
        "/health",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert response.headers.get("access-control-allow-origin") == "http://localhost:3000"


@pytest.mark.asyncio
async def test_cors_blocks_unknown_origin(client):
    """CORS does not allow unknown origins."""
    response = await client.options(
        "/health",
        headers={
            "Origin": "http://evil.com",
            "Access-Control-Request-Method": "GET",
        },
    )
    # FastAPI CORS middleware doesn't set the header for disallowed origins
    allow_origin = response.headers.get("access-control-allow-origin")
    assert allow_origin != "http://evil.com"
```

Create `backend/tests/test_config.py`:

```python
"""Tests for application configuration."""

import os

import pytest

from og_scraper.config import Settings, get_settings


class TestSettings:
    def test_defaults(self):
        """Settings have sensible defaults."""
        settings = Settings()
        assert "asyncpg" in settings.database_url
        assert settings.environment == "development"
        assert settings.ocr_confidence_threshold == 0.80
        assert settings.api_v1_prefix == "/api/v1"

    def test_from_env(self, monkeypatch):
        """Settings can be loaded from environment variables."""
        monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://test:test@testdb:5432/testdb")
        monkeypatch.setenv("ENVIRONMENT", "production")
        monkeypatch.setenv("LOG_LEVEL", "warning")

        settings = Settings()
        assert settings.database_url == "postgresql+asyncpg://test:test@testdb:5432/testdb"
        assert settings.environment == "production"
        assert settings.log_level == "warning"

    def test_ocr_threshold_from_env(self, monkeypatch):
        """OCR confidence threshold can be customized."""
        monkeypatch.setenv("OCR_CONFIDENCE_THRESHOLD", "0.90")
        settings = Settings()
        assert settings.ocr_confidence_threshold == 0.90

    def test_get_settings_returns_settings(self):
        settings = get_settings()
        assert isinstance(settings, Settings)
```

### Step 10: Update Package __init__.py

Ensure `backend/src/og_scraper/__init__.py` has the version:

```python
"""Oil & Gas Document Scraper."""

__version__ = "0.1.0"
```

## Files to Create

- `backend/src/og_scraper/config.py` - Pydantic Settings with all config values
- `backend/src/og_scraper/worker.py` - Huey SqliteHuey instance
- `backend/src/og_scraper/logging_config.py` - Structlog JSON logging setup
- `backend/src/og_scraper/api/app.py` - FastAPI app factory with lifespan, CORS
- `backend/src/og_scraper/api/deps.py` - Dependency injection providers
- `backend/src/og_scraper/api/routes/health.py` - Health check endpoint
- `backend/tests/api/__init__.py` - Test package
- `backend/tests/api/test_health.py` - Health endpoint tests
- `backend/tests/api/test_cors.py` - CORS configuration tests
- `backend/tests/test_config.py` - Settings tests

## Files to Modify

- `backend/src/og_scraper/database.py` - Refactor to use Settings instead of direct os.environ
- `backend/src/og_scraper/api/routes/__init__.py` - Add router aggregation with api_v1_router

## Contracts

### Provides (for downstream tasks)

- **FastAPI app factory**: `og_scraper.api.app:create_app` -- used by uvicorn with `--factory` flag
- **Health endpoint**: `GET /health` returns `{"status": "ok"|"degraded", "version": "0.1.0", "db": "connected"|"disconnected", "db_version": str, "postgis_version": str}`
- **API v1 router**: `og_scraper.api.routes.api_v1_router` -- prefix `/api/v1`, all Phase 3 endpoints attach here
- **Database dependency**: `og_scraper.api.deps.get_db()` yields `AsyncSession`
- **Settings dependency**: `og_scraper.api.deps.get_settings_dep()` returns `Settings`
- **Huey dependency**: `og_scraper.api.deps.get_huey()` returns `SqliteHuey` instance
- **Huey instance**: `og_scraper.worker.huey_app` -- the SqliteHuey instance for task definitions
- **Settings class**: `og_scraper.config.Settings` with all configuration values
- **CORS**: Allows `http://localhost:3000` (frontend origin)
- **OpenAPI docs**: Available at `/docs` (Swagger) and `/redoc`

### Consumes (from upstream tasks)

- Task 1.1: Project structure, Docker Compose, Python dependencies
- Task 1.2: Database models at `og_scraper.models`, async engine/session in `og_scraper.database`

## Acceptance Criteria

- [ ] `uvicorn og_scraper.api.app:create_app --factory --host 0.0.0.0 --port 8000` starts the server
- [ ] `GET /health` returns 200 with JSON body containing status, version, and db fields
- [ ] When PostgreSQL is running, health check reports `"db": "connected"` and includes PostGIS version
- [ ] When PostgreSQL is not running, health check returns 200 with `"db": "disconnected"` or error message (graceful degradation)
- [ ] CORS headers allow `http://localhost:3000` origin
- [ ] CORS blocks requests from unknown origins
- [ ] OpenAPI documentation is accessible at `/docs`
- [ ] Huey instance is configured with SQLite storage at the configured path
- [ ] Settings load correctly from environment variables
- [ ] Settings use sensible defaults when env vars are not set
- [ ] structlog produces formatted log output on startup
- [ ] All tests pass: `uv run pytest backend/tests/api/ backend/tests/test_config.py -v`

## Testing Protocol

### Unit/Integration Tests

- Test file: `backend/tests/api/test_health.py`
  - [ ] Health endpoint returns 200 status code
  - [ ] Health response contains status, version, and db fields
  - [ ] Version matches "0.1.0"
  - [ ] Database connection status is reported correctly

- Test file: `backend/tests/api/test_cors.py`
  - [ ] CORS allows `http://localhost:3000` origin
  - [ ] CORS does not allow `http://evil.com` origin

- Test file: `backend/tests/test_config.py`
  - [ ] Settings have sensible defaults
  - [ ] Settings load from environment variables
  - [ ] OCR threshold is configurable
  - [ ] get_settings() returns a Settings instance

### API/Script Testing

- Start the server: `cd backend && uv run uvicorn og_scraper.api.app:create_app --factory --port 8000`
- Test health: `curl http://localhost:8000/health | python3 -m json.tool`
- Expected response shape:
  ```json
  {
    "status": "ok",
    "version": "0.1.0",
    "db": "connected",
    "db_version": "PostgreSQL 16.x ...",
    "postgis_version": "3.4 ..."
  }
  ```
- Test OpenAPI docs: open `http://localhost:8000/docs` in browser -- should show Swagger UI
- Test CORS: `curl -H "Origin: http://localhost:3000" -H "Access-Control-Request-Method: GET" -X OPTIONS http://localhost:8000/health -v` -- should include `access-control-allow-origin: http://localhost:3000`

### Docker Testing

- `docker compose up -d db backend` starts database and backend
- `docker compose ps` shows both as healthy
- `curl http://localhost:8000/health` returns connected status
- `docker compose logs backend` shows structlog startup output

### Build/Lint/Type Checks

- [ ] `cd backend && uv run ruff check src/og_scraper/api/ src/og_scraper/config.py src/og_scraper/worker.py` passes
- [ ] `cd backend && uv run pytest tests/api/ tests/test_config.py -v` passes

## Skills to Read

- `fastapi-backend` - App factory pattern, async SQLAlchemy, Huey integration, SSE, Pydantic models
- `docker-local-deployment` - Environment variables, service health checks, container configuration

## Research Files to Read

- `.claude/orchestration-og-doc-scraper/research/backend-schema-implementation.md` - FastAPI backend design (section 3), Docker Compose (section 6)
- `.claude/orchestration-og-doc-scraper/research/architecture-storage.md` - Task queue evaluation (section 7), API design (section 10)

## Git

- Branch: `task/1.4-fastapi-skeleton`
- Commit message prefix: `Task 1.4:`
