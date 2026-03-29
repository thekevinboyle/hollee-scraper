# Task 7.1: Full Pipeline E2E Testing

## Objective

Test the complete flow from scrape trigger through data access for every state and document type. This task validates that all 10 state scrapers feed correctly through the seven-stage pipeline (discover, download, classify, extract, normalize, validate, store), that confidence scoring routes documents to the correct disposition (accept/review/reject), and that stored data is accurate and accessible via the API.

## Context

This is the first task in Phase 7 (Comprehensive E2E Testing), the final phase of the project. All previous phases are complete: the project foundation (Phase 1), document processing pipeline (Phase 2), backend API (Phase 3), first scrapers (Phase 4), frontend dashboard (Phase 5), and remaining scrapers (Phase 6). This task exercises the backend pipeline end-to-end without the frontend. Tasks 7.2-7.4 cover dashboard E2E, error handling, and performance respectively.

## Dependencies

- All Phase 1-6 tasks must be complete
- All 10 state scrapers implemented and passing VCR tests
- Full document pipeline operational (OCR, classify, extract, validate, store)
- All 17 API endpoints functional
- Docker Compose stack running with PostgreSQL+PostGIS

## Blocked By

- All Phase 1-6 tasks

## Research Findings

Key findings from research files relevant to this task:

- From `testing-deployment-implementation.md`: VCR.py cassettes per state provide recorded HTTP responses for deterministic testing without live network calls. Use `record_mode="none"` to guarantee no live HTTP in tests.
- From `og-data-models.md`: API numbers are 14-digit (XX-YYY-ZZZZZ-SS-EE) with state prefix validation. Production volumes have expected ranges (oil 0-50,000 bbl/mo, gas 0-500,000 MCF/mo).
- From `confidence-scoring` skill: Three-tier scoring formula is `0.3 * classification_conf + 0.5 * weighted_field_avg + 0.2 * ocr_conf`. Auto-accept >= 0.85, review 0.50-0.84, reject < 0.50.
- From `og-scraper-architecture` skill: File storage follows `data/{state}/{operator}/{doc_type}/{filename}` convention. Document status state machine tracks progression through pipeline stages.

## Implementation Plan

### Step 1: Set Up E2E Test Infrastructure

Create a comprehensive E2E test module at `backend/tests/e2e/` that orchestrates full pipeline runs against VCR cassettes and a real PostgreSQL database via testcontainers.

- Create `backend/tests/e2e/__init__.py`
- Create `backend/tests/e2e/conftest.py` with:
  - Session-scoped PostgreSQL+PostGIS testcontainer
  - Database session factory with Alembic migrations applied
  - VCR configuration with `record_mode="none"`
  - Fixture to seed the 10 states into the `states` table
  - Fixture providing an httpx.AsyncClient against the FastAPI app
  - Temporary data directory for file storage

```python
# backend/tests/e2e/conftest.py
import pytest
import pytest_asyncio
from testcontainers.postgres import PostgresContainer
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from httpx import AsyncClient, ASGITransport

@pytest.fixture(scope="session")
def postgres_container():
    with PostgresContainer(
        image="postgis/postgis:16-3.4",
        username="test",
        password="test",
        dbname="test_ogdocs",
    ) as postgres:
        yield postgres

@pytest.fixture(scope="session")
def database_url(postgres_container):
    sync_url = postgres_container.get_connection_url()
    return sync_url.replace("postgresql://", "postgresql+asyncpg://")

@pytest_asyncio.fixture(scope="session")
async def engine(database_url):
    engine = create_async_engine(database_url, echo=False)
    # Run Alembic migrations
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()

@pytest_asyncio.fixture
async def db_session(engine):
    async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session() as session:
        async with session.begin():
            yield session
        await session.rollback()

@pytest_asyncio.fixture
async def client(db_session):
    async def override_get_db():
        yield db_session
    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()

@pytest.fixture
def data_dir(tmp_path):
    """Temporary directory for document file storage during tests."""
    docs_dir = tmp_path / "data" / "documents"
    docs_dir.mkdir(parents=True)
    return docs_dir
```

### Step 2: Per-State Pipeline E2E Tests

Create `backend/tests/e2e/test_pipeline_per_state.py` that triggers a scrape for each of the 10 states (using VCR cassettes) and verifies the full pipeline.

For each state (TX, NM, ND, OK, CO, WY, LA, PA, CA, AK):
1. Trigger the scrape via `POST /api/scrape` with `{state: "<code>"}`
2. Wait for the Huey task to complete (use `immediate=True` mode for tests)
3. Verify the scrape job status is `completed`
4. Verify documents exist in the database for this state
5. Verify extracted data exists for at least some documents
6. Verify file storage structure is correct

```python
# backend/tests/e2e/test_pipeline_per_state.py
import pytest

ALL_STATES = ["TX", "NM", "ND", "OK", "CO", "WY", "LA", "PA", "CA", "AK"]

@pytest.mark.asyncio
@pytest.mark.parametrize("state_code", ALL_STATES)
@pytest.mark.vcr()
async def test_full_pipeline_for_state(client, db_session, state_code, data_dir):
    """Trigger scrape for a state and verify complete pipeline execution."""
    # 1. Trigger scrape
    response = await client.post("/api/scrape", json={"state": state_code})
    assert response.status_code == 202
    job_id = response.json()["job_id"]

    # 2. Wait for completion (Huey immediate mode)
    job_response = await client.get(f"/api/scrape/{job_id}")
    assert job_response.status_code == 200
    job_data = job_response.json()
    assert job_data["status"] == "completed", f"Job failed: {job_data.get('errors')}"

    # 3. Verify documents in database
    docs_response = await client.get("/api/documents", params={"state": state_code})
    assert docs_response.status_code == 200
    docs = docs_response.json()
    assert docs["total"] > 0, f"No documents found for state {state_code}"

    # 4. Verify wells exist
    wells_response = await client.get("/api/wells", params={"state": state_code})
    assert wells_response.status_code == 200
    wells = wells_response.json()
    assert wells["total"] > 0, f"No wells found for state {state_code}"

    # 5. Verify extracted data on at least one document
    doc_id = docs["items"][0]["id"]
    detail_response = await client.get(f"/api/documents/{doc_id}")
    assert detail_response.status_code == 200
    detail = detail_response.json()
    assert detail.get("extracted_data") is not None
```

### Step 3: Document Type Classification Verification

Create `backend/tests/e2e/test_classification_accuracy.py` that verifies all 7 document types are correctly classified using known test fixtures.

```python
# backend/tests/e2e/test_classification_accuracy.py
import pytest

KNOWN_DOCUMENTS = [
    ("tests/fixtures/documents/texas/production_report_2025.pdf", "production_report"),
    ("tests/fixtures/documents/texas/well_permit_42-001-12345.pdf", "well_permit"),
    ("tests/fixtures/documents/oklahoma/completion_report.pdf", "completion_report"),
    ("tests/fixtures/documents/colorado/spacing_order.pdf", "spacing_order"),
    ("tests/fixtures/documents/pennsylvania/plugging_report.pdf", "plugging_report"),
    ("tests/fixtures/documents/newmexico/inspection_record.pdf", "inspection_record"),
    ("tests/fixtures/documents/northdakota/incident_report.pdf", "incident_report"),
]

@pytest.mark.asyncio
@pytest.mark.parametrize("fixture_path,expected_type", KNOWN_DOCUMENTS)
async def test_document_type_classification(pipeline, fixture_path, expected_type):
    """Verify each document type is classified correctly."""
    result = await pipeline.process(fixture_path, state="TX")
    assert result.doc_type == expected_type, (
        f"Expected {expected_type}, got {result.doc_type} for {fixture_path}"
    )
```

### Step 4: Confidence Scoring Disposition Tests

Create `backend/tests/e2e/test_confidence_routing.py` that verifies documents are routed to the correct disposition based on confidence scoring.

```python
# backend/tests/e2e/test_confidence_routing.py
import pytest

@pytest.mark.asyncio
async def test_high_quality_text_pdf_auto_accepted(pipeline, db_session):
    """Clean text PDF should score >= 0.85 and be auto-accepted."""
    result = await pipeline.process(
        "tests/fixtures/documents/texas/clean_production_report.pdf", state="TX"
    )
    assert result.confidence.overall >= 0.85
    assert result.disposition == "auto_accepted"

    # Verify NOT in review queue
    from sqlalchemy import select
    from og_scraper.models.review_queue import ReviewQueue
    review_items = await db_session.execute(
        select(ReviewQueue).where(ReviewQueue.document_id == result.document_id)
    )
    assert review_items.scalars().first() is None

@pytest.mark.asyncio
async def test_medium_quality_scan_sent_to_review(pipeline, db_session):
    """Medium-quality scanned PDF should score 0.50-0.84 and route to review queue."""
    result = await pipeline.process(
        "tests/fixtures/ocr/edge_cases/medium_quality_scan.pdf", state="TX"
    )
    assert 0.50 <= result.confidence.overall < 0.85
    assert result.disposition == "review_queue"

    # Verify IN review queue
    from sqlalchemy import select
    from og_scraper.models.review_queue import ReviewQueue
    review_items = await db_session.execute(
        select(ReviewQueue).where(ReviewQueue.document_id == result.document_id)
    )
    assert review_items.scalars().first() is not None

@pytest.mark.asyncio
async def test_low_quality_document_rejected(pipeline, db_session):
    """Unreadable/garbage document should score < 0.50 and be rejected."""
    result = await pipeline.process(
        "tests/fixtures/ocr/edge_cases/low_quality_scan.pdf", state="TX"
    )
    assert result.confidence.overall < 0.50
    assert result.disposition == "rejected"

@pytest.mark.asyncio
async def test_critical_field_override_forces_review(pipeline, db_session):
    """A document with high overall confidence but garbled API number
    should still go to review queue due to critical field override rule."""
    result = await pipeline.process(
        "tests/fixtures/documents/texas/good_doc_bad_api_number.pdf", state="TX"
    )
    # Overall might be above 0.85 but API number field is below its threshold
    assert result.disposition == "review_queue"
    # Verify the reason references the API number field
    from sqlalchemy import select
    from og_scraper.models.review_queue import ReviewQueue
    review_item = await db_session.execute(
        select(ReviewQueue).where(ReviewQueue.document_id == result.document_id)
    )
    item = review_item.scalars().first()
    assert item is not None
    assert "api_number" in (item.reason or "").lower()
```

### Step 5: Extracted Data Accuracy Validation

Create `backend/tests/e2e/test_extraction_accuracy.py` that verifies extracted field values match known ground truth for test documents.

```python
# backend/tests/e2e/test_extraction_accuracy.py
import pytest
import json
from pathlib import Path

GROUND_TRUTH_DOCS = [
    (
        "tests/fixtures/ocr/known_good/texas_production_001.pdf",
        "tests/fixtures/ocr/known_good/texas_production_001.json",
        "TX",
    ),
]

@pytest.mark.asyncio
@pytest.mark.parametrize("pdf_path,truth_path,state", GROUND_TRUTH_DOCS)
async def test_extracted_data_matches_ground_truth(
    pipeline, pdf_path, truth_path, state
):
    """Extracted data from known-good documents should match ground truth."""
    result = await pipeline.process(pdf_path, state=state)
    expected = json.loads(Path(truth_path).read_text())

    for field_name, expected_value in expected["required_fields"].items():
        actual = result.extracted_data.get(field_name)
        assert actual is not None, f"Missing field: {field_name}"
        assert actual == expected_value, (
            f"Field {field_name}: expected {expected_value!r}, got {actual!r}"
        )

@pytest.mark.asyncio
async def test_api_number_extracted_correctly(pipeline):
    """API number extraction verified across multiple known documents."""
    test_cases = [
        ("tests/fixtures/documents/texas/permit_42-461-12345.pdf", "42461123450000"),
        ("tests/fixtures/documents/oklahoma/well_35-019-23456.pdf", "35019234560000"),
        ("tests/fixtures/documents/colorado/apd_05-123-06789.pdf", "05123067890000"),
    ]
    for pdf_path, expected_api in test_cases:
        result = await pipeline.process(pdf_path, state=pdf_path.split("/")[3][:2].upper())
        assert result.extracted_data.get("api_number") == expected_api

@pytest.mark.asyncio
async def test_production_volumes_within_expected_ranges(pipeline):
    """Production volumes should fall within realistic oil & gas ranges."""
    result = await pipeline.process(
        "tests/fixtures/documents/texas/production_report_2025.pdf", state="TX"
    )
    data = result.extracted_data
    if "oil_bbls" in data:
        oil = float(data["oil_bbls"])
        assert 0 <= oil <= 100_000, f"Oil volume {oil} bbls out of realistic range"
    if "gas_mcf" in data:
        gas = float(data["gas_mcf"])
        assert 0 <= gas <= 1_000_000, f"Gas volume {gas} MCF out of realistic range"
    if "water_bbls" in data:
        water = float(data["water_bbls"])
        assert 0 <= water <= 100_000, f"Water volume {water} bbls out of realistic range"
```

### Step 6: Review Queue API Integration Tests

Create `backend/tests/e2e/test_review_queue_e2e.py` that verifies the full review queue lifecycle.

```python
# backend/tests/e2e/test_review_queue_e2e.py
import pytest

@pytest.mark.asyncio
async def test_review_queue_populated_from_pipeline(client, pipeline):
    """Processing a medium-confidence doc should populate the review queue."""
    await pipeline.process(
        "tests/fixtures/ocr/edge_cases/medium_quality_scan.pdf", state="TX"
    )
    response = await client.get("/api/review")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] > 0
    assert all(item["confidence_score"] < 0.85 for item in data["items"])

@pytest.mark.asyncio
async def test_review_queue_contains_only_medium_confidence(client, db_session):
    """Review queue should NOT contain auto-accepted or rejected documents."""
    response = await client.get("/api/review")
    data = response.json()
    for item in data["items"]:
        assert 0.50 <= item["confidence_score"] < 0.85, (
            f"Review item has unexpected confidence: {item['confidence_score']}"
        )

@pytest.mark.asyncio
async def test_approve_review_item_removes_from_queue(client, seed_review_item):
    """Approving a review item should remove it from the queue."""
    item_id = seed_review_item["id"]
    response = await client.post(f"/api/review/{item_id}/approve")
    assert response.status_code == 200

    # Verify removed from queue
    queue_response = await client.get("/api/review")
    item_ids = [i["id"] for i in queue_response.json()["items"]]
    assert item_id not in item_ids

@pytest.mark.asyncio
async def test_correct_review_item_updates_data(client, seed_review_item):
    """Correcting a review item should update the extracted data and create audit trail."""
    item_id = seed_review_item["id"]
    corrections = {"operator_name": "CORRECTED OIL CO"}
    response = await client.post(
        f"/api/review/{item_id}/correct",
        json={"corrections": corrections},
    )
    assert response.status_code == 200

    # Verify data was updated
    doc_id = seed_review_item["document_id"]
    doc_response = await client.get(f"/api/documents/{doc_id}")
    doc_data = doc_response.json()
    assert doc_data["extracted_data"]["operator_name"] == "CORRECTED OIL CO"

@pytest.mark.asyncio
async def test_reject_review_item(client, seed_review_item):
    """Rejecting a review item should mark it rejected."""
    item_id = seed_review_item["id"]
    response = await client.post(f"/api/review/{item_id}/reject")
    assert response.status_code == 200
```

### Step 7: File Storage Verification

Create `backend/tests/e2e/test_file_storage.py` that verifies the file organization structure.

```python
# backend/tests/e2e/test_file_storage.py
import pytest
from pathlib import Path

@pytest.mark.asyncio
async def test_file_storage_structure(pipeline, data_dir):
    """Processed documents should be stored in data/{state}/{operator}/{doc_type}/."""
    result = await pipeline.process(
        "tests/fixtures/documents/texas/production_report_2025.pdf", state="TX"
    )
    file_path = Path(result.file_path)
    assert file_path.exists(), f"Stored file not found: {file_path}"

    # Verify path structure: data_dir/TX/{operator}/{doc_type}/{hash}.pdf
    relative = file_path.relative_to(data_dir)
    parts = relative.parts
    assert parts[0] == "TX", f"Expected state 'TX' in path, got {parts[0]}"
    assert len(parts) == 4, f"Expected 4-level path, got {len(parts)}: {relative}"

@pytest.mark.asyncio
async def test_deduplication_via_file_hash(pipeline):
    """Processing the same file twice should not create a duplicate."""
    result1 = await pipeline.process(
        "tests/fixtures/documents/texas/production_report_2025.pdf", state="TX"
    )
    result2 = await pipeline.process(
        "tests/fixtures/documents/texas/production_report_2025.pdf", state="TX"
    )
    assert result1.file_hash == result2.file_hash
    # Same document ID should be returned (deduplicated)
    assert result1.document_id == result2.document_id

@pytest.mark.asyncio
async def test_document_file_served_via_api(client, pipeline):
    """Original document files should be downloadable via the API."""
    result = await pipeline.process(
        "tests/fixtures/documents/texas/production_report_2025.pdf", state="TX"
    )
    response = await client.get(f"/api/documents/{result.document_id}/file")
    assert response.status_code == 200
    assert response.headers["content-type"] in [
        "application/pdf",
        "application/octet-stream",
    ]
    assert len(response.content) > 0
```

### Step 8: Cross-State Data Integrity Verification via API

Create `backend/tests/e2e/test_cross_state_integrity.py` with API-level tests using curl/httpx to validate data across all 10 states.

```python
# backend/tests/e2e/test_cross_state_integrity.py
import pytest

@pytest.mark.asyncio
async def test_all_states_have_data_after_full_scrape(client):
    """After scraping all states, each state should have wells and documents."""
    states_response = await client.get("/api/states")
    states = states_response.json()
    assert len(states) == 10

    for state in states:
        code = state["code"]
        wells_resp = await client.get("/api/wells", params={"state": code, "per_page": 1})
        assert wells_resp.json()["total"] > 0, f"State {code} has no wells"

        docs_resp = await client.get("/api/documents", params={"state": code, "per_page": 1})
        assert docs_resp.json()["total"] > 0, f"State {code} has no documents"

@pytest.mark.asyncio
async def test_search_returns_results_across_states(client):
    """Full-text search should find results across multiple states."""
    response = await client.get("/api/wells/search", params={"q": "production"})
    assert response.status_code == 200
    data = response.json()
    if data["total"] > 0:
        states_found = set(item["state"] for item in data["items"])
        assert len(states_found) >= 1  # At least one state has matching results

@pytest.mark.asyncio
async def test_map_endpoint_returns_wells_in_viewport(client):
    """Map endpoint should return wells within a bounding box."""
    # Bounding box covering Permian Basin area
    response = await client.get("/api/map/wells", params={
        "min_lat": 31.0,
        "max_lat": 33.0,
        "min_lng": -104.0,
        "max_lng": -101.0,
        "limit": 1000,
    })
    assert response.status_code == 200
    wells = response.json()
    for well in wells:
        assert 31.0 <= well["latitude"] <= 33.0
        assert -104.0 <= well["longitude"] <= -101.0
```

## Files to Create

- `backend/tests/e2e/__init__.py` - Package init
- `backend/tests/e2e/conftest.py` - E2E test infrastructure (testcontainers, fixtures, VCR config)
- `backend/tests/e2e/test_pipeline_per_state.py` - Per-state full pipeline tests
- `backend/tests/e2e/test_classification_accuracy.py` - Document type classification verification
- `backend/tests/e2e/test_confidence_routing.py` - Confidence scoring disposition tests
- `backend/tests/e2e/test_extraction_accuracy.py` - Extracted data accuracy validation
- `backend/tests/e2e/test_review_queue_e2e.py` - Review queue lifecycle tests
- `backend/tests/e2e/test_file_storage.py` - File storage structure verification
- `backend/tests/e2e/test_cross_state_integrity.py` - Cross-state data integrity checks

## Files to Modify

- `backend/tests/conftest.py` - Add shared E2E fixtures if needed
- `justfile` - Add `test-e2e-pipeline` command

## Contracts

### Provides (for downstream tasks)

- Validated pipeline: Confirmation that all 10 states produce correct data through the full pipeline
- Test fixtures: Known-good documents with ground truth JSON for extraction accuracy
- E2E test infrastructure: Reusable conftest with testcontainers + VCR for other E2E tests

### Consumes (from upstream tasks)

- From Task 1.2: Database schema (all 8 tables, Alembic migrations)
- From Task 1.3: Base scraper framework (BaseOGSpider, state registry)
- From Task 2.1-2.4: Document processing pipeline (OCR, classify, extract, validate)
- From Task 3.1-3.4: All 17 API endpoints
- From Tasks 4.1-4.3, 6.1-6.3: All 10 state scrapers with VCR cassettes
- From `confidence-scoring` skill: Threshold values (0.85 auto-accept, 0.50-0.84 review, <0.50 reject)

## Acceptance Criteria

- [ ] Trigger scrape for each of 10 states, verify documents appear in database
- [ ] All 7 document types classified correctly from known test fixtures
- [ ] Extracted data matches ground truth for known-good documents
- [ ] High-confidence text PDFs auto-accepted (>= 0.85)
- [ ] Medium-confidence scans routed to review queue (0.50-0.84)
- [ ] Low-confidence/garbage documents rejected (< 0.50)
- [ ] Critical field override rule works (bad API number forces review)
- [ ] Review queue contains only medium-confidence documents
- [ ] File storage follows `data/{state}/{operator}/{doc_type}/` structure
- [ ] SHA-256 deduplication prevents duplicate file storage
- [ ] Document files downloadable via API
- [ ] Map endpoint returns wells within bounding box
- [ ] All tests pass: `uv run pytest backend/tests/e2e/ -v`

## Testing Protocol

### Unit/Integration Tests

- Test file: `backend/tests/e2e/test_pipeline_per_state.py`
- Test cases:
  - [ ] Each of 10 states completes scrape with VCR cassettes
  - [ ] Each state produces at least 1 well and 1 document in the database

- Test file: `backend/tests/e2e/test_classification_accuracy.py`
- Test cases:
  - [ ] production_report classified as production_report
  - [ ] well_permit classified as well_permit
  - [ ] completion_report classified as completion_report
  - [ ] spacing_order classified as spacing_order
  - [ ] plugging_report classified as plugging_report
  - [ ] inspection_record classified as inspection_record
  - [ ] incident_report classified as incident_report

- Test file: `backend/tests/e2e/test_confidence_routing.py`
- Test cases:
  - [ ] Clean text PDF scores >= 0.85 and is auto-accepted
  - [ ] Medium scan scores 0.50-0.84 and routes to review
  - [ ] Garbage document scores < 0.50 and is rejected
  - [ ] Critical field override sends high-overall-confidence doc to review

- Test file: `backend/tests/e2e/test_extraction_accuracy.py`
- Test cases:
  - [ ] API numbers extracted correctly from 3+ states
  - [ ] Production volumes within realistic ranges
  - [ ] Ground truth fields match expected values

### API/Script Testing

Run the full E2E test suite:
```bash
# Run all E2E pipeline tests
uv run pytest backend/tests/e2e/ -v --timeout=300

# Run per-state pipeline tests only
uv run pytest backend/tests/e2e/test_pipeline_per_state.py -v

# Run confidence routing tests only
uv run pytest backend/tests/e2e/test_confidence_routing.py -v
```

Verify via curl against a running Docker stack:
```bash
# Trigger a scrape
curl -X POST http://localhost:8000/api/scrape \
  -H "Content-Type: application/json" \
  -d '{"state": "TX"}'

# Check job status
curl http://localhost:8000/api/scrape/{job_id}

# Verify wells exist
curl "http://localhost:8000/api/wells?state=TX&per_page=5"

# Verify documents exist
curl "http://localhost:8000/api/documents?state=TX&per_page=5"

# Verify review queue
curl http://localhost:8000/api/review

# Check a document's extracted data
curl http://localhost:8000/api/documents/{doc_id}

# Download a document file
curl -O http://localhost:8000/api/documents/{doc_id}/file

# Map viewport query
curl "http://localhost:8000/api/map/wells?min_lat=31&max_lat=33&min_lng=-104&max_lng=-101"

# Stats endpoint
curl http://localhost:8000/api/stats
```

### Build/Lint/Type Checks

- [ ] `uv run ruff check backend/tests/e2e/` passes
- [ ] `uv run ruff format --check backend/tests/e2e/` passes
- [ ] `uv run pytest backend/tests/e2e/ -v --timeout=300` all pass

## Skills to Read

- `og-testing-strategies` - Testing infrastructure patterns (VCR, testcontainers, fixtures)
- `og-scraper-architecture` - Project structure, pipeline stages, file organization
- `confidence-scoring` - Three-tier scoring formula, thresholds, critical field override
- `document-processing-pipeline` - Pipeline stage details, document status state machine
- `state-regulatory-sites` - Per-state scraper details for understanding expected data

## Research Files to Read

- `.claude/orchestration-og-doc-scraper/research/testing-deployment-implementation.md` - Full testing code examples, Docker Compose config
- `.claude/orchestration-og-doc-scraper/research/document-pipeline-implementation.md` - Pipeline stage implementation details
- `.claude/orchestration-og-doc-scraper/research/og-data-models.md` - API number formats, production volume ranges, validation rules

## Git

- Branch: `task-7-1/full-pipeline-e2e`
- Commit message prefix: `Task 7.1:`
