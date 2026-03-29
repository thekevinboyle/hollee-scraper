# Task 4.1: Pennsylvania Scraper (GreenPort CSV)

## Objective

Implement the PA DEP GreenPort scraper -- the easiest state to scrape. Pennsylvania provides all oil and gas data as on-demand CSV exports from GreenPort Report Extracts. This spider downloads CSV files for production, well inventory, compliance, plugging, and waste reports, parses them, and feeds structured data through the document processing pipeline into the database.

## Context

This is the first state scraper built in the project (Phase 4). It serves as the proof-of-concept that validates the full end-to-end pipeline: scrape -> download -> pipeline -> database -> API. PA was chosen first because it has the simplest data access pattern (direct CSV downloads, no Playwright, no authentication, no complex pagination). Tasks 4.2 (CO) and 4.3 (OK) follow and build on patterns established here. The Phase 4 regression test (4.R) will verify all three states work together.

## Dependencies

- Task 1.3 - Provides `BaseOGSpider` abstract class, `DocumentItem` dataclass, Scrapy settings, download pipeline, state registry
- Task 2.4 - Provides `DocumentPipeline.process()` for routing documents through classification, extraction, normalization, validation, confidence scoring

## Blocked By

- 1.3, 2.4

## Research Findings

Key findings from research files relevant to this task:

- From `state-regulatory-sites.md`: PA is rated **Easy** difficulty, 1-2 dev days. GreenPort CSV exports are designed for public bulk access. No authentication, no Playwright needed. Rate limit: 3s base delay, 4 max concurrent requests.
- From `per-state-scrapers-implementation.md`: Spider type is `BulkDownloadSpider`. Each GreenPort report requires selecting a reporting period parameter (year/quarter), then downloading the CSV. May need ASP.NET ViewState handling for form submission. Data dictionary PDF defines all fields.
- From `state-regulatory-sites.md`: PA state code for API numbers is `37` (FIPS code). Primary activity is unconventional gas (Marcellus/Utica Shale). No spacing/pooling orders -- compliance and permitting are the key regulatory documents.
- From `scrapy-playwright-scraping.md`: PA is in the `BulkDownloadSpider` category. `requires_playwright = False`. State registry config: `rate_limit_seconds: 3`, `data_formats: ["CSV"]`.

## Implementation Plan

### Step 1: Create PA Spider Class

Create `backend/src/og_scraper/scrapers/spiders/pa_spider.py` inheriting from `BaseOGSpider`.

**Class attributes:**
```python
state_code = "PA"
state_name = "Pennsylvania"
agency_name = "Dept of Environmental Protection (DEP)"
base_url = "https://greenport.pa.gov/ReportExtracts/OG/Index"
requires_playwright = False

custom_settings = {
    'DOWNLOAD_DELAY': 3,
    'CONCURRENT_REQUESTS_PER_DOMAIN': 4,
    'AUTOTHROTTLE_ENABLED': True,
    'AUTOTHROTTLE_START_DELAY': 3,
    'AUTOTHROTTLE_MAX_DELAY': 30,
    'AUTOTHROTTLE_TARGET_CONCURRENCY': 2.0,
}
```

**GreenPort Report URLs (exact endpoints):**

| Report | URL |
|--------|-----|
| Production Report | `https://greenport.pa.gov/ReportExtracts/OG/OilGasWellProdReport` |
| Well Inventory | `https://greenport.pa.gov/ReportExtracts/OG/OilGasWellInventoryReport` |
| Compliance Report | `https://greenport.pa.gov/ReportExtracts/OG/OilComplianceReport` |
| Plugged Wells | `https://greenport.pa.gov/ReportExtracts/OG/OGPluggedWellsReport` |
| Well Waste Report | `https://greenport.pa.gov/ReportExtracts/OG/OilGasWellWasteReport` |
| Production Not Submitted | `https://greenport.pa.gov/ReportExtracts/OG/WellNotSubReport` |

**Data Dictionary (for field mapping):**
`https://files.dep.state.pa.us/oilgas/bogm/bogmportalfiles/oilgasreports/HelpDocs/SSRS_Report_Data_Dictionary/DEP_Oil_and_GAS_Reports_Data_Dictionary.pdf`

### Step 2: Implement start_requests()

GreenPort reports require reporting period parameters. Implement `start_requests()` to:

1. First, fetch the GreenPort index page to discover available reporting periods.
2. For each report type, construct HTTP requests with reporting period parameters (year/quarter).
3. The reports are ASP.NET server-rendered pages. Use Scrapy `FormRequest` if ViewState is needed, or direct GET/POST with query parameters if the reports support direct URL parameters.

**Parameter strategy:** Start with the well inventory report (no period parameter needed -- it returns current statewide data). Then iterate production reports across recent periods (e.g., last 8 quarters).

```python
def start_requests(self):
    # Well Inventory -- current snapshot, no period needed
    yield scrapy.Request(
        url="https://greenport.pa.gov/ReportExtracts/OG/OilGasWellInventoryReport",
        callback=self.parse_report_page,
        meta={"report_type": "well_inventory"},
    )
    # Production Reports -- need period parameter
    yield scrapy.Request(
        url="https://greenport.pa.gov/ReportExtracts/OG/OilGasWellProdReport",
        callback=self.parse_report_page,
        meta={"report_type": "production"},
    )
    # Compliance, Plugged Wells, Waste -- additional report types
    for report_type, path in self.REPORT_URLS.items():
        yield scrapy.Request(
            url=f"https://greenport.pa.gov/ReportExtracts/OG/{path}",
            callback=self.parse_report_page,
            meta={"report_type": report_type},
        )
```

### Step 3: Implement Report Page Parsing and CSV Download

Each GreenPort report page has an "Export" or "Download" button that generates a CSV. Implement:

1. `parse_report_page()` -- Extract the form action, any hidden fields (ViewState, event validation), and available reporting periods from dropdowns. Submit the form to trigger CSV generation.
2. `parse_csv_download()` -- Handle the CSV response. If the response is the CSV data directly, parse it. If it redirects to a download link, follow the redirect.

**ViewState handling pattern (if needed):**
```python
def parse_report_page(self, response):
    viewstate = response.css('input#__VIEWSTATE::attr(value)').get()
    event_validation = response.css('input#__EVENTVALIDATION::attr(value)').get()

    yield scrapy.FormRequest.from_response(
        response,
        formdata={
            '__VIEWSTATE': viewstate,
            '__EVENTVALIDATION': event_validation,
            'ctl00$ContentPlaceHolder1$ddlYear': '2025',
            'ctl00$ContentPlaceHolder1$ddlQuarter': 'Q4',
            'ctl00$ContentPlaceHolder1$btnExport': 'Export',
        },
        callback=self.parse_csv_response,
        meta=response.meta,
    )
```

### Step 4: Implement CSV Parsing

Parse the downloaded CSV data and yield `DocumentItem` / `WellItem` objects. Use the PA data dictionary for field mapping.

**Production Report CSV expected fields:**
- Well API Number, Operator Name, Well Name, County, Municipality
- Reporting Period (Year/Quarter)
- Oil Production (BBL), Gas Production (MCF), Condensate (BBL), Water Production (BBL)
- Days Produced

**Well Inventory CSV expected fields:**
- Well API Number, Permit Number, Operator Name, Well Name
- County, Municipality, Latitude, Longitude
- Well Type, Well Status, Spud Date, Total Depth
- Farm Name, Configuration (Conventional/Unconventional)

**Parsing implementation:**
```python
import csv
import io

def parse_csv_response(self, response):
    report_type = response.meta["report_type"]
    reader = csv.DictReader(io.StringIO(response.text))

    for row in reader:
        if report_type == "well_inventory":
            yield self.build_well_item(
                api_number=self.normalize_api_number(row.get("Well API Number", "")),
                well_name=row.get("Well Name", "").strip(),
                operator_name=row.get("Operator Name", "").strip(),
                county=row.get("County", "").strip(),
                latitude=self._parse_float(row.get("Latitude")),
                longitude=self._parse_float(row.get("Longitude")),
                well_type=row.get("Well Type", "").strip(),
                well_status=row.get("Well Status", "").strip(),
                spud_date=row.get("Spud Date", "").strip(),
                total_depth=self._parse_float(row.get("Total Depth")),
                permit_number=row.get("Permit Number", "").strip(),
                configuration=row.get("Configuration", "").strip(),
            )
        elif report_type == "production":
            yield self.build_document_item(
                api_number=self.normalize_api_number(row.get("Well API Number", "")),
                doc_type="production_report",
                operator_name=row.get("Operator Name", "").strip(),
                well_name=row.get("Well Name", "").strip(),
                raw_metadata={
                    "oil_bbls": self._parse_float(row.get("Oil Production")),
                    "gas_mcf": self._parse_float(row.get("Gas Production")),
                    "water_bbls": self._parse_float(row.get("Water Production")),
                    "condensate_bbls": self._parse_float(row.get("Condensate")),
                    "days_produced": self._parse_int(row.get("Days Produced")),
                    "reporting_period": row.get("Reporting Period", "").strip(),
                },
            )
```

### Step 5: Implement Helper Methods

```python
@staticmethod
def _parse_float(value: str | None) -> float | None:
    """Parse a float value, returning None for empty/invalid."""
    if not value or not value.strip():
        return None
    try:
        return float(value.strip().replace(",", ""))
    except (ValueError, TypeError):
        return None

@staticmethod
def _parse_int(value: str | None) -> int | None:
    """Parse an integer value, returning None for empty/invalid."""
    if not value or not value.strip():
        return None
    try:
        return int(value.strip().replace(",", ""))
    except (ValueError, TypeError):
        return None
```

### Step 6: Record VCR.py Cassettes

Record real HTTP responses from GreenPort for deterministic test replay.

**Cassette recording procedure:**

1. Create cassette directory: `backend/tests/scrapers/cassettes/pa/`
2. Write a recording script that fetches real responses from each GreenPort endpoint:

```python
# backend/tests/scrapers/record_pa_cassettes.py
import vcr

my_vcr = vcr.VCR(
    cassette_library_dir='backend/tests/scrapers/cassettes/pa',
    record_mode='new_episodes',
    match_on=['uri', 'method', 'body'],
    decode_compressed_response=True,
)

# Record each report endpoint
with my_vcr.use_cassette('greenport_index.yaml'):
    # fetch https://greenport.pa.gov/ReportExtracts/OG/Index
    pass

with my_vcr.use_cassette('greenport_well_inventory.yaml'):
    # fetch well inventory report page + CSV export
    pass

with my_vcr.use_cassette('greenport_production.yaml'):
    # fetch production report page + CSV export for one period
    pass
```

3. Each cassette file captures: the report page HTML (with ViewState), the form POST, and the CSV response.
4. Store cassettes in YAML format for readability.
5. Keep cassettes small by recording only one reporting period per report type for tests.

### Step 7: Write Tests

Create comprehensive tests in `backend/tests/scrapers/test_pa_spider.py`.

**Test structure:**
```python
import vcr
import pytest
from og_scraper.scrapers.spiders.pa_spider import PennsylvaniaDEPSpider

class TestPASpiderUnit:
    """Unit tests for PA spider parsing logic."""

    def test_parse_production_csv(self):
        """Verify production CSV rows parse into correct DocumentItems."""

    def test_parse_well_inventory_csv(self):
        """Verify well inventory CSV rows parse into correct WellItems."""

    def test_api_number_normalization_pa_format(self):
        """PA API numbers start with 37 (FIPS). Verify normalization."""
        spider = PennsylvaniaDEPSpider()
        assert spider.normalize_api_number("37-003-20001") == "37-003-20001-00-00"
        assert spider.normalize_api_number("3700320001") == "37-003-20001-00-00"

    def test_parse_float_handles_commas_and_empty(self):
        """Helper correctly parses '1,234.56', '', None."""

    def test_parse_int_handles_commas_and_empty(self):
        """Helper correctly parses '1,234', '', None."""

class TestPASpiderVCR:
    """Integration tests using VCR.py recorded cassettes."""

    @vcr.use_cassette('backend/tests/scrapers/cassettes/pa/greenport_well_inventory.yaml')
    def test_well_inventory_scrape(self):
        """Spider fetches and parses well inventory from recorded response."""

    @vcr.use_cassette('backend/tests/scrapers/cassettes/pa/greenport_production.yaml')
    def test_production_report_scrape(self):
        """Spider fetches and parses production data from recorded response."""

class TestPASpiderIntegration:
    """Integration tests verifying pipeline flow."""

    def test_spider_yields_well_items(self):
        """Spider parse methods yield valid WellItem objects."""

    def test_spider_yields_document_items(self):
        """Spider parse methods yield valid DocumentItem objects."""

    def test_items_flow_through_pipeline(self):
        """Items from spider can be processed by DocumentPipeline."""
```

### Step 8: Update State Registry

Ensure the state registry entry for PA points to the new spider class:

```python
"PA": {
    "name": "Pennsylvania",
    "agency": "Dept of Environmental Protection (DEP)",
    "spider_class": "og_scraper.scrapers.spiders.pa_spider.PennsylvaniaDEPSpider",
    "requires_playwright": False,
    "requires_auth": False,
    "scrape_type": "bulk_download",
    "rate_limit_seconds": 3,
    "data_formats": ["CSV"],
},
```

## Files to Create

- `backend/src/og_scraper/scrapers/spiders/pa_spider.py` - PA DEP GreenPort spider
- `backend/tests/scrapers/test_pa_spider.py` - Unit, VCR, and integration tests
- `backend/tests/scrapers/cassettes/pa/greenport_index.yaml` - Recorded GreenPort index page
- `backend/tests/scrapers/cassettes/pa/greenport_well_inventory.yaml` - Recorded well inventory CSV
- `backend/tests/scrapers/cassettes/pa/greenport_production.yaml` - Recorded production CSV
- `backend/tests/scrapers/cassettes/pa/greenport_compliance.yaml` - Recorded compliance CSV
- `backend/tests/scrapers/cassettes/pa/greenport_plugged.yaml` - Recorded plugged wells CSV
- `backend/tests/scrapers/record_pa_cassettes.py` - Helper script for recording cassettes

## Files to Modify

- `backend/src/og_scraper/scrapers/state_registry.py` - Update PA entry with real spider class path

## Contracts

### Provides (for downstream tasks)

- **PA Spider class**: `PennsylvaniaDEPSpider` inheriting from `BaseOGSpider` -- can be instantiated and run via Scrapy or Huey task
- **PA WellItems**: Yields `WellItem` objects with fields: `api_number`, `well_name`, `operator_name`, `county`, `latitude`, `longitude`, `well_type`, `well_status`, `spud_date`, `total_depth`, `permit_number`, `configuration`, `state_code="PA"`
- **PA DocumentItems**: Yields `DocumentItem` objects with fields: `api_number`, `doc_type`, `operator_name`, `well_name`, `raw_metadata` (containing production volumes, dates, etc.), `state_code="PA"`
- **VCR cassettes**: Reusable recorded responses in `backend/tests/scrapers/cassettes/pa/`

### Consumes (from upstream tasks)

- `BaseOGSpider` from Task 1.3: Abstract base class with `normalize_api_number()`, `build_well_item()`, `build_document_item()`, `errback_handler()`
- `DocumentItem` / `WellItem` from Task 1.3: Item dataclasses yielded by the spider
- `DocumentPipeline.process()` from Task 2.4: Called by the Scrapy item pipeline to process scraped data through classification, extraction, normalization, validation, and confidence scoring
- Scrapy settings from Task 1.3: AutoThrottle, concurrency, retry configuration
- State registry from Task 1.3: PA entry used by Huey task to look up the spider class

## Acceptance Criteria

- [ ] Spider navigates PA GreenPort and downloads CSV data for all report types
- [ ] CSV parsing extracts well data (inventory) with correct field mapping
- [ ] CSV parsing extracts production data with oil/gas/water volumes
- [ ] CSV parsing extracts compliance, plugging, and waste report data
- [ ] Data flows through full pipeline and is stored in database
- [ ] API number normalization handles PA format (state code 37, 10/12/14-digit variants)
- [ ] Rate limiting respects PA site (3s delay, 4 max concurrent)
- [ ] Spider handles empty CSV responses gracefully (no crash)
- [ ] Spider handles malformed CSV rows gracefully (logs error, continues)
- [ ] All tests pass
- [ ] Build succeeds

## Testing Protocol

### Unit/Integration Tests

- Test file: `backend/tests/scrapers/test_pa_spider.py`
- Test cases:
  - [ ] Production CSV parsing produces correct DocumentItems with oil/gas/water values
  - [ ] Well inventory CSV parsing produces correct WellItems with lat/long
  - [ ] API number normalization: `"37-003-20001"` -> `"37-003-20001-00-00"`
  - [ ] API number normalization: `"3700320001"` -> `"37-003-20001-00-00"`
  - [ ] API number normalization: `"37-003-20001-01-00"` -> `"37-003-20001-01-00"`
  - [ ] Float parsing: `"1,234.56"` -> `1234.56`, `""` -> `None`, `None` -> `None`
  - [ ] Int parsing: `"1,234"` -> `1234`, `""` -> `None`
  - [ ] Empty CSV (headers only, no data rows) yields zero items
  - [ ] Malformed row (missing required fields) is skipped with error log
  - [ ] Spider custom_settings match expected rate limit values

### API/Script Testing

- Run spider standalone: `uv run scrapy crawl pa_dep -s LOG_LEVEL=DEBUG -a limit=10`
- Expected: Downloads CSV, logs parsed items, stores to `data/PA/` directory
- Verify: `ls data/PA/` shows files organized by operator/doc_type

### VCR Cassette Testing

- Record cassettes: `uv run python backend/tests/scrapers/record_pa_cassettes.py`
- Replay tests: `uv run pytest backend/tests/scrapers/test_pa_spider.py -v`
- Expected: All VCR-based tests pass without network access
- Verify: Cassette YAML files exist and contain valid recorded responses

### Build/Lint/Type Checks

- [ ] `uv run ruff check backend/src/og_scraper/scrapers/spiders/pa_spider.py` passes
- [ ] `uv run ruff format --check backend/src/og_scraper/scrapers/spiders/pa_spider.py` passes
- [ ] `uv run pytest backend/tests/scrapers/test_pa_spider.py` passes

## Skills to Read

- `scrapy-playwright-scraping` - BaseOGSpider pattern, BulkDownloadSpider examples, Scrapy settings, VCR testing patterns
- `state-regulatory-sites` - PA-specific URLs, data formats, known quirks, rate limits
- `document-processing-pipeline` - Pipeline integration, DocumentItem fields, confidence scoring thresholds

## Research Files to Read

- `.claude/orchestration-og-doc-scraper/research/per-state-scrapers-implementation.md` - Section 3.8 (Pennsylvania) for exact URLs, adapter strategy, gotchas
- `.claude/orchestration-og-doc-scraper/research/state-regulatory-sites.md` - PA section for GreenPort details, data dictionary URL

## Git

- Branch: `feat/task-4.1-pa-scraper`
- Commit message prefix: `Task 4.1:`
