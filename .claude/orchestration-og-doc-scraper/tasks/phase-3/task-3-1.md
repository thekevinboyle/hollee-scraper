# Task 3.1: Core CRUD Endpoints

## Objective

Implement the foundational REST API endpoints for wells, documents, operators, and states. These endpoints provide search, filtering, pagination, and detail views that all other Phase 3 tasks build upon. This task also establishes the shared Pydantic schemas, pagination utilities, and query builder patterns used across all API routes.

## Context

Phase 3 builds the complete backend API. This task (3.1) is the first and most critical -- it creates the CRUD layer that serves as the foundation for scrape endpoints (3.2), review queue (3.3), and map/export (3.4). Phase 1 already created the database models (1.2) and FastAPI skeleton (1.4). Phase 2 built the document pipeline. This task wires the database to HTTP endpoints.

No authentication is needed (DISCOVERY D7 -- internal tool for 1-2 users).

## Dependencies

- Task 1.2 - Database schema and SQLAlchemy models (all 8 tables)
- Task 1.4 - FastAPI skeleton with app factory, database session dependency, health check, CORS, Huey instance

## Blocked By

- Task 1.4 (FastAPI skeleton must exist)
- Task 1.2 (database models must exist)

## Research Findings

Key findings from research files relevant to this task:

- From `backend-schema-implementation.md` Section 3.1: Complete endpoint signatures for wells (`GET /wells`, `GET /wells/{api_number}`) and documents (`GET /documents`, `GET /documents/{id}`, `GET /documents/{id}/file`) with full query parameter specifications
- From `backend-schema-implementation.md` Section 3.2: Complete Pydantic model definitions for `WellSummary`, `WellDetail`, `DocumentSummary`, `DocumentDetail`, `ExtractedDataSummary`, `PaginationParams`, `PaginatedResponse`, and all enum types
- From `backend-schema-implementation.md` Section 3.5: File serving pattern using `FileResponse` with MIME type detection
- From `postgresql-postgis-schema` skill: Full-text search query pattern using `plainto_tsquery` with `ts_rank` ordering, and trigram fuzzy search via `pg_trgm`
- From `fastapi-backend` skill: Async database session dependency pattern with `expire_on_commit=False`, Pydantic `model_config = ConfigDict(from_attributes=True)` for ORM serialization

## Implementation Plan

### Step 1: Create Shared Pydantic Schemas

Create all the Pydantic request/response models that will be reused across endpoints.

**File: `backend/src/og_scraper/api/schemas/__init__.py`**

Export all schemas from a single module.

**File: `backend/src/og_scraper/api/schemas/enums.py`**

Define string enums that mirror the PostgreSQL enum types:

```python
from enum import Enum

class DocType(str, Enum):
    WELL_PERMIT = "well_permit"
    COMPLETION_REPORT = "completion_report"
    PRODUCTION_REPORT = "production_report"
    SPACING_ORDER = "spacing_order"
    POOLING_ORDER = "pooling_order"
    PLUGGING_REPORT = "plugging_report"
    INSPECTION_RECORD = "inspection_record"
    INCIDENT_REPORT = "incident_report"
    OTHER = "other"

class WellStatus(str, Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    PLUGGED = "plugged"
    PERMITTED = "permitted"
    DRILLING = "drilling"
    COMPLETED = "completed"
    SHUT_IN = "shut_in"
    TEMPORARILY_ABANDONED = "temporarily_abandoned"
    UNKNOWN = "unknown"

class DocumentStatus(str, Enum):
    DISCOVERED = "discovered"
    DOWNLOADING = "downloading"
    DOWNLOADED = "downloaded"
    CLASSIFYING = "classifying"
    CLASSIFIED = "classified"
    EXTRACTING = "extracting"
    EXTRACTED = "extracted"
    NORMALIZED = "normalized"
    STORED = "stored"
    FLAGGED_FOR_REVIEW = "flagged_for_review"
    DOWNLOAD_FAILED = "download_failed"
    CLASSIFICATION_FAILED = "classification_failed"
    EXTRACTION_FAILED = "extraction_failed"

class ScrapeJobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

class ReviewStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    CORRECTED = "corrected"

class SortDirection(str, Enum):
    ASC = "asc"
    DESC = "desc"
```

**File: `backend/src/og_scraper/api/schemas/pagination.py`**

```python
from typing import Any, Generic, TypeVar
from pydantic import BaseModel, Field

T = TypeVar("T")

class PaginationParams(BaseModel):
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=50, ge=1, le=200)

class PaginatedResponse(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int
    page_size: int
    total_pages: int
```

**File: `backend/src/og_scraper/api/schemas/well.py`**

Define `WellSummary` and `WellDetail` schemas exactly as specified in the research:

- `WellSummary`: id, api_number, well_name, operator_name (joined), state_code, county, well_status, well_type, latitude, longitude, document_count (computed)
- `WellDetail`: All WellSummary fields plus api_10, well_number, operator_id, basin, field_name, lease_name, spud_date, completion_date, total_depth, true_vertical_depth, lateral_length, metadata (dict), alternate_ids (dict), documents (list[DocumentSummary]), created_at, updated_at

Both use `model_config = ConfigDict(from_attributes=True)`.

**File: `backend/src/og_scraper/api/schemas/document.py`**

Define `DocumentSummary`, `DocumentDetail`, and `ExtractedDataSummary`:

- `DocumentSummary`: id, well_id, state_code, doc_type, document_date, confidence_score, file_format, source_url, scraped_at
- `DocumentDetail`: All summary fields plus well_api_number (joined), status, file_path, file_size_bytes, file_hash, ocr_confidence, classification_method, processed_at, raw_metadata, extracted_data (list[ExtractedDataSummary]), created_at, updated_at
- `ExtractedDataSummary`: id, document_id, data_type, data (dict), field_confidence (dict), confidence_score, extractor_used, reporting_period_start, reporting_period_end, extracted_at

**File: `backend/src/og_scraper/api/schemas/operator.py`**

- `OperatorSummary`: id, name, normalized_name, well_count (computed), state_codes (computed list)
- `OperatorDetail`: All summary fields plus aliases (list), state_operator_ids (dict), metadata (dict), created_at, updated_at

**File: `backend/src/og_scraper/api/schemas/state.py`**

- `StateSummary`: code, name, api_state_code, tier, last_scraped_at, well_count (computed), document_count (computed)

### Step 2: Create Pagination Utility

**File: `backend/src/og_scraper/api/utils/pagination.py`**

Create a reusable function that applies pagination to any SQLAlchemy query:

```python
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

async def paginate(db: AsyncSession, query, page: int, page_size: int):
    # Count total
    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar_one()

    # Apply offset/limit
    offset = (page - 1) * page_size
    items_query = query.offset(offset).limit(page_size)
    result = await db.execute(items_query)
    items = result.all()

    total_pages = (total + page_size - 1) // page_size

    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": total_pages,
    }
```

### Step 3: Create Query Builder Utility

**File: `backend/src/og_scraper/api/utils/query_builder.py`**

Create a reusable query builder that supports filtering, sorting, and full-text search:

```python
from sqlalchemy import select, or_, desc, asc, func
from og_scraper.models.well import Well
from og_scraper.models.operator import Operator

def build_wells_query(
    q: str | None = None,
    api_number: str | None = None,
    state: str | None = None,
    county: str | None = None,
    operator: str | None = None,
    lease_name: str | None = None,
    well_status: str | None = None,
    well_type: str | None = None,
    sort_by: str = "api_number",
    sort_dir: str = "asc",
):
    query = (
        select(
            Well,
            Operator.name.label("operator_name"),
            func.count(Document.id).over(partition_by=Well.id).label("document_count"),
        )
        .outerjoin(Operator, Well.operator_id == Operator.id)
        .outerjoin(Document, Document.well_id == Well.id)
    )

    # Full-text search
    if q:
        ts_query = func.plainto_tsquery("english", q)
        query = query.where(Well.search_vector.op("@@")(ts_query))
        # Order by relevance when searching
        query = query.order_by(func.ts_rank(Well.search_vector, ts_query).desc())

    # API number: exact or prefix match (also try fuzzy via trigram)
    if api_number:
        normalized = api_number.replace("-", "").replace(" ", "")
        query = query.where(
            or_(
                Well.api_number == normalized,
                Well.api_10 == normalized[:10] if len(normalized) >= 10 else Well.api_number.startswith(normalized),
            )
        )

    # Simple filters
    if state:
        query = query.where(Well.state_code == state.upper())
    if county:
        query = query.where(Well.county.ilike(f"%{county}%"))
    if operator:
        query = query.where(Operator.name.ilike(f"%{operator}%"))
    if lease_name:
        query = query.where(Well.lease_name.ilike(f"%{lease_name}%"))
    if well_status:
        query = query.where(Well.well_status == well_status)
    if well_type:
        query = query.where(Well.well_type == well_type)

    # Sorting (only if not using full-text relevance sorting)
    if not q:
        sort_column = getattr(Well, sort_by, Well.api_number)
        order_func = desc if sort_dir == "desc" else asc
        query = query.order_by(order_func(sort_column))

    return query.group_by(Well.id, Operator.name)
```

Create a similar `build_documents_query` function supporting: q, well_id, state, doc_type, date_from, date_to, min_confidence, status, sort_by, sort_dir.

### Step 4: Create API Number Utility

**File: `backend/src/og_scraper/api/utils/api_number.py`**

```python
import re

def normalize_api_number(raw: str) -> str:
    """Strip dashes/spaces, preserve leading zeros. Returns 10-14 char string."""
    cleaned = re.sub(r"[^0-9]", "", raw)
    # Zero-pad to at least 10 digits
    if len(cleaned) < 10:
        cleaned = cleaned.zfill(10)
    return cleaned[:14]  # Truncate to max 14

def format_api_number(api: str) -> str:
    """Format for display: XX-YYY-ZZZZZ[-SS[-EE]]"""
    if len(api) >= 10:
        parts = [api[:2], api[2:5], api[5:10]]
        if len(api) > 10:
            parts.append(api[10:12])
        if len(api) > 12:
            parts.append(api[12:14])
        return "-".join(parts)
    return api
```

### Step 5: Implement Wells Router

**File: `backend/src/og_scraper/api/routes/wells.py`**

Two endpoints:

**`GET /api/v1/wells`** -- Search/filter/paginate wells

Query parameters (all optional):
- `q` (str): full-text search
- `api_number` (str): exact or prefix API number match
- `state` (str): state code filter
- `county` (str): county name filter (fuzzy)
- `operator` (str): operator name filter (fuzzy)
- `lease_name` (str): lease name filter (fuzzy)
- `well_status` (WellStatus enum): status filter
- `well_type` (str): type filter
- `page` (int, default=1): page number
- `page_size` (int, default=50, max=200): results per page
- `sort_by` (str, default="api_number"): sort field
- `sort_dir` (SortDirection, default="asc"): sort direction

Response: `PaginatedResponse[WellSummary]`

```python
@router.get("/", response_model=PaginatedResponse[WellSummary])
async def list_wells(
    q: str | None = None,
    api_number: str | None = None,
    state: str | None = None,
    county: str | None = None,
    operator: str | None = None,
    lease_name: str | None = None,
    well_status: WellStatus | None = None,
    well_type: str | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    sort_by: str = "api_number",
    sort_dir: SortDirection = SortDirection.ASC,
    db: AsyncSession = Depends(get_db),
):
    query = build_wells_query(q=q, api_number=api_number, state=state, ...)
    return await paginate(db, query, page, page_size)
```

**`GET /api/v1/wells/{api_number}`** -- Well detail with documents

The `api_number` path parameter accepts API numbers with or without dashes. Normalize it, then look up:

```python
@router.get("/{api_number}", response_model=WellDetail)
async def get_well(api_number: str, db: AsyncSession = Depends(get_db)):
    normalized = normalize_api_number(api_number)
    query = (
        select(Well)
        .options(selectinload(Well.documents), selectinload(Well.operator))
        .where(or_(Well.api_number == normalized, Well.api_10 == normalized[:10]))
    )
    result = await db.execute(query)
    well = result.scalar_one_or_none()
    if not well:
        raise HTTPException(status_code=404, detail=f"Well not found: {api_number}")
    return well
```

### Step 6: Implement Documents Router

**File: `backend/src/og_scraper/api/routes/documents.py`**

Three endpoints:

**`GET /api/v1/documents`** -- Search/filter/paginate documents

Query parameters:
- `q` (str): full-text search
- `well_id` (UUID): filter by well
- `state` (str): state code filter
- `doc_type` (DocType enum): document type filter
- `date_from` (date): document date range start
- `date_to` (date): document date range end
- `min_confidence` (float): minimum confidence score filter
- `status` (DocumentStatus enum): document status filter
- `page`, `page_size`, `sort_by`, `sort_dir`: pagination/sorting

Response: `PaginatedResponse[DocumentSummary]`

**`GET /api/v1/documents/{id}`** -- Document detail with extracted data

Returns `DocumentDetail` with nested `extracted_data` list and joined `well_api_number`. Uses `selectinload` for eager loading of extracted data records.

Returns 404 if document ID not found.

**`GET /api/v1/documents/{id}/file`** -- Serve the original document file

MIME type mapping:
```python
MIME_TYPES = {
    "pdf": "application/pdf",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "xls": "application/vnd.ms-excel",
    "csv": "text/csv",
    "html": "text/html",
    "tif": "image/tiff",
    "tiff": "image/tiff",
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
}
```

Use `FileResponse`. For PDFs, set `Content-Disposition: inline` (view in browser). For other types, use `attachment` (download). Return 404 if document not found, file_path not set, or file not found on disk.

### Step 7: Implement Operators Router

**File: `backend/src/og_scraper/api/routes/operators.py`**

**`GET /api/v1/operators`** -- List/search operators

Query parameters:
- `q` (str): search by name (uses trigram similarity)
- `state` (str): filter operators with wells in a specific state
- `page`, `page_size`

Response: `PaginatedResponse[OperatorSummary]`

Query pattern: Join operators to wells, group by operator, compute well_count and state_codes. If `q` is provided, use trigram similarity: `WHERE similarity(operators.name, :q) > 0.3 ORDER BY similarity DESC`.

### Step 8: Implement States Router

**File: `backend/src/og_scraper/api/routes/states.py`**

**`GET /api/v1/states`** -- List all 10 states with summary stats

No query parameters. Returns all states with computed well_count and document_count via subqueries.

Response: `list[StateSummary]`

### Step 9: Register All Routers

**File: `backend/src/og_scraper/api/routes/__init__.py`**

Update the router aggregation to include all new routers:

```python
from fastapi import APIRouter
from .wells import router as wells_router
from .documents import router as documents_router
from .operators import router as operators_router
from .states import router as states_router

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(wells_router, prefix="/wells", tags=["wells"])
api_router.include_router(documents_router, prefix="/documents", tags=["documents"])
api_router.include_router(operators_router, prefix="/operators", tags=["operators"])
api_router.include_router(states_router, prefix="/states", tags=["states"])
```

### Step 10: Write Tests

**File: `backend/tests/api/test_wells.py`**

**File: `backend/tests/api/test_documents.py`**

**File: `backend/tests/api/test_operators.py`**

**File: `backend/tests/api/test_states.py`**

Use `httpx.AsyncClient` with the FastAPI test app. Create test fixtures that seed the database with sample data (wells, operators, documents, extracted_data).

## Files to Create

- `backend/src/og_scraper/api/schemas/__init__.py` - Schema package init, re-exports all schemas
- `backend/src/og_scraper/api/schemas/enums.py` - String enum types mirroring PostgreSQL enums
- `backend/src/og_scraper/api/schemas/pagination.py` - PaginationParams, PaginatedResponse
- `backend/src/og_scraper/api/schemas/well.py` - WellSummary, WellDetail
- `backend/src/og_scraper/api/schemas/document.py` - DocumentSummary, DocumentDetail, ExtractedDataSummary
- `backend/src/og_scraper/api/schemas/operator.py` - OperatorSummary, OperatorDetail
- `backend/src/og_scraper/api/schemas/state.py` - StateSummary
- `backend/src/og_scraper/api/utils/__init__.py` - Utility package init
- `backend/src/og_scraper/api/utils/pagination.py` - Reusable paginate() function
- `backend/src/og_scraper/api/utils/query_builder.py` - build_wells_query(), build_documents_query()
- `backend/src/og_scraper/api/utils/api_number.py` - normalize_api_number(), format_api_number()
- `backend/src/og_scraper/api/routes/wells.py` - GET /wells, GET /wells/{api_number}
- `backend/src/og_scraper/api/routes/documents.py` - GET /documents, GET /documents/{id}, GET /documents/{id}/file
- `backend/src/og_scraper/api/routes/operators.py` - GET /operators
- `backend/src/og_scraper/api/routes/states.py` - GET /states
- `backend/tests/api/test_wells.py` - Well endpoint tests
- `backend/tests/api/test_documents.py` - Document endpoint tests
- `backend/tests/api/test_operators.py` - Operator endpoint tests
- `backend/tests/api/test_states.py` - State endpoint tests
- `backend/tests/api/conftest.py` - Shared test fixtures (db session, test client, seed data)

## Files to Modify

- `backend/src/og_scraper/api/routes/__init__.py` - Register new routers (wells, documents, operators, states)
- `backend/src/og_scraper/api/app.py` - Include the api_router from routes/__init__.py

## Contracts

### Provides (for downstream tasks)

- **Endpoint**: `GET /api/v1/wells` - Paginated well list with search/filter
  - Request: Query params (q, api_number, state, county, operator, lease_name, well_status, well_type, page, page_size, sort_by, sort_dir)
  - Response: `PaginatedResponse[WellSummary]`
- **Endpoint**: `GET /api/v1/wells/{api_number}` - Well detail with documents
  - Response: `WellDetail` with nested `documents: list[DocumentSummary]`
- **Endpoint**: `GET /api/v1/documents` - Paginated document list with search/filter
  - Request: Query params (q, well_id, state, doc_type, date_from, date_to, min_confidence, status, page, page_size, sort_by, sort_dir)
  - Response: `PaginatedResponse[DocumentSummary]`
- **Endpoint**: `GET /api/v1/documents/{id}` - Document detail with extracted data
  - Response: `DocumentDetail` with nested `extracted_data: list[ExtractedDataSummary]`
- **Endpoint**: `GET /api/v1/documents/{id}/file` - Serve original document file
  - Response: `FileResponse` with correct Content-Type
- **Endpoint**: `GET /api/v1/operators` - Paginated operator list
  - Response: `PaginatedResponse[OperatorSummary]`
- **Endpoint**: `GET /api/v1/states` - All states with stats
  - Response: `list[StateSummary]`
- **Shared schemas**: `WellSummary`, `WellDetail`, `DocumentSummary`, `DocumentDetail`, `ExtractedDataSummary`, `PaginatedResponse`, `PaginationParams`, all enums
- **Shared utilities**: `paginate()`, `build_wells_query()`, `build_documents_query()`, `normalize_api_number()`

### Consumes (from upstream tasks)

- SQLAlchemy models from Task 1.2: `Well`, `Operator`, `Document`, `ExtractedData`, `State`
- FastAPI app factory from Task 1.4: `create_app()`, `get_db()` dependency
- Database session from Task 1.4: `AsyncSession` via dependency injection
- Huey instance from Task 1.4: `SqliteHuey` (not used in this task, but available)

## Acceptance Criteria

- [ ] `GET /api/v1/wells` returns paginated well list with correct schema
- [ ] `GET /api/v1/wells` full-text search via `?q=` returns relevant results ordered by relevance
- [ ] `GET /api/v1/wells` filters by state, operator, county, well_status, well_type
- [ ] `GET /api/v1/wells/{api_number}` returns well detail with nested documents (accepts dashes in API number)
- [ ] `GET /api/v1/wells/{api_number}` returns 404 for non-existent wells
- [ ] `GET /api/v1/documents` returns paginated document list with correct schema
- [ ] `GET /api/v1/documents` filters by state, doc_type, date range, min_confidence, status
- [ ] `GET /api/v1/documents/{id}` returns document detail with nested extracted_data
- [ ] `GET /api/v1/documents/{id}/file` serves file with correct Content-Type (inline for PDF, attachment for others)
- [ ] `GET /api/v1/documents/{id}/file` returns 404 when file missing
- [ ] `GET /api/v1/operators` returns paginated operator list with well counts
- [ ] `GET /api/v1/states` returns all 10 states with well/document counts
- [ ] All paginated responses include total, page, page_size, total_pages
- [ ] All tests pass
- [ ] Build succeeds

## Testing Protocol

### Unit/Integration Tests

- Test file: `backend/tests/api/conftest.py`
- Test cases:
  - [ ] Fixture seeds database with 3 states, 2 operators, 5 wells, 10 documents, 5 extracted_data records

- Test file: `backend/tests/api/test_wells.py`
- Test cases:
  - [ ] `GET /api/v1/wells` returns 200 with paginated response structure
  - [ ] `GET /api/v1/wells?state=TX` returns only Texas wells
  - [ ] `GET /api/v1/wells?operator=Devon` returns wells with matching operator
  - [ ] `GET /api/v1/wells?q=permian` returns wells matching full-text search
  - [ ] `GET /api/v1/wells?api_number=42-501-20130` normalizes and finds the well
  - [ ] `GET /api/v1/wells?page=2&page_size=2` returns correct page
  - [ ] `GET /api/v1/wells/{api_number}` returns well detail with documents
  - [ ] `GET /api/v1/wells/{api_number}` with dashes works (normalization)
  - [ ] `GET /api/v1/wells/99999999999` returns 404

- Test file: `backend/tests/api/test_documents.py`
- Test cases:
  - [ ] `GET /api/v1/documents` returns 200 with paginated response
  - [ ] `GET /api/v1/documents?state=TX&doc_type=production_report` filters correctly
  - [ ] `GET /api/v1/documents?min_confidence=0.9` returns only high-confidence docs
  - [ ] `GET /api/v1/documents?date_from=2025-01-01&date_to=2025-12-31` filters by date
  - [ ] `GET /api/v1/documents/{id}` returns detail with extracted_data list
  - [ ] `GET /api/v1/documents/{id}/file` returns FileResponse for existing file
  - [ ] `GET /api/v1/documents/{id}/file` returns 404 for missing file
  - [ ] `GET /api/v1/documents/nonexistent-uuid` returns 404

- Test file: `backend/tests/api/test_operators.py`
- Test cases:
  - [ ] `GET /api/v1/operators` returns paginated operator list
  - [ ] `GET /api/v1/operators?q=Devon` returns matching operators

- Test file: `backend/tests/api/test_states.py`
- Test cases:
  - [ ] `GET /api/v1/states` returns all seeded states with counts

### API/Script Testing

- Start backend: `uv run uvicorn og_scraper.api.app:create_app --factory --port 8000`
- Visit `http://localhost:8000/docs` to verify OpenAPI documentation shows all endpoints
- Test with curl: `curl http://localhost:8000/api/v1/wells` returns valid JSON
- Test with curl: `curl http://localhost:8000/api/v1/states` returns state list

### Build/Lint/Type Checks

- [ ] `uv run pytest backend/tests/api/` succeeds
- [ ] `uv run ruff check backend/src/og_scraper/api/` passes
- [ ] `uv run ruff format --check backend/src/og_scraper/api/` passes

## Skills to Read

- `fastapi-backend` - API patterns, Pydantic models, async SQLAlchemy session, pagination
- `postgresql-postgis-schema` - Database schema, full-text search, trigram search, query patterns

## Research Files to Read

- `.claude/orchestration-og-doc-scraper/research/backend-schema-implementation.md` - Section 3.1 (endpoint signatures), Section 3.2 (Pydantic models), Section 3.5 (file serving)

## Git

- Branch: `phase-3/task-3-1-core-crud-endpoints`
- Commit message prefix: `Task 3.1:`
