# Task 6.R: Phase 6 Regression -- All 10 State Scrapers End-to-End

## Objective

Comprehensive regression test verifying that all 10 state scrapers are working end-to-end: scraping data, feeding through the document processing pipeline, storing results in PostgreSQL, and being accessible through the API and dashboard. This task does not create new code -- it runs the full test suite, exercises every spider, and validates the complete data flow from scrape trigger to database to API to dashboard for every state.

## Context

Phase 6 (Tasks 6.1-6.3) implemented the remaining 7 state scrapers (TX, NM, ND, WY, CA, AK, LA). Phase 4 previously implemented 3 scrapers (PA, CO, OK). This regression task validates the entire scraper ecosystem: all 10 states operating together, the pipeline handling all state-specific data formats, the database containing multi-state data, the API serving cross-state queries, and the dashboard displaying nationwide well data on the map. This is the final validation before Phase 7 comprehensive E2E testing.

## Dependencies

- **Task 6.1** - TX and NM scrapers (EBCDIC, ArcGIS)
- **Task 6.2** - ND, WY, and AK scrapers (paywall, ColdFusion, Data Miner)
- **Task 6.3** - CA and LA scrapers (WellSTAR, SONRIS)
- **Task 4.1-4.3** - PA, CO, OK scrapers (bulk download, mixed, CSV)
- **Task 1.3** - Base scraper framework and state registry
- **Task 2.4** - Document processing pipeline
- **Task 3.x** - Backend API endpoints (wells, documents, states, scrape jobs)
- **Task 5.x** - Frontend dashboard (map, search, scrape trigger)

## Blocked By

- All Phase 6 tasks (6.1, 6.2, 6.3)
- All Phase 4 tasks (4.1, 4.2, 4.3)

## Research Findings

Key testing considerations from research:

- From `per-state-scrapers-implementation.md`: Each state has different data formats, rate limits, and scraping patterns. Regression must verify that all patterns work: BulkDownloadSpider (TX, OK, PA), ArcGISAPISpider (NM, CA), MixedSpider (CO, WY, AK), HybridSpider (ND), PlaywrightFormSpider (LA).
- From `state-regulatory-sites.md`: Rate limits vary from 3s/4 concurrent (PA, OK) to 15s/1 concurrent (ND, LA). Regression tests using VCR cassettes should still respect the spider configuration.
- From `scrapy-playwright-scraping` skill: VCR.py cassettes provide HTTP replay. For Playwright-dependent states (ND, WY, LA, AK), use HAR recordings or mock Playwright pages.
- From `state-regulatory-sites.md`: All 10 states have different API number formats, document types, operator naming conventions. Regression must verify normalization produces consistent output.

## Implementation Plan

### Step 1: Run All Scraper Unit Tests

Execute the full scraper test suite to verify all individual spider components.

```bash
uv run pytest backend/tests/scrapers/ -v --tb=long
```

This covers:
- `test_tx_spider.py` -- EBCDIC parsing, COMP-3 decoding, CSV parsing, fixed-width ASCII
- `test_nm_spider.py` -- ArcGIS pagination, OCD Permitting HTML parsing
- `test_nd_spider.py` -- PDF URL generation, well search, subscription handling
- `test_wy_spider.py` -- ArcGIS parsing, Excel parsing, Data Explorer mocks
- `test_ca_spider.py` -- ArcGIS pagination, coordinate conversion, CKAN API
- `test_ak_spider.py` -- Data Miner CSV parsing, HTTP (not HTTPS) handling
- `test_la_spider.py` -- IDR Excel parsing, serial numbers, circuit breaker, session management
- `test_pa_spider.py` -- GreenPort CSV parsing, reporting period handling
- `test_co_spider.py` -- Bulk CSV, COGIS form queries
- `test_ok_spider.py` -- RBDMS CSV, XLSX parsing

All tests must pass. Zero failures allowed.

### Step 2: Run VCR Cassette Replay Tests for All States

Verify that each spider can replay its VCR cassettes and produce expected output.

```bash
uv run pytest backend/tests/scrapers/ -v -k "vcr or cassette"
```

Verify cassettes exist and work for all states:
- `backend/tests/scrapers/cassettes/tx/` -- TX bulk download responses
- `backend/tests/scrapers/cassettes/nm/` -- NM ArcGIS and OCD Permitting responses
- `backend/tests/scrapers/cassettes/nd/` -- ND monthly PDF and well search responses
- `backend/tests/scrapers/cassettes/wy/` -- WY ArcGIS responses
- `backend/tests/scrapers/cassettes/ca/` -- CA WellSTAR ArcGIS and Open Data responses
- `backend/tests/scrapers/cassettes/ak/` -- AK ArcGIS responses
- `backend/tests/scrapers/cassettes/la/` -- LA DOTD ArcGIS responses
- `backend/tests/scrapers/cassettes/pa/` -- PA GreenPort responses
- `backend/tests/scrapers/cassettes/co/` -- CO bulk CSV and COGIS responses
- `backend/tests/scrapers/cassettes/ok/` -- OK bulk download responses

### Step 3: Run Integration Tests -- Each Spider Through Pipeline to Database

For each state, run a limited integration test that scrapes from VCR cassettes, processes through the pipeline, and stores in PostgreSQL.

```bash
uv run pytest backend/tests/scrapers/ -v -k "integration" --timeout=120
```

Verify for each state:
- Spider yields `WellItem` and/or `DocumentItem` objects
- Items pass through the validation pipeline (Task 2.4)
- Items pass through the normalization pipeline
- Items are stored in PostgreSQL `wells` and `documents` tables
- API numbers are normalized to 14-digit format
- Coordinates are in WGS84 (EPSG:4326)
- Confidence scores are present and within valid range (0.0-1.0)

### Step 4: Verify Database State After All Spiders Run

Connect to PostgreSQL and verify the database contains data from all 10 states.

SQL verification queries:
```sql
-- Verify all 10 states have wells
SELECT state_code, COUNT(*) as well_count
FROM wells
GROUP BY state_code
ORDER BY state_code;
-- Expected: TX, NM, ND, OK, CO, WY, LA, PA, CA, AK all present

-- Verify all 10 states have documents
SELECT state_code, COUNT(*) as doc_count
FROM documents
GROUP BY state_code
ORDER BY state_code;

-- Verify API numbers are normalized (14-digit format)
SELECT state_code, api_number
FROM wells
WHERE api_number NOT SIMILAR TO '\d{2}-\d{3}-\d{5}-\d{2}-\d{2}'
LIMIT 10;
-- Expected: 0 rows (all normalized)

-- Verify extracted data exists
SELECT d.state_code, COUNT(ed.id) as extracted_count
FROM documents d
LEFT JOIN extracted_data ed ON d.id = ed.document_id
GROUP BY d.state_code;

-- Verify confidence scores are present and valid
SELECT state_code,
  AVG(confidence) as avg_confidence,
  MIN(confidence) as min_confidence,
  MAX(confidence) as max_confidence
FROM documents
WHERE confidence IS NOT NULL
GROUP BY state_code;

-- Verify wells have coordinates
SELECT state_code,
  COUNT(*) as total_wells,
  COUNT(latitude) as wells_with_coords,
  COUNT(*) - COUNT(latitude) as wells_without_coords
FROM wells
GROUP BY state_code;

-- Verify PostGIS geometry column is populated where coordinates exist
SELECT state_code, COUNT(*) as geo_count
FROM wells
WHERE location IS NOT NULL
GROUP BY state_code;

-- Verify LA serial numbers are stored (LA-specific)
SELECT COUNT(*) as la_wells_with_serial
FROM wells
WHERE state_code = 'LA' AND raw_metadata::jsonb ? 'la_serial_number';

-- Verify document types are classified
SELECT state_code, doc_type, COUNT(*) as count
FROM documents
GROUP BY state_code, doc_type
ORDER BY state_code, count DESC;
```

### Step 5: Verify API Endpoints Return Multi-State Data

Test the backend API endpoints to confirm they serve data from all 10 states.

```bash
# Health check
curl http://localhost:8000/health

# States endpoint -- all 10 states with data counts
curl http://localhost:8000/api/states

# Wells per state
for state in TX NM ND OK CO WY LA PA CA AK; do
  echo "=== $state ==="
  curl "http://localhost:8000/api/wells?state=$state&limit=5"
done

# Documents per state
for state in TX NM ND OK CO WY LA PA CA AK; do
  echo "=== $state ==="
  curl "http://localhost:8000/api/documents?state=$state&limit=5"
done

# Cross-state search
curl "http://localhost:8000/api/wells?search=Devon%20Energy"

# Well by API number (pick one from each state)
curl "http://localhost:8000/api/wells/{known_api_number}"
```

Verify:
- `GET /api/states` returns all 10 states with non-zero well and document counts
- `GET /api/wells?state=XX` returns results for each state
- `GET /api/documents?state=XX` returns results for each state
- Cross-state search returns results from multiple states
- Individual well lookup returns complete data with documents and extracted fields

### Step 6: Verify Dashboard Displays All States

Use Playwright MCP (browser testing) to verify the frontend dashboard displays data from all 10 states.

**Prerequisites:** Start the full stack with `docker compose up` or `just dev`.

Browser testing steps:
1. Navigate to `http://localhost:3000` (dashboard home)
2. Verify the map renders with well pins from multiple states
3. Zoom out to see nationwide coverage -- verify pins appear in TX, NM, ND, OK, CO, WY, LA, PA, CA, AK geographic regions
4. Click a well pin -- verify popup shows well details with correct state
5. Navigate to the scrape management page
6. Verify all 10 state buttons are displayed ("Scrape TX", "Scrape NM", etc.)
7. Navigate to the wells search page
8. Search without filters -- verify results include wells from multiple states
9. Filter by each state -- verify results update correctly
10. Click a well in the table -- verify detail view shows documents and extracted data
11. Navigate to the review queue -- verify any review items show state codes

Screenshot key screens:
- Dashboard with map showing nationwide well coverage
- Wells list filtered by each state
- Scrape management page with all 10 state buttons
- Well detail view with documents

### Step 7: Verify State-Specific Data Format Handling

Spot-check that state-specific data quirks are handled correctly.

| State | Check |
|-------|-------|
| TX | EBCDIC-sourced data has readable field values (not garbled encoding artifacts) |
| TX | API numbers from dBase/Shapefile data match those from CSV/EBCDIC sources |
| NM | ArcGIS-sourced wells have valid coordinates (within NM geographic bounds) |
| NM | OCD Permitting documents have form numbers (C-101, C-103, etc.) |
| ND | Free-tier PDFs have been OCR-processed and classified |
| ND | Subscription data (if available) includes production histories |
| WY | ArcGIS and Well Header DB5 data are consistent (same wells, same API numbers) |
| CA | Coordinates have been converted from EPSG:3857 to EPSG:4326 (WGS84) |
| CA | Open Data CSV and ArcGIS API produce consistent records |
| AK | Data Miner exports include production data (oil, gas, water columns) |
| LA | Wells have both API numbers and LA serial numbers stored |
| LA | IDR production data has oil, gas, and condensate columns |
| PA | GreenPort CSV data includes all report types (production, inventory, compliance) |
| CO | Production CSV since 1999 is parsed without errors |
| OK | RBDMS well data matches RBDMS data dictionary field definitions |

### Step 8: Verify Error Handling and Graceful Degradation

Test that error conditions are handled gracefully across all states.

- [ ] ND spider without subscription credentials: logs warning, scrapes free data only, no crash
- [ ] LA spider with SONRIS unavailable (mock): circuit breaker opens, partial data preserved, clear error message
- [ ] TX spider with corrupt EBCDIC file: skips file, logs error, continues with other files
- [ ] NM spider with ArcGIS timeout: retries, backs off, eventually skips with warning
- [ ] CA spider with coordinate conversion failure: logs warning, stores null coordinates, does not crash
- [ ] WY spider with ColdFusion session expiry: detects and re-establishes session
- [ ] AK spider with Data Miner returning empty export: handles gracefully, no error
- [ ] All spiders: network error during download -> retry logic engages correctly

### Step 9: Verify Scraper Performance and Rate Compliance

Check that rate limiting is applied correctly per state.

- Verify via Scrapy logs that download delays match configuration:
  - TX: ~10s between requests
  - NM: ~5s between requests
  - ND: ~15s between requests
  - OK: ~3s between requests
  - CO: ~8s between requests
  - WY: ~10s between requests
  - LA: ~15s between requests
  - PA: ~3s between requests
  - CA: ~3s between requests
  - AK: ~5s between requests
- Verify AutoThrottle is active in Scrapy logs
- Verify `robots.txt` is obeyed (Scrapy logs should show "robots.txt" fetch)
- Verify User-Agent is set to `OGDocScraper/1.0 (Research tool; contact@example.com)`

### Step 10: Generate Final State Coverage Report

Produce a summary report of data coverage across all 10 states.

Query the database and format results:
```sql
SELECT
  s.state_code,
  s.state_name,
  COUNT(DISTINCT w.id) as wells,
  COUNT(DISTINCT d.id) as documents,
  COUNT(DISTINCT CASE WHEN d.doc_type = 'PRODUCTION_REPORT' THEN d.id END) as production_docs,
  COUNT(DISTINCT CASE WHEN d.doc_type = 'WELL_PERMIT' THEN d.id END) as permit_docs,
  AVG(d.confidence) as avg_confidence,
  COUNT(DISTINCT CASE WHEN d.status = 'VALIDATED' THEN d.id END) as validated_docs,
  COUNT(DISTINCT CASE WHEN rq.id IS NOT NULL THEN d.id END) as review_queue_docs
FROM states s
LEFT JOIN wells w ON s.state_code = w.state_code
LEFT JOIN documents d ON w.id = d.well_id
LEFT JOIN review_queue rq ON d.id = rq.document_id
GROUP BY s.state_code, s.state_name
ORDER BY wells DESC;
```

All 10 states must have non-zero well counts. Document counts may vary (especially ND free tier and LA due to complexity), but all states should have at least some data.

## Files to Create

- None. This is a testing-only task.

## Files to Modify

- None. This task only runs tests and verifies existing functionality.

## Contracts

### Provides (for downstream tasks)

- Validated confirmation that all 10 state scrapers work end-to-end
- State coverage report showing data volume per state
- Identified issues or gaps documented for Phase 7 follow-up

### Consumes (from upstream tasks)

- All spider implementations from Tasks 6.1, 6.2, 6.3, 4.1, 4.2, 4.3
- Base scraper framework from Task 1.3
- Document pipeline from Task 2.4
- Database schema from Task 1.2
- API endpoints from Phase 3
- Dashboard from Phase 5

## Acceptance Criteria

- [ ] All scraper unit tests pass: `uv run pytest backend/tests/scrapers/ -v` (0 failures)
- [ ] VCR cassette replay tests pass for all 10 states
- [ ] Integration tests pass: each spider -> pipeline -> database
- [ ] Database contains wells from all 10 states (SQL verification)
- [ ] Database contains documents from all 10 states
- [ ] API numbers are normalized to 14-digit format across all states
- [ ] Coordinates are in WGS84 (EPSG:4326) across all states
- [ ] `GET /api/states` returns all 10 states with data
- [ ] `GET /api/wells?state=XX` returns results for each of the 10 states
- [ ] Dashboard map shows well pins in all 10 state geographic regions
- [ ] Dashboard scrape page shows all 10 state scrape buttons
- [ ] ND graceful degradation works (free tier without credentials)
- [ ] LA circuit breaker works (error handling tested)
- [ ] TX EBCDIC data is correctly decoded (readable field values)
- [ ] CA coordinates are converted from Web Mercator to WGS84
- [ ] LA wells have both API numbers and serial numbers
- [ ] Rate limiting configuration is correct per state
- [ ] All lint and type checks pass

## Testing Protocol

### Unit/Integration Tests

- Test command: `uv run pytest backend/tests/scrapers/ -v --tb=long`
- Expected: All tests pass (0 failures, 0 errors)
- Timeout: 300 seconds for full suite (VCR cassettes make tests fast)

### API/Script Testing

- Start backend: `docker compose up backend` or `just dev-backend`
- Run API verification script:
  ```bash
  curl http://localhost:8000/api/states | python -m json.tool
  for state in TX NM ND OK CO WY LA PA CA AK; do
    curl -s "http://localhost:8000/api/wells?state=$state&limit=1" | python -m json.tool
  done
  ```

### Browser Testing (Playwright MCP)

- Start: `docker compose up` or `just dev`
- Navigate to: `http://localhost:3000`
- Actions: Check map, search, filter by each state, view well details
- Verify: All 10 states have data displayed
- Screenshot: Map with nationwide coverage, wells list per state, scrape management page

### Database Verification

- Connect: `psql postgresql://postgres:postgres@localhost:5432/ogdocs`
- Run all SQL queries from Step 4
- Verify: Non-zero counts for all 10 states

### Build/Lint/Type Checks

- [ ] `uv run pytest backend/tests/scrapers/` passes (all tests)
- [ ] `uv run pytest backend/tests/` passes (full test suite)
- [ ] `uv run ruff check backend/` passes
- [ ] `uv run ruff format --check backend/` passes

## Skills to Read

- `scrapy-playwright-scraping` - Per-state rate limits, testing strategy, VCR cassette organization
- `state-regulatory-sites` - All 10 state site details for verification
- `og-testing-strategies` - Regression testing approach, VCR cassettes, testcontainers

## Research Files to Read

- `.claude/orchestration-og-doc-scraper/research/per-state-scrapers-implementation.md` - Per-state data formats and expected outputs for verification
- `.claude/orchestration-og-doc-scraper/research/state-regulatory-sites.md` - All state URLs and data availability for coverage verification

## Git

- Branch: `feature/phase-6-regression`
- Commit message prefix: `Task 6.R:`
