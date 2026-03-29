# Task 4.2: Colorado Scraper (ECMC Bulk CSV + COGIS)

## Objective

Implement the Colorado ECMC scraper targeting both bulk CSV downloads and the COGIS database query interface. Colorado provides downloadable CSV files for well spots, permits, and production data, plus a COGIS ASP.NET query system for detailed facility and production queries. This spider uses a `MixedSpider` pattern -- primary bulk CSV downloads via standard HTTP, with optional COGIS form queries for supplementary data.

## Context

This is the second state scraper in Phase 4, building on patterns established by Task 4.1 (PA). Colorado is rated Medium difficulty due to its dual-domain setup (`ecmc.colorado.gov` and `ecmc.state.co.us`) and the COGIS form-based query interface. The bulk CSV downloads cover the majority of needed data (well locations, permits, production since 1999). COGIS queries add facility details and completions not available in bulk files. Together with PA (4.1) and OK (4.3), this task proves the full pipeline works across different scraping patterns.

## Dependencies

- Task 1.3 - Provides `BaseOGSpider` abstract class, `DocumentItem` / `WellItem` dataclasses, Scrapy settings, download pipeline, state registry
- Task 2.4 - Provides `DocumentPipeline.process()` for routing documents through all 7 pipeline stages

## Blocked By

- 1.3, 2.4

## Research Findings

Key findings from research files relevant to this task:

- From `state-regulatory-sites.md`: CO is rated **Medium** difficulty, 3-4 dev days. ECMC uses dual domains: `ecmc.colorado.gov` (new) and `ecmc.state.co.us` (legacy). Rate limit: 8s base delay, 2 max concurrent. Agency was formerly COGCC, now ECMC.
- From `per-state-scrapers-implementation.md`: Spider type is `MixedSpider` -- bulk CSV downloads (primary) + COGIS form queries (secondary). Downloadable production CSV contains ALL production reports since 1999 in a single (large) file. COGIS query pages are server-rendered ASP.NET. Data Download Guide PDF available for field definitions.
- From `scrapy-playwright-scraping.md`: CO may need Playwright for some COGIS queries, but bulk CSV downloads use standard HTTP. State registry has `requires_playwright: True` for COGIS but primary data access is via bulk files.
- From `state-regulatory-sites.md`: CO state FIPS code is `05` for API numbers. Document types include Form 2 (well permit), Form 5/5A (completion report), Form 6 (plugging report).

## Implementation Plan

### Step 1: Create CO Spider Class

Create `backend/src/og_scraper/scrapers/spiders/co_spider.py` inheriting from `BaseOGSpider`.

**Class attributes:**
```python
state_code = "CO"
state_name = "Colorado"
agency_name = "Energy & Carbon Management Commission (ECMC)"
base_url = "https://ecmc.colorado.gov/"
requires_playwright = False  # Bulk CSV mode does not need Playwright

custom_settings = {
    'DOWNLOAD_DELAY': 8,
    'CONCURRENT_REQUESTS_PER_DOMAIN': 2,
    'AUTOTHROTTLE_ENABLED': True,
    'AUTOTHROTTLE_START_DELAY': 8,
    'AUTOTHROTTLE_MAX_DELAY': 60,
    'AUTOTHROTTLE_TARGET_CONCURRENCY': 1.0,
}
```

**Exact data URLs:**

| Dataset | URL | Format | Notes |
|---------|-----|--------|-------|
| Downloadable Data Page | `https://ecmc.colorado.gov/data-maps-reports/downloadable-data-documents` | HTML | Index page listing all available downloads |
| Data Page (legacy) | `https://ecmc.state.co.us/data2.html` | HTML | Legacy download links |
| Data Download Guide | `https://ecmc.state.co.us/documents/data/downloads/COGCC_Download_Guidance.pdf` | PDF | Field definitions |
| COGIS Database | `https://ecmc.colorado.gov/data-maps/cogis-database` | HTML | Query interface home |
| Facility Search | `https://ecmc.state.co.us/cogisdb/Facility/FacilitySearch` | HTML | ASP.NET form |
| Production Data Inquiry | `https://ecmc.colorado.gov/data-maps-reports/cogis-database/cogis-production-data-inquiry` | HTML | ASP.NET form |
| Well Analytical Data | `https://ecmc.colorado.gov/data-maps/downloadable-data-documents/prod-well-download` | HTML | Monthly CSV download page |
| Operator Search | `https://ecmc.colorado.gov/data-maps-reports/cogis-database/cogis-operator-name-address-and-financial-assurance` | HTML | Operator lookup |

### Step 2: Implement start_requests() for Bulk CSV Downloads

The primary data acquisition strategy downloads bulk CSV files from the ECMC downloadable data page.

```python
# Bulk CSV download URLs (discovered from the downloadable data page)
BULK_DOWNLOADS = {
    "well_spots": {
        "description": "Well Spots (APIs) - active/plugged wells + permits",
        "format": "csv",
    },
    "well_permits": {
        "description": "Active well permits",
        "format": "csv",
    },
    "pending_permits": {
        "description": "Pending well permits",
        "format": "csv",
    },
    "production": {
        "description": "Production data - all wells since 1999",
        "format": "csv",  # May be zipped
    },
    "well_analytical": {
        "description": "Oil & Gas Well Analytical Data",
        "format": "csv",
    },
}

def start_requests(self):
    # Step 1: Fetch the downloadable data page to discover current download links
    yield scrapy.Request(
        url="https://ecmc.colorado.gov/data-maps-reports/downloadable-data-documents",
        callback=self.parse_download_page,
    )
    # Also check legacy data page for additional downloads
    yield scrapy.Request(
        url="https://ecmc.state.co.us/data2.html",
        callback=self.parse_legacy_download_page,
    )
```

### Step 3: Implement Download Page Parsing

The downloadable data page contains links to CSV files. Parse the page to extract current download URLs.

```python
def parse_download_page(self, response):
    """Parse the ECMC downloadable data page to find CSV download links."""
    # Look for links to CSV/ZIP files
    for link in response.css('a[href]'):
        href = link.attrib.get('href', '')
        text = link.css('::text').get('').strip().lower()

        if href.endswith('.csv') or href.endswith('.zip'):
            # Determine report type from link text
            report_type = self._classify_download_link(text, href)
            if report_type:
                full_url = response.urljoin(href)
                yield scrapy.Request(
                    url=full_url,
                    callback=self.parse_csv_file,
                    meta={
                        "report_type": report_type,
                        "source_url": full_url,
                    },
                )

def _classify_download_link(self, text: str, href: str) -> str | None:
    """Classify a download link by its text/URL into a report type."""
    if 'well spot' in text or 'wellspot' in text:
        return 'well_spots'
    elif 'permit' in text and 'pending' in text:
        return 'pending_permits'
    elif 'permit' in text:
        return 'well_permits'
    elif 'production' in text or 'prod' in href.lower():
        return 'production'
    elif 'analytical' in text:
        return 'well_analytical'
    return None
```

### Step 4: Implement CSV Parsing for Each Data Type

**Well Spots CSV expected fields (per Data Download Guide):**
- API_Number (05-XXX-XXXXX format), Well_Name, Operator_Name
- County, Field_Name, Formation
- Latitude, Longitude (NAD83)
- Well_Status, Well_Type, Spud_Date, First_Prod_Date
- Total_Depth, Elevation

**Production CSV expected fields:**
- API_Number, Operator_Name, Well_Name
- Year, Month (or reporting period)
- Oil_BBL, Gas_MCF, Water_BBL, Days_Produced
- Formation

```python
def parse_csv_file(self, response):
    """Parse a downloaded CSV file into items."""
    report_type = response.meta["report_type"]

    # Handle ZIP files
    if response.url.endswith('.zip'):
        yield from self._parse_zipped_csv(response)
        return

    reader = csv.DictReader(io.StringIO(response.text))

    for row in reader:
        if report_type == "well_spots":
            yield from self._parse_well_spot_row(row)
        elif report_type == "production":
            yield from self._parse_production_row(row)
        elif report_type in ("well_permits", "pending_permits"):
            yield from self._parse_permit_row(row)
        elif report_type == "well_analytical":
            yield from self._parse_analytical_row(row)

def _parse_well_spot_row(self, row: dict):
    api_raw = row.get("API_Number", row.get("api_number", row.get("API", "")))
    if api_raw:
        yield self.build_well_item(
            api_number=self.normalize_api_number(api_raw),
            well_name=row.get("Well_Name", row.get("well_name", "")).strip(),
            operator_name=row.get("Operator_Name", row.get("operator_name", "")).strip(),
            county=row.get("County", row.get("county", "")).strip(),
            latitude=self._parse_float(row.get("Latitude", row.get("latitude"))),
            longitude=self._parse_float(row.get("Longitude", row.get("longitude"))),
            well_status=row.get("Well_Status", row.get("well_status", "")).strip(),
            well_type=row.get("Well_Type", row.get("well_type", "")).strip(),
            spud_date=row.get("Spud_Date", row.get("spud_date", "")).strip(),
            total_depth=self._parse_float(row.get("Total_Depth", row.get("total_depth"))),
            field_name=row.get("Field_Name", row.get("field_name", "")).strip(),
            formation=row.get("Formation", row.get("formation", "")).strip(),
        )

def _parse_production_row(self, row: dict):
    api_raw = row.get("API_Number", row.get("api_number", row.get("API", "")))
    if api_raw:
        yield self.build_document_item(
            api_number=self.normalize_api_number(api_raw),
            doc_type="production_report",
            operator_name=row.get("Operator_Name", row.get("operator_name", "")).strip(),
            well_name=row.get("Well_Name", row.get("well_name", "")).strip(),
            raw_metadata={
                "oil_bbls": self._parse_float(row.get("Oil_BBL", row.get("oil_bbl"))),
                "gas_mcf": self._parse_float(row.get("Gas_MCF", row.get("gas_mcf"))),
                "water_bbls": self._parse_float(row.get("Water_BBL", row.get("water_bbl"))),
                "days_produced": self._parse_int(row.get("Days_Produced", row.get("days_produced"))),
                "year": row.get("Year", row.get("year", "")).strip(),
                "month": row.get("Month", row.get("month", "")).strip(),
                "formation": row.get("Formation", row.get("formation", "")).strip(),
            },
        )
```

### Step 5: Handle ZIP File Downloads

The production CSV may be delivered as a ZIP archive. Implement extraction.

```python
import zipfile

def _parse_zipped_csv(self, response):
    """Extract CSV from a ZIP response and parse it."""
    zip_buffer = io.BytesIO(response.body)
    with zipfile.ZipFile(zip_buffer) as zf:
        for name in zf.namelist():
            if name.endswith('.csv'):
                with zf.open(name) as csv_file:
                    text = csv_file.read().decode('utf-8', errors='replace')
                    reader = csv.DictReader(io.StringIO(text))
                    report_type = response.meta["report_type"]
                    for row in reader:
                        if report_type == "production":
                            yield from self._parse_production_row(row)
                        elif report_type == "well_spots":
                            yield from self._parse_well_spot_row(row)
```

### Step 6: Implement COGIS Form Queries (Secondary)

For facility details and completions not in the bulk CSVs, implement optional COGIS queries. These use ASP.NET form POST with ViewState.

```python
def query_cogis_facility(self, api_number: str):
    """Query COGIS Facility Search for detailed well info."""
    yield scrapy.Request(
        url="https://ecmc.state.co.us/cogisdb/Facility/FacilitySearch",
        callback=self.parse_cogis_form,
        meta={"api_number": api_number, "query_type": "facility"},
    )

def parse_cogis_form(self, response):
    """Submit COGIS search form with API number."""
    yield scrapy.FormRequest.from_response(
        response,
        formdata={
            'ApiCounty': response.meta['api_number'][:5],  # county portion
            'ApiSequence': response.meta['api_number'][5:],  # sequence
        },
        callback=self.parse_cogis_results,
        meta=response.meta,
    )

def parse_cogis_results(self, response):
    """Parse COGIS query results HTML table."""
    for row in response.css('table.results tr')[1:]:  # Skip header
        cells = row.css('td::text').getall()
        if cells:
            yield self.build_well_item(
                api_number=self.normalize_api_number(cells[0].strip()),
                well_name=cells[1].strip() if len(cells) > 1 else "",
                operator_name=cells[2].strip() if len(cells) > 2 else "",
                # ... additional fields from table columns
            )
```

### Step 7: Record VCR.py Cassettes

**Cassette directory:** `backend/tests/scrapers/cassettes/co/`

**Cassettes to record:**

| Cassette File | What It Records |
|---------------|-----------------|
| `ecmc_download_page.yaml` | The downloadable data page HTML |
| `ecmc_legacy_data_page.yaml` | Legacy data2.html page |
| `ecmc_well_spots.yaml` | Well spots CSV download (first 100 rows) |
| `ecmc_production.yaml` | Production CSV download (first 100 rows) |
| `ecmc_permits.yaml` | Well permits CSV download |
| `ecmc_cogis_facility_search.yaml` | COGIS facility search form + results |

```python
# backend/tests/scrapers/record_co_cassettes.py
import vcr

my_vcr = vcr.VCR(
    cassette_library_dir='backend/tests/scrapers/cassettes/co',
    record_mode='new_episodes',
    match_on=['uri', 'method', 'body'],
    decode_compressed_response=True,
)

with my_vcr.use_cassette('ecmc_download_page.yaml'):
    # fetch https://ecmc.colorado.gov/data-maps-reports/downloadable-data-documents
    pass

with my_vcr.use_cassette('ecmc_well_spots.yaml'):
    # fetch well spots CSV
    pass

with my_vcr.use_cassette('ecmc_production.yaml'):
    # fetch production CSV (truncated)
    pass
```

### Step 8: Write Tests

Create `backend/tests/scrapers/test_co_spider.py`.

```python
class TestCOSpiderUnit:
    """Unit tests for CO spider parsing logic."""

    def test_parse_well_spot_row(self):
        """Well spot CSV row produces correct WellItem."""

    def test_parse_production_row(self):
        """Production CSV row produces correct DocumentItem with volumes."""

    def test_parse_permit_row(self):
        """Permit CSV row produces correct WellItem with permit info."""

    def test_classify_download_link(self):
        """Download link classifier correctly identifies report types."""

    def test_api_number_normalization_co_format(self):
        """CO API numbers start with 05. Verify normalization."""
        spider = ColoradoECMCSpider()
        assert spider.normalize_api_number("05-123-45678") == "05-123-45678-00-00"

    def test_handles_zip_file(self):
        """ZIP file extraction correctly yields CSV rows."""

    def test_dual_domain_urls(self):
        """Spider handles both ecmc.colorado.gov and ecmc.state.co.us URLs."""

class TestCOSpiderVCR:
    """VCR cassette-based tests."""

    @vcr.use_cassette('backend/tests/scrapers/cassettes/co/ecmc_download_page.yaml')
    def test_download_page_parsing(self):
        """Download page yields requests for CSV files."""

    @vcr.use_cassette('backend/tests/scrapers/cassettes/co/ecmc_well_spots.yaml')
    def test_well_spots_csv(self):
        """Well spots CSV parsed correctly from recorded response."""

    @vcr.use_cassette('backend/tests/scrapers/cassettes/co/ecmc_production.yaml')
    def test_production_csv(self):
        """Production CSV parsed correctly from recorded response."""

class TestCOSpiderIntegration:
    """Pipeline integration tests."""

    def test_items_flow_through_pipeline(self):
        """CO items are processable by DocumentPipeline."""

    def test_large_production_csv_performance(self):
        """Production CSV (all since 1999) processes within acceptable time."""
```

### Step 9: Update State Registry

```python
"CO": {
    "name": "Colorado",
    "agency": "Energy & Carbon Management Commission (ECMC)",
    "spider_class": "og_scraper.scrapers.spiders.co_spider.ColoradoECMCSpider",
    "requires_playwright": False,  # Bulk CSV mode, Playwright only for COGIS forms
    "requires_auth": False,
    "scrape_type": "mixed",
    "rate_limit_seconds": 8,
    "data_formats": ["CSV", "PDF"],
},
```

## Files to Create

- `backend/src/og_scraper/scrapers/spiders/co_spider.py` - Colorado ECMC spider
- `backend/tests/scrapers/test_co_spider.py` - Unit, VCR, and integration tests
- `backend/tests/scrapers/cassettes/co/ecmc_download_page.yaml` - Recorded download page
- `backend/tests/scrapers/cassettes/co/ecmc_legacy_data_page.yaml` - Recorded legacy page
- `backend/tests/scrapers/cassettes/co/ecmc_well_spots.yaml` - Recorded well spots CSV
- `backend/tests/scrapers/cassettes/co/ecmc_production.yaml` - Recorded production CSV
- `backend/tests/scrapers/cassettes/co/ecmc_permits.yaml` - Recorded permits CSV
- `backend/tests/scrapers/cassettes/co/ecmc_cogis_facility_search.yaml` - Recorded COGIS form
- `backend/tests/scrapers/record_co_cassettes.py` - Helper script for recording cassettes

## Files to Modify

- `backend/src/og_scraper/scrapers/state_registry.py` - Update CO entry with real spider class path

## Contracts

### Provides (for downstream tasks)

- **CO Spider class**: `ColoradoECMCSpider` inheriting from `BaseOGSpider` -- `MixedSpider` pattern with bulk CSV primary and COGIS secondary
- **CO WellItems**: Yields `WellItem` objects with fields: `api_number`, `well_name`, `operator_name`, `county`, `latitude`, `longitude`, `well_status`, `well_type`, `spud_date`, `total_depth`, `field_name`, `formation`, `state_code="CO"`
- **CO DocumentItems**: Yields `DocumentItem` objects for production reports with `raw_metadata` containing `oil_bbls`, `gas_mcf`, `water_bbls`, `days_produced`, `year`, `month`, `formation`
- **ZIP handling utility**: Reusable `_parse_zipped_csv()` method for other states that deliver zipped data
- **VCR cassettes**: Recorded responses in `backend/tests/scrapers/cassettes/co/`

### Consumes (from upstream tasks)

- `BaseOGSpider` from Task 1.3: Abstract base class with `normalize_api_number()`, `build_well_item()`, `build_document_item()`
- `DocumentItem` / `WellItem` from Task 1.3: Item dataclasses
- `DocumentPipeline.process()` from Task 2.4: Pipeline processing
- Scrapy settings from Task 1.3: AutoThrottle, concurrency, retry
- State registry from Task 1.3: CO entry for Huey task lookup
- PA spider patterns from Task 4.1: CSV parsing patterns, helper methods (`_parse_float`, `_parse_int`)

## Acceptance Criteria

- [ ] Spider discovers and downloads bulk CSV files from ECMC downloadable data page
- [ ] Well spots CSV parsing extracts well data with correct lat/long (NAD83)
- [ ] Production CSV parsing extracts production data for all wells since 1999
- [ ] Permit CSV parsing extracts active and pending permits
- [ ] ZIP file downloads are handled (extracted and parsed)
- [ ] COGIS facility search form query works (secondary data source)
- [ ] Both domains handled (`ecmc.colorado.gov` and `ecmc.state.co.us`)
- [ ] Data flows through full pipeline and is stored in database
- [ ] API number normalization handles CO format (state code 05)
- [ ] Rate limiting respects CO site (8s delay, 2 max concurrent)
- [ ] Large production CSV processes without memory issues
- [ ] All tests pass
- [ ] Build succeeds

## Testing Protocol

### Unit/Integration Tests

- Test file: `backend/tests/scrapers/test_co_spider.py`
- Test cases:
  - [ ] Well spots CSV row parsing produces correct WellItem
  - [ ] Production CSV row parsing produces correct DocumentItem with volumes
  - [ ] Permit CSV row parsing produces correct WellItem with permit data
  - [ ] Download link classifier: "Well Spots" -> `well_spots`, "Production" -> `production`
  - [ ] API number normalization: `"05-123-45678"` -> `"05-123-45678-00-00"`
  - [ ] API number normalization: `"0512345678"` -> `"05-123-45678-00-00"`
  - [ ] ZIP extraction: Zipped CSV is correctly extracted and parsed
  - [ ] Empty CSV yields zero items
  - [ ] Malformed rows handled gracefully with error log
  - [ ] COGIS form HTML with ViewState is correctly submitted
  - [ ] COGIS results table rows parse into WellItems
  - [ ] Dual domain URLs both resolve correctly

### API/Script Testing

- Run spider standalone: `uv run scrapy crawl co_ecmc -s LOG_LEVEL=DEBUG -a limit=10`
- Expected: Downloads CSVs from ECMC, logs parsed items, stores to `data/CO/`
- Verify: `ls data/CO/` shows files organized by operator/doc_type

### VCR Cassette Testing

- Record cassettes: `uv run python backend/tests/scrapers/record_co_cassettes.py`
- Replay tests: `uv run pytest backend/tests/scrapers/test_co_spider.py -v`
- Expected: All VCR tests pass offline

### Build/Lint/Type Checks

- [ ] `uv run ruff check backend/src/og_scraper/scrapers/spiders/co_spider.py` passes
- [ ] `uv run ruff format --check backend/src/og_scraper/scrapers/spiders/co_spider.py` passes
- [ ] `uv run pytest backend/tests/scrapers/test_co_spider.py` passes

## Skills to Read

- `scrapy-playwright-scraping` - MixedSpider pattern, Scrapy FormRequest for ASP.NET, VCR cassettes
- `state-regulatory-sites` - CO-specific URLs, dual domain quirks, COGIS details, rate limits
- `document-processing-pipeline` - Pipeline integration, CSV data routing through extraction stages

## Research Files to Read

- `.claude/orchestration-og-doc-scraper/research/per-state-scrapers-implementation.md` - Section 3.5 (Colorado) for exact URLs, downloadable data details, COGIS strategy
- `.claude/orchestration-og-doc-scraper/research/state-regulatory-sites.md` - CO section for data download guide, facility search, production inquiry

## Git

- Branch: `feat/task-4.2-co-scraper`
- Commit message prefix: `Task 4.2:`
