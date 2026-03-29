# Task 6.3: California & Louisiana Scrapers

## Objective

Implement the California CalGEM spider (WellSTAR ArcGIS REST API + Open Data portal) and the Louisiana SONRIS spider (the hardest state to scrape -- Oracle-backed complex JavaScript web application with no REST API). California is straightforward via ArcGIS API. Louisiana requires extensive Playwright browser automation, robust session management, and careful handling of Oracle query timeouts. SONRIS alone is estimated at 5-8 days of development.

## Context

Phase 6 implements the remaining 7 state scrapers. Task 6.3 is deliberately paired to put the easiest remaining state (CA) with the hardest (LA) in a single task. California should be completed first as a warm-up, then all remaining effort goes to Louisiana SONRIS. After this task, all 10 states will have functional scrapers. The SONRIS spider is the most complex individual component in the entire project -- it involves Playwright throughout, Oracle database timeouts, session state management, IDR (Interactive Data Report) automation, and a web application that recently changed URLs due to agency reorganization.

## Dependencies

- **Task 1.3** - Provides `BaseOGSpider` adapter class, Scrapy settings, download pipeline, state registry
- **Task 2.4** - Provides the full 7-stage document processing pipeline
- **Task 1.2** - Provides database schema (wells, documents, extracted_data tables)

## Blocked By

- Task 1.3 (base scraper framework must exist)
- Task 2.4 (pipeline must be operational)

## Research Findings

Key findings from research files relevant to this task:

- From `per-state-scrapers-implementation.md`: CA WellSTAR ArcGIS REST API endpoint is `https://gis.conservation.ca.gov/server/rest/services/WellSTAR/Wells/MapServer/0`. Max Record Count is 5,000 per query. Must paginate with `resultOffset`. Spatial reference is EPSG:3857 (Web Mercator) -- must convert to WGS84 for standard lat/long.
- From `per-state-scrapers-implementation.md`: CA Open Data portal at `data.ca.gov` provides CKAN-based API with WellSTAR datasets as CSV, Shapefile, GeoJSON, KML. Creative Commons Attribution license.
- From `per-state-scrapers-implementation.md`: CA WellSTAR is under active development. CalGEM continuously updates the system. As of Jan 2026, Well Finder was updated with new layers and features.
- From `per-state-scrapers-implementation.md`: LA SONRIS is the hardest state to scrape. Oracle-backed with millions of records. No REST API -- all access is through a complex JavaScript web application. Requires Playwright throughout. Budget 5-8 days.
- From `per-state-scrapers-implementation.md`: LA IDR (Interactive Data Reports) are the primary extraction method. They can be exported to Excel. Key IDR topics: Well Information, Production Data, Injection Data, Scout Reports, Permit Data, Well Test Data, P&A.
- From `per-state-scrapers-implementation.md`: LA agency renamed from DENR to Dept of Conservation and Energy (Oct 2025). URLs are in flux across three domains: `denr.louisiana.gov`, `dce.louisiana.gov`, `dnr.louisiana.gov`.
- From `per-state-scrapers-implementation.md`: LA uses its own serial number system for wells in addition to API numbers.
- From `state-regulatory-sites.md`: LA SONRIS anti-bot protections are moderate-high. Expect session-based state management, JavaScript-heavy dynamic content, potential CAPTCHAs, and Oracle query timeouts. DOTD provides an ArcGIS MapServer at `giswebnew.dotd.la.gov` as partial alternative.
- From `per-state-scrapers-implementation.md`: CA production data is separate from well location/status data. Well data is via ArcGIS API; production data is primarily through WellSTAR Dashboard which may need Playwright for export.

## Implementation Plan

### Step 1: Implement CA CalGEM Spider -- ArcGIS REST API (Primary)

Build the primary California data access path. This is straightforward and follows the same ArcGIS pattern as NM (Task 6.1) and WY (Task 6.2).

- Create `backend/src/og_scraper/scrapers/spiders/ca_spider.py`:
  - Inherit from `BaseOGSpider`
  - Set: `state_code = "CA"`, `state_name = "California"`, `agency_name = "CalGEM (Geologic Energy Management Division)"`, `base_url = "https://www.conservation.ca.gov/calgem/"`, `requires_playwright = False`
  - `custom_settings`: `DOWNLOAD_DELAY = 3`, `CONCURRENT_REQUESTS_PER_DOMAIN = 3`
- WellSTAR ArcGIS REST API endpoint:
  ```
  https://gis.conservation.ca.gov/server/rest/services/WellSTAR/Wells/MapServer/0/query?
    where=1%3D1&outFields=*&resultOffset=0&resultRecordCount=5000&f=json
  ```
- Key API parameters:
  - Display Field: `LeaseName`
  - Geometry Type: Point (esriGeometryPoint)
  - Max Record Count: 5,000
  - Supported Formats: JSON, GeoJSON, PBF
  - Spatial Reference: EPSG:3857 (Web Mercator)
  - Supports Advanced Queries: Yes
  - Supports Statistics: Yes
- Implement `start_requests()` with initial query at offset 0
- Implement `parse_api_response()`:
  - Parse JSON features array
  - For each feature, extract `attributes` dict and `geometry` dict
  - **Coordinate conversion**: Transform from Web Mercator (EPSG:3857) to WGS84 (EPSG:4326) using `pyproj`:
    ```python
    from pyproj import Transformer
    transformer = Transformer.from_crs("EPSG:3857", "EPSG:4326", always_xy=True)
    lon, lat = transformer.transform(x, y)
    ```
  - Build `WellItem` with converted coordinates
  - Check `exceededTransferLimit`, paginate with `resultOffset += 5000`
- Support filtered queries for specific well statuses:
  ```
  where=WellStatus%3D%27Active%27
  where=WellStatus%3D%27Plugged%27
  ```

### Step 2: Implement CA CalGEM Spider -- Open Data Portal (Bulk)

Add California Open Data portal access for bulk CSV downloads.

- CA Open Data (CKAN) URLs:
  - Wells: `https://data.ca.gov/dataset/wellstar-oil-and-gas-wells`
  - Facilities: `https://data.ca.gov/dataset/wellstar-oil-and-gas-facilities`
  - Notices: `https://data.ca.gov/dataset/wellstar-notices`
  - Also via CNRA: `https://data.cnra.ca.gov/dataset/wellstar-oil-and-gas-wells`
- Use CKAN API to discover CSV download URLs:
  - `https://data.ca.gov/api/3/action/package_show?id=wellstar-oil-and-gas-wells`
  - Extract resource URLs from response
  - Download CSV files directly
- Parse CSVs with pandas for well data, facility data, and notices
- This provides a bulk alternative to the paginated ArcGIS API

### Step 3: Implement CA CalGEM Spider -- WellSTAR Dashboard (Production Data)

Production data may require Playwright for the WellSTAR Dashboard.

- WellSTAR Dashboard: `https://www.conservation.ca.gov/calgem/Online_Data/Pages/WellSTAR-Data-Dashboard.aspx`
- If dashboard provides direct export (Excel/CSV download button):
  - Use Playwright to navigate, select parameters, trigger export
  - Handle file download
- If dashboard data is rendered in-page:
  - Use Playwright to render the page, extract data from DOM
- This is the optional/tertiary data path -- ArcGIS API and Open Data cover most needs

### Step 4: Implement LA SONRIS Spider -- Architecture Design

SONRIS is the most complex scraper. Plan the architecture carefully before coding.

- Create `backend/src/og_scraper/scrapers/spiders/la_spider.py`:
  - Inherit from `BaseOGSpider`
  - Set: `state_code = "LA"`, `state_name = "Louisiana"`, `agency_name = "Dept of Conservation & Energy (SONRIS)"`, `base_url = "https://www.sonris.com/"`, `requires_playwright = True`
  - `custom_settings`: `DOWNLOAD_DELAY = 15`, `CONCURRENT_REQUESTS_PER_DOMAIN = 1`
- Architecture decisions:
  - **All requests use Playwright** -- SONRIS has no useful static HTML paths
  - **Single session strategy** -- maintain one browser context with session cookies
  - **IDR reports are the primary extraction method** -- automate report generation and Excel export
  - **DOTD ArcGIS as GIS supplement** -- use the ArcGIS MapServer for spatial data only
  - **Circuit breaker with low threshold** -- `fail_max=3, reset_timeout=600` to protect against Oracle timeouts
- Key URLs (note: URLs are in flux across three domains):
  - SONRIS Main: `https://www.sonris.com/`
  - SONRIS Integrated Apps: `https://www.sonris.com/homemain.htm`
  - IDR Index by Topic: `https://www.dnr.louisiana.gov/page/cons-sonris-idr-index-by-topic`
  - SONRIS Guides: `https://www.dce.louisiana.gov/page/sonris-guides`
  - GIS Map: `https://sonris-gis.dnr.la.gov/gis/agsweb/IE/JSViewer/index.html?TemplateID=181`
  - Production Data: `https://www.dnr.louisiana.gov/page/oil-and-gas-production-data`
  - DOTD ArcGIS MapServer: `https://giswebnew.dotd.la.gov/arcgis/rest/services/LTRC/SONRIS/MapServer`

### Step 5: Implement LA SONRIS Spider -- IDR Report Automation

The core of the LA spider: automating IDR report generation and Excel export.

- IDR (Interactive Data Reports) workflow via Playwright:
  1. Navigate to SONRIS IDR interface
  2. Select report topic (Well Information, Production Data, etc.)
  3. Set report parameters:
     - Filter by parish, field, operator, serial number range
     - Select date range for production data
     - Choose output format (Excel export)
  4. Wait for report generation (Oracle query -- may be slow)
  5. Click "Export" or "Download" to get Excel file
  6. Handle file download via Playwright download event
  7. Parse exported Excel with openpyxl

- Implement report automation for each IDR topic:
  - **Well Information**: Query by operator or field to get well headers with serial numbers and API numbers
  - **Production Data**: Query oil, gas, condensate production by well, field, or parish. Use date range filters to batch requests.
  - **Injection Data**: Same pattern as production
  - **Scout Reports**: Well-level scout reports with geological data
  - **Permit Data**: Drilling and work permits
  - **Well Test Data**: Initial production tests, pressure tests
  - **P&A Data**: Plugging and abandonment records

- Important: LA uses serial numbers as primary well identifiers, not just API numbers. Store both:
  - `la_serial_number` as additional field in WellItem
  - Map serial numbers to API numbers where available

### Step 6: Implement LA SONRIS Spider -- Session and Error Management

Build robust session management for the complex SONRIS web application.

- Session management:
  - Use `playwright_include_page: True` to maintain page/context across requests
  - Store session cookies and reuse across requests
  - Detect session expiry (redirects to login or home page) and re-establish
  - Single concurrent session to avoid Oracle contention
- Oracle timeout handling:
  - SONRIS queries can time out when the Oracle database is under load
  - Implement timeout detection (page shows error message or loading spinner exceeds threshold)
  - On timeout: wait 30-60 seconds, retry with smaller scope (fewer records, shorter date range)
  - If repeated timeouts, break query into smaller batches (by parish, by date quarter)
- Error recovery:
  - Circuit breaker: open after 3 consecutive failures, reset after 600 seconds
  - On circuit open, log warning and skip remaining LA requests for current scrape run
  - Partial results are still saved -- don't discard successfully scraped data
- Rate limiting:
  - 15-second minimum delay between requests
  - Add 30% jitter to avoid patterns
  - After each IDR report generation, add extra 5-10 second pause for Oracle recovery

### Step 7: Implement LA SONRIS Spider -- DOTD ArcGIS GIS Data

Add GIS spatial data access via the DOTD ArcGIS MapServer.

- DOTD ArcGIS endpoint: `https://giswebnew.dotd.la.gov/arcgis/rest/services/LTRC/SONRIS/MapServer`
- This provides well locations and spatial data without going through the SONRIS web UI
- Use standard ArcGIS REST API query pattern (like NM, WY, CA)
- This supplements the IDR data with geographic coordinates
- No Playwright needed for this component -- standard Scrapy HTTP requests

### Step 8: Implement URL Resilience for LA Domain Changes

Handle the fact that LA URLs are in flux across three domains.

- Create a URL resolver helper in the spider:
  ```python
  LA_DOMAIN_ALIASES = [
      "www.dnr.louisiana.gov",
      "www.dce.louisiana.gov",
      "www.denr.louisiana.gov",
  ]
  ```
- When a request to one domain fails with 404 or redirect, automatically try the other domains
- Store the currently-working domain and prefer it for subsequent requests
- Log domain changes for monitoring

### Step 9: Set Up VCR.py Cassettes and HAR Recordings

- Create cassette directories: `backend/tests/scrapers/cassettes/ca/`, `la/`
- CA cassettes:
  - `ca_wellstar_arcgis_page1.yaml` -- First page of ArcGIS well query (5000 records)
  - `ca_wellstar_arcgis_page2.yaml` -- Second page (pagination test)
  - `ca_open_data_package.yaml` -- CKAN package metadata response
  - `ca_open_data_csv_wells.yaml` -- CSV download response (truncated sample)
- LA cassettes/HAR:
  - `la_dotd_arcgis_wells.yaml` -- DOTD ArcGIS MapServer well query
- LA HAR recordings (for Playwright interactions):
  - `la_sonris_navigation.har` -- SONRIS main page navigation
  - `la_sonris_idr_well_info.har` -- IDR Well Information report generation
  - `la_sonris_idr_production.har` -- IDR Production Data report generation
  - `la_sonris_idr_export.har` -- IDR Excel export flow
- LA HTML fixtures:
  - `la_sonris_idr_report.html` -- Rendered IDR report page
  - `la_sonris_idr_index.html` -- IDR topic index page
- LA Excel fixtures:
  - `la_sonris_well_info_export.xlsx` -- Sample IDR well info Excel export
  - `la_sonris_production_export.xlsx` -- Sample IDR production Excel export

### Step 10: Write Tests

Create comprehensive tests for both spiders.

- `backend/tests/scrapers/test_ca_spider.py`:
  - Test ArcGIS JSON response parsing with CA-specific fields (LeaseName, WellStatus, etc.)
  - Test coordinate conversion from EPSG:3857 to EPSG:4326
  - Test pagination with `exceededTransferLimit` and `resultOffset=5000`
  - Test CKAN API package metadata parsing
  - Test CSV download and parsing from Open Data portal
  - VCR cassette replay for ArcGIS and Open Data flows
  - Integration test: CA spider -> pipeline -> database

- `backend/tests/scrapers/test_la_spider.py`:
  - Test SONRIS IDR report page detection and navigation
  - Test IDR Excel export file parsing (well info, production, injection)
  - Test serial number to API number mapping
  - Test domain alias URL resolution
  - Test Oracle timeout detection and retry logic
  - Test circuit breaker trigger and recovery
  - Test session expiry detection
  - Mock Playwright: IDR report generation flow
  - Mock Playwright: Excel export download handling
  - Test DOTD ArcGIS query (standard ArcGIS pattern)
  - VCR cassette replay for DOTD ArcGIS
  - Integration test: LA spider (mocked) -> pipeline -> database
  - Edge case: Oracle timeout mid-report (partial data handling)
  - Edge case: session expiry during long scrape run
  - Edge case: domain redirect between dnr/dce/denr

## Files to Create

- `backend/src/og_scraper/scrapers/spiders/ca_spider.py` - California CalGEM spider (ArcGIS + Open Data + Dashboard)
- `backend/src/og_scraper/scrapers/spiders/la_spider.py` - Louisiana SONRIS spider (Playwright IDR + DOTD ArcGIS)
- `backend/src/og_scraper/scrapers/utils/coordinate_transform.py` - EPSG:3857 to EPSG:4326 coordinate conversion utility (used by CA, potentially reusable by others)
- `backend/tests/scrapers/test_ca_spider.py` - CA spider tests
- `backend/tests/scrapers/test_la_spider.py` - LA spider tests
- `backend/tests/scrapers/cassettes/ca/` - CA VCR cassettes
- `backend/tests/scrapers/cassettes/la/` - LA VCR cassettes
- `backend/tests/scrapers/fixtures/la_sonris_idr_report.html` - LA IDR report HTML fixture
- `backend/tests/scrapers/fixtures/la_sonris_well_info_export.xlsx` - LA well info Excel fixture
- `backend/tests/scrapers/fixtures/la_sonris_production_export.xlsx` - LA production Excel fixture
- `backend/tests/scrapers/fixtures/ca_arcgis_response.json` - CA ArcGIS JSON fixture

## Files to Modify

- `backend/src/og_scraper/scrapers/state_registry.py` - Update CA and LA entries with actual spider class references

## Contracts

### Provides (for downstream tasks)

- **CA Spider**: `CaliforniaCalGEMSpider` class
  - Yields `WellItem` from ArcGIS API with WGS84-converted coordinates
  - Yields `WellItem` from Open Data CSV downloads
  - Optional: yields `DocumentItem` from WellSTAR Dashboard production exports
- **LA Spider**: `LouisianaSONRISSpider` class
  - Yields `WellItem` from IDR Well Information reports (includes serial numbers + API numbers)
  - Yields `DocumentItem` from IDR Production, Injection, Scout, Permit, Well Test, P&A reports (as Excel exports)
  - Yields `WellItem` from DOTD ArcGIS MapServer for spatial data
  - Includes LA-specific `la_serial_number` field on WellItem
- **Coordinate Transformer**: `transform_web_mercator_to_wgs84(x, y) -> (lon, lat)` utility function

### Consumes (from upstream tasks)

- `BaseOGSpider` from Task 1.3: Base class for both spiders
- `DocumentItem`, `WellItem` from Task 1.3: Item classes for yielded data
- `DocumentPipeline` from Task 2.4: Full 7-stage processing pipeline
- Database models from Task 1.2: `wells`, `documents`, `extracted_data` tables
- State registry from Task 1.3: CA and LA configuration entries

## Acceptance Criteria

- [ ] CA spider queries WellSTAR ArcGIS REST API with pagination in 5,000-record batches
- [ ] CA spider correctly converts coordinates from EPSG:3857 (Web Mercator) to EPSG:4326 (WGS84)
- [ ] CA spider downloads and parses CSV from Open Data portal
- [ ] CA spider handles `exceededTransferLimit` flag for pagination
- [ ] LA spider navigates SONRIS IDR interface via Playwright
- [ ] LA spider generates IDR reports for all key topics (well info, production, injection, scouts, permits, well tests, P&A)
- [ ] LA spider exports IDR reports to Excel and parses the downloaded files
- [ ] LA spider stores both LA serial numbers and API numbers for wells
- [ ] LA spider handles Oracle query timeouts with retry and scope reduction
- [ ] LA spider implements circuit breaker (opens after 3 failures, resets after 600s)
- [ ] LA spider detects and handles session expiry
- [ ] LA spider resolves URLs across dnr/dce/denr domain aliases
- [ ] LA spider queries DOTD ArcGIS MapServer for GIS data without Playwright
- [ ] Both spiders feed items into the full pipeline and store in database
- [ ] Both spiders have VCR.py cassettes and/or HAR recordings for reproducible testing
- [ ] All tests pass
- [ ] Build succeeds

## Testing Protocol

### Unit/Integration Tests

- Test file: `backend/tests/scrapers/test_ca_spider.py`
- Test cases:
  - [ ] ArcGIS JSON response parsing with California-specific field names
  - [ ] Coordinate conversion: Web Mercator (3857) -> WGS84 (4326) for known coordinate pairs
  - [ ] Pagination: first page -> check exceededTransferLimit -> second page at offset 5000
  - [ ] Pagination termination when exceededTransferLimit is false
  - [ ] CKAN package metadata parsing extracts correct CSV download URL
  - [ ] CSV parsing produces correct WellItem fields
  - [ ] VCR cassette replay: full ArcGIS pagination flow
  - [ ] Integration: CA items -> pipeline -> database

- Test file: `backend/tests/scrapers/test_la_spider.py`
- Test cases:
  - [ ] IDR report Excel parsing: well info export with correct field mapping
  - [ ] IDR report Excel parsing: production data with oil/gas/condensate columns
  - [ ] Serial number extraction and mapping to API numbers
  - [ ] Domain alias URL resolution: try dnr -> fail -> try dce -> succeed
  - [ ] Oracle timeout detection: identify timeout indicator in page content
  - [ ] Timeout retry logic: scope reduction (smaller date range, single parish)
  - [ ] Circuit breaker: opens after 3 failures, returns cached partial data
  - [ ] Circuit breaker: resets after timeout, retries successfully
  - [ ] Session expiry detection: redirect to login/home page triggers re-auth
  - [ ] Mock Playwright: navigate to IDR topic -> set parameters -> generate -> export -> download
  - [ ] DOTD ArcGIS query: standard REST API pagination
  - [ ] VCR replay: DOTD ArcGIS well query
  - [ ] Integration: LA items (mocked Playwright) -> pipeline -> database
  - [ ] Edge case: empty IDR report (no matching records)
  - [ ] Edge case: partial Excel export (truncated by Oracle)
  - [ ] Edge case: IDR report with merged cells and multi-row headers

### API/Script Testing

- Run CA spider against VCR cassettes: `uv run scrapy crawl ca_calgem`
- Run LA spider against mocked sessions: `uv run scrapy crawl la_sonris` (with test fixtures)
- Verify items appear in PostgreSQL tables for each state

### Build/Lint/Type Checks

- [ ] `uv run pytest backend/tests/scrapers/test_ca_spider.py` passes
- [ ] `uv run pytest backend/tests/scrapers/test_la_spider.py` passes
- [ ] `uv run ruff check backend/src/og_scraper/scrapers/spiders/` passes
- [ ] `uv run ruff format --check backend/src/og_scraper/scrapers/spiders/` passes

## Skills to Read

- `scrapy-playwright-scraping` - Playwright PageMethod patterns, session management, circuit breaker, SONRIS-specific guidance
- `state-regulatory-sites` - CA WellSTAR API details, LA SONRIS IDR system, domain alias issues, DOTD ArcGIS endpoint
- `document-processing-pipeline` - Pipeline integration for processing LA Excel exports and CA CSV data

## Research Files to Read

- `.claude/orchestration-og-doc-scraper/research/per-state-scrapers-implementation.md` - CA ArcGIS endpoint details, LA SONRIS IDR workflow, Oracle timeout handling, recommended adapter strategies
- `.claude/orchestration-og-doc-scraper/research/state-regulatory-sites.md` - CA and LA regulatory body details, URL inventory, anti-bot protections, data availability

## Git

- Branch: `feature/phase-6-ca-la-scrapers`
- Commit message prefix: `Task 6.3:`
