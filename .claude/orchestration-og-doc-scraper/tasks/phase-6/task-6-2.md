# Task 6.2: North Dakota, Wyoming & Alaska Scrapers

## Objective

Implement scrapers for three browser-automation states: North Dakota DMR (paywalled subscription portal with free PDF fallback), Wyoming WOGCC (mixed ArcGIS API + JS-heavy Data Explorer + ColdFusion legacy portal), and Alaska AOGCC (ASP.NET Data Miner with export + ArcGIS Open Data). These states represent the "browser automation" tier of difficulty and all require Playwright for at least some data access.

## Context

Phase 6 implements the remaining 7 state scrapers. Task 6.2 covers three states that share a common need for Playwright browser automation but at varying levels of complexity. North Dakota is the hardest of the three due to its paid subscription wall and PDF-heavy free data. Wyoming requires navigating three separate data sources (Data Explorer, legacy ColdFusion portal, ArcGIS). Alaska is the simplest, with a smaller dataset and a standard ASP.NET Data Miner with export functionality. All three spiders must integrate with the existing pipeline (Phase 2) and database (Phase 1).

## Dependencies

- **Task 1.3** - Provides `BaseOGSpider` adapter class, Scrapy settings, download pipeline, state registry
- **Task 2.4** - Provides the full 7-stage document processing pipeline
- **Task 1.2** - Provides database schema (wells, documents, extracted_data tables)

## Blocked By

- Task 1.3 (base scraper framework must exist)
- Task 2.4 (pipeline must be operational)

## Research Findings

Key findings from research files relevant to this task:

- From `per-state-scrapers-implementation.md`: ND requires paid subscription ($100-$500/year) for detailed data. Free tier provides only monthly production report PDFs, daily activity reports, well search basic headers, and weekly permit listings. Free data URL pattern: `https://www.dmr.nd.gov/oilgas/mpr{YYYY}{MM}.pdf`.
- From `per-state-scrapers-implementation.md`: ND is migrating to NorthSTAR cloud-based system. URLs and interfaces may change without notice. Monitor for API endpoints that may emerge.
- From `per-state-scrapers-implementation.md`: WY data is spread across three sources: Data Explorer (JS-heavy, needs Playwright), legacy ColdFusion portal at `pipeline.wyo.gov` with quirky session management, and ArcGIS Wells MapServer (updated nightly). Well Header DB5 (Excel, ~114,000 wells) available from legacy site download menu.
- From `per-state-scrapers-implementation.md`: AK Data Miner runs on plain HTTP (not HTTPS) at `http://aogweb.state.ak.us`. Uses ASP.NET WebForms with ViewState/PostBack. Export buttons trigger server-side CSV generation. Full MS Access database also available for bulk import.
- From `state-regulatory-sites.md`: ND rate limit should be 15s base delay, 1 max concurrent to avoid triggering subscription account lockout. WY should be 10s/1 concurrent. AK can be moderate at 5s/2 concurrent.
- From `state-regulatory-sites.md`: AK has two agencies -- AOGCC (Commerce Dept) for conservation/regulatory data, Division of Oil and Gas (DNR) for leasing/exploration. Separate portals.
- From `per-state-scrapers-implementation.md`: ND confidential well production data is excluded even from premium subscribers.

## Implementation Plan

### Step 1: Implement ND DMR Spider -- Free Tier (PDF/HTML Scraping)

Build the free-tier component of the ND spider first, which requires no subscription.

- Create `backend/src/og_scraper/scrapers/spiders/nd_spider.py`:
  - Inherit from `BaseOGSpider`
  - Set: `state_code = "ND"`, `state_name = "North Dakota"`, `agency_name = "Department of Mineral Resources (DMR)"`, `base_url = "https://www.dmr.nd.gov/oilgas/"`, `requires_playwright = True`, `requires_auth = True`
  - `custom_settings`: `DOWNLOAD_DELAY = 15`, `CONCURRENT_REQUESTS_PER_DOMAIN = 1`
- Free data download targets:
  - Monthly Production Reports (PDF): `https://www.dmr.nd.gov/oilgas/mpr{YYYY}{MM}.pdf`
    - Generate URLs for all available months/years
    - Store PDFs for OCR pipeline processing
  - Daily Activity Reports: Indexed at `https://www.dmr.nd.gov/oilgas/dailyindex.asp`
    - Parse the index page to discover individual report PDF links
    - Download each linked PDF
  - Annual Production Statistics: `https://www.dmr.nd.gov/oilgas/stats/AnnualProduction/{YYYY}AnnualProductionReport.pdf`
  - Well Search (basic headers): `https://www.dmr.nd.gov/oilgas/findwellsvw.asp`
    - This is a Classic ASP form with ViewState
    - Use Scrapy `FormRequest` or Playwright to submit searches
    - Parse HTML results for well header data (API number, operator, well name, location, status)
  - Weekly Permit Listings: Linked from main O&G Division page

### Step 2: Implement ND DMR Spider -- Subscription Tier (Optional)

Build the subscription-authenticated component. This path should gracefully degrade if no credentials are configured.

- Add configuration for ND subscription credentials:
  - Environment variables: `ND_SUBSCRIPTION_USERNAME`, `ND_SUBSCRIPTION_PASSWORD`
  - Config check: if credentials not set, log warning and skip subscription features
- Subscription portal navigation requires Playwright:
  - Navigate to subscription login page
  - Authenticate with credentials
  - Use `playwright_include_page: True` to maintain session
  - Navigate to data sections:
    - Well Index (Excel download)
    - Scout tickets (well info, log tops, completion data, IP tests)
    - Production/injection histories by well/unit/field
    - GIS Map Server access
  - Download Excel files via Playwright download handling
  - Parse Excel with openpyxl (not just pandas -- government Excel files often have merged cells, multi-row headers)
- Handle session management carefully:
  - Maintain single session throughout scraping run
  - Do NOT open multiple concurrent sessions (risk of account lockout)
  - Implement session refresh if timeout detected

### Step 3: Implement ND Free Data PDF Processing Integration

Since free ND data is primarily PDFs, ensure integration with the OCR pipeline.

- Monthly production report PDFs contain tabular production data
- Route downloaded PDFs through the document processing pipeline (Task 2.4):
  - Classify as `PRODUCTION_REPORT`
  - Extract via PyMuPDF4LLM (if text-based) or PaddleOCR (if scanned)
  - Use PPStructureV3 for table extraction from production summaries
  - Extract: well counts, total oil/gas production by county/field, monthly totals
- Daily activity reports are simpler PDFs with well activity listings
  - Classify as appropriate type based on content
  - Extract API numbers, operator names, well names, activity types

### Step 4: Implement WY WOGCC Spider -- ArcGIS API Component (Primary)

Build the primary data access path via ArcGIS REST API.

- Create `backend/src/og_scraper/scrapers/spiders/wy_spider.py`:
  - Inherit from `BaseOGSpider`
  - Set: `state_code = "WY"`, `state_name = "Wyoming"`, `agency_name = "Oil & Gas Conservation Commission (WOGCC)"`, `base_url = "https://wogcc.wyo.gov/"`, `requires_playwright = True`
  - `custom_settings`: `DOWNLOAD_DELAY = 10`, `CONCURRENT_REQUESTS_PER_DOMAIN = 1`
- ArcGIS Wells MapServer endpoint (updated nightly):
  ```
  https://gis.deq.wyoming.gov/arcgis_443/rest/services/WOGCC_WELLS/MapServer/query?
    where=1%3D1&outFields=*&resultOffset=0&resultRecordCount=1000&f=json
  ```
- Implement ArcGIS pagination identical to NM spider (Task 6.1):
  - Parse JSON features, build WellItem objects
  - Check `exceededTransferLimit`, paginate with `resultOffset`
- Also query Geospatial Hub datasets:
  - Active Wells: `https://data.geospatialhub.org/datasets/46d3629e4e3b4ef6978cb5e6598f97bb_0`
  - Bottom Hole Data: `https://data.geospatialhub.org/datasets/290e6b5d473f47f783ef08691f613c87_0/geoservice`
  - WSGS Oil & Gas: `https://portal.wsgs.wyo.gov/ags/rest/services/OilGas/Data_layers/MapServer`

### Step 5: Implement WY WOGCC Spider -- Data Explorer (Playwright)

Add Playwright-based access to the Data Explorer for production data and well details.

- Data Explorer URL: `https://dataexplorer.wogcc.wyo.gov/`
- This is a modern JS-heavy web application requiring Playwright:
  - Use `meta={"playwright": True, "playwright_include_page": True}`
  - Wait for the application to load (JS framework initialization)
  - Navigate to well search, enter criteria
  - Extract production data, completion data, well details from rendered HTML
  - Handle JavaScript-driven pagination within the Data Explorer
- Implement as secondary data source to supplement ArcGIS API data

### Step 6: Implement WY WOGCC Spider -- Legacy Portal and Bulk Header

Add ColdFusion legacy portal access and bulk Excel download.

- Legacy Portal: `https://pipeline.wyo.gov/legacywogcce.cfm`
  - ColdFusion (.cfm) pages with quirky session management
  - May need Playwright for session handling
  - Access download menu for Well Header DB5 (Excel, ~114,000 wells)
- Well Header DB5 download:
  - Download the zipped Excel file
  - Parse with openpyxl for comprehensive well header data
  - This provides the most complete well header dataset for WY

### Step 7: Implement AK AOGCC Spider -- Data Miner Component

Build the Alaska spider using Data Miner ASP.NET export functionality.

- Create `backend/src/og_scraper/scrapers/spiders/ak_spider.py`:
  - Inherit from `BaseOGSpider`
  - Set: `state_code = "AK"`, `state_name = "Alaska"`, `agency_name = "Oil & Gas Conservation Commission (AOGCC)"`, `base_url = "https://www.commerce.alaska.gov/web/aogcc/"`, `requires_playwright = True`
  - `custom_settings`: `DOWNLOAD_DELAY = 5`, `CONCURRENT_REQUESTS_PER_DOMAIN = 2`
- Data Miner forms (NOTE: plain HTTP, not HTTPS):
  - Wells: `http://aogweb.state.ak.us/DataMiner4/Forms/Wells.aspx`
  - Well Data: `http://aogweb.state.ak.us/DataMiner4/Forms/WellData.aspx`
  - Well History: `http://aogweb.state.ak.us/DataMiner4/Forms/WellHistory.aspx`
  - Production: `http://aogweb.state.ak.us/DataMiner4/Forms/Production.aspx`
- For each Data Miner form:
  - Use Playwright to navigate to the form (plain HTTP -- configure Scrapy to allow HTTP)
  - Set filters or select "all" to get full table export
  - Click "Export As..." button to trigger server-side CSV generation
  - Handle file download via Playwright's download event handling
  - Parse downloaded CSV with pandas
- ASP.NET WebForms handling:
  - ViewState and PostBack patterns require Playwright for reliable interaction
  - Alternative: reverse-engineer the POST parameters (ViewState, EventValidation, etc.) for Scrapy `FormRequest`, but Playwright is more reliable
- For smaller datasets, consider downloading the full MS Access database:
  - Parse with `mdbtools` (CLI) or `pyodbc` for bulk import
  - This bypasses the Data Miner UI entirely

### Step 8: Implement AK AOGCC Spider -- ArcGIS Open Data Component

Add ArcGIS data access for spatial/GIS data.

- AK Division of Oil and Gas Open Data: `https://dog-soa-dnr.opendata.arcgis.com/`
- AOGCC Well Surface Locations: `https://data-soa-dnr.opendata.arcgis.com/maps/00a886f1c8954dc49e674881a3018000`
- Use standard ArcGIS REST API query pattern (same as NM and WY)
- Supplement Data Miner exports with GIS coordinate data

### Step 9: Set Up VCR.py Cassettes and HAR Recordings

- Create cassette directories: `backend/tests/scrapers/cassettes/nd/`, `wy/`, `ak/`
- ND cassettes:
  - `nd_monthly_production_pdf.yaml` -- Monthly production PDF download
  - `nd_daily_activity_index.yaml` -- Daily activity index HTML page
  - `nd_well_search.yaml` -- Well search form results
- ND HAR recordings (for Playwright interactions):
  - `nd_subscription_login.har` -- Subscription portal login flow (mocked)
  - `nd_well_search_form.har` -- Well search Classic ASP form interaction
- WY cassettes:
  - `wy_arcgis_wells_page1.yaml` -- ArcGIS well query page 1
  - `wy_arcgis_wells_page2.yaml` -- ArcGIS well query page 2
- WY HAR recordings:
  - `wy_data_explorer.har` -- Data Explorer Playwright session
  - `wy_legacy_portal.har` -- ColdFusion legacy portal session
- AK cassettes:
  - `ak_arcgis_wells.yaml` -- ArcGIS well query
- AK HAR recordings:
  - `ak_dataminer_wells_export.har` -- Data Miner wells export flow
  - `ak_dataminer_production_export.har` -- Data Miner production export flow

### Step 10: Write Tests

Create comprehensive tests for all three spiders.

- `backend/tests/scrapers/test_nd_spider.py`:
  - Test free-tier PDF URL generation for monthly production reports
  - Test daily activity index HTML parsing
  - Test well search form submission and result parsing
  - Test subscription credential check (graceful skip when not configured)
  - Mock Playwright tests for subscription portal navigation
  - VCR cassette replay for free-tier data
  - Integration test: ND spider (free tier) -> pipeline -> database
  - Edge case: confidential well handling (data withheld)

- `backend/tests/scrapers/test_wy_spider.py`:
  - Test ArcGIS JSON response parsing with WY-specific field names
  - Test ArcGIS pagination
  - Test Well Header DB5 Excel parsing
  - Mock Playwright tests for Data Explorer interaction
  - Test ColdFusion session handling
  - VCR cassette replay for ArcGIS queries
  - Integration test: WY spider -> pipeline -> database

- `backend/tests/scrapers/test_ak_spider.py`:
  - Test Data Miner CSV export parsing
  - Test plain HTTP (not HTTPS) request handling
  - Test ASP.NET ViewState/PostBack parameter extraction
  - Mock Playwright tests for export button click and download handling
  - Test ArcGIS Open Data query
  - VCR cassette replay for ArcGIS queries
  - Integration test: AK spider -> pipeline -> database
  - Test MS Access database import (if implemented)

## Files to Create

- `backend/src/og_scraper/scrapers/spiders/nd_spider.py` - North Dakota DMR spider (free + subscription tiers)
- `backend/src/og_scraper/scrapers/spiders/wy_spider.py` - Wyoming WOGCC spider (ArcGIS + Data Explorer + legacy)
- `backend/src/og_scraper/scrapers/spiders/ak_spider.py` - Alaska AOGCC spider (Data Miner + ArcGIS)
- `backend/tests/scrapers/test_nd_spider.py` - ND spider tests
- `backend/tests/scrapers/test_wy_spider.py` - WY spider tests
- `backend/tests/scrapers/test_ak_spider.py` - AK spider tests
- `backend/tests/scrapers/cassettes/nd/` - ND VCR cassettes
- `backend/tests/scrapers/cassettes/wy/` - WY VCR cassettes
- `backend/tests/scrapers/cassettes/ak/` - AK VCR cassettes
- `backend/tests/scrapers/fixtures/nd_well_search_results.html` - ND well search HTML fixture
- `backend/tests/scrapers/fixtures/wy_data_explorer.html` - WY Data Explorer HTML fixture
- `backend/tests/scrapers/fixtures/ak_dataminer_wells.csv` - AK Data Miner CSV fixture

## Files to Modify

- `backend/src/og_scraper/scrapers/state_registry.py` - Update ND, WY, AK entries with actual spider class references
- `backend/src/og_scraper/config.py` - Add ND subscription credential settings (`ND_SUBSCRIPTION_USERNAME`, `ND_SUBSCRIPTION_PASSWORD`)

## Contracts

### Provides (for downstream tasks)

- **ND Spider**: `NorthDakotaDMRSpider` class
  - Free tier: yields `DocumentItem` (PDFs for pipeline processing) and `WellItem` (from well search)
  - Subscription tier: yields `WellItem` (from Excel), `DocumentItem` (scout tickets, production histories)
  - Graceful degradation: works without subscription credentials (free tier only)
- **WY Spider**: `WyomingWOGCCSpider` class
  - Yields `WellItem` from ArcGIS API and Well Header DB5
  - Yields `DocumentItem` from Data Explorer (production data, completions)
  - Three data source paths: ArcGIS (primary), legacy Excel (secondary), Data Explorer (tertiary)
- **AK Spider**: `AlaskaAOGCCSpider` class
  - Yields `WellItem` and `DocumentItem` from Data Miner CSV exports
  - Yields `WellItem` from ArcGIS Open Data for spatial data
  - Handles plain HTTP connections

### Consumes (from upstream tasks)

- `BaseOGSpider` from Task 1.3: Base class for all three spiders
- `DocumentItem`, `WellItem` from Task 1.3: Item classes for yielded data
- `DocumentPipeline` from Task 2.4: Full 7-stage processing pipeline (especially OCR for ND PDFs)
- Database models from Task 1.2: `wells`, `documents`, `extracted_data` tables
- State registry from Task 1.3: ND, WY, AK configuration entries

## Acceptance Criteria

- [ ] ND spider downloads free-tier monthly production PDFs for configurable date range
- [ ] ND spider parses daily activity report index and downloads linked PDFs
- [ ] ND spider extracts basic well headers from well search form
- [ ] ND spider gracefully skips subscription features when credentials are not configured
- [ ] ND spider logs clear warning about subscription-only data being unavailable
- [ ] ND spider authenticates and downloads subscription data when credentials are provided (tested with mocks)
- [ ] WY spider queries ArcGIS Wells MapServer with correct pagination
- [ ] WY spider downloads and parses Well Header DB5 Excel file
- [ ] WY spider uses Playwright to navigate Data Explorer for production data
- [ ] WY spider handles ColdFusion legacy portal session management
- [ ] AK spider navigates Data Miner forms via Playwright and exports CSV
- [ ] AK spider handles plain HTTP (not HTTPS) connections correctly
- [ ] AK spider queries ArcGIS Open Data for well surface locations
- [ ] All three spiders feed items into the full pipeline and store in database
- [ ] All three spiders have VCR.py cassettes for reproducible testing
- [ ] All tests pass
- [ ] Build succeeds

## Testing Protocol

### Unit/Integration Tests

- Test file: `backend/tests/scrapers/test_nd_spider.py`
- Test cases:
  - [ ] Monthly PDF URL generation for date range (e.g., 2020-01 through 2026-03)
  - [ ] Daily activity index HTML parsing extracts correct PDF links
  - [ ] Well search form submission with ViewState handling
  - [ ] Well search result HTML parsing extracts all header fields
  - [ ] Subscription credential detection and graceful skip
  - [ ] Mock Playwright: subscription login flow
  - [ ] VCR replay: free-tier PDF download and index parsing
  - [ ] Integration: free-tier items -> pipeline -> database

- Test file: `backend/tests/scrapers/test_wy_spider.py`
- Test cases:
  - [ ] ArcGIS JSON parsing with WY-specific attribute names
  - [ ] ArcGIS pagination (offset increments by 1000)
  - [ ] Well Header DB5 Excel parsing handles merged cells and multi-row headers
  - [ ] Mock Playwright: Data Explorer search and result extraction
  - [ ] Mock Playwright: legacy portal session and download
  - [ ] VCR replay: ArcGIS well query with pagination
  - [ ] Integration: all data sources -> pipeline -> database

- Test file: `backend/tests/scrapers/test_ak_spider.py`
- Test cases:
  - [ ] Data Miner CSV parsing for wells, well data, production forms
  - [ ] Plain HTTP URL handling (no SSL)
  - [ ] Mock Playwright: form navigation, filter setting, export button click, download
  - [ ] ArcGIS well surface location query
  - [ ] VCR replay: ArcGIS query
  - [ ] Integration: Data Miner exports -> pipeline -> database
  - [ ] Edge case: empty export (no matching records)

### API/Script Testing

- Run each spider against VCR cassettes: `uv run scrapy crawl nd_dmr`, `uv run scrapy crawl wy_wogcc`, `uv run scrapy crawl ak_aogcc`
- Verify items appear in PostgreSQL tables for each state

### Build/Lint/Type Checks

- [ ] `uv run pytest backend/tests/scrapers/test_nd_spider.py` passes
- [ ] `uv run pytest backend/tests/scrapers/test_wy_spider.py` passes
- [ ] `uv run pytest backend/tests/scrapers/test_ak_spider.py` passes
- [ ] `uv run ruff check backend/src/og_scraper/scrapers/spiders/` passes
- [ ] `uv run ruff format --check backend/src/og_scraper/scrapers/spiders/` passes

## Skills to Read

- `scrapy-playwright-scraping` - Playwright integration patterns, PageMethod usage, errback handling, per-state rate limits
- `state-regulatory-sites` - ND subscription details, WY Data Explorer/legacy portal URLs, AK Data Miner forms and quirks
- `document-processing-pipeline` - OCR processing for ND PDF documents, table extraction from production reports

## Research Files to Read

- `.claude/orchestration-og-doc-scraper/research/per-state-scrapers-implementation.md` - ND subscription tiers and free data URLs, WY adapter strategy across three sources, AK Data Miner forms and export pattern
- `.claude/orchestration-og-doc-scraper/research/state-regulatory-sites.md` - ND/WY/AK regulatory body details, anti-bot protections, data format specifics

## Git

- Branch: `feature/phase-6-nd-wy-ak-scrapers`
- Commit message prefix: `Task 6.2:`
