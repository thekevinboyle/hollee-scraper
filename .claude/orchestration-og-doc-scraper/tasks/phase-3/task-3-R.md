# Task 3.R: Phase 3 Regression Testing

## Objective

Perform a comprehensive regression test of all 17 REST API endpoints implemented in Phase 3. Verify that every endpoint works correctly end-to-end with a real PostgreSQL+PostGIS database, that the Huey task queue integrates properly, that SSE streaming works, that search/filter/pagination operates correctly, and that data flows correctly through the full scrape-trigger-to-review-queue workflow. This task catches any integration issues between the four Phase 3 tasks.

## Context

Phase 3 produced four task deliverables:
- Task 3.1: Core CRUD endpoints (wells, documents, operators, states) -- 8 endpoints
- Task 3.2: Scrape job endpoints and Huey integration -- 4 endpoints including SSE
- Task 3.3: Review queue and data correction endpoints -- 3 endpoints
- Task 3.4: Map, stats, and export endpoints -- 6 endpoints (including per-state stats)

Total: 17+ endpoints that must work together. This regression test verifies:
1. Each endpoint individually (happy path + error cases)
2. Cross-endpoint workflows (create scrape -> check status -> review queue -> approve -> verify in stats)
3. Data consistency (changes in one endpoint reflected in others)
4. Infrastructure (Docker services communicate, database migrations applied, PostGIS functional)

## Dependencies

- Task 3.1 - Core CRUD endpoints must be complete
- Task 3.2 - Scrape job endpoints must be complete
- Task 3.3 - Review queue endpoints must be complete
- Task 3.4 - Map, stats, and export endpoints must be complete

## Blocked By

- All Phase 3 tasks (3.1, 3.2, 3.3, 3.4) must be complete

## Research Findings

- From `fastapi-backend` skill: Test with `httpx.AsyncClient`, `testcontainers` for real PostgreSQL, `huey.immediate = True` for synchronous task testing
- From `og-scraper-architecture` skill: All services should be testable via `docker compose up db backend worker`
- From `og-testing-strategies` skill: Regression tests exercise full request-response cycles, verify cross-service data consistency, and check error handling

## Implementation Plan

### Step 1: Set Up Regression Test Infrastructure

**File: `backend/tests/regression/conftest.py`**

Create comprehensive test fixtures that seed the database with realistic data:

```python
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

@pytest.fixture(scope="session")
def postgres_container():
    """Spin up a real PostgreSQL+PostGIS container for integration testing."""
    from testcontainers.postgres import PostgresContainer
    with PostgresContainer("postgis/postgis:16-3.4") as pg:
        yield pg

@pytest.fixture
async def seeded_db(db: AsyncSession):
    """
    Seed database with comprehensive test data:
    - 3 states (TX, OK, PA)
    - 3 operators
    - 10 wells (5 TX, 3 OK, 2 PA) with lat/long coordinates
    - 20 documents across various types and states
    - 15 extracted_data records
    - 3 review_queue items (pending)
    - 2 scrape_jobs (1 completed, 1 pending)
    """
    # States
    states = [
        State(code="TX", name="Texas", api_state_code="42", tier=1),
        State(code="OK", name="Oklahoma", api_state_code="37", tier=1),
        State(code="PA", name="Pennsylvania", api_state_code="39", tier=2),
    ]

    # Operators
    operators = [
        Operator(name="Devon Energy Corporation", normalized_name="devon energy corporation"),
        Operator(name="Continental Resources", normalized_name="continental resources"),
        Operator(name="Range Resources", normalized_name="range resources"),
    ]

    # Wells with known coordinates for map testing
    wells = [
        Well(api_number="42501201300300", state_code="TX", well_name="Wolfcamp 1H",
             latitude=31.5, longitude=-103.5, well_status="active", well_type="oil",
             county="Ector", basin="Permian", operator_id=operators[0].id),
        Well(api_number="42501201300301", state_code="TX", well_name="Spraberry 2H",
             latitude=31.7, longitude=-103.2, well_status="active", well_type="oil",
             county="Midland", basin="Permian", operator_id=operators[0].id),
        # ... more wells for TX, OK, PA
    ]

    # Documents with various types and confidence scores
    # Extracted data with production, permit, completion types
    # Review queue items for low-confidence documents
    # Scrape jobs with different statuses

    # Add all to session
    for obj in states + operators + wells:
        db.add(obj)
    await db.commit()

    return {
        "states": states,
        "operators": operators,
        "wells": wells,
        # ...
    }
```

### Step 2: Test All 17 Endpoints Individually

**File: `backend/tests/regression/test_all_endpoints.py`**

Systematically test every endpoint:

```python
# ============================================================
# WELLS (2 endpoints)
# ============================================================

@pytest.mark.asyncio
async def test_list_wells(client, seeded_db):
    """GET /api/v1/wells returns paginated well list."""
    response = await client.get("/api/v1/wells")
    assert response.status_code == 200
    data = response.json()
    assert "items" in data
    assert "total" in data
    assert "page" in data
    assert "page_size" in data
    assert "total_pages" in data
    assert data["total"] >= 10  # We seeded 10 wells
    assert len(data["items"]) <= data["page_size"]

@pytest.mark.asyncio
async def test_list_wells_with_filters(client, seeded_db):
    """GET /api/v1/wells with all filter combinations."""
    # By state
    r = await client.get("/api/v1/wells?state=TX")
    assert r.status_code == 200
    assert all(w["state_code"] == "TX" for w in r.json()["items"])

    # By operator name (fuzzy)
    r = await client.get("/api/v1/wells?operator=Devon")
    assert r.status_code == 200
    assert r.json()["total"] >= 1

    # By well status
    r = await client.get("/api/v1/wells?well_status=active")
    assert r.status_code == 200

    # By full-text search
    r = await client.get("/api/v1/wells?q=Wolfcamp")
    assert r.status_code == 200

    # Pagination
    r = await client.get("/api/v1/wells?page=1&page_size=2")
    assert r.status_code == 200
    assert len(r.json()["items"]) <= 2

@pytest.mark.asyncio
async def test_get_well_detail(client, seeded_db):
    """GET /api/v1/wells/{api_number} returns detail with documents."""
    r = await client.get("/api/v1/wells/42501201300300")
    assert r.status_code == 200
    data = r.json()
    assert data["api_number"] == "42501201300300"
    assert "documents" in data
    assert isinstance(data["documents"], list)

@pytest.mark.asyncio
async def test_get_well_detail_with_dashes(client, seeded_db):
    """GET /api/v1/wells/{api_number} accepts dashed format."""
    r = await client.get("/api/v1/wells/42-501-20130-03-00")
    assert r.status_code == 200

@pytest.mark.asyncio
async def test_get_well_not_found(client):
    """GET /api/v1/wells/{api_number} returns 404 for missing well."""
    r = await client.get("/api/v1/wells/99999999999999")
    assert r.status_code == 404

# ============================================================
# DOCUMENTS (3 endpoints)
# ============================================================

@pytest.mark.asyncio
async def test_list_documents(client, seeded_db):
    """GET /api/v1/documents returns paginated document list."""
    r = await client.get("/api/v1/documents")
    assert r.status_code == 200
    data = r.json()
    assert data["total"] >= 20

@pytest.mark.asyncio
async def test_list_documents_filters(client, seeded_db):
    """GET /api/v1/documents with state, type, confidence filters."""
    r = await client.get("/api/v1/documents?state=TX&doc_type=production_report")
    assert r.status_code == 200

    r = await client.get("/api/v1/documents?min_confidence=0.9")
    assert r.status_code == 200
    for doc in r.json()["items"]:
        assert doc.get("confidence_score", 0) >= 0.9 or doc.get("confidence_score") is None

@pytest.mark.asyncio
async def test_get_document_detail(client, seeded_db):
    """GET /api/v1/documents/{id} returns detail with extracted data."""
    # First get a document ID
    r = await client.get("/api/v1/documents?page_size=1")
    doc_id = r.json()["items"][0]["id"]

    r = await client.get(f"/api/v1/documents/{doc_id}")
    assert r.status_code == 200
    assert "extracted_data" in r.json()

@pytest.mark.asyncio
async def test_get_document_file_missing(client, seeded_db):
    """GET /api/v1/documents/{id}/file returns 404 for missing file."""
    r = await client.get("/api/v1/documents?page_size=1")
    doc_id = r.json()["items"][0]["id"]
    r = await client.get(f"/api/v1/documents/{doc_id}/file")
    # Expect 404 since test fixtures don't have actual files on disk
    assert r.status_code == 404

# ============================================================
# SCRAPE JOBS (4 endpoints)
# ============================================================

@pytest.mark.asyncio
async def test_create_scrape_job(client, seeded_db):
    """POST /api/v1/scrape creates job and returns 202."""
    r = await client.post("/api/v1/scrape", json={
        "state_code": "TX",
        "job_type": "full",
    })
    assert r.status_code == 202
    data = r.json()
    assert data["status"] == "pending"
    assert data["state_code"] == "TX"

@pytest.mark.asyncio
async def test_create_scrape_invalid_state(client, seeded_db):
    """POST /api/v1/scrape with invalid state returns 400."""
    r = await client.post("/api/v1/scrape", json={"state_code": "ZZ"})
    assert r.status_code == 400

@pytest.mark.asyncio
async def test_list_scrape_jobs(client, seeded_db):
    """GET /api/v1/scrape/jobs returns paginated list."""
    r = await client.get("/api/v1/scrape/jobs")
    assert r.status_code == 200
    assert "items" in r.json()

@pytest.mark.asyncio
async def test_get_scrape_job_detail(client, seeded_db):
    """GET /api/v1/scrape/jobs/{id} returns detailed status."""
    # Create a job first
    create_r = await client.post("/api/v1/scrape", json={"state_code": "PA"})
    job_id = create_r.json()["id"]

    r = await client.get(f"/api/v1/scrape/jobs/{job_id}")
    assert r.status_code == 200
    data = r.json()
    assert data["id"] == job_id
    assert "errors" in data
    assert "parameters" in data

@pytest.mark.asyncio
async def test_scrape_job_sse_endpoint(client, seeded_db):
    """GET /api/v1/scrape/jobs/{id}/events returns event-stream content type."""
    create_r = await client.post("/api/v1/scrape", json={"state_code": "OK"})
    job_id = create_r.json()["id"]

    # For testing, just verify the endpoint responds with correct content type
    # Full SSE testing requires async streaming client
    r = await client.get(f"/api/v1/scrape/jobs/{job_id}/events")
    assert r.headers.get("content-type", "").startswith("text/event-stream")

# ============================================================
# REVIEW QUEUE (3 endpoints)
# ============================================================

@pytest.mark.asyncio
async def test_list_review_queue(client, seeded_db):
    """GET /api/v1/review returns pending review items."""
    r = await client.get("/api/v1/review")
    assert r.status_code == 200
    data = r.json()
    assert data["total"] >= 1
    for item in data["items"]:
        assert item["status"] == "pending"

@pytest.mark.asyncio
async def test_get_review_detail(client, seeded_db):
    """GET /api/v1/review/{id} returns full detail."""
    r = await client.get("/api/v1/review?page_size=1")
    review_id = r.json()["items"][0]["id"]

    r = await client.get(f"/api/v1/review/{review_id}")
    assert r.status_code == 200
    data = r.json()
    assert "document" in data
    assert "extracted_data" in data

@pytest.mark.asyncio
async def test_approve_review_item(client, seeded_db):
    """PATCH /api/v1/review/{id} with approved status."""
    r = await client.get("/api/v1/review?page_size=1")
    review_id = r.json()["items"][0]["id"]

    r = await client.patch(f"/api/v1/review/{review_id}", json={
        "status": "approved",
        "reviewed_by": "Regression Test",
    })
    assert r.status_code == 200
    assert r.json()["status"] == "approved"

# ============================================================
# MAP (1 endpoint)
# ============================================================

@pytest.mark.asyncio
async def test_map_wells(client, seeded_db):
    """GET /api/v1/map/wells returns wells in bounding box."""
    r = await client.get("/api/v1/map/wells", params={
        "min_lat": 30.0, "max_lat": 35.0,
        "min_lng": -106.0, "max_lng": -100.0,
    })
    assert r.status_code == 200
    wells = r.json()
    assert isinstance(wells, list)
    # Should contain TX wells but not PA or ND wells
    for w in wells:
        assert 30.0 <= w["latitude"] <= 35.0
        assert -106.0 <= w["longitude"] <= -100.0

# ============================================================
# STATS (2 endpoints)
# ============================================================

@pytest.mark.asyncio
async def test_dashboard_stats(client, seeded_db):
    """GET /api/v1/stats returns correct aggregate stats."""
    r = await client.get("/api/v1/stats")
    assert r.status_code == 200
    data = r.json()
    assert data["total_wells"] >= 10
    assert data["total_documents"] >= 20
    assert "documents_by_state" in data
    assert "wells_by_status" in data
    assert "review_queue_pending" in data

@pytest.mark.asyncio
async def test_state_stats(client, seeded_db):
    """GET /api/v1/stats/state/TX returns TX-specific stats."""
    r = await client.get("/api/v1/stats/state/TX")
    assert r.status_code == 200
    assert r.json()["state_code"] == "TX"

# ============================================================
# EXPORT (2 endpoints)
# ============================================================

@pytest.mark.asyncio
async def test_export_wells_csv(client, seeded_db):
    """GET /api/v1/export/wells?format=csv streams valid CSV."""
    r = await client.get("/api/v1/export/wells?format=csv")
    assert r.status_code == 200
    assert r.headers["content-type"] == "text/csv"
    lines = r.text.strip().split("\n")
    assert len(lines) >= 2  # header + data

@pytest.mark.asyncio
async def test_export_wells_json(client, seeded_db):
    """GET /api/v1/export/wells?format=json streams valid JSON."""
    r = await client.get("/api/v1/export/wells?format=json")
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list)

@pytest.mark.asyncio
async def test_export_production(client, seeded_db):
    """GET /api/v1/export/production?format=csv streams production data."""
    r = await client.get("/api/v1/export/production?format=csv")
    assert r.status_code == 200
```

### Step 3: Cross-Endpoint Workflow Tests

**File: `backend/tests/regression/test_workflows.py`**

Test complete user workflows that span multiple endpoints:

```python
@pytest.mark.asyncio
async def test_full_scrape_workflow(client, seeded_db):
    """
    Full workflow: trigger scrape -> check status -> verify in stats.
    """
    # 1. Trigger scrape
    r = await client.post("/api/v1/scrape", json={
        "state_code": "TX",
        "job_type": "full",
    })
    assert r.status_code == 202
    job_id = r.json()["id"]

    # 2. Check job appears in list
    r = await client.get("/api/v1/scrape/jobs")
    job_ids = [j["id"] for j in r.json()["items"]]
    assert job_id in job_ids

    # 3. Check job detail
    r = await client.get(f"/api/v1/scrape/jobs/{job_id}")
    assert r.json()["state_code"] == "TX"

    # 4. Stats should show the recent scrape job
    r = await client.get("/api/v1/stats")
    recent_ids = [j["id"] for j in r.json()["recent_scrape_jobs"]]
    assert job_id in recent_ids

@pytest.mark.asyncio
async def test_review_correction_workflow(client, seeded_db):
    """
    Full workflow: list review items -> get detail -> correct -> verify changes.
    """
    # 1. List pending review items
    r = await client.get("/api/v1/review?status=pending")
    assert r.json()["total"] >= 1
    review_item = r.json()["items"][0]
    review_id = review_item["id"]

    # 2. Get detail to see extracted data
    r = await client.get(f"/api/v1/review/{review_id}")
    detail = r.json()
    assert detail["extracted_data"] is not None

    # 3. Correct a field
    r = await client.patch(f"/api/v1/review/{review_id}", json={
        "status": "corrected",
        "corrections": {
            "operator_name": {"old": "bad_value", "new": "Devon Energy"},
        },
        "reviewed_by": "Test User",
        "notes": "Fixed operator name",
    })
    assert r.status_code == 200
    assert r.json()["status"] == "corrected"

    # 4. Verify item no longer in pending queue
    r = await client.get("/api/v1/review?status=pending")
    pending_ids = [i["id"] for i in r.json()["items"]]
    assert review_id not in pending_ids

    # 5. Stats should show reduced pending count
    r = await client.get("/api/v1/stats")
    # (Count should be one less than before)

@pytest.mark.asyncio
async def test_well_document_navigation(client, seeded_db):
    """
    Workflow: search wells -> get detail -> browse documents -> get document detail.
    """
    # 1. Search wells
    r = await client.get("/api/v1/wells?state=TX")
    assert r.json()["total"] >= 1
    well = r.json()["items"][0]

    # 2. Get well detail
    r = await client.get(f"/api/v1/wells/{well['api_number']}")
    assert r.status_code == 200
    documents = r.json()["documents"]

    # 3. If documents exist, get document detail
    if documents:
        doc_id = documents[0]["id"]
        r = await client.get(f"/api/v1/documents/{doc_id}")
        assert r.status_code == 200
        assert "extracted_data" in r.json()

@pytest.mark.asyncio
async def test_map_then_well_detail(client, seeded_db):
    """
    Workflow: map viewport query -> click a well pin -> get well detail.
    """
    # 1. Get wells on map
    r = await client.get("/api/v1/map/wells", params={
        "min_lat": 30.0, "max_lat": 35.0,
        "min_lng": -106.0, "max_lng": -100.0,
    })
    wells = r.json()
    assert len(wells) >= 1

    # 2. Click a well pin -> navigate to detail
    api_number = wells[0]["api_number"]
    r = await client.get(f"/api/v1/wells/{api_number}")
    assert r.status_code == 200
    assert r.json()["api_number"] == api_number

@pytest.mark.asyncio
async def test_export_matches_list(client, seeded_db):
    """Verify export data is consistent with list endpoint data."""
    # Get well count for TX from API
    r = await client.get("/api/v1/wells?state=TX&page_size=200")
    api_count = r.json()["total"]

    # Get well count from CSV export
    r = await client.get("/api/v1/export/wells?format=csv&state=TX")
    csv_lines = r.text.strip().split("\n")
    csv_count = len(csv_lines) - 1  # Subtract header

    assert api_count == csv_count
```

### Step 4: Infrastructure Verification

**File: `backend/tests/regression/test_infrastructure.py`**

```python
@pytest.mark.asyncio
async def test_health_check(client):
    """Health endpoint still works after all Phase 3 changes."""
    r = await client.get("/health")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "ok"
    assert data["db"] == "connected"

@pytest.mark.asyncio
async def test_openapi_docs(client):
    """OpenAPI documentation includes all 17+ endpoints."""
    r = await client.get("/openapi.json")
    assert r.status_code == 200
    paths = r.json()["paths"]
    # Verify key endpoints are present
    expected_paths = [
        "/api/v1/wells",
        "/api/v1/documents",
        "/api/v1/scrape",
        "/api/v1/review",
        "/api/v1/map/wells",
        "/api/v1/stats",
        "/api/v1/export/wells",
    ]
    for path in expected_paths:
        assert any(path in p for p in paths), f"Missing endpoint: {path}"

@pytest.mark.asyncio
async def test_cors_headers(client):
    """CORS allows frontend origin."""
    r = await client.options("/api/v1/wells", headers={
        "Origin": "http://localhost:3000",
        "Access-Control-Request-Method": "GET",
    })
    # CORS should be configured to allow localhost:3000

@pytest.mark.asyncio
async def test_postgis_functional(client, seeded_db):
    """PostGIS spatial queries work correctly."""
    # This is implicitly tested by test_map_wells but verify explicitly
    r = await client.get("/api/v1/map/wells", params={
        "min_lat": -90, "max_lat": 90,
        "min_lng": -180, "max_lng": 180,
    })
    assert r.status_code == 200
    # Should return all wells with coordinates
```

### Step 5: Error Handling Verification

**File: `backend/tests/regression/test_error_handling.py`**

```python
@pytest.mark.asyncio
async def test_404_responses(client):
    """All detail endpoints return proper 404 for missing resources."""
    import uuid
    fake_id = str(uuid.uuid4())

    assert (await client.get(f"/api/v1/wells/99999999999999")).status_code == 404
    assert (await client.get(f"/api/v1/documents/{fake_id}")).status_code == 404
    assert (await client.get(f"/api/v1/documents/{fake_id}/file")).status_code == 404
    assert (await client.get(f"/api/v1/scrape/jobs/{fake_id}")).status_code == 404
    assert (await client.get(f"/api/v1/review/{fake_id}")).status_code == 404
    assert (await client.get("/api/v1/stats/state/ZZ")).status_code == 404

@pytest.mark.asyncio
async def test_validation_errors(client):
    """Invalid input returns proper 400/422 errors."""
    # Invalid page size
    r = await client.get("/api/v1/wells?page_size=999")
    assert r.status_code == 422

    # Invalid map bounds
    r = await client.get("/api/v1/map/wells", params={
        "min_lat": 50, "max_lat": 30,  # inverted
        "min_lng": -100, "max_lng": -90,
    })
    assert r.status_code == 400

    # Invalid scrape state
    r = await client.post("/api/v1/scrape", json={"state_code": "ZZ"})
    assert r.status_code == 400

    # Correct without corrections
    r = await client.get("/api/v1/review?page_size=1")
    if r.json()["total"] > 0:
        review_id = r.json()["items"][0]["id"]
        r = await client.patch(f"/api/v1/review/{review_id}", json={
            "status": "corrected",
            # Missing corrections dict
        })
        assert r.status_code == 400

@pytest.mark.asyncio
async def test_missing_required_params(client):
    """Endpoints with required params return 422 when missing."""
    r = await client.get("/api/v1/map/wells")  # Missing required min_lat etc.
    assert r.status_code == 422

    r = await client.post("/api/v1/scrape", json={})  # OK - state_code is optional
    assert r.status_code in (202, 400)  # 202 if valid, 400 if validation fails
```

## Files to Create

- `backend/tests/regression/__init__.py` - Regression test package
- `backend/tests/regression/conftest.py` - Shared fixtures with comprehensive seed data
- `backend/tests/regression/test_all_endpoints.py` - Individual endpoint tests for all 17+ endpoints
- `backend/tests/regression/test_workflows.py` - Cross-endpoint workflow tests
- `backend/tests/regression/test_infrastructure.py` - Health, CORS, OpenAPI, PostGIS verification
- `backend/tests/regression/test_error_handling.py` - 404, 400, 422 error response tests

## Files to Modify

None -- regression tests are additive.

## Contracts

### Provides (for downstream tasks)

- Confidence that all 17 API endpoints work correctly and are ready for frontend integration (Phase 5)
- Verified that the scrape-trigger-to-review-queue workflow completes end-to-end
- Verified PostGIS spatial queries work with test data

### Consumes (from upstream tasks)

- All endpoints from Tasks 3.1, 3.2, 3.3, 3.4
- Database models from Task 1.2
- FastAPI app from Task 1.4
- Pipeline routing logic from Task 2.4

## Acceptance Criteria

- [ ] All 17+ endpoints tested and returning correct responses
- [ ] Full scrape workflow: POST /scrape -> GET /scrape/jobs/{id} -> verify in GET /stats
- [ ] Full review workflow: GET /review -> PATCH /review/{id} approve/correct/reject -> verify status changes
- [ ] Well navigation: GET /wells -> GET /wells/{api_number} -> GET /documents/{id}
- [ ] Map workflow: GET /map/wells -> GET /wells/{api_number}
- [ ] Export consistency: export CSV count matches list endpoint total
- [ ] All 404 responses correct for missing resources
- [ ] All validation errors (400/422) correct for invalid input
- [ ] Health check returns 200 with db connected
- [ ] OpenAPI docs include all endpoints
- [ ] PostGIS bounding box queries return correct spatial results
- [ ] SSE endpoint returns text/event-stream content type
- [ ] All tests pass: `uv run pytest backend/tests/regression/`
- [ ] Docker: `docker compose up db backend worker` all services healthy

## Testing Protocol

### Unit/Integration Tests

- Test directory: `backend/tests/regression/`
- Run all: `uv run pytest backend/tests/regression/ -v`
- Test cases: See Steps 2-5 above (40+ individual test cases)

### API/Script Testing

After all automated tests pass, manually verify with the running Docker stack:

1. Start services: `docker compose up db backend worker`
2. Wait for healthy: `docker compose ps` shows all services healthy
3. Run manual smoke tests:
   ```bash
   # Health
   curl http://localhost:8000/health

   # Wells
   curl "http://localhost:8000/api/v1/wells?page_size=5"
   curl "http://localhost:8000/api/v1/wells?state=TX&q=permian"

   # Documents
   curl "http://localhost:8000/api/v1/documents?page_size=5"

   # Scrape
   curl -X POST http://localhost:8000/api/v1/scrape -H "Content-Type: application/json" -d '{"state_code": "TX"}'
   curl http://localhost:8000/api/v1/scrape/jobs

   # Review
   curl http://localhost:8000/api/v1/review

   # Map
   curl "http://localhost:8000/api/v1/map/wells?min_lat=30&max_lat=35&min_lng=-106&max_lng=-100"

   # Stats
   curl http://localhost:8000/api/v1/stats

   # Export
   curl -o wells.csv "http://localhost:8000/api/v1/export/wells?format=csv"

   # OpenAPI docs
   curl http://localhost:8000/docs  # (opens in browser)
   ```

### External Service Verification

- PostgreSQL: `docker compose exec db psql -U postgres -d ogdocs -c "SELECT count(*) FROM wells;"`
- PostGIS: `docker compose exec db psql -U postgres -d ogdocs -c "SELECT PostGIS_Version();"`
- Huey: Check `data/huey.db` exists and contains task records

### Build/Lint/Type Checks

- [ ] `uv run pytest backend/tests/` succeeds (all tests including regression)
- [ ] `uv run ruff check backend/` passes
- [ ] `uv run ruff format --check backend/` passes

## Skills to Read

- `fastapi-backend` - Testing patterns with httpx.AsyncClient, testcontainers
- `og-testing-strategies` - Regression testing methodology
- `postgresql-postgis-schema` - Verify spatial queries and indexes
- `docker-local-deployment` - Docker Compose service health checks

## Research Files to Read

- `.claude/orchestration-og-doc-scraper/research/testing-deployment-implementation.md` - Test strategy, Docker configuration

## Git

- Branch: `phase-3/task-3-R-regression`
- Commit message prefix: `Task 3.R:`
