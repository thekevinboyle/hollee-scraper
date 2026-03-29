# Task 4.R: Phase 4 Regression -- Full End-to-End Pipeline Validation

## Objective

Run comprehensive regression testing across all three Phase 4 scrapers (PA, CO, OK) to validate that the full end-to-end pipeline works: scrape -> download -> pipeline -> database -> API. This is not a feature task -- it is a verification task that ensures all Phase 4 work integrates correctly, data flows from state regulatory sites through the document processing pipeline into PostgreSQL, and the API can query and return the stored data.

## Context

This is the final task in Phase 4. Tasks 4.1 (PA), 4.2 (CO), and 4.3 (OK) each built a state scraper independently. This regression task verifies they all work together, the pipeline processes data from all three states correctly, the database contains properly structured data, and the API (from Phase 3) can serve queries across all three states. This is the critical validation point before moving to Phase 5 (Frontend Dashboard). Any failures here indicate pipeline integration issues that must be fixed before proceeding.

## Dependencies

- Task 4.1 - Pennsylvania scraper (`PennsylvaniaDEPSpider`) with VCR cassettes
- Task 4.2 - Colorado scraper (`ColoradoECMCSpider`) with VCR cassettes
- Task 4.3 - Oklahoma scraper (`OklahomaOCCSpider`) with VCR cassettes
- Phase 3 (all tasks) - API endpoints for wells, documents, search, states, review queue

## Blocked By

- 4.1, 4.2, 4.3, Phase 3 (all)

## Research Findings

Key findings from research files relevant to this task:

- From `per-state-scrapers-implementation.md`: PA uses CSV only, CO uses CSV + optional COGIS forms, OK uses CSV + XLSX. All three are `BulkDownloadSpider` or `MixedSpider` patterns -- no Playwright needed for primary data access.
- From `document-processing-pipeline.md`: Pipeline stages are discover -> download -> classify -> extract -> normalize -> validate -> store. Confidence thresholds: accept >= 0.85, review 0.50-0.84, reject < 0.50. CSV data from structured sources should score high confidence.
- From `state-regulatory-sites.md`: PA state code `37`, CO state code `05`, OK state code `35`. Each has distinct data formats and field naming conventions that must be normalized by the pipeline.
- From `scrapy-playwright-scraping.md`: VCR.py cassettes for all three states should enable fully offline test replay. Cassette directories: `backend/tests/scrapers/cassettes/pa/`, `co/`, `ok/`.

## Implementation Plan

### Step 1: Run All Scraper Unit Tests

Run the full scraper test suite to verify each spider's parsing logic passes independently.

```bash
uv run pytest backend/tests/scrapers/ -v --tb=short
```

**Expected results:**
- `test_pa_spider.py` -- all tests pass (CSV parsing, API normalization, VCR replay)
- `test_co_spider.py` -- all tests pass (CSV parsing, ZIP handling, dual domain, VCR replay)
- `test_ok_spider.py` -- all tests pass (CSV + XLSX parsing, header detection, VCR replay)

### Step 2: VCR-Based Scraper Integration Tests

Run all three spiders against recorded VCR cassettes to verify scraping works end-to-end without hitting live servers.

```python
# backend/tests/regression/test_phase4_regression.py

import vcr
import pytest
from og_scraper.scrapers.spiders.pa_spider import PennsylvaniaDEPSpider
from og_scraper.scrapers.spiders.co_spider import ColoradoECMCSpider
from og_scraper.scrapers.spiders.ok_spider import OklahomaOCCSpider


class TestPhase4ScraperRegression:
    """Run all 3 spiders against VCR cassettes."""

    @vcr.use_cassette('backend/tests/scrapers/cassettes/pa/greenport_well_inventory.yaml')
    def test_pa_spider_produces_items(self):
        """PA spider yields WellItems from VCR cassette."""
        spider = PennsylvaniaDEPSpider()
        # ... run parse method against recorded response
        # Assert items produced and have required fields

    @vcr.use_cassette('backend/tests/scrapers/cassettes/co/ecmc_well_spots.yaml')
    def test_co_spider_produces_items(self):
        """CO spider yields WellItems from VCR cassette."""
        spider = ColoradoECMCSpider()
        # Assert items produced with CO-specific fields

    @vcr.use_cassette('backend/tests/scrapers/cassettes/ok/occ_rbdms_wells.yaml')
    def test_ok_spider_produces_items(self):
        """OK spider yields WellItems from VCR cassette."""
        spider = OklahomaOCCSpider()
        # Assert items produced with OK-specific fields
```

### Step 3: Pipeline Integration Tests

Verify that items produced by each spider can be processed through the full document pipeline.

```python
class TestPhase4PipelineRegression:
    """Items from all 3 spiders flow through the full pipeline."""

    def test_pa_items_through_pipeline(self):
        """PA CSV items process through classify -> extract -> normalize -> validate -> store."""
        # Create a PA WellItem with realistic data
        # Run through DocumentPipeline.process()
        # Verify ProcessingResult has correct disposition
        # CSV structured data should score high confidence (>= 0.85)

    def test_co_items_through_pipeline(self):
        """CO CSV items process through the pipeline."""
        # Same as PA but with CO-specific fields

    def test_ok_csv_items_through_pipeline(self):
        """OK CSV items (RBDMS wells) process through the pipeline."""

    def test_ok_xlsx_items_through_pipeline(self):
        """OK XLSX items (completions) process through the pipeline."""

    def test_cross_state_normalization(self):
        """Items from PA, CO, OK all normalize to the same output format."""
        # Verify API numbers are all 14-digit format with dashes
        # Verify production volumes are in consistent units
        # Verify dates are in consistent format
```

### Step 4: Database Population Verification

After running spiders against cassettes and processing through the pipeline, verify data is correctly stored in PostgreSQL.

```python
class TestPhase4DatabaseRegression:
    """Verify data is correctly stored in PostgreSQL."""

    @pytest.fixture
    def populated_db(self):
        """Fixture: Run all 3 spiders and pipeline, populate test DB."""
        # Use testcontainers for PostgreSQL
        # Run migrations
        # Process spider output through pipeline into DB
        yield db_session

    def test_pa_wells_in_database(self, populated_db):
        """PA wells are stored in the wells table."""
        pa_wells = populated_db.query(Well).filter(Well.state_code == "PA").all()
        assert len(pa_wells) > 0
        for well in pa_wells:
            assert well.api_number.startswith("37-")
            assert well.state_code == "PA"
            assert well.operator_name is not None

    def test_co_wells_in_database(self, populated_db):
        """CO wells are stored in the wells table."""
        co_wells = populated_db.query(Well).filter(Well.state_code == "CO").all()
        assert len(co_wells) > 0
        for well in co_wells:
            assert well.api_number.startswith("05-")

    def test_ok_wells_in_database(self, populated_db):
        """OK wells are stored in the wells table."""
        ok_wells = populated_db.query(Well).filter(Well.state_code == "OK").all()
        assert len(ok_wells) > 0
        for well in ok_wells:
            assert well.api_number.startswith("35-")

    def test_documents_in_database(self, populated_db):
        """Documents from all 3 states are stored."""
        for state in ["PA", "CO", "OK"]:
            docs = populated_db.query(Document).filter(Document.state_code == state).all()
            assert len(docs) > 0

    def test_extracted_data_in_database(self, populated_db):
        """Extracted data (JSONB) is populated for processed documents."""
        extracted = populated_db.query(ExtractedData).all()
        assert len(extracted) > 0
        for ed in extracted:
            assert ed.data is not None  # JSONB column
            assert isinstance(ed.data, dict)

    def test_review_queue_populated(self, populated_db):
        """Documents below confidence threshold are in review queue."""
        reviews = populated_db.query(ReviewQueue).all()
        # Some documents may be in review if confidence < 0.85
        # At minimum, verify the table is queryable

    def test_postgis_geometry_populated(self, populated_db):
        """Wells with lat/long have PostGIS geometry column populated."""
        wells_with_coords = (
            populated_db.query(Well)
            .filter(Well.latitude.isnot(None), Well.longitude.isnot(None))
            .all()
        )
        for well in wells_with_coords:
            assert well.location is not None  # PostGIS geometry auto-populated by trigger

    def test_full_text_search_vector(self, populated_db):
        """Wells have search_vector populated for full-text search."""
        wells = populated_db.query(Well).limit(10).all()
        for well in wells:
            assert well.search_vector is not None
```

### Step 5: API Endpoint Verification

Verify the Phase 3 API endpoints return data from all three states.

```python
class TestPhase4APIRegression:
    """API endpoints return correct data for PA, CO, OK."""

    @pytest.fixture
    def client(self, populated_db):
        """Fixture: httpx AsyncClient for API testing."""
        from og_scraper.api.app import create_app
        app = create_app()
        yield httpx.AsyncClient(app=app, base_url="http://test")

    async def test_get_wells_by_state_pa(self, client):
        """GET /api/wells?state=PA returns PA wells."""
        resp = await client.get("/api/wells", params={"state": "PA"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] > 0
        assert all(w["state_code"] == "PA" for w in data["items"])

    async def test_get_wells_by_state_co(self, client):
        """GET /api/wells?state=CO returns CO wells."""
        resp = await client.get("/api/wells", params={"state": "CO"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] > 0
        assert all(w["state_code"] == "CO" for w in data["items"])

    async def test_get_wells_by_state_ok(self, client):
        """GET /api/wells?state=OK returns OK wells."""
        resp = await client.get("/api/wells", params={"state": "OK"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] > 0

    async def test_get_documents_by_state_and_type(self, client):
        """GET /api/documents?state=CO&type=PRODUCTION_REPORT returns CO production reports."""
        resp = await client.get("/api/documents", params={
            "state": "CO",
            "type": "PRODUCTION_REPORT",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] > 0
        for doc in data["items"]:
            assert doc["state_code"] == "CO"
            assert doc["doc_type"] == "PRODUCTION_REPORT"

    async def test_full_text_search(self, client):
        """GET /api/wells/search?q=<operator> returns matching wells."""
        # Use an operator name that appears in test cassette data
        resp = await client.get("/api/wells/search", params={"q": "Devon"})
        assert resp.status_code == 200
        data = resp.json()
        # May or may not have results depending on cassette data
        assert "items" in data

    async def test_get_states_summary(self, client):
        """GET /api/states returns all states with scrape status."""
        resp = await client.get("/api/states")
        assert resp.status_code == 200
        data = resp.json()
        state_codes = [s["code"] for s in data]
        assert "PA" in state_codes
        assert "CO" in state_codes
        assert "OK" in state_codes

    async def test_get_well_documents(self, client, populated_db):
        """GET /api/wells/{id}/documents returns documents for a specific well."""
        # Get a well ID from the database
        well = populated_db.query(Well).first()
        if well:
            resp = await client.get(f"/api/wells/{well.id}/documents")
            assert resp.status_code == 200

    async def test_review_queue_endpoint(self, client):
        """GET /api/review returns documents in review queue."""
        resp = await client.get("/api/review")
        assert resp.status_code == 200
        data = resp.json()
        assert "items" in data
```

### Step 6: Cross-State Data Consistency Checks

```python
class TestPhase4CrossStateConsistency:
    """Verify data consistency across all 3 states."""

    def test_api_numbers_all_14_digit(self, populated_db):
        """All stored API numbers are in 14-digit format XX-XXX-XXXXX-XX-XX."""
        import re
        pattern = re.compile(r'^\d{2}-\d{3}-\d{5}-\d{2}-\d{2}$')
        wells = populated_db.query(Well).all()
        for well in wells:
            assert pattern.match(well.api_number), \
                f"API number {well.api_number} not in 14-digit format"

    def test_state_codes_correct(self, populated_db):
        """Each well's API number prefix matches its state_code."""
        state_fips = {"PA": "37", "CO": "05", "OK": "35"}
        wells = populated_db.query(Well).all()
        for well in wells:
            expected_prefix = state_fips.get(well.state_code)
            if expected_prefix:
                assert well.api_number.startswith(expected_prefix), \
                    f"Well {well.api_number} has wrong prefix for state {well.state_code}"

    def test_coordinates_in_valid_ranges(self, populated_db):
        """All coordinates are within reasonable US ranges."""
        wells = populated_db.query(Well).filter(
            Well.latitude.isnot(None),
            Well.longitude.isnot(None)
        ).all()
        for well in wells:
            # Continental US bounds (approximate)
            assert 24.0 <= well.latitude <= 50.0, \
                f"Latitude {well.latitude} out of US range for {well.api_number}"
            assert -130.0 <= well.longitude <= -65.0, \
                f"Longitude {well.longitude} out of US range for {well.api_number}"

    def test_no_duplicate_wells(self, populated_db):
        """No duplicate API numbers in the wells table."""
        from sqlalchemy import func
        dupes = (
            populated_db.query(Well.api_number, func.count(Well.id))
            .group_by(Well.api_number)
            .having(func.count(Well.id) > 1)
            .all()
        )
        assert len(dupes) == 0, f"Duplicate API numbers found: {dupes[:5]}"

    def test_documents_linked_to_wells(self, populated_db):
        """Documents have valid well references."""
        docs = populated_db.query(Document).filter(Document.well_id.isnot(None)).all()
        for doc in docs:
            well = populated_db.query(Well).get(doc.well_id)
            assert well is not None, f"Document {doc.id} references non-existent well {doc.well_id}"
```

### Step 7: Run Full Test Suite

```bash
# All scraper tests
uv run pytest backend/tests/scrapers/ -v --tb=short

# All pipeline tests
uv run pytest backend/tests/pipeline/ -v --tb=short

# All API tests
uv run pytest backend/tests/api/ -v --tb=short

# Phase 4 regression suite
uv run pytest backend/tests/regression/test_phase4_regression.py -v --tb=long

# Full test suite
uv run pytest backend/tests/ -v --tb=short
```

## Files to Create

- `backend/tests/regression/test_phase4_regression.py` - Comprehensive regression test suite
- `backend/tests/regression/__init__.py` - Package init
- `backend/tests/regression/conftest.py` - Shared fixtures (populated_db, client, test data)

## Files to Modify

- None (this is a testing-only task)

## Contracts

### Provides (for downstream tasks)

- **Regression test suite**: Reusable test patterns in `backend/tests/regression/` for future phases
- **Validated pipeline**: Confidence that the scrape -> pipeline -> database -> API flow works for 3 states
- **Cross-state consistency checks**: Reusable validation functions for API number format, coordinate ranges, duplicate detection

### Consumes (from upstream tasks)

- PA spider + VCR cassettes from Task 4.1
- CO spider + VCR cassettes from Task 4.2
- OK spider + VCR cassettes from Task 4.3
- All Phase 3 API endpoints (wells, documents, search, states, review queue)
- DocumentPipeline from Task 2.4
- Database models from Task 1.2
- FastAPI app from Task 1.4

## Acceptance Criteria

- [ ] All 3 spiders run successfully against VCR cassettes (no network access)
- [ ] Pipeline processes data from all 3 states through all 7 stages
- [ ] Database contains wells with correct state codes (PA=37, CO=05, OK=35)
- [ ] Database contains documents for all 3 states
- [ ] All API numbers are in normalized 14-digit format (XX-XXX-XXXXX-XX-XX)
- [ ] PostGIS geometry populated for wells with coordinates
- [ ] Full-text search vector populated for all wells
- [ ] `GET /api/wells?state=PA` returns PA wells
- [ ] `GET /api/wells?state=CO` returns CO wells
- [ ] `GET /api/wells?state=OK` returns OK wells
- [ ] `GET /api/documents?state=CO&type=PRODUCTION_REPORT` returns CO production reports
- [ ] `GET /api/wells/search?q=<operator>` returns matching wells
- [ ] `GET /api/states` shows PA, CO, OK with data counts
- [ ] Review queue contains documents below confidence threshold (if any)
- [ ] No duplicate API numbers in wells table
- [ ] All coordinates within valid US continental ranges
- [ ] `uv run pytest backend/tests/scrapers/` -- all scraper tests pass
- [ ] `uv run pytest backend/tests/regression/` -- all regression tests pass
- [ ] Full test suite passes: `uv run pytest backend/tests/`

## Testing Protocol

### Unit/Integration Tests

- Test file: `backend/tests/regression/test_phase4_regression.py`
- Test cases:
  - [ ] PA spider produces items from VCR cassette
  - [ ] CO spider produces items from VCR cassette
  - [ ] OK spider produces items from VCR cassette
  - [ ] PA items process through pipeline with high confidence
  - [ ] CO items process through pipeline with high confidence
  - [ ] OK CSV items process through pipeline
  - [ ] OK XLSX items process through pipeline
  - [ ] Cross-state normalization produces consistent output format
  - [ ] Database populated with PA wells (API prefix 37-)
  - [ ] Database populated with CO wells (API prefix 05-)
  - [ ] Database populated with OK wells (API prefix 35-)
  - [ ] Documents stored for all 3 states
  - [ ] ExtractedData JSONB column populated
  - [ ] PostGIS geometry auto-populated by trigger
  - [ ] Full-text search vector populated
  - [ ] No duplicate API numbers
  - [ ] Coordinates in valid US ranges
  - [ ] API returns PA wells
  - [ ] API returns CO wells
  - [ ] API returns OK wells
  - [ ] API returns CO production reports
  - [ ] API search returns results
  - [ ] API states endpoint shows all 3 states
  - [ ] Review queue endpoint works

### API/Script Testing

- Run regression suite: `uv run pytest backend/tests/regression/test_phase4_regression.py -v --tb=long`
- Expected: All tests pass
- Run full suite: `uv run pytest backend/tests/ -v --tb=short`
- Expected: All tests pass (scrapers + pipeline + API + regression)

### Build/Lint/Type Checks

- [ ] `uv run ruff check backend/tests/regression/` passes
- [ ] `uv run pytest backend/tests/ -v` -- full test suite passes

## Skills to Read

- `og-testing-strategies` - VCR cassettes, testcontainers, integration test patterns, regression testing
- `scrapy-playwright-scraping` - VCR test patterns for spider replay
- `fastapi-backend` - API endpoint testing with httpx.AsyncClient
- `postgresql-postgis-schema` - Database assertions, PostGIS geometry, tsvector

## Research Files to Read

- `.claude/orchestration-og-doc-scraper/research/per-state-scrapers-implementation.md` - Cross-state data format comparison
- `.claude/orchestration-og-doc-scraper/research/state-regulatory-sites.md` - State FIPS codes, coordinate systems

## Git

- Branch: `feat/task-4.R-phase4-regression`
- Commit message prefix: `Task 4.R:`
