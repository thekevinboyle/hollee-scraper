---
name: fastapi-backend
description: FastAPI backend with Huey task queue, SSE progress, and SQLAlchemy async ORM. Use when implementing API endpoints, database models, or backend services.
---

# FastAPI Backend Skill

## What It Is

A Python FastAPI backend serving as the API layer for the Oil & Gas Document Scraper. The backend provides:

- **FastAPI** REST API with automatic OpenAPI documentation at `/docs`
- **Huey** task queue with **SQLite backend** (no Redis) for asynchronous scrape job processing
- **SSE (Server-Sent Events)** via `sse-starlette` for real-time scrape progress streaming
- **SQLAlchemy 2.0** async ORM with `asyncpg` driver for PostgreSQL
- **Alembic** for database schema migrations
- **Pydantic** models for all request/response validation
- **PostgreSQL + PostGIS** for relational data, JSONB flexibility, and spatial queries

No authentication is required (DISCOVERY D7 -- internal tool for 1-2 users on a local machine).

## When To Use This Skill

Use this skill when:

- Implementing or modifying API endpoints
- Creating or updating SQLAlchemy database models
- Writing Alembic migrations
- Defining Pydantic request/response schemas
- Adding Huey task queue jobs (scrape tasks, document processing)
- Working with SSE endpoints for real-time progress
- Building database query logic (search, filtering, pagination, spatial queries)
- Configuring Docker Compose services for the backend stack

## Setup and Dependencies

### Python Dependencies

```
fastapi
uvicorn[standard]
huey>=2.6.0
sse-starlette
sqlalchemy[asyncio]>=2.0
asyncpg
alembic
geoalchemy2
pydantic>=2.0
pydantic-settings
```

### Infrastructure (Docker Compose)

- **PostgreSQL 17** with PostGIS 3.5 (`postgis/postgis:17-3.5`)
- **No Redis** -- Huey uses a local SQLite file for task persistence
- Database URL format: `postgresql+asyncpg://og_user:og_password@localhost:5432/og_scraper`

### Required PostgreSQL Extensions

```sql
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";   -- UUID generation
CREATE EXTENSION IF NOT EXISTS "postgis";      -- spatial queries
CREATE EXTENSION IF NOT EXISTS "pg_trgm";      -- fuzzy/typo-tolerant search
```

## Project Structure

```
backend/
├── alembic/                        # Database migrations
│   ├── versions/
│   ├── env.py                      # Async migration runner
│   └── alembic.ini
├── app/
│   ├── __init__.py
│   ├── main.py                     # FastAPI application factory
│   ├── config.py                   # Settings (pydantic-settings)
│   ├── database.py                 # Async engine + session factory
│   ├── models/                     # SQLAlchemy ORM models
│   │   ├── base.py                 # DeclarativeBase, TimestampMixin, UUIDPrimaryKeyMixin
│   │   ├── state.py
│   │   ├── operator.py
│   │   ├── well.py
│   │   ├── document.py
│   │   ├── extracted_data.py
│   │   ├── review_queue.py
│   │   ├── scrape_job.py
│   │   └── data_correction.py
│   ├── schemas/                    # Pydantic request/response models
│   │   ├── well.py                 # WellSummary, WellDetail, WellMapPoint
│   │   ├── document.py             # DocumentSummary, DocumentDetail
│   │   ├── scrape.py               # ScrapeJobCreate, ScrapeJobSummary, ScrapeJobDetail
│   │   ├── review.py               # ReviewQueueItem, ReviewItemDetail, ReviewAction
│   │   ├── map.py
│   │   ├── stats.py                # DashboardStats
│   │   └── export.py
│   ├── api/                        # FastAPI routers
│   │   ├── wells.py
│   │   ├── documents.py
│   │   ├── scrape.py               # Includes SSE endpoint
│   │   ├── review.py
│   │   ├── map.py
│   │   ├── stats.py
│   │   └── export.py
│   ├── services/                   # Business logic layer
│   │   ├── well_service.py
│   │   ├── document_service.py
│   │   ├── search_service.py       # Full-text + spatial search
│   │   ├── review_service.py
│   │   └── stats_service.py
│   ├── tasks/                      # Huey task definitions
│   │   ├── __init__.py             # SqliteHuey instance
│   │   ├── scrape_tasks.py
│   │   ├── process_tasks.py
│   │   └── review_tasks.py
│   └── utils/
│       ├── api_number.py           # API number normalization (strip dashes, zero-pad)
│       ├── pagination.py           # PaginationParams, PaginatedResponse
│       └── query_builder.py        # Reusable filter/sort query construction
├── tests/
├── pyproject.toml
├── Dockerfile
└── docker-compose.yml
```

## API Endpoints (17 REST Endpoints)

Base URL: `http://localhost:8000/api/v1`

### Wells (CRUD + Search)

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/wells` | Search/filter/paginate wells. Query params: `q`, `api_number`, `state`, `county`, `operator`, `lease_name`, `well_status`, `well_type`, `page`, `page_size`, `sort_by`, `sort_dir` |
| `GET` | `/wells/{api_number}` | Well detail with associated documents and extracted data |

### Documents (CRUD + By-Well)

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/documents` | Search/filter/paginate documents. Query params: `q`, `well_id`, `state`, `doc_type`, `date_from`, `date_to`, `min_confidence`, `status`, `page`, `page_size` |
| `GET` | `/documents/{id}` | Document detail with nested extracted data |
| `GET` | `/documents/{id}/file` | Serve the original document file (PDF, XLSX, etc.) with correct Content-Type |

### Scrape Jobs (Trigger + Status + Progress SSE)

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/scrape` | Trigger a new scrape job. Body: `{ state_code?, job_type, parameters? }`. Returns job ID immediately; work runs in Huey |
| `GET` | `/scrape/jobs` | List scrape jobs with status. Query params: `status`, `state`, `page`, `page_size` |
| `GET` | `/scrape/jobs/{id}` | Detailed job status with progress counters and error list |
| `GET` | `/scrape/jobs/{id}/events` | **SSE stream** for real-time progress. Events: `progress`, `document`, `error`, `complete` |

### Review Queue (List + Approve/Reject)

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/review` | List items needing review. Query params: `status` (default: pending), `state`, `doc_type`, `page`, `page_size` |
| `GET` | `/review/{id}` | Review item detail with document, extracted data, and original file URL |
| `PATCH` | `/review/{id}` | Approve, reject, or correct. Body: `{ status, corrections?, notes?, reviewed_by? }` |

### Map, Operators, Stats, Export

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/map/wells` | Wells within a bounding box. Query params: `min_lat`, `max_lat`, `min_lng`, `max_lng`, `well_status`, `well_type`, `limit` |
| `GET` | `/operators` | List/search operators |
| `GET` | `/stats` | Dashboard statistics (totals, breakdowns by state/type/status, pending review count) |
| `GET` | `/export/wells` | Export wells as CSV or JSON (streaming) |
| `GET` | `/export/production` | Export production data as CSV or JSON (streaming) |

## Database Schema (8 Core Tables)

PostgreSQL with PostGIS. All primary keys are UUIDs (except `states` which uses `VARCHAR(2)`).

### Tables

1. **states** -- 10 supported states with tier and scraper config (PK: `code` VARCHAR(2))
2. **operators** -- Normalized operator entities with aliases and per-state IDs
3. **wells** -- One row per physical well, API number as primary business identifier
4. **documents** -- Every scraped document with provenance, confidence, and status tracking
5. **extracted_data** -- Structured data extracted from documents (JSONB `data` column varies by doc_type)
6. **review_queue** -- Low-confidence items flagged for human review
7. **scrape_jobs** -- On-demand scrape job tracking with progress counters
8. **data_corrections** -- Audit trail for manual corrections from the review queue

### API Number Storage

- `api_number` as `VARCHAR(14)` -- stored without dashes, leading zeros preserved
- `api_10` as `VARCHAR(10) GENERATED ALWAYS AS (LEFT(api_number, 10)) STORED` -- auto-computed for cross-referencing
- Searches match against both `api_number` (exact) and `api_10` (prefix)
- Application layer normalizes on input: strip dashes/spaces, zero-pad to 10+ digits

### Dual Location Strategy

- `latitude` / `longitude` as `DOUBLE PRECISION` -- simple queries, CSV export, human-readable
- `location` as `GEOMETRY(Point, 4326)` -- PostGIS spatial index, bounding box queries, distance calculations
- A PostgreSQL trigger auto-syncs `location` from `latitude`/`longitude` on INSERT/UPDATE:

```sql
CREATE OR REPLACE FUNCTION wells_location_update() RETURNS trigger AS $$
BEGIN
    IF NEW.latitude IS NOT NULL AND NEW.longitude IS NOT NULL THEN
        NEW.location := ST_SetSRID(ST_MakePoint(NEW.longitude, NEW.latitude), 4326);
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
```

### Full-Text Search

- `tsvector` columns on `wells`, `operators`, and `documents` tables
- Weighted search vectors (A/B/C priority) updated via PostgreSQL triggers
- `pg_trgm` extension for fuzzy/typo-tolerant matching on operator names, lease names, and API numbers
- GIN indexes on all `tsvector` and trigram columns

### JSONB Patterns

| Table.Column | Contains |
|-------------|----------|
| `wells.metadata` | State-specific well attributes (formation, pool, abstract) |
| `wells.alternate_ids` | Non-API identifiers (permit number, RRC lease ID) |
| `operators.aliases` | Name variations as JSON array |
| `operators.state_operator_ids` | Per-state operator numbers |
| `documents.raw_metadata` | Original scrape metadata (page count, form number) |
| `extracted_data.data` | Extracted fields -- varies by `data_type` (production, permit, completion) |
| `extracted_data.field_confidence` | Per-field confidence scores |
| `scrape_jobs.parameters` | Job configuration (date range, doc types) |
| `review_queue.flag_details` | Why the item was flagged |

### Enum Types

- `doc_type_enum`: well_permit, completion_report, production_report, spacing_order, pooling_order, plugging_report, inspection_record, incident_report, other
- `document_status_enum`: discovered -> downloading -> downloaded -> classifying -> classified -> extracting -> extracted -> normalized -> stored (with failure states)
- `scrape_job_status_enum`: pending, running, completed, failed, cancelled
- `review_status_enum`: pending, approved, rejected, corrected
- `well_status_enum`: active, inactive, plugged, permitted, drilling, completed, shut_in, temporarily_abandoned, unknown

## Key Implementation Patterns

### Async Database Session (FastAPI Dependency)

```python
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

engine = create_async_engine(
    "postgresql+asyncpg://og_user:og_password@localhost:5432/og_scraper",
    pool_size=20,
    max_overflow=10,
    pool_pre_ping=True,
)

async_session_factory = async_sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False,
)

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
```

### Huey Task Queue (SQLite Backend)

```python
from huey import SqliteHuey

huey = SqliteHuey(
    "og-scraper",
    filename="data/huey.db",  # SQLite file, NOT Redis
)

@huey.task(retries=2, retry_delay=60)
def run_scrape_job(job_id: str, state_code: str | None, parameters: dict):
    """Execute a scrape job. Enqueued from FastAPI endpoint."""
    pass

@huey.task(retries=3, retry_delay=30)
def process_document(document_id: str):
    """Classify -> extract -> normalize -> store a single document."""
    pass
```

### SSE for Real-Time Progress

```python
from sse_starlette.sse import EventSourceResponse

@router.get("/scrape/jobs/{job_id}/events")
async def scrape_job_events(job_id: UUID, db: AsyncSession = Depends(get_db)):
    async def event_generator():
        last_state = None
        while True:
            job = await db.get(ScrapeJob, job_id)
            current_state = {
                "status": job.status,
                "documents_found": job.documents_found,
                "documents_processed": job.documents_processed,
            }
            if current_state != last_state:
                yield {"event": "progress", "data": json.dumps(current_state)}
                last_state = current_state
            if job.status in ("completed", "failed", "cancelled"):
                yield {"event": "complete", "data": json.dumps(current_state)}
                break
            await asyncio.sleep(1)

    return EventSourceResponse(event_generator())
```

### PostGIS Bounding Box Query (Map Viewport)

```python
from geoalchemy2.functions import ST_MakeEnvelope

envelope = func.ST_MakeEnvelope(min_lng, min_lat, max_lng, max_lat, 4326)
query = select(Well).where(Well.location.op("&&")(envelope)).limit(limit)
```

### Pydantic Model Pattern

All response models use `model_config = ConfigDict(from_attributes=True)` for direct SQLAlchemy-to-Pydantic serialization. Pagination is standardized:

```python
class PaginatedResponse(BaseModel):
    items: list[Any]
    total: int
    page: int
    page_size: int
    total_pages: int
```

### Confidence Scoring (Three Levels)

1. **OCR confidence** (`documents.ocr_confidence`) -- set by PaddleOCR
2. **Field confidence** (`extracted_data.field_confidence` JSONB) -- per-field scores from extraction engine
3. **Document confidence** (`documents.confidence_score`) -- aggregate; drives review queue threshold (default 0.80)

## Common Pitfalls

1. **Use async SQLAlchemy throughout** -- never use synchronous `Session` or `create_engine`. Always use `AsyncSession`, `create_async_engine`, and `async_sessionmaker`. The async driver is `asyncpg`, not `psycopg2`.

2. **Huey uses SQLite storage, NOT Redis** -- instantiate with `SqliteHuey("og-scraper", filename="data/huey.db")`, not `RedisHuey`. This eliminates the Redis dependency for local deployment.

3. **SSE connections need proper cleanup** -- always check for terminal job states (`completed`, `failed`, `cancelled`) and break out of the generator loop. Set `Cache-Control: no-cache` and `X-Accel-Buffering: no` headers to prevent proxy buffering.

4. **PostGIS extension must be enabled** -- the first Alembic migration must run `CREATE EXTENSION IF NOT EXISTS "postgis"` before creating any table with `GEOMETRY` columns. Use the `postgis/postgis:17-3.5` Docker image which has PostGIS pre-installed.

5. **API number normalization** -- always strip dashes and spaces before storing or querying. Use `VARCHAR(14)` not `INTEGER` because API numbers have leading zeros (e.g., Alaska state code '02').

6. **expire_on_commit=False** -- required in the async session factory to prevent `MissingGreenlet` errors when accessing attributes after commit in async contexts.

7. **Alembic async env.py** -- the migration runner must use `async_engine_from_config` and `asyncio.run()`. Import all models in `env.py` so Alembic's autogenerate can detect them.

8. **GeoAlchemy2 import** -- the `Well` model needs `from geoalchemy2 import Geometry` for the `location` column. This also requires `geoalchemy2` in dependencies.

9. **JSONB default values** -- use `default=dict` (factory) in SQLAlchemy mapped columns, not `default={}` (shared mutable). For server defaults, use `server_default="'{}'::jsonb"`.

10. **Streaming exports** -- use `StreamingResponse` with async generators for CSV/JSON exports to handle large datasets without loading everything into memory.

## Testing Strategy

- **pytest-asyncio** for async test functions
- **httpx.AsyncClient** with FastAPI's `TestClient` for API endpoint tests
- **testcontainers** for spinning up real PostgreSQL+PostGIS instances in tests
- **Factory fixtures** for generating test data (wells, documents, operators)
- Run Huey tasks synchronously in tests using `huey.immediate = True`

```python
import pytest
from httpx import AsyncClient
from app.main import app

@pytest.fixture
async def client():
    async with AsyncClient(app=app, base_url="http://test") as ac:
        yield ac

@pytest.mark.asyncio
async def test_list_wells(client):
    response = await client.get("/api/v1/wells")
    assert response.status_code == 200
    assert "items" in response.json()
```

## Cost Implications

**Free.** All components run locally:
- PostgreSQL + PostGIS in Docker (free)
- Huey with SQLite (free, no Redis)
- FastAPI + uvicorn (free)
- No external API calls, no cloud services, no paid OCR

## References

- [DISCOVERY.md](../../orchestration-og-doc-scraper/DISCOVERY.md) -- all project decisions (D1-D26)
- [Backend Schema Implementation](../../orchestration-og-doc-scraper/research/backend-schema-implementation.md) -- complete PostgreSQL DDL, FastAPI endpoints, SQLAlchemy models, Alembic setup, Pydantic schemas
- [Architecture & Storage Research](../../orchestration-og-doc-scraper/research/architecture-storage.md) -- database selection, search strategy, task queue evaluation, file storage, deployment
