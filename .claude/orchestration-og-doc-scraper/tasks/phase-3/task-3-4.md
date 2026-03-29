# Task 3.4: Map, Stats & Export Endpoints

## Objective

Implement three endpoint groups: (1) map viewport endpoint returning wells within a geographic bounding box via PostGIS spatial queries, (2) dashboard statistics endpoint aggregating counts and breakdowns, and (3) streaming export endpoints for wells and production data in CSV and JSON formats. These are the final API endpoints, completing the full set of 17 REST endpoints.

## Context

This task creates the endpoints that power the map (Phase 5, Task 5.3), the dashboard overview (Task 5.1), and the export functionality. The map endpoint is performance-critical -- it is called on every pan/zoom of the interactive Leaflet map and must return results within ~50ms for up to 1000 wells. The export endpoints use streaming responses to handle potentially large datasets (hundreds of thousands of wells) without loading everything into memory.

DISCOVERY D13 requires well-level pins on the map. DISCOVERY D12 requires search/browse plus an interactive map. The stats endpoint provides the overview numbers for the dashboard home page.

## Dependencies

- Task 3.1 - Core API structure (Pydantic schemas, pagination, router registration, query builder patterns)
- Task 1.2 - Database models with PostGIS geometry column, spatial indexes, and full schema

## Blocked By

- Task 3.1 (base API patterns must exist)

## Research Findings

Key findings from research files relevant to this task:

- From `backend-schema-implementation.md` Section 2.2: PostGIS bounding box query using `&&` operator with `ST_MakeEnvelope` and GiST index returns <10ms for ~500K wells
- From `backend-schema-implementation.md` Section 3.1: Map endpoint signature: `GET /map/wells?min_lat=&max_lat=&min_lng=&max_lng=&well_status=&well_type=&limit=1000`
- From `backend-schema-implementation.md` Section 3.6: Streaming export using `StreamingResponse` with async generators for CSV/JSON
- From `postgresql-postgis-schema` skill: `wells.location` GEOMETRY(Point, 4326) with GiST index `idx_wells_location_gist`, the `&&` operator for bounding box checks
- From `postgresql-postgis-schema` skill: `ST_MakePoint` takes longitude first, latitude second
- From `fastapi-backend` skill: Use `StreamingResponse` with async generators for large exports; pagination max 200 for normal endpoints but map uses `limit` param up to 5000
- From `og-scraper-architecture` skill: Stats endpoint returns total_wells, total_documents, total_extracted, documents_by_state, documents_by_type, wells_by_status, review_queue_pending, avg_confidence, recent_scrape_jobs

## Implementation Plan

### Step 1: Create Map Pydantic Schemas

**File: `backend/src/og_scraper/api/schemas/map.py`**

```python
from typing import Optional
from uuid import UUID
from pydantic import BaseModel, ConfigDict
from .enums import WellStatus

class WellMapPoint(BaseModel):
    """Minimal well data for map pin rendering. Keep payload small."""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    api_number: str
    well_name: Optional[str] = None
    operator_name: Optional[str] = None
    latitude: float
    longitude: float
    well_status: Optional[WellStatus] = None
    well_type: Optional[str] = None

class MapBoundsParams(BaseModel):
    """Query parameters for the map viewport request."""
    min_lat: float  # south boundary
    max_lat: float  # north boundary
    min_lng: float  # west boundary
    max_lng: float  # east boundary
    well_status: Optional[str] = None
    well_type: Optional[str] = None
    limit: int = 1000  # max wells to return (prevent overwhelming the frontend)
```

### Step 2: Create Stats Pydantic Schemas

**File: `backend/src/og_scraper/api/schemas/stats.py`**

```python
from typing import Optional
from pydantic import BaseModel

class DashboardStats(BaseModel):
    total_wells: int
    total_documents: int
    total_extracted: int
    documents_by_state: dict[str, int]     # {"TX": 1500, "NM": 800, ...}
    documents_by_type: dict[str, int]      # {"production_report": 3000, "well_permit": 1200, ...}
    wells_by_status: dict[str, int]        # {"active": 5000, "plugged": 2000, ...}
    wells_by_state: dict[str, int]         # {"TX": 3000, "NM": 1500, ...}
    review_queue_pending: int
    avg_confidence: Optional[float]        # average document confidence score
    recent_scrape_jobs: list[dict]         # last 5 scrape jobs (simplified)

class StateStats(BaseModel):
    state_code: str
    state_name: str
    total_wells: int
    total_documents: int
    documents_by_type: dict[str, int]
    wells_by_status: dict[str, int]
    avg_confidence: Optional[float]
    last_scraped_at: Optional[str]
    review_queue_pending: int
```

### Step 3: Create Export Pydantic Schemas

**File: `backend/src/og_scraper/api/schemas/export.py`**

```python
from enum import Enum
from pydantic import BaseModel

class ExportFormat(str, Enum):
    CSV = "csv"
    JSON = "json"
```

### Step 4: Implement Map Router

**File: `backend/src/og_scraper/api/routes/map.py`**

One endpoint:

**`GET /api/v1/map/wells`** -- Wells within a bounding box

This is the primary map query, called on every pan/zoom. Uses PostGIS bounding box operator `&&` with GiST index for maximum performance.

```python
from fastapi import APIRouter, Query, Depends
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from geoalchemy2.functions import ST_MakeEnvelope

from og_scraper.api.deps import get_db
from og_scraper.models.well import Well
from og_scraper.models.operator import Operator
from og_scraper.api.schemas.map import WellMapPoint

router = APIRouter()

@router.get("/wells", response_model=list[WellMapPoint])
async def get_map_wells(
    min_lat: float = Query(..., description="South boundary latitude"),
    max_lat: float = Query(..., description="North boundary latitude"),
    min_lng: float = Query(..., description="West boundary longitude"),
    max_lng: float = Query(..., description="East boundary longitude"),
    well_status: str | None = Query(None, description="Filter by well status"),
    well_type: str | None = Query(None, description="Filter by well type"),
    limit: int = Query(default=1000, ge=1, le=5000, description="Max wells to return"),
    db: AsyncSession = Depends(get_db),
):
    """
    Return wells within the given map viewport bounding box.

    Uses PostGIS spatial index (GiST) with the && operator for
    sub-10ms query performance on large datasets.

    IMPORTANT: ST_MakeEnvelope takes (min_lng, min_lat, max_lng, max_lat, srid)
    -- longitude first, latitude second.
    """
    # Validate bounds
    if min_lat >= max_lat:
        raise HTTPException(status_code=400, detail="min_lat must be less than max_lat")
    if min_lng >= max_lng:
        raise HTTPException(status_code=400, detail="min_lng must be less than max_lng")

    # Build the bounding box envelope
    envelope = func.ST_MakeEnvelope(min_lng, min_lat, max_lng, max_lat, 4326)

    query = (
        select(
            Well.id,
            Well.api_number,
            Well.well_name,
            Operator.name.label("operator_name"),
            Well.latitude,
            Well.longitude,
            Well.well_status,
            Well.well_type,
        )
        .outerjoin(Operator, Well.operator_id == Operator.id)
        .where(Well.location.op("&&")(envelope))  # Bounding box check using GiST index
        .where(Well.latitude.is_not(None))
        .where(Well.longitude.is_not(None))
    )

    if well_status:
        query = query.where(Well.well_status == well_status)
    if well_type:
        query = query.where(Well.well_type == well_type)

    query = query.order_by(Well.api_number).limit(limit)

    result = await db.execute(query)
    rows = result.all()

    return [
        WellMapPoint(
            id=row.id,
            api_number=row.api_number,
            well_name=row.well_name,
            operator_name=row.operator_name,
            latitude=row.latitude,
            longitude=row.longitude,
            well_status=row.well_status,
            well_type=row.well_type,
        )
        for row in rows
    ]
```

Key implementation notes:
- The `&&` operator is critical -- it uses the GiST spatial index for a bounding-box-only check (no full geometry computation)
- `ST_MakeEnvelope` takes `(min_lng, min_lat, max_lng, max_lat, srid)` -- longitude first!
- The `limit` parameter caps results to prevent overloading the frontend; the frontend should use Supercluster for clustering at low zoom levels
- Filter out wells with null latitude/longitude (they cannot be plotted)
- Return `list[WellMapPoint]` not `PaginatedResponse` (no pagination for map data, just a limit)

### Step 5: Implement Stats Router

**File: `backend/src/og_scraper/api/routes/stats.py`**

Two endpoints:

**`GET /api/v1/stats`** -- Dashboard overview statistics

```python
@router.get("/", response_model=DashboardStats)
async def get_dashboard_stats(db: AsyncSession = Depends(get_db)):
    """Aggregate dashboard statistics. Runs multiple count queries."""

    # Total counts
    total_wells = (await db.execute(select(func.count(Well.id)))).scalar_one()
    total_documents = (await db.execute(select(func.count(Document.id)))).scalar_one()
    total_extracted = (await db.execute(select(func.count(ExtractedData.id)))).scalar_one()

    # Documents by state
    docs_by_state_result = await db.execute(
        select(Document.state_code, func.count(Document.id))
        .group_by(Document.state_code)
    )
    documents_by_state = {row[0]: row[1] for row in docs_by_state_result.all()}

    # Documents by type
    docs_by_type_result = await db.execute(
        select(Document.doc_type, func.count(Document.id))
        .group_by(Document.doc_type)
    )
    documents_by_type = {row[0]: row[1] for row in docs_by_type_result.all()}

    # Wells by status
    wells_by_status_result = await db.execute(
        select(Well.well_status, func.count(Well.id))
        .group_by(Well.well_status)
    )
    wells_by_status = {str(row[0]): row[1] for row in wells_by_status_result.all()}

    # Wells by state
    wells_by_state_result = await db.execute(
        select(Well.state_code, func.count(Well.id))
        .group_by(Well.state_code)
    )
    wells_by_state = {row[0]: row[1] for row in wells_by_state_result.all()}

    # Review queue pending count
    review_pending = (await db.execute(
        select(func.count(ReviewQueue.id)).where(ReviewQueue.status == "pending")
    )).scalar_one()

    # Average document confidence
    avg_conf = (await db.execute(
        select(func.avg(Document.confidence_score))
        .where(Document.confidence_score.is_not(None))
    )).scalar_one()

    # Recent scrape jobs (last 5)
    recent_jobs_result = await db.execute(
        select(ScrapeJob)
        .order_by(ScrapeJob.created_at.desc())
        .limit(5)
    )
    recent_jobs = [
        {
            "id": str(j.id),
            "state_code": j.state_code,
            "status": j.status,
            "job_type": j.job_type,
            "documents_found": j.documents_found or 0,
            "documents_processed": j.documents_processed or 0,
            "created_at": j.created_at.isoformat() if j.created_at else None,
        }
        for j in recent_jobs_result.scalars().all()
    ]

    return DashboardStats(
        total_wells=total_wells,
        total_documents=total_documents,
        total_extracted=total_extracted,
        documents_by_state=documents_by_state,
        documents_by_type=documents_by_type,
        wells_by_status=wells_by_status,
        wells_by_state=wells_by_state,
        review_queue_pending=review_pending,
        avg_confidence=round(float(avg_conf), 4) if avg_conf else None,
        recent_scrape_jobs=recent_jobs,
    )
```

**`GET /api/v1/stats/state/{state_code}`** -- Per-state statistics

```python
@router.get("/state/{state_code}", response_model=StateStats)
async def get_state_stats(state_code: str, db: AsyncSession = Depends(get_db)):
    state_code = state_code.upper()
    state = await db.get(State, state_code)
    if not state:
        raise HTTPException(status_code=404, detail=f"State not found: {state_code}")

    # Similar aggregation queries but filtered to specific state
    total_wells = (await db.execute(
        select(func.count(Well.id)).where(Well.state_code == state_code)
    )).scalar_one()

    total_documents = (await db.execute(
        select(func.count(Document.id)).where(Document.state_code == state_code)
    )).scalar_one()

    # ... documents_by_type, wells_by_status for this state
    # ... avg_confidence for this state
    # ... review_queue_pending for this state

    return StateStats(
        state_code=state_code,
        state_name=state.name,
        total_wells=total_wells,
        total_documents=total_documents,
        documents_by_type=docs_by_type,
        wells_by_status=wells_status,
        avg_confidence=avg_conf,
        last_scraped_at=state.last_scraped_at.isoformat() if state.last_scraped_at else None,
        review_queue_pending=review_pending,
    )
```

### Step 6: Implement Export Router

**File: `backend/src/og_scraper/api/routes/export.py`**

Two endpoints using `StreamingResponse` for memory-efficient large dataset exports:

**`GET /api/v1/export/wells`** -- Export wells data

```python
@router.get("/wells")
async def export_wells(
    format: ExportFormat = ExportFormat.CSV,
    state: str | None = None,
    county: str | None = None,
    well_status: str | None = None,
    well_type: str | None = None,
    operator: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    """Export wells data as CSV or JSON. Uses streaming for large datasets."""

    # Build query with filters
    query = (
        select(
            Well.api_number,
            Well.well_name,
            Well.well_number,
            Operator.name.label("operator_name"),
            Well.state_code,
            Well.county,
            Well.basin,
            Well.field_name,
            Well.lease_name,
            Well.latitude,
            Well.longitude,
            Well.well_status,
            Well.well_type,
            Well.spud_date,
            Well.completion_date,
            Well.total_depth,
        )
        .outerjoin(Operator, Well.operator_id == Operator.id)
        .order_by(Well.api_number)
    )

    if state:
        query = query.where(Well.state_code == state.upper())
    if county:
        query = query.where(Well.county.ilike(f"%{county}%"))
    if well_status:
        query = query.where(Well.well_status == well_status)
    if well_type:
        query = query.where(Well.well_type == well_type)
    if operator:
        query = query.where(Operator.name.ilike(f"%{operator}%"))

    if format == ExportFormat.CSV:
        async def csv_generator():
            import csv
            import io
            output = io.StringIO()
            writer = csv.writer(output)

            # Header row
            headers = [
                "api_number", "well_name", "well_number", "operator",
                "state", "county", "basin", "field_name", "lease_name",
                "latitude", "longitude", "well_status", "well_type",
                "spud_date", "completion_date", "total_depth",
            ]
            writer.writerow(headers)
            yield output.getvalue()
            output.seek(0)
            output.truncate(0)

            # Stream data rows
            result = await db.stream(query)
            async for row in result:
                writer.writerow([
                    row.api_number, row.well_name, row.well_number,
                    row.operator_name, row.state_code, row.county,
                    row.basin, row.field_name, row.lease_name,
                    row.latitude, row.longitude,
                    str(row.well_status) if row.well_status else "",
                    row.well_type,
                    str(row.spud_date) if row.spud_date else "",
                    str(row.completion_date) if row.completion_date else "",
                    row.total_depth,
                ])
                yield output.getvalue()
                output.seek(0)
                output.truncate(0)

        return StreamingResponse(
            csv_generator(),
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=wells_export.csv"},
        )

    else:  # JSON
        async def json_generator():
            import json
            yield "["
            first = True
            result = await db.stream(query)
            async for row in result:
                if not first:
                    yield ","
                first = False
                yield json.dumps({
                    "api_number": row.api_number,
                    "well_name": row.well_name,
                    "well_number": row.well_number,
                    "operator": row.operator_name,
                    "state": row.state_code,
                    "county": row.county,
                    "basin": row.basin,
                    "field_name": row.field_name,
                    "lease_name": row.lease_name,
                    "latitude": row.latitude,
                    "longitude": row.longitude,
                    "well_status": str(row.well_status) if row.well_status else None,
                    "well_type": row.well_type,
                    "spud_date": str(row.spud_date) if row.spud_date else None,
                    "completion_date": str(row.completion_date) if row.completion_date else None,
                    "total_depth": row.total_depth,
                })
            yield "]"

        return StreamingResponse(
            json_generator(),
            media_type="application/json",
            headers={"Content-Disposition": "attachment; filename=wells_export.json"},
        )
```

**`GET /api/v1/export/production`** -- Export production data

```python
@router.get("/production")
async def export_production(
    format: ExportFormat = ExportFormat.CSV,
    state: str | None = None,
    well_id: UUID | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    db: AsyncSession = Depends(get_db),
):
    """Export production data from extracted_data table (data_type='production')."""

    query = (
        select(
            Well.api_number,
            Well.well_name,
            Operator.name.label("operator_name"),
            Well.state_code,
            Well.county,
            ExtractedData.data,
            ExtractedData.reporting_period_start,
            ExtractedData.reporting_period_end,
            ExtractedData.confidence_score,
        )
        .join(ExtractedData, ExtractedData.well_id == Well.id)
        .outerjoin(Operator, Well.operator_id == Operator.id)
        .where(ExtractedData.data_type == "production")
        .order_by(Well.api_number, ExtractedData.reporting_period_start)
    )

    if state:
        query = query.where(Well.state_code == state.upper())
    if well_id:
        query = query.where(ExtractedData.well_id == well_id)
    if date_from:
        query = query.where(ExtractedData.reporting_period_start >= date_from)
    if date_to:
        query = query.where(ExtractedData.reporting_period_end <= date_to)

    # CSV/JSON streaming pattern same as wells export
    # Production CSV columns: api_number, well_name, operator, state, county,
    #   reporting_period_start, reporting_period_end, oil_bbl, gas_mcf,
    #   water_bbl, days_produced, confidence_score
    # Extract oil_bbl, gas_mcf, water_bbl, days_produced from JSONB data column
```

Key patterns for streaming exports:
- Use `db.stream(query)` for memory-efficient row-by-row processing
- CSV uses `io.StringIO` buffer, writes one row at a time, yields and clears
- JSON streams as `[{...},{...}]` with comma logic for proper array formatting
- Set `Content-Disposition: attachment; filename=...` header for browser download
- Production data extracts specific fields from `extracted_data.data` JSONB

### Step 7: Register All Routers

Update `backend/src/og_scraper/api/routes/__init__.py`:

```python
from .map import router as map_router
from .stats import router as stats_router
from .export import router as export_router

api_router.include_router(map_router, prefix="/map", tags=["map"])
api_router.include_router(stats_router, prefix="/stats", tags=["statistics"])
api_router.include_router(export_router, prefix="/export", tags=["export"])
```

### Step 8: Write Tests

**File: `backend/tests/api/test_map.py`**

```python
@pytest.fixture
async def map_wells(db: AsyncSession):
    """Seed wells with known coordinates for map testing."""
    wells = [
        Well(api_number="42501201300300", state_code="TX", latitude=31.5, longitude=-103.5, well_status="active"),
        Well(api_number="42501201300301", state_code="TX", latitude=31.7, longitude=-103.2, well_status="active"),
        Well(api_number="35053000010000", state_code="ND", latitude=48.1, longitude=-103.8, well_status="active"),
    ]
    for w in wells:
        db.add(w)
    await db.commit()
    return wells

@pytest.mark.asyncio
async def test_map_wells_bounding_box(client, map_wells):
    # Bounding box around West Texas
    response = await client.get("/api/v1/map/wells", params={
        "min_lat": 31.0, "max_lat": 32.0,
        "min_lng": -104.0, "max_lng": -103.0,
    })
    assert response.status_code == 200
    wells = response.json()
    assert len(wells) == 2  # Only TX wells, not ND
    assert all(w["latitude"] >= 31.0 and w["latitude"] <= 32.0 for w in wells)

@pytest.mark.asyncio
async def test_map_wells_with_filter(client, map_wells):
    response = await client.get("/api/v1/map/wells", params={
        "min_lat": 30.0, "max_lat": 50.0,
        "min_lng": -110.0, "max_lng": -100.0,
        "well_status": "active",
    })
    assert response.status_code == 200

@pytest.mark.asyncio
async def test_map_wells_invalid_bounds(client):
    response = await client.get("/api/v1/map/wells", params={
        "min_lat": 40.0, "max_lat": 30.0,  # inverted
        "min_lng": -110.0, "max_lng": -100.0,
    })
    assert response.status_code == 400

@pytest.mark.asyncio
async def test_map_wells_empty_area(client, map_wells):
    # Bounding box in the ocean
    response = await client.get("/api/v1/map/wells", params={
        "min_lat": 0.0, "max_lat": 1.0,
        "min_lng": 0.0, "max_lng": 1.0,
    })
    assert response.status_code == 200
    assert len(response.json()) == 0
```

**File: `backend/tests/api/test_stats.py`**

```python
@pytest.mark.asyncio
async def test_dashboard_stats(client, seeded_db):
    response = await client.get("/api/v1/stats")
    assert response.status_code == 200
    data = response.json()
    assert "total_wells" in data
    assert "total_documents" in data
    assert "documents_by_state" in data
    assert "wells_by_status" in data
    assert "review_queue_pending" in data
    assert isinstance(data["documents_by_state"], dict)

@pytest.mark.asyncio
async def test_state_stats(client, seeded_db):
    response = await client.get("/api/v1/stats/state/TX")
    assert response.status_code == 200
    data = response.json()
    assert data["state_code"] == "TX"
    assert "total_wells" in data

@pytest.mark.asyncio
async def test_state_stats_not_found(client):
    response = await client.get("/api/v1/stats/state/ZZ")
    assert response.status_code == 404
```

**File: `backend/tests/api/test_export.py`**

```python
@pytest.mark.asyncio
async def test_export_wells_csv(client, seeded_db):
    response = await client.get("/api/v1/export/wells?format=csv")
    assert response.status_code == 200
    assert response.headers["content-type"] == "text/csv"
    assert "Content-Disposition" in response.headers
    # Parse CSV content
    lines = response.text.strip().split("\n")
    assert len(lines) >= 2  # header + at least 1 data row
    header = lines[0]
    assert "api_number" in header
    assert "well_name" in header

@pytest.mark.asyncio
async def test_export_wells_json(client, seeded_db):
    response = await client.get("/api/v1/export/wells?format=json")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) >= 1
    assert "api_number" in data[0]

@pytest.mark.asyncio
async def test_export_wells_with_filter(client, seeded_db):
    response = await client.get("/api/v1/export/wells?format=csv&state=TX")
    assert response.status_code == 200
    lines = response.text.strip().split("\n")
    # All data rows should be TX
    for line in lines[1:]:
        assert "TX" in line

@pytest.mark.asyncio
async def test_export_production_csv(client, seeded_db):
    response = await client.get("/api/v1/export/production?format=csv")
    assert response.status_code == 200
    assert "oil_bbl" in response.text or "api_number" in response.text
```

## Files to Create

- `backend/src/og_scraper/api/schemas/map.py` - WellMapPoint, MapBoundsParams
- `backend/src/og_scraper/api/schemas/stats.py` - DashboardStats, StateStats
- `backend/src/og_scraper/api/schemas/export.py` - ExportFormat enum
- `backend/src/og_scraper/api/routes/map.py` - GET /map/wells
- `backend/src/og_scraper/api/routes/stats.py` - GET /stats, GET /stats/state/{state_code}
- `backend/src/og_scraper/api/routes/export.py` - GET /export/wells, GET /export/production
- `backend/tests/api/test_map.py` - Map endpoint tests
- `backend/tests/api/test_stats.py` - Stats endpoint tests
- `backend/tests/api/test_export.py` - Export endpoint tests

## Files to Modify

- `backend/src/og_scraper/api/routes/__init__.py` - Register map, stats, and export routers
- `backend/src/og_scraper/api/schemas/__init__.py` - Export new schemas

## Contracts

### Provides (for downstream tasks)

- **Endpoint**: `GET /api/v1/map/wells` - Wells within bounding box
  - Request: Query params (min_lat, max_lat, min_lng, max_lng, well_status?, well_type?, limit=1000)
  - Response: `list[WellMapPoint]` (NOT paginated -- uses limit instead)
  - Error 400: Invalid bounds (min >= max)
- **Endpoint**: `GET /api/v1/stats` - Dashboard aggregate statistics
  - Response: `DashboardStats` with totals, breakdowns, and recent jobs
- **Endpoint**: `GET /api/v1/stats/state/{state_code}` - Per-state statistics
  - Response: `StateStats`
  - Error 404: Unknown state code
- **Endpoint**: `GET /api/v1/export/wells` - Export wells data
  - Request: Query params (format=csv|json, state?, county?, well_status?, well_type?, operator?)
  - Response: `StreamingResponse` with Content-Disposition attachment header
- **Endpoint**: `GET /api/v1/export/production` - Export production data
  - Request: Query params (format=csv|json, state?, well_id?, date_from?, date_to?)
  - Response: `StreamingResponse` with Content-Disposition attachment header
- **Schemas**: `WellMapPoint`, `DashboardStats`, `StateStats`, `ExportFormat`

### Consumes (from upstream tasks)

- From Task 3.1: Router registration pattern, Pydantic model conventions, query builder patterns, `paginate()`, `get_db()` dependency
- From Task 1.2: `Well` model with PostGIS `location` column and GiST index, `Document` model, `ExtractedData` model, `ReviewQueue` model, `ScrapeJob` model, `State` model, `Operator` model

## Acceptance Criteria

- [ ] `GET /api/v1/map/wells` returns wells within specified bounding box
- [ ] Map query uses PostGIS `&&` operator with GiST index (NOT ST_Contains which is slower)
- [ ] Map query returns <50ms for 1000 wells with spatial index
- [ ] Map query filters by well_status and well_type
- [ ] Map query respects the limit parameter (max 5000)
- [ ] Map query returns 400 for invalid bounds (min >= max)
- [ ] Map query returns empty list for bounding box with no wells
- [ ] `GET /api/v1/stats` returns correct total counts
- [ ] `GET /api/v1/stats` returns breakdowns by state, type, and status
- [ ] `GET /api/v1/stats` returns review_queue_pending count and avg_confidence
- [ ] `GET /api/v1/stats/state/{code}` returns state-specific stats
- [ ] `GET /api/v1/stats/state/ZZ` returns 404
- [ ] `GET /api/v1/export/wells?format=csv` streams valid CSV with headers
- [ ] `GET /api/v1/export/wells?format=json` streams valid JSON array
- [ ] Export endpoints respect filter parameters (state, county, etc.)
- [ ] `GET /api/v1/export/production` exports production data from JSONB
- [ ] Export uses `StreamingResponse` (not loading all data into memory)
- [ ] All tests pass
- [ ] Build succeeds

## Testing Protocol

### Unit/Integration Tests

- Test file: `backend/tests/api/test_map.py`
- Test cases:
  - [ ] Bounding box returns wells inside (not outside) the box
  - [ ] Filter by well_status narrows results
  - [ ] Limit parameter caps results
  - [ ] Invalid bounds (min >= max) returns 400
  - [ ] Empty bounding box returns empty list
  - [ ] Wells without coordinates are excluded

- Test file: `backend/tests/api/test_stats.py`
- Test cases:
  - [ ] Dashboard stats returns all expected fields
  - [ ] Counts match seeded test data
  - [ ] State stats returns correct state-specific data
  - [ ] Non-existent state returns 404

- Test file: `backend/tests/api/test_export.py`
- Test cases:
  - [ ] Wells CSV export has correct headers and data rows
  - [ ] Wells JSON export is a valid JSON array
  - [ ] State filter limits export to that state only
  - [ ] Production CSV includes JSONB-derived columns (oil_bbl, gas_mcf)
  - [ ] Production date range filter works correctly
  - [ ] Empty export returns headers-only CSV or empty JSON array

### API/Script Testing

- `curl "http://localhost:8000/api/v1/map/wells?min_lat=31&max_lat=33&min_lng=-104&max_lng=-101"` returns JSON array of wells
- `curl http://localhost:8000/api/v1/stats` returns dashboard overview
- `curl -o wells.csv "http://localhost:8000/api/v1/export/wells?format=csv&state=TX"` downloads CSV
- Open wells.csv in a spreadsheet to verify format

### Build/Lint/Type Checks

- [ ] `uv run pytest backend/tests/api/test_map.py backend/tests/api/test_stats.py backend/tests/api/test_export.py` succeeds
- [ ] `uv run ruff check backend/src/og_scraper/api/routes/map.py` passes
- [ ] `uv run ruff check backend/src/og_scraper/api/routes/stats.py` passes
- [ ] `uv run ruff check backend/src/og_scraper/api/routes/export.py` passes

## Skills to Read

- `fastapi-backend` - StreamingResponse, PostGIS bounding box query, Pydantic models
- `postgresql-postgis-schema` - GiST index, ST_MakeEnvelope, `&&` operator, distance queries, SRID 4326

## Research Files to Read

- `.claude/orchestration-og-doc-scraper/research/backend-schema-implementation.md` - Section 2.2 (bounding box query), Section 3.1 (map/stats/export endpoint signatures), Section 3.6 (streaming export implementation)

## Git

- Branch: `phase-3/task-3-4-map-stats-export`
- Commit message prefix: `Task 3.4:`
