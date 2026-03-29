# Task 6.1: Texas & New Mexico Scrapers

## Objective

Implement the Texas Railroad Commission (RRC) bulk download spider with EBCDIC encoding support and the New Mexico Oil Conservation Division (OCD) spider with ArcGIS REST API access and OCD Permitting portal navigation. These are the two largest oil-producing states in the US (42.9% and 15.1% of US oil, respectively) and represent the highest data-volume scrapers in the project.

## Context

Phase 6 implements the remaining 7 state scrapers after Phase 4 proved the pipeline end-to-end with PA, CO, and OK. Task 6.1 tackles the two highest-production states. Texas is unique for its EBCDIC mainframe data encoding (the only state using it). New Mexico requires integrating multiple fragmented data systems (OCD Hub, OCD Permitting, ONGARD, GO-TECH). Both spiders must feed scraped data into the existing 7-stage document processing pipeline (Phase 2) and store results in PostgreSQL (Phase 1).

## Dependencies

- **Task 1.3** - Provides `BaseOGSpider` adapter class, Scrapy settings, download pipeline, state registry
- **Task 2.4** - Provides the full 7-stage document processing pipeline (extract -> classify -> normalize -> validate -> score -> route)
- **Task 1.2** - Provides database schema (wells, documents, extracted_data tables)

## Blocked By

- Task 1.3 (base scraper framework must exist)
- Task 2.4 (pipeline must be operational to process scraped documents)

## Research Findings

Key findings from research files relevant to this task:

- From `per-state-scrapers-implementation.md`: TX RRC provides extensive bulk downloads via `mft.rrc.texas.gov` with static GUIDs per dataset. CRITICAL: DO NOT scrape the Production Data Query (PDQ) web interface -- RRC explicitly detects and blocks automated tools, terminating sessions.
- From `per-state-scrapers-implementation.md`: TX production data is available in both EBCDIC and CSV formats. The monthly PDQ Dump (CSV) provides the same data as EBCDIC ledger files. Prefer CSV; use EBCDIC only for datasets not available in CSV/ASCII.
- From `per-state-scrapers-implementation.md`: EBCDIC files use IBM mainframe encoding with COMP-3 (packed decimal) fields. Code page is `cp037` (US/Canada). Use `ebcdic-parser` library with JSON layout definitions derived from RRC-provided PDF manuals.
- From `per-state-scrapers-implementation.md`: NM data is spread across four fragmented systems: OCD Hub (ArcGIS), OCD Permitting (ASP.NET), ONGARD (State Land Office), GO-TECH (NM Tech). No single unified source.
- From `per-state-scrapers-implementation.md`: NM ArcGIS REST API limits results to 1,000-2,000 records per query. Must paginate with `resultOffset` and `resultRecordCount`.
- From `state-regulatory-sites.md`: TX data formats include EBCDIC (.ebc, .ebc.Z), ASCII fixed-width, CSV, JSON, dBase (.dbf), PDF, TIFF, Shapefile. Many downloads are compressed with .Z (Unix compress) or .zip.
- From `state-regulatory-sites.md`: NM OCD Permitting uses ASP.NET with ViewState. Can use Scrapy `FormRequest` but may need Playwright for complex interactions. ONGARD production data is managed by NM State Land Office, separate from OCD.

## Implementation Plan

### Step 1: Create TX EBCDIC Parser and Layout Definitions

Create the EBCDIC parsing utility that converts IBM mainframe EBCDIC data to UTF-8 CSV. This is the most technically unique component in the entire scraper system.

- Install `ebcdic-parser` package (already in project dependencies from Phase 1)
- Create `backend/src/og_scraper/scrapers/utils/ebcdic.py` with:
  - Wrapper around `ebcdic_parser.convert.run()` for batch conversion
  - COMP-3 (packed decimal) decoder function for numeric fields
  - .Z (Unix compress) and .zip decompression handling
  - Code page `cp037` (US/Canada EBCDIC) as default
- Create JSON layout definition files in `backend/src/og_scraper/scrapers/config/tx_layouts/`:
  - `wellbore.json` -- Full wellbore dataset (record length ~1200 bytes)
  - `oil_ledger.json` -- Oil production ledger
  - `gas_ledger.json` -- Gas production ledger
  - `production.json` -- Statewide production (oil and gas)
  - `drilling_permit.json` -- Drilling permit records
- Layout JSON format:
  ```json
  {
    "record_length": 1200,
    "encoding": "cp037",
    "fields": [
      {"name": "API_NUMBER", "type": "string", "start": 1, "length": 14},
      {"name": "OPERATOR_NUMBER", "type": "string", "start": 15, "length": 6},
      {"name": "OIL_PRODUCTION", "type": "packedDecimal", "start": 59, "length": 5}
    ]
  }
  ```
- Field positions must be derived from RRC-provided PDF layout manuals. For initial implementation, create layout files for the most critical datasets (wellbore, production). Mark others as TODO with placeholder layouts.

### Step 2: Create TX Fixed-Width ASCII Parser

Many TX datasets use fixed-width ASCII format (no delimiters, fields at fixed byte positions).

- Create `backend/src/og_scraper/scrapers/utils/fixed_width.py` with:
  - Generic fixed-width record parser that accepts layout definitions
  - Reuse the same JSON layout format as EBCDIC but with `"encoding": "ascii"`
  - Handle field types: string, integer, decimal, date (various TX date formats)
- Create layout files for ASCII datasets:
  - `completion_info.json` -- Completion information (nightly updates)
  - `permit_daily.json` -- Drilling permits with coordinates (nightly updates)
  - `inspections.json` -- Inspections/violations ICE data (weekly)

### Step 3: Implement TX RRC Spider

Create the Texas spider using the `BulkDownloadSpider` pattern. No Playwright needed.

- Create `backend/src/og_scraper/scrapers/spiders/tx_spider.py`:
  - Inherit from `BaseOGSpider`
  - Set: `state_code = "TX"`, `state_name = "Texas"`, `agency_name = "Railroad Commission of Texas (RRC)"`, `base_url = "https://www.rrc.texas.gov/"`, `requires_playwright = False`
  - `custom_settings`: `DOWNLOAD_DELAY = 10`, `CONCURRENT_REQUESTS_PER_DOMAIN = 2`
  - Implement `start_requests()` to yield download requests for each bulk dataset
- Bulk download URLs (via `mft.rrc.texas.gov` GUIDs):

  **Production Data (primary -- use CSV first):**
  - PDQ Dump (CSV, last Saturday/month): `https://mft.rrc.texas.gov/link/1f5ddb8d-329a-4459-b7f8-177b4f5ee60d`
  - Statewide Production Oil (EBCDIC, monthly): `https://mft.rrc.texas.gov/link/20ff2205-6579-450f-a2ee-cbd37986b557`
  - Statewide Production Gas (EBCDIC, monthly): `https://mft.rrc.texas.gov/link/22b56e60-e700-4ee0-a718-9a4bb690f3c8`
  - Oil Ledger all districts (EBCDIC, monthly): `https://mft.rrc.texas.gov/link/c5081c77-d32c-4ded-9b33-5aca3833306c`
  - Gas Ledger all districts (EBCDIC, monthly): `https://mft.rrc.texas.gov/link/c45ee840-9d50-4a74-b6b0-dba0cb4954b7`

  **Well Data:**
  - Full Wellbore (EBCDIC + ASCII, weekly): `https://mft.rrc.texas.gov/link/b070ce28-5c58-4fe2-9eb7-8b70befb7af9`
  - Completion Info (ASCII, nightly): `https://mft.rrc.texas.gov/link/ed7ab066-879f-40b6-8144-2ae4b6810c04`
  - Imaged Completion Files (PDF, nightly): `https://mft.rrc.texas.gov/link/8e91acb8-69cc-4d57-ad72-c7f7d5a7675e`

  **Drilling Permits:**
  - Permit Daily w/ Coords (ASCII, nightly): `https://mft.rrc.texas.gov/link/5f07cc72-2e79-4df8-ade1-9aeb792e03fc`
  - Permit Master (ASCII, monthly): `https://mft.rrc.texas.gov/link/e99fbe81-40cd-4a79-b992-9fc71d0f06d4`
  - W-1 Imaged Permits (PDF, nightly): `https://mft.rrc.texas.gov/link/f11363bb-8120-4e8c-bbc0-a253ec0a85d4`

  **Regulatory:**
  - Inspections/Violations ICE (TXT, weekly): `https://mft.rrc.texas.gov/link/c7c28dc9-b218-4f0a-8278-bf15d009def1`
  - P5 Organization/Operators (ASCII+EBCDIC, monthly): `https://mft.rrc.texas.gov/link/04652169-eed6-4396-9019-2e270e790f6c`

  **GIS:**
  - Well Layers by County (Shapefile, twice weekly): `https://mft.rrc.texas.gov/link/d551fb20-442e-4b67-84fa-ac3f23ecabb4`
  - Statewide API Data (dBase, twice weekly): `https://mft.rrc.texas.gov/link/1eb94d66-461d-4114-93f7-b4bc04a70674`

- Implement parse callbacks that route files by format:
  - CSV files -> `parse_csv()` (pandas)
  - EBCDIC files -> `parse_ebcdic()` (ebcdic_parser with layout JSON)
  - ASCII fixed-width -> `parse_fixed_width()` (custom parser)
  - PDF files -> store as-is for OCR pipeline
  - dBase (.dbf) -> `parse_dbase()` (dbfread library)
  - Compressed (.Z, .zip) -> decompress first, then route

### Step 4: Implement NM OCD Spider -- ArcGIS API Component

Create the primary NM spider using the `ArcGISAPISpider` pattern.

- Create `backend/src/og_scraper/scrapers/spiders/nm_spider.py`:
  - Inherit from `BaseOGSpider`
  - Set: `state_code = "NM"`, `state_name = "New Mexico"`, `agency_name = "Oil Conservation Division (OCD)"`, `base_url = "https://www.emnrd.nm.gov/ocd/"`, `requires_playwright = False` (primary path)
  - `custom_settings`: `DOWNLOAD_DELAY = 5`, `CONCURRENT_REQUESTS_PER_DOMAIN = 2`
- ArcGIS REST API endpoints:
  - Wells Feature Service (MapServer): `https://mapservice.nmstatelands.org/arcgis/rest/services/Public/NMOCD_Wells_V3/MapServer/5`
  - Hub Dataset for download: `https://ocd-hub-nm-emnrd.hub.arcgis.com/datasets/dd971b8e25c54d1a8ab7c549244cf3cc`
- Implement `start_requests()` with ArcGIS query:
  ```
  https://mapservice.nmstatelands.org/arcgis/rest/services/Public/NMOCD_Wells_V3/MapServer/5/query?
    where=1%3D1&outFields=*&resultOffset=0&resultRecordCount=1000&f=json
  ```
- Implement `parse_api_response()`:
  - Parse JSON response, extract features array
  - For each feature, build `WellItem` from `feature["attributes"]`
  - Check `exceededTransferLimit` flag to determine if more pages exist
  - If more pages, yield next request with `resultOffset` incremented by 1000
- Also implement bulk CSV download from OCD Hub as a fallback/alternative path

### Step 5: Implement NM OCD Spider -- Permitting Portal Component

Add OCD Permitting portal access for permit documents (C-101, C-102, C-103, C-115, C-145).

- OCD Permitting URLs:
  - Portal: `https://wwwapps.emnrd.nm.gov/ocd/ocdpermitting/`
  - Wells Search: `https://wwwapps.emnrd.nm.gov/ocd/ocdpermitting/data/wells.aspx`
  - Well Details: `https://wwwapps.emnrd.nm.gov/ocd/ocdpermitting/Data/WellDetails.aspx?api={API_NUMBER}`
- The OCD Permitting portal is ASP.NET with ViewState. Use Scrapy `FormRequest` for simple queries. If ViewState handling is too complex, fall back to Playwright with `meta={"playwright": True}`.
- Implement `parse_well_search()` to extract well listings from search results
- Implement `parse_well_details()` to extract per-well document links and metadata
- For each well, follow links to download available permit documents (C-101, C-103, etc.)

### Step 6: Implement NM ONGARD Access (Production Data)

ONGARD is managed by NM State Land Office (separate from OCD) and contains production data.

- ONGARD URL: `https://www.nmstatelands.org/divisions/oil-gas-and-minerals/ongard-and-data-resources/`
- Determine if ONGARD provides direct data download or requires form interaction
- If form-based, use Playwright for navigation
- As a fallback, use the ArcGIS Hub's production-related datasets from Step 4

### Step 7: Set Up VCR.py Cassettes and HAR Recordings

- Create `backend/tests/scrapers/cassettes/tx/` directory
- Record cassettes for TX:
  - `tx_pdq_dump_download.yaml` -- Response from CSV PDQ dump URL
  - `tx_wellbore_download.yaml` -- Response from wellbore bulk download
  - `tx_permit_daily_download.yaml` -- Response from permit daily download
- Create `backend/tests/scrapers/cassettes/nm/` directory
- Record cassettes for NM:
  - `nm_arcgis_wells_page1.yaml` -- First page of ArcGIS well query
  - `nm_arcgis_wells_page2.yaml` -- Second page (pagination test)
  - `nm_ocd_well_search.yaml` -- OCD Permitting search results
  - `nm_ocd_well_details.yaml` -- OCD Permitting well details page
- For Playwright-dependent NM interactions, record HAR files:
  - `nm_ocd_permitting.har` -- Full session recording of OCD Permitting navigation

### Step 8: Write Tests

Create comprehensive tests for both spiders:

- `backend/tests/scrapers/test_tx_spider.py`:
  - Test EBCDIC parsing with known input/output pairs
  - Test COMP-3 packed decimal decoding
  - Test fixed-width ASCII parsing
  - Test CSV PDQ dump parsing
  - Test file decompression (.Z, .zip)
  - Test spider routes files correctly by format
  - VCR cassette replay test for bulk download flow
  - Integration test: TX spider -> pipeline -> database

- `backend/tests/scrapers/test_nm_spider.py`:
  - Test ArcGIS JSON response parsing
  - Test pagination (exceededTransferLimit handling)
  - Test OCD Permitting HTML parsing
  - Test well details extraction
  - VCR cassette replay for ArcGIS queries
  - Integration test: NM spider -> pipeline -> database

- `backend/tests/scrapers/test_ebcdic.py`:
  - Test EBCDIC to UTF-8 conversion with cp037 code page
  - Test COMP-3 decoding for positive, negative, and zero values
  - Test layout JSON loading and field extraction
  - Test error handling for corrupt/truncated EBCDIC records

## Files to Create

- `backend/src/og_scraper/scrapers/spiders/tx_spider.py` - Texas RRC bulk download spider
- `backend/src/og_scraper/scrapers/spiders/nm_spider.py` - New Mexico OCD spider (ArcGIS + Permitting)
- `backend/src/og_scraper/scrapers/utils/ebcdic.py` - EBCDIC parser wrapper with COMP-3 support
- `backend/src/og_scraper/scrapers/utils/fixed_width.py` - Fixed-width ASCII record parser
- `backend/src/og_scraper/scrapers/config/tx_layouts/wellbore.json` - TX wellbore EBCDIC layout
- `backend/src/og_scraper/scrapers/config/tx_layouts/oil_ledger.json` - TX oil ledger EBCDIC layout
- `backend/src/og_scraper/scrapers/config/tx_layouts/gas_ledger.json` - TX gas ledger EBCDIC layout
- `backend/src/og_scraper/scrapers/config/tx_layouts/production.json` - TX production EBCDIC layout
- `backend/src/og_scraper/scrapers/config/tx_layouts/drilling_permit.json` - TX permit ASCII layout
- `backend/src/og_scraper/scrapers/config/tx_layouts/completion_info.json` - TX completion ASCII layout
- `backend/tests/scrapers/test_tx_spider.py` - TX spider tests
- `backend/tests/scrapers/test_nm_spider.py` - NM spider tests
- `backend/tests/scrapers/test_ebcdic.py` - EBCDIC parser unit tests
- `backend/tests/scrapers/cassettes/tx/` - TX VCR cassette directory
- `backend/tests/scrapers/cassettes/nm/` - NM VCR cassette directory

## Files to Modify

- `backend/src/og_scraper/scrapers/state_registry.py` - Update TX and NM entries with actual spider class references (replacing placeholders)

## Contracts

### Provides (for downstream tasks)

- **TX Spider**: `TexasRRCSpider` class at `backend/src/og_scraper/scrapers/spiders/tx_spider.py`
  - Yields `DocumentItem` and `WellItem` objects through the standard pipeline
  - Supports all TX document types: production reports, well permits (W-1), completions, directional surveys, inspections (ICE), operators (P-5)
- **NM Spider**: `NewMexicoOCDSpider` class at `backend/src/og_scraper/scrapers/spiders/nm_spider.py`
  - Yields `WellItem` from ArcGIS API queries
  - Yields `DocumentItem` from OCD Permitting portal (C-101, C-103, C-115 forms)
- **EBCDIC Parser**: `parse_ebcdic(input_file, layout_file, output_dir)` -> CSV files
- **Fixed-Width Parser**: `parse_fixed_width(input_file, layout_file)` -> list of dicts
- **TX Layout JSON Files**: Reusable layout definitions for each TX dataset

### Consumes (from upstream tasks)

- `BaseOGSpider` from Task 1.3: Base class for both spiders
- `DocumentItem`, `WellItem` from Task 1.3: Item classes for yielded data
- `DocumentPipeline` from Task 2.4: Full 7-stage processing pipeline
- Database models from Task 1.2: `wells`, `documents`, `extracted_data` tables
- State registry from Task 1.3: TX and NM entries for spider configuration

## Acceptance Criteria

- [ ] TX spider downloads bulk files from mft.rrc.texas.gov via standard HTTP
- [ ] TX EBCDIC parser converts EBCDIC files to readable CSV using cp037 code page
- [ ] TX COMP-3 packed decimal fields are correctly decoded to numeric values
- [ ] TX fixed-width ASCII parser extracts fields at correct byte positions
- [ ] TX spider prefers CSV PDQ dump over EBCDIC when both are available
- [ ] TX spider handles .Z and .zip decompression
- [ ] TX spider does NOT access the PDQ web interface (webapps2.rrc.texas.gov)
- [ ] NM spider queries ArcGIS REST API with correct pagination
- [ ] NM spider paginates through all results using resultOffset increments of 1000
- [ ] NM spider accesses OCD Permitting portal for permit documents
- [ ] NM spider handles ASP.NET ViewState in form submissions
- [ ] Both spiders yield items that pass through the full pipeline to database storage
- [ ] Both spiders have VCR.py cassettes for reproducible testing
- [ ] All tests pass
- [ ] Build succeeds

## Testing Protocol

### Unit/Integration Tests

- Test file: `backend/tests/scrapers/test_tx_spider.py`
- Test cases:
  - [ ] EBCDIC file conversion produces UTF-8 output with correct field values
  - [ ] COMP-3 decoding: positive numbers, negative numbers, zero, max values
  - [ ] Fixed-width ASCII parsing extracts fields at correct positions
  - [ ] CSV PDQ dump parses correctly into WellItem/DocumentItem
  - [ ] Spider correctly routes EBCDIC, ASCII, CSV, and PDF files to appropriate parsers
  - [ ] Decompression handles .Z and .zip formats
  - [ ] VCR cassette replay: full bulk download flow produces expected items

- Test file: `backend/tests/scrapers/test_nm_spider.py`
- Test cases:
  - [ ] ArcGIS JSON response parsing extracts well attributes correctly
  - [ ] Pagination continues when `exceededTransferLimit` is true
  - [ ] Pagination stops when `exceededTransferLimit` is false or absent
  - [ ] OCD Permitting HTML is parsed correctly for well listings
  - [ ] Well details page extraction works for all document types (C-101 through C-145)
  - [ ] VCR cassette replay: full ArcGIS query flow produces expected items

- Test file: `backend/tests/scrapers/test_ebcdic.py`
- Test cases:
  - [ ] cp037 character conversion for all printable characters
  - [ ] COMP-3 decode for known byte sequences
  - [ ] Layout JSON schema validation
  - [ ] Error handling for truncated records, missing fields, corrupt data

### API/Script Testing

- Run TX spider against VCR cassettes: `uv run scrapy crawl tx_rrc` (with cassettes)
- Run NM spider against VCR cassettes: `uv run scrapy crawl nm_ocd` (with cassettes)
- Verify items appear in PostgreSQL `wells` and `documents` tables

### Build/Lint/Type Checks

- [ ] `uv run pytest backend/tests/scrapers/test_tx_spider.py` passes
- [ ] `uv run pytest backend/tests/scrapers/test_nm_spider.py` passes
- [ ] `uv run pytest backend/tests/scrapers/test_ebcdic.py` passes
- [ ] `uv run ruff check backend/src/og_scraper/scrapers/` passes
- [ ] `uv run ruff format --check backend/src/og_scraper/scrapers/` passes

## Skills to Read

- `scrapy-playwright-scraping` - Base spider patterns, Scrapy settings, per-state adapter architecture, EBCDIC handling guidance
- `state-regulatory-sites` - TX and NM specific URLs, data formats, quirks, rate limits
- `document-processing-pipeline` - Pipeline integration for processing scraped documents

## Research Files to Read

- `.claude/orchestration-og-doc-scraper/research/per-state-scrapers-implementation.md` - Detailed TX bulk download URLs, EBCDIC layout examples, NM ArcGIS endpoints, adapter strategies
- `.claude/orchestration-og-doc-scraper/research/state-regulatory-sites.md` - TX and NM regulatory site analysis, document types, data access methods

## Git

- Branch: `feature/phase-6-tx-nm-scrapers`
- Commit message prefix: `Task 6.1:`
