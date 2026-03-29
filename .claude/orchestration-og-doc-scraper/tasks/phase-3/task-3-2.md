# Task 3.2: Scrape Job Endpoints & Huey Integration

## Objective

Implement the scrape job management API: a POST endpoint to trigger new scrape jobs, GET endpoints for job status and listing, an SSE endpoint for real-time progress streaming, and Huey task definitions that execute the actual scraping work asynchronously. This is the control plane that connects the dashboard's "Scrape" button to the scraping engine.

## Context

This task builds on the core CRUD endpoints (Task 3.1) and the base scraper framework (Task 1.3). When a user clicks "Scrape Texas" in the dashboard, the frontend POSTs to `/api/v1/scrape`, which creates a database record and enqueues a Huey task. The Huey worker picks up the task, runs the appropriate state spider, and updates progress counters in the database. Meanwhile, the frontend subscribes to the SSE endpoint for real-time updates.

Huey uses SQLite storage (not Redis) per DISCOVERY D6 and the `fastapi-backend` skill. This eliminates the Redis dependency for local deployment.

## Dependencies

- Task 3.1 - Core API structure, Pydantic schemas, pagination utilities, router registration pattern
- Task 1.3 - Base scraper framework (BaseOGSpider, state registry, download pipeline)
- Task 1.4 - FastAPI skeleton with Huey SqliteHuey instance
- Task 1.2 - Database models (scrape_jobs table)

## Blocked By

- Task 3.1 (base API patterns must exist)
- Task 1.3 (scraper framework must exist for Huey tasks to call)
- Task 2.4 (document pipeline must exist — Huey tasks call DocumentPipeline.process() to process downloaded documents)

## Research Findings

Key findings from research files relevant to this task:

- From `backend-schema-implementation.md` Section 3.3: Huey is chosen over FastAPI BackgroundTasks because scrape jobs are long-running, must survive restarts, need progress tracking, and benefit from retry logic
- From `backend-schema-implementation.md` Section 3.4: Complete SSE implementation with database polling, `event: progress` and `event: complete` event types, StreamingResponse with `Cache-Control: no-cache` and `X-Accel-Buffering: no` headers
- From `fastapi-backend` skill: Huey uses SqliteHuey with `filename="data/huey.db"`, tasks decorated with `@huey.task(retries=2, retry_delay=60)`, SSE via `sse-starlette` package with `EventSourceResponse`
- From `fastapi-backend` skill: SSE connections need proper cleanup -- always check for terminal job states and break out of the generator loop
- From `og-scraper-architecture` skill: Scrape jobs table has progress counters: documents_found, documents_downloaded, documents_processed, documents_failed

## Implementation Plan

### Step 1: Create Scrape Job Pydantic Schemas

**File: `backend/src/og_scraper/api/schemas/scrape.py`**

```python
from datetime import datetime
from typing import Optional
from uuid import UUID
from pydantic import BaseModel, Field, ConfigDict
from .enums import ScrapeJobStatus

class ScrapeJobCreate(BaseModel):
    """Request body for POST /api/v1/scrape"""
    state_code: Optional[str] = Field(
        None,
        description="2-letter state code (e.g., TX). None = all states.",
        min_length=2, max_length=2,
    )
    job_type: str = Field(
        default="full",
        description="Job type: 'full', 'incremental', or 'targeted'",
    )
    parameters: dict = Field(
        default_factory=dict,
        description="Optional parameters: date_range, doc_types, operator, etc.",
    )

class ScrapeJobSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    state_code: Optional[str]
    status: ScrapeJobStatus
    job_type: str
    documents_found: int = 0
    documents_downloaded: int = 0
    documents_processed: int = 0
    documents_failed: int = 0
    started_at: Optional[datetime]
    finished_at: Optional[datetime]
    created_at: datetime

class ScrapeJobDetail(ScrapeJobSummary):
    parameters: dict = {}
    errors: list[dict] = []
    total_documents: int = 0

class ScrapeProgressEvent(BaseModel):
    """Shape of each SSE progress event data payload."""
    status: str
    documents_found: int = 0
    documents_downloaded: int = 0
    documents_processed: int = 0
    documents_failed: int = 0
    current_stage: Optional[str] = None
    message: Optional[str] = None
```

### Step 2: Create Huey Task Definitions

**File: `backend/src/og_scraper/tasks/__init__.py`**

Import the canonical Huey instance from the worker module (created in Task 1.4). Do NOT create a second instance — there must be exactly one Huey instance shared between the API and worker:

```python
# backend/src/og_scraper/tasks/__init__.py
# Re-export the canonical Huey instance from worker module
from og_scraper.worker import huey_app as huey
```

**File: `backend/src/og_scraper/tasks/scrape_task.py`**

Define the main scrape task:

```python
from og_scraper.tasks import huey
from og_scraper.models.scrape_job import ScrapeJob
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

# IMPORTANT: Huey tasks run in a separate process/thread, so they
# use SYNCHRONOUS SQLAlchemy (not async). Use the SYNC_DATABASE_URL.
from og_scraper.config import settings

sync_engine = create_engine(settings.sync_database_url)

@huey.task(retries=2, retry_delay=60)
def run_scrape_job(job_id: str, state_code: str | None, parameters: dict):
    """
    Execute a scrape job. Enqueued from the FastAPI POST /scrape endpoint.

    This runs in the Huey worker process (synchronous context).
    Updates the scrape_jobs row with progress as it goes.
    """
    with Session(sync_engine) as db:
        job = db.get(ScrapeJob, job_id)
        if not job:
            return

        # Mark as running
        job.status = "running"
        job.started_at = datetime.utcnow()
        db.commit()

        try:
            # Determine which states to scrape
            if state_code:
                state_codes = [state_code]
            else:
                state_codes = ["TX", "NM", "ND", "OK", "CO", "WY", "LA", "PA", "CA", "AK"]

            for sc in state_codes:
                # Get spider class from state registry
                # spider = state_registry.get_spider(sc)
                # Run the spider, yielding documents
                # For each document:
                #   1. Update documents_found
                #   2. Download -> update documents_downloaded
                #   3. Process through pipeline -> update documents_processed
                #   4. On failure -> update documents_failed, append to errors
                #   5. db.commit() after each document (so SSE picks up changes)
                pass

            job.status = "completed"
            job.finished_at = datetime.utcnow()
            db.commit()

        except Exception as e:
            job.status = "failed"
            job.finished_at = datetime.utcnow()
            job.errors = job.errors + [{"error": str(e), "timestamp": datetime.utcnow().isoformat()}]
            db.commit()
            raise  # Re-raise so Huey's retry mechanism can catch it

@huey.task(retries=3, retry_delay=30)
def process_document(document_id: str):
    """Process a single document through classify -> extract -> normalize -> store."""
    with Session(sync_engine) as db:
        # Load document
        # Run through pipeline stages
        # Update document status and confidence scores
        # If low confidence, call flag_for_review
        pass

@huey.task()
def flag_for_review(document_id: str, reason: str, details: dict):
    """Create a review queue entry for a low-confidence document."""
    with Session(sync_engine) as db:
        # Create review_queue record
        pass
```

Key patterns:
- Huey tasks use **synchronous** SQLAlchemy because they run in a separate worker process
- Use `SYNC_DATABASE_URL` (`postgresql://...` not `postgresql+asyncpg://...`)
- Commit after each document so the SSE endpoint sees incremental progress
- `retries=2, retry_delay=60` for scrape jobs (they can be long, retry on transient failures)
- `retries=3, retry_delay=30` for document processing (faster retry cycle)

### Step 3: Implement Scrape Router

**File: `backend/src/og_scraper/api/routes/scrape.py`**

Four endpoints:

**`POST /api/v1/scrape`** -- Trigger a new scrape job

```python
@router.post("/", response_model=ScrapeJobDetail, status_code=202)
async def create_scrape_job(
    job_in: ScrapeJobCreate,
    db: AsyncSession = Depends(get_db),
):
    """Trigger a new scrape job. Returns 202 Accepted with job ID immediately."""
    # Validate state_code if provided
    if job_in.state_code:
        state = await db.get(State, job_in.state_code.upper())
        if not state:
            raise HTTPException(status_code=400, detail=f"Unknown state: {job_in.state_code}")

    # Prevent duplicate running jobs for the same state
    existing = await db.execute(
        select(ScrapeJob).where(
            ScrapeJob.state_code == job_in.state_code,
            ScrapeJob.status.in_(["pending", "running"]),
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=409,
            detail=f"A scrape job is already running for state: {job_in.state_code or 'all'}",
        )

    # Create job record
    job = ScrapeJob(
        state_code=job_in.state_code.upper() if job_in.state_code else None,
        job_type=job_in.job_type,
        parameters=job_in.parameters,
        status="pending",
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)

    # Enqueue to Huey (fire and forget)
    run_scrape_job(str(job.id), job_in.state_code, job_in.parameters)

    return job
```

Return 202 Accepted (not 200 or 201) since the work happens asynchronously.

**`GET /api/v1/scrape/jobs`** -- List scrape jobs

```python
@router.get("/jobs", response_model=PaginatedResponse[ScrapeJobSummary])
async def list_scrape_jobs(
    status: ScrapeJobStatus | None = None,
    state: str | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    query = select(ScrapeJob).order_by(ScrapeJob.created_at.desc())
    if status:
        query = query.where(ScrapeJob.status == status.value)
    if state:
        query = query.where(ScrapeJob.state_code == state.upper())
    return await paginate(db, query, page, page_size)
```

**`GET /api/v1/scrape/jobs/{id}`** -- Detailed job status

```python
@router.get("/jobs/{job_id}", response_model=ScrapeJobDetail)
async def get_scrape_job(job_id: UUID, db: AsyncSession = Depends(get_db)):
    job = await db.get(ScrapeJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Scrape job not found")
    return job
```

**`GET /api/v1/scrape/jobs/{id}/events`** -- SSE real-time progress stream

```python
from sse_starlette.sse import EventSourceResponse

@router.get("/jobs/{job_id}/events")
async def scrape_job_events(job_id: UUID, db: AsyncSession = Depends(get_db)):
    """SSE endpoint for real-time scrape job progress."""
    # Verify job exists first
    job = await db.get(ScrapeJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Scrape job not found")

    async def event_generator():
        last_state = None
        while True:
            # Refresh the session to see latest DB state
            await db.expire_all()
            job = await db.get(ScrapeJob, job_id)

            if job is None:
                yield {
                    "event": "error",
                    "data": json.dumps({"message": "Job not found"}),
                }
                break

            current_state = {
                "status": job.status,
                "documents_found": job.documents_found or 0,
                "documents_downloaded": job.documents_downloaded or 0,
                "documents_processed": job.documents_processed or 0,
                "documents_failed": job.documents_failed or 0,
            }

            # Only emit when state changes
            if current_state != last_state:
                yield {
                    "event": "progress",
                    "data": json.dumps(current_state),
                }
                last_state = current_state.copy()

            # Terminal states
            if job.status in ("completed", "failed", "cancelled"):
                final_data = {
                    **current_state,
                    "finished_at": job.finished_at.isoformat() if job.finished_at else None,
                }
                yield {
                    "event": "complete",
                    "data": json.dumps(final_data),
                }
                break

            await asyncio.sleep(1)  # 1-second poll interval

    return EventSourceResponse(
        event_generator(),
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
```

SSE event shapes:

| Event | Data Shape | When |
|-------|-----------|------|
| `progress` | `{"status": "running", "documents_found": 12, "documents_downloaded": 8, "documents_processed": 5, "documents_failed": 0}` | Progress counters change |
| `error` | `{"message": "Job not found"}` | Job deleted or not found |
| `complete` | `{"status": "completed", "documents_found": 50, ..., "finished_at": "2026-03-28T..."}` | Job reaches terminal state |

### Step 4: Update Config for Sync Database URL

**File: `backend/src/og_scraper/config.py`**

Add `SYNC_DATABASE_URL` to the Pydantic Settings model. This is the synchronous URL used by Huey worker tasks (which cannot use async):

```python
class Settings(BaseSettings):
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@db:5432/ogdocs"
    SYNC_DATABASE_URL: str = "postgresql://postgres:postgres@db:5432/ogdocs"
    DATA_DIR: str = "/app/data"
    HUEY_DB_PATH: str = "data/huey.db"
    # ... existing settings
```

### Step 5: Register Scrape Router

Update `backend/src/og_scraper/api/routes/__init__.py` to include the scrape router:

```python
from .scrape import router as scrape_router
api_router.include_router(scrape_router, prefix="/scrape", tags=["scraping"])
```

### Step 6: Write Tests

**File: `backend/tests/api/test_scrape.py`**

```python
import pytest
from httpx import AsyncClient

@pytest.mark.asyncio
async def test_create_scrape_job(client: AsyncClient):
    response = await client.post("/api/v1/scrape", json={
        "state_code": "TX",
        "job_type": "full",
    })
    assert response.status_code == 202
    data = response.json()
    assert "id" in data
    assert data["status"] == "pending"
    assert data["state_code"] == "TX"

@pytest.mark.asyncio
async def test_create_scrape_job_invalid_state(client: AsyncClient):
    response = await client.post("/api/v1/scrape", json={
        "state_code": "ZZ",
    })
    assert response.status_code == 400

@pytest.mark.asyncio
async def test_create_duplicate_scrape_job(client: AsyncClient):
    # First job
    await client.post("/api/v1/scrape", json={"state_code": "TX"})
    # Duplicate should be rejected
    response = await client.post("/api/v1/scrape", json={"state_code": "TX"})
    assert response.status_code == 409

@pytest.mark.asyncio
async def test_list_scrape_jobs(client: AsyncClient):
    response = await client.get("/api/v1/scrape/jobs")
    assert response.status_code == 200
    assert "items" in response.json()

@pytest.mark.asyncio
async def test_get_scrape_job(client: AsyncClient):
    # Create a job first
    create_resp = await client.post("/api/v1/scrape", json={"state_code": "OK"})
    job_id = create_resp.json()["id"]
    # Fetch it
    response = await client.get(f"/api/v1/scrape/jobs/{job_id}")
    assert response.status_code == 200
    assert response.json()["id"] == job_id

@pytest.mark.asyncio
async def test_get_scrape_job_not_found(client: AsyncClient):
    import uuid
    response = await client.get(f"/api/v1/scrape/jobs/{uuid.uuid4()}")
    assert response.status_code == 404
```

For SSE testing, use `httpx` streaming:

```python
@pytest.mark.asyncio
async def test_sse_stream(client: AsyncClient):
    # Create a job, manually set it to completed in DB
    # Then connect to SSE endpoint and verify we get a 'complete' event
    pass
```

For Huey task testing, use `huey.immediate = True`:

```python
@pytest.fixture
def immediate_huey():
    """Run Huey tasks synchronously for testing."""
    from og_scraper.tasks import huey
    huey.immediate = True
    yield huey
    huey.immediate = False
```

## Files to Create

- `backend/src/og_scraper/api/schemas/scrape.py` - ScrapeJobCreate, ScrapeJobSummary, ScrapeJobDetail, ScrapeProgressEvent
- `backend/src/og_scraper/api/routes/scrape.py` - POST /scrape, GET /scrape/jobs, GET /scrape/jobs/{id}, GET /scrape/jobs/{id}/events
- `backend/src/og_scraper/tasks/__init__.py` - SqliteHuey instance configuration
- `backend/src/og_scraper/tasks/scrape_task.py` - run_scrape_job, process_document, flag_for_review Huey tasks
- `backend/tests/api/test_scrape.py` - All scrape endpoint tests

## Files to Modify

- `backend/src/og_scraper/api/routes/__init__.py` - Register scrape router
- `backend/src/og_scraper/config.py` - Add SYNC_DATABASE_URL and HUEY_DB_PATH settings

## Contracts

### Provides (for downstream tasks)

- **Endpoint**: `POST /api/v1/scrape` - Trigger a new scrape job
  - Request: `ScrapeJobCreate` body: `{"state_code": "TX" | null, "job_type": "full", "parameters": {}}`
  - Response: `ScrapeJobDetail` with status 202
  - Error 400: Invalid state code
  - Error 409: Duplicate running job for same state
- **Endpoint**: `GET /api/v1/scrape/jobs` - List scrape jobs
  - Request: Query params (status, state, page, page_size)
  - Response: `PaginatedResponse[ScrapeJobSummary]`
- **Endpoint**: `GET /api/v1/scrape/jobs/{id}` - Get job detail
  - Response: `ScrapeJobDetail` with progress counters and error list
  - Error 404: Job not found
- **Endpoint**: `GET /api/v1/scrape/jobs/{id}/events` - SSE progress stream
  - Response: `text/event-stream`
  - Events: `progress` (progress data), `error` (error message), `complete` (final state)
  - Error 404: Job not found (before stream starts)
- **Huey task**: `run_scrape_job(job_id, state_code, parameters)` - Async scrape execution
- **Huey task**: `process_document(document_id)` - Async document pipeline execution
- **Huey task**: `flag_for_review(document_id, reason, details)` - Create review queue entry

### Consumes (from upstream tasks)

- From Task 3.1: `PaginatedResponse`, `PaginationParams`, `paginate()` utility, router registration pattern
- From Task 1.3: `BaseOGSpider`, `state_registry`, `DocumentItem`, download pipeline
- From Task 1.4: `get_db()` dependency, `create_app()`, `SqliteHuey` configuration pattern
- From Task 1.2: `ScrapeJob` SQLAlchemy model, `State` model for validation

## Acceptance Criteria

- [ ] `POST /api/v1/scrape` creates a job record and returns 202 with job ID
- [ ] `POST /api/v1/scrape` validates state_code against states table (400 for invalid)
- [ ] `POST /api/v1/scrape` rejects duplicate running jobs for the same state (409)
- [ ] `GET /api/v1/scrape/jobs` returns paginated list of scrape jobs (newest first)
- [ ] `GET /api/v1/scrape/jobs` filters by status and state
- [ ] `GET /api/v1/scrape/jobs/{id}` returns detailed job with progress counters and errors
- [ ] `GET /api/v1/scrape/jobs/{id}` returns 404 for non-existent job
- [ ] `GET /api/v1/scrape/jobs/{id}/events` streams SSE events as job progresses
- [ ] SSE stream emits `progress` events when counters change
- [ ] SSE stream emits `complete` event and closes when job reaches terminal state
- [ ] SSE response headers include `Cache-Control: no-cache` and `X-Accel-Buffering: no`
- [ ] Huey task `run_scrape_job` updates job status from `pending` to `running` to `completed`/`failed`
- [ ] Huey task records errors in `scrape_jobs.errors` JSONB array
- [ ] Huey tasks use synchronous SQLAlchemy (not async) with SYNC_DATABASE_URL
- [ ] All tests pass
- [ ] Build succeeds

## Testing Protocol

### Unit/Integration Tests

- Test file: `backend/tests/api/test_scrape.py`
- Test cases:
  - [ ] POST /scrape with valid state returns 202 with job ID and pending status
  - [ ] POST /scrape with null state_code (all states) returns 202
  - [ ] POST /scrape with invalid state returns 400
  - [ ] POST /scrape with duplicate running job returns 409
  - [ ] GET /scrape/jobs returns paginated list ordered by created_at desc
  - [ ] GET /scrape/jobs?status=pending returns only pending jobs
  - [ ] GET /scrape/jobs?state=TX returns only TX jobs
  - [ ] GET /scrape/jobs/{id} returns correct job details
  - [ ] GET /scrape/jobs/{nonexistent} returns 404
  - [ ] SSE endpoint returns event-stream content type
  - [ ] SSE endpoint for completed job immediately sends complete event
  - [ ] Huey run_scrape_job task updates job status in DB (with immediate=True)
  - [ ] Huey run_scrape_job handles exceptions and marks job as failed

### API/Script Testing

- Start backend: `uv run uvicorn og_scraper.api.app:create_app --factory --port 8000`
- Start Huey worker: `uv run huey_consumer og_scraper.tasks.huey`
- Test scrape trigger: `curl -X POST http://localhost:8000/api/v1/scrape -H "Content-Type: application/json" -d '{"state_code": "TX", "job_type": "full"}'`
- Test job list: `curl http://localhost:8000/api/v1/scrape/jobs`
- Test SSE stream: `curl -N http://localhost:8000/api/v1/scrape/jobs/{job_id}/events`

### Build/Lint/Type Checks

- [ ] `uv run pytest backend/tests/api/test_scrape.py` succeeds
- [ ] `uv run ruff check backend/src/og_scraper/api/routes/scrape.py` passes
- [ ] `uv run ruff check backend/src/og_scraper/tasks/` passes

## Skills to Read

- `fastapi-backend` - Huey SqliteHuey pattern, SSE via sse-starlette, async session dependency
- `scrapy-playwright-scraping` - Spider execution pattern that Huey task will call
- `og-scraper-architecture` - Service communication: API -> Huey -> DB -> SSE

## Research Files to Read

- `.claude/orchestration-og-doc-scraper/research/backend-schema-implementation.md` - Section 3.3 (Huey integration), Section 3.4 (SSE implementation)

## Git

- Branch: `phase-3/task-3-2-scrape-huey-sse`
- Commit message prefix: `Task 3.2:`
