# Task 4.3: Oklahoma Scraper (OCC Bulk Downloads)

## Objective

Implement the Oklahoma OCC scraper targeting nightly/daily bulk file downloads from the Oklahoma Corporation Commission. Oklahoma provides extensive CSV and XLSX data files covering wells (RBDMS), drilling permits (Intent to Drill), completions, incidents, operators, and UIC injection volumes. This spider downloads all available bulk files, parses both CSV and XLSX formats, and feeds structured data through the pipeline. Production data from the Oklahoma Tax Commission (OkTAP) is handled as a secondary data source.

## Context

This is the third and final state scraper in Phase 4, completing the set of "first scrapers" that prove the full pipeline. Oklahoma is rated Easy difficulty with a `BulkDownloadSpider` pattern -- all data files are static URLs with no authentication. The main complexity is handling two data sources (OCC for well data, Oklahoma Tax Commission for production data) and parsing both CSV and XLSX formats. Together with PA (4.1) and CO (4.2), this task validates that the pipeline handles different data formats and state-specific quirks correctly. The Phase 4 regression test (4.R) follows.

## Dependencies

- Task 1.3 - Provides `BaseOGSpider` abstract class, `DocumentItem` / `WellItem` dataclasses, Scrapy settings, download pipeline, state registry
- Task 2.4 - Provides `DocumentPipeline.process()` for routing documents through all 7 pipeline stages

## Blocked By

- 1.3, 2.4

## Research Findings

Key findings from research files relevant to this task:

- From `state-regulatory-sites.md`: OK is rated **Easy** difficulty, 2-3 dev days. All bulk downloads are free, public, no authentication. Rate limit: 3s base delay, 4 max concurrent. OK uses RBDMS standard for well data.
- From `per-state-scrapers-implementation.md`: Spider type is `BulkDownloadSpider`. 15+ downloadable files with static URLs. RBDMS Well Data is CSV (nightly). Most other files are XLSX (daily/weekly). Data dictionaries are provided as companion XLSX files.
- From `per-state-scrapers-implementation.md`: **CRITICAL** -- Production data is maintained by the Oklahoma Tax Commission, NOT the OCC. Must scrape OkTAP at `https://oktap.tax.ok.gov/OkTAP/web?link=PUBLICPUNLKP` for production volumes. OkTAP may require form interaction.
- From `state-regulatory-sites.md`: OK state FIPS code is `35` for API numbers. Document form numbers: 1002A (well permit), 1002C (completion report).
- From `per-state-scrapers-implementation.md`: Well Browse at `https://wellbrowse.occ.ok.gov/` provides electronic imaged documents (scanned PDFs). GIS data available at `https://gisdata-occokc.opendata.arcgis.com/`.

## Implementation Plan

### Step 1: Create OK Spider Class

Create `backend/src/og_scraper/scrapers/spiders/ok_spider.py` inheriting from `BaseOGSpider`.

**Class attributes:**
```python
state_code = "OK"
state_name = "Oklahoma"
agency_name = "Corporation Commission (OCC)"
base_url = "https://oklahoma.gov/occ/divisions/oil-gas.html"
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

**All bulk download URLs (base: `https://oklahoma.gov`):**

**Well Information:**

| File | Format | Frequency | URL Path |
|------|--------|-----------|----------|
| RBDMS Well Data | CSV | Nightly | `/content/dam/ok/en/occ/documents/og/ogdatafiles/rbdms-wells.csv` |
| RBDMS Data Dictionary | XLSX | Nightly | `/content/dam/ok/en/occ/documents/og/ogdatafiles/rbdms-wells-data-dictionary.xlsx` |
| RBDMS Wells GIS | Shapefile (ZIP) | Nightly | `/content/dam/ok/en/occ/documents/og/esri/files/RBDMS_WELLS.zip` |
| Incident Report Archive | CSV | Daily | `/content/dam/ok/en/occ/documents/og/ogdatafiles/ogcd-incidents.csv` |
| Orphan Well List | XLSX | Weekly (Thu) | `/content/dam/ok/en/occ/documents/og/ogdatafiles/orphan-well-list.xlsx` |
| State Funds Well List | XLSX | Weekly (Thu) | `/content/dam/ok/en/occ/documents/og/ogdatafiles/stfd-well-list.xlsx` |

**Intent to Drill & Completions:**

| File | Format | Frequency | URL Path |
|------|--------|-----------|----------|
| Intent to Drill (7-day) | XLSX | Daily | `/content/dam/ok/en/occ/documents/og/ogdatafiles/ITD-wells-formations-daily.xlsx` |
| Intent to Drill Master | XLSX | Daily | `/content/dam/ok/en/occ/documents/og/ogdatafiles/ITD-wells-formations-base.xlsx` |
| Well Completions Monthly | XLSX | Daily | `/content/dam/ok/en/occ/documents/og/ogdatafiles/completions-wells-formations-base.xlsx` |
| Well Completions (7-day) | XLSX | Daily | `/content/dam/ok/en/occ/documents/og/ogdatafiles/completions-wells-formations-daily.xlsx` |
| Well Completions Legacy | XLSX | Static | `/content/dam/ok/en/occ/documents/og/ogdatafiles/completions-wells-legacy.xlsx` |
| Well Transfer File | XLSX | Daily | `/content/dam/ok/en/occ/documents/og/ogdatafiles/well-transfers-daily.xlsx` |

**Operators/Purchasers:**

| File | Format | Frequency | URL Path |
|------|--------|-----------|----------|
| Operator List | XLSX | Daily | `/content/dam/ok/en/occ/documents/og/ogdatafiles/operator-list.xlsx` |
| Purchaser List | XLSX | Daily | `/content/dam/ok/en/occ/documents/og/ogdatafiles/purchaser-list.xlsx` |
| Plugger List | XLSX | Daily | `/content/dam/ok/en/occ/documents/og/ogdatafiles/plugger-list.xlsx` |

**UIC Injection Volumes:**

| File | Format | URL Path |
|------|--------|----------|
| All UIC Wells | XLSX | `/content/dam/ok/en/occ/documents/og/ogdatafiles/online-active-well-list.xlsx` |
| 2024 Injection Volumes | XLSX | `/content/dam/ok/en/occ/documents/og/ogdatafiles/2024-uic-injection-volumes.xlsx` |
| 2025 Injection Volumes | XLSX | `/content/dam/ok/en/occ/documents/og/ogdatafiles/2025-uic-injection-volumes.xlsx` |
| 2026 Arbuckle 1012D | XLSX | `/content/dam/ok/en/occ/documents/og/ogdatafiles/dly1012d_2026.xlsx` |

**Production Data (separate system):**

| Resource | URL |
|----------|-----|
| OkTAP Production Lookup | `https://oktap.tax.ok.gov/OkTAP/web?link=PUBLICPUNLKP` |
| Gross Production Portal | `https://otcportal.tax.ok.gov/gpx/index.php` |

### Step 2: Implement start_requests() for All Bulk Downloads

```python
BASE_URL = "https://oklahoma.gov"

# Map of dataset name -> (relative_url, format, report_type)
BULK_FILES = {
    # Well Information
    "rbdms_wells": (
        "/content/dam/ok/en/occ/documents/og/ogdatafiles/rbdms-wells.csv",
        "csv",
        "well_data",
    ),
    "incidents": (
        "/content/dam/ok/en/occ/documents/og/ogdatafiles/ogcd-incidents.csv",
        "csv",
        "incident_report",
    ),
    # Intent to Drill & Completions
    "itd_master": (
        "/content/dam/ok/en/occ/documents/og/ogdatafiles/ITD-wells-formations-base.xlsx",
        "xlsx",
        "well_permit",
    ),
    "completions_master": (
        "/content/dam/ok/en/occ/documents/og/ogdatafiles/completions-wells-formations-base.xlsx",
        "xlsx",
        "completion_report",
    ),
    "well_transfers": (
        "/content/dam/ok/en/occ/documents/og/ogdatafiles/well-transfers-daily.xlsx",
        "xlsx",
        "well_transfer",
    ),
    # Operators
    "operators": (
        "/content/dam/ok/en/occ/documents/og/ogdatafiles/operator-list.xlsx",
        "xlsx",
        "operator_list",
    ),
    # UIC
    "uic_wells": (
        "/content/dam/ok/en/occ/documents/og/ogdatafiles/online-active-well-list.xlsx",
        "xlsx",
        "uic_data",
    ),
    "uic_2025": (
        "/content/dam/ok/en/occ/documents/og/ogdatafiles/2025-uic-injection-volumes.xlsx",
        "xlsx",
        "uic_injection",
    ),
}

def start_requests(self):
    for dataset_name, (url_path, fmt, report_type) in self.BULK_FILES.items():
        yield scrapy.Request(
            url=f"{self.BASE_URL}{url_path}",
            callback=self.parse_bulk_file,
            meta={
                "dataset_name": dataset_name,
                "file_format": fmt,
                "report_type": report_type,
            },
            errback=self.errback_handler,
        )
```

### Step 3: Implement CSV Parsing for RBDMS Well Data

The RBDMS wells CSV is the primary well data file. Use the companion data dictionary XLSX for field mapping.

**RBDMS CSV expected fields (from data dictionary):**
- API_WELL_NUMBER (10-digit OK format), WELL_NAME, OPERATOR_NAME, OPERATOR_NUMBER
- COUNTY, SECTION, TOWNSHIP, RANGE
- LATITUDE, LONGITUDE
- WELL_STATUS, WELL_TYPE, WELL_CLASS
- SPUD_DATE, COMPLETION_DATE, FIRST_PROD_DATE, PLUG_DATE
- TOTAL_DEPTH, FORMATION_NAME

```python
def parse_bulk_file(self, response):
    """Route parsing based on file format."""
    fmt = response.meta["file_format"]
    report_type = response.meta["report_type"]

    if fmt == "csv":
        yield from self._parse_csv(response, report_type)
    elif fmt == "xlsx":
        yield from self._parse_xlsx(response, report_type)

def _parse_csv(self, response, report_type: str):
    """Parse CSV files (RBDMS wells, incidents)."""
    reader = csv.DictReader(io.StringIO(response.text))

    for row in reader:
        if report_type == "well_data":
            yield from self._parse_rbdms_well_row(row)
        elif report_type == "incident_report":
            yield from self._parse_incident_row(row)

def _parse_rbdms_well_row(self, row: dict):
    """Parse a single RBDMS well data CSV row."""
    api_raw = row.get("API_WELL_NUMBER", row.get("api_well_number", ""))
    if not api_raw:
        return

    yield self.build_well_item(
        api_number=self.normalize_api_number(api_raw),
        well_name=row.get("WELL_NAME", "").strip(),
        operator_name=row.get("OPERATOR_NAME", "").strip(),
        county=row.get("COUNTY", "").strip(),
        latitude=self._parse_float(row.get("LATITUDE")),
        longitude=self._parse_float(row.get("LONGITUDE")),
        well_status=row.get("WELL_STATUS", "").strip(),
        well_type=row.get("WELL_TYPE", "").strip(),
        spud_date=row.get("SPUD_DATE", "").strip(),
        completion_date=row.get("COMPLETION_DATE", "").strip(),
        total_depth=self._parse_float(row.get("TOTAL_DEPTH")),
        formation=row.get("FORMATION_NAME", "").strip(),
        section=row.get("SECTION", "").strip(),
        township=row.get("TOWNSHIP", "").strip(),
        range_=row.get("RANGE", "").strip(),
    )
```

### Step 4: Implement XLSX Parsing

Oklahoma provides most supplementary data in XLSX format. Use `openpyxl` for fine-grained control (government Excel files often have merged cells, multi-row headers).

```python
import openpyxl

def _parse_xlsx(self, response, report_type: str):
    """Parse XLSX files (permits, completions, operators, UIC)."""
    workbook = openpyxl.load_workbook(io.BytesIO(response.body), read_only=True)
    sheet = workbook.active

    # Find header row (may not be row 1 in government Excel files)
    headers = None
    data_start_row = 0
    for i, row in enumerate(sheet.iter_rows(max_row=10, values_only=True)):
        # Look for a row that looks like headers (non-empty, text values)
        if row and any(isinstance(cell, str) for cell in row if cell):
            headers = [str(cell).strip() if cell else "" for cell in row]
            data_start_row = i + 1
            break

    if not headers:
        self.logger.error(f"No header row found in XLSX for {report_type}")
        return

    for row in sheet.iter_rows(min_row=data_start_row + 1, values_only=True):
        row_dict = dict(zip(headers, row))

        if report_type == "well_permit":
            yield from self._parse_itd_row(row_dict)
        elif report_type == "completion_report":
            yield from self._parse_completion_row(row_dict)
        elif report_type == "operator_list":
            yield from self._parse_operator_row(row_dict)
        elif report_type == "uic_data":
            yield from self._parse_uic_row(row_dict)
        elif report_type == "uic_injection":
            yield from self._parse_uic_injection_row(row_dict)
        elif report_type == "well_transfer":
            yield from self._parse_transfer_row(row_dict)

    workbook.close()

def _parse_itd_row(self, row: dict):
    """Parse Intent to Drill (drilling permit) row."""
    api_raw = row.get("API_WELL_NUMBER", row.get("API", ""))
    if not api_raw:
        return
    yield self.build_document_item(
        api_number=self.normalize_api_number(str(api_raw)),
        doc_type="well_permit",
        operator_name=str(row.get("OPERATOR_NAME", "")).strip(),
        well_name=str(row.get("WELL_NAME", "")).strip(),
        raw_metadata={
            "permit_type": "Intent to Drill",
            "county": str(row.get("COUNTY", "")).strip(),
            "formation": str(row.get("FORMATION", "")).strip(),
            "proposed_depth": self._parse_float(row.get("PROPOSED_DEPTH")),
            "filing_date": str(row.get("FILING_DATE", "")).strip(),
        },
    )

def _parse_completion_row(self, row: dict):
    """Parse well completion row."""
    api_raw = row.get("API_WELL_NUMBER", row.get("API", ""))
    if not api_raw:
        return
    yield self.build_document_item(
        api_number=self.normalize_api_number(str(api_raw)),
        doc_type="completion_report",
        operator_name=str(row.get("OPERATOR_NAME", "")).strip(),
        well_name=str(row.get("WELL_NAME", "")).strip(),
        raw_metadata={
            "completion_date": str(row.get("COMPLETION_DATE", "")).strip(),
            "formation": str(row.get("FORMATION", "")).strip(),
            "total_depth": self._parse_float(row.get("TOTAL_DEPTH")),
            "first_prod_date": str(row.get("FIRST_PROD_DATE", "")).strip(),
            "initial_oil": self._parse_float(row.get("INITIAL_OIL_PROD")),
            "initial_gas": self._parse_float(row.get("INITIAL_GAS_PROD")),
        },
    )

def _parse_operator_row(self, row: dict):
    """Parse operator list row (yields operator data, not well items)."""
    operator_name = str(row.get("OPERATOR_NAME", "")).strip()
    if operator_name:
        yield {
            "type": "operator",
            "state_code": self.state_code,
            "operator_name": operator_name,
            "operator_number": str(row.get("OPERATOR_NUMBER", "")).strip(),
            "address": str(row.get("ADDRESS", "")).strip(),
            "city": str(row.get("CITY", "")).strip(),
            "state": str(row.get("STATE", "")).strip(),
            "zip_code": str(row.get("ZIP", "")).strip(),
        }
```

### Step 5: Implement Incident Report Parsing

```python
def _parse_incident_row(self, row: dict):
    """Parse incident report CSV row."""
    yield self.build_document_item(
        api_number=self.normalize_api_number(row.get("API_WELL_NUMBER", "")),
        doc_type="incident_report",
        operator_name=row.get("OPERATOR_NAME", "").strip(),
        well_name=row.get("WELL_NAME", "").strip(),
        raw_metadata={
            "incident_date": row.get("INCIDENT_DATE", "").strip(),
            "incident_type": row.get("INCIDENT_TYPE", "").strip(),
            "county": row.get("COUNTY", "").strip(),
            "description": row.get("DESCRIPTION", "").strip(),
            "resolution": row.get("RESOLUTION", "").strip(),
        },
    )
```

### Step 6: Stub OkTAP Production Data Access

Production data lives on the Oklahoma Tax Commission portal, not OCC. Implement a stub for future Playwright-based interaction.

```python
# NOTE: OkTAP production data requires form interaction.
# This is stubbed for Phase 4 and will be fully implemented if needed.
# The OCC bulk files cover well data, permits, completions, incidents.
# Production volumes specifically require OkTAP.

OKTAP_URL = "https://oktap.tax.ok.gov/OkTAP/web?link=PUBLICPUNLKP"
GROSS_PRODUCTION_URL = "https://otcportal.tax.ok.gov/gpx/index.php"

def start_oktap_requests(self):
    """Stub: Production data from Oklahoma Tax Commission.

    OkTAP requires JavaScript form interaction. This will be
    implemented with Playwright if production data is needed.
    For Phase 4, the OCC bulk files provide sufficient well/permit data.
    """
    self.logger.info(
        "OkTAP production data not implemented in Phase 4. "
        "Use OCC bulk files for well data, permits, completions."
    )
```

### Step 7: Record VCR.py Cassettes

**Cassette directory:** `backend/tests/scrapers/cassettes/ok/`

**Cassettes to record:**

| Cassette File | What It Records |
|---------------|-----------------|
| `occ_rbdms_wells.yaml` | RBDMS wells CSV download (first 100 rows) |
| `occ_incidents.yaml` | Incident report CSV download (first 50 rows) |
| `occ_itd_master.yaml` | Intent to Drill master XLSX download |
| `occ_completions.yaml` | Well completions XLSX download |
| `occ_operators.yaml` | Operator list XLSX download |
| `occ_uic_wells.yaml` | UIC wells XLSX download |

```python
# backend/tests/scrapers/record_ok_cassettes.py
import vcr
import requests

my_vcr = vcr.VCR(
    cassette_library_dir='backend/tests/scrapers/cassettes/ok',
    record_mode='new_episodes',
    match_on=['uri', 'method'],
    decode_compressed_response=True,
)

BASE = "https://oklahoma.gov"

with my_vcr.use_cassette('occ_rbdms_wells.yaml'):
    resp = requests.get(f"{BASE}/content/dam/ok/en/occ/documents/og/ogdatafiles/rbdms-wells.csv",
                        stream=True)
    # Read only first 10KB for test cassette
    content = resp.raw.read(10240)

with my_vcr.use_cassette('occ_itd_master.yaml'):
    requests.get(f"{BASE}/content/dam/ok/en/occ/documents/og/ogdatafiles/ITD-wells-formations-base.xlsx")
```

**Important:** XLSX files are binary. VCR.py stores them as base64-encoded content in the cassette YAML. Ensure `decode_compressed_response=True` and cassettes are not corrupted during storage.

### Step 8: Write Tests

Create `backend/tests/scrapers/test_ok_spider.py`.

```python
class TestOKSpiderUnit:
    """Unit tests for OK spider parsing logic."""

    def test_parse_rbdms_well_row(self):
        """RBDMS CSV row produces correct WellItem with all fields."""

    def test_parse_incident_row(self):
        """Incident CSV row produces correct DocumentItem."""

    def test_parse_itd_row(self):
        """Intent to Drill XLSX row produces correct DocumentItem."""

    def test_parse_completion_row(self):
        """Completion XLSX row produces correct DocumentItem."""

    def test_parse_operator_row(self):
        """Operator XLSX row produces correct operator data dict."""

    def test_api_number_normalization_ok_format(self):
        """OK API numbers start with 35. Verify normalization."""
        spider = OklahomaOCCSpider()
        assert spider.normalize_api_number("35-017-20001") == "35-017-20001-00-00"
        assert spider.normalize_api_number("3501720001") == "35-017-20001-00-00"

    def test_xlsx_header_detection(self):
        """XLSX parser correctly finds header row even if not row 1."""

    def test_xlsx_handles_merged_cells(self):
        """XLSX parser handles merged cells without crashing."""

    def test_csv_and_xlsx_both_routed_correctly(self):
        """parse_bulk_file routes CSV to _parse_csv and XLSX to _parse_xlsx."""

    def test_missing_api_number_skipped(self):
        """Rows with empty API number are skipped, not yielded."""

    def test_str_conversion_for_xlsx_values(self):
        """XLSX numeric values are converted to str before processing."""

class TestOKSpiderVCR:
    """VCR cassette-based tests."""

    @vcr.use_cassette('backend/tests/scrapers/cassettes/ok/occ_rbdms_wells.yaml')
    def test_rbdms_wells_csv(self):
        """RBDMS wells CSV parsed correctly from recorded response."""

    @vcr.use_cassette('backend/tests/scrapers/cassettes/ok/occ_incidents.yaml')
    def test_incidents_csv(self):
        """Incidents CSV parsed correctly from recorded response."""

    @vcr.use_cassette('backend/tests/scrapers/cassettes/ok/occ_itd_master.yaml')
    def test_itd_xlsx(self):
        """Intent to Drill XLSX parsed correctly from recorded response."""

    @vcr.use_cassette('backend/tests/scrapers/cassettes/ok/occ_completions.yaml')
    def test_completions_xlsx(self):
        """Completions XLSX parsed correctly from recorded response."""

class TestOKSpiderIntegration:
    """Pipeline integration tests."""

    def test_well_items_flow_through_pipeline(self):
        """OK WellItems are processable by DocumentPipeline."""

    def test_document_items_flow_through_pipeline(self):
        """OK DocumentItems are processable by DocumentPipeline."""

    def test_start_requests_covers_all_bulk_files(self):
        """start_requests yields one request per entry in BULK_FILES."""
```

### Step 9: Update State Registry

```python
"OK": {
    "name": "Oklahoma",
    "agency": "Corporation Commission (OCC)",
    "spider_class": "og_scraper.scrapers.spiders.ok_spider.OklahomaOCCSpider",
    "requires_playwright": False,
    "requires_auth": False,
    "scrape_type": "bulk_download",
    "rate_limit_seconds": 3,
    "data_formats": ["CSV", "XLSX", "Shapefile", "PDF"],
},
```

## Files to Create

- `backend/src/og_scraper/scrapers/spiders/ok_spider.py` - Oklahoma OCC spider
- `backend/tests/scrapers/test_ok_spider.py` - Unit, VCR, and integration tests
- `backend/tests/scrapers/cassettes/ok/occ_rbdms_wells.yaml` - Recorded RBDMS CSV
- `backend/tests/scrapers/cassettes/ok/occ_incidents.yaml` - Recorded incidents CSV
- `backend/tests/scrapers/cassettes/ok/occ_itd_master.yaml` - Recorded ITD XLSX
- `backend/tests/scrapers/cassettes/ok/occ_completions.yaml` - Recorded completions XLSX
- `backend/tests/scrapers/cassettes/ok/occ_operators.yaml` - Recorded operators XLSX
- `backend/tests/scrapers/cassettes/ok/occ_uic_wells.yaml` - Recorded UIC XLSX
- `backend/tests/scrapers/record_ok_cassettes.py` - Helper script for recording cassettes

## Files to Modify

- `backend/src/og_scraper/scrapers/state_registry.py` - Update OK entry with real spider class path

## Contracts

### Provides (for downstream tasks)

- **OK Spider class**: `OklahomaOCCSpider` inheriting from `BaseOGSpider` -- `BulkDownloadSpider` pattern with CSV + XLSX support
- **OK WellItems**: Yields `WellItem` objects from RBDMS CSV with fields: `api_number`, `well_name`, `operator_name`, `county`, `latitude`, `longitude`, `well_status`, `well_type`, `spud_date`, `completion_date`, `total_depth`, `formation`, `section`, `township`, `range_`, `state_code="OK"`
- **OK DocumentItems (permits)**: Yields `DocumentItem` with `doc_type="well_permit"` from Intent to Drill XLSX
- **OK DocumentItems (completions)**: Yields `DocumentItem` with `doc_type="completion_report"` from completions XLSX
- **OK DocumentItems (incidents)**: Yields `DocumentItem` with `doc_type="incident_report"` from incidents CSV
- **XLSX parsing utility**: Reusable `_parse_xlsx()` method with header detection that handles government Excel quirks (merged cells, non-row-1 headers) -- reusable by other state spiders
- **VCR cassettes**: Recorded responses in `backend/tests/scrapers/cassettes/ok/`
- **OkTAP stub**: Documented stub for future production data access via Oklahoma Tax Commission

### Consumes (from upstream tasks)

- `BaseOGSpider` from Task 1.3: Abstract base class with `normalize_api_number()`, `build_well_item()`, `build_document_item()`
- `DocumentItem` / `WellItem` from Task 1.3: Item dataclasses
- `DocumentPipeline.process()` from Task 2.4: Pipeline processing
- Scrapy settings from Task 1.3: AutoThrottle, concurrency, retry
- State registry from Task 1.3: OK entry for Huey task lookup
- CSV parsing patterns from Task 4.1 (PA): `_parse_float`, `_parse_int` helpers

## Acceptance Criteria

- [ ] Spider downloads all bulk files from OCC static URLs
- [ ] RBDMS well data CSV parsing extracts wells with correct field mapping
- [ ] Incident report CSV parsing extracts incidents
- [ ] Intent to Drill XLSX parsing extracts drilling permits
- [ ] Well completions XLSX parsing extracts completion reports
- [ ] Operator list XLSX parsing extracts operator data
- [ ] UIC injection XLSX parsing extracts injection data
- [ ] XLSX parser correctly detects header row (handles non-row-1 headers)
- [ ] XLSX parser handles merged cells without crashing
- [ ] Data flows through full pipeline and is stored in database
- [ ] API number normalization handles OK format (state code 35)
- [ ] Rate limiting respects OK site (3s delay, 4 max concurrent)
- [ ] OkTAP production data stub is documented with URLs
- [ ] Spider handles HTTP errors (404, 500) gracefully for individual files without aborting entire crawl
- [ ] All tests pass
- [ ] Build succeeds

## Testing Protocol

### Unit/Integration Tests

- Test file: `backend/tests/scrapers/test_ok_spider.py`
- Test cases:
  - [ ] RBDMS CSV row parsing produces correct WellItem
  - [ ] Incident CSV row parsing produces correct DocumentItem
  - [ ] ITD XLSX row parsing produces correct DocumentItem (well_permit type)
  - [ ] Completion XLSX row parsing produces correct DocumentItem (completion_report type)
  - [ ] Operator XLSX row parsing produces correct operator dict
  - [ ] API number normalization: `"35-017-20001"` -> `"35-017-20001-00-00"`
  - [ ] API number normalization: `"3501720001"` -> `"35-017-20001-00-00"`
  - [ ] XLSX header detection finds headers in row 1, row 2, or row 3
  - [ ] XLSX with merged cells does not crash
  - [ ] Rows with empty API number are skipped
  - [ ] Numeric values from XLSX are converted to str before strip()
  - [ ] start_requests() yields correct number of requests (one per BULK_FILES entry)
  - [ ] parse_bulk_file routes CSV to `_parse_csv` and XLSX to `_parse_xlsx`
  - [ ] HTTP 404 for one file does not abort other file downloads

### API/Script Testing

- Run spider standalone: `uv run scrapy crawl ok_occ -s LOG_LEVEL=DEBUG -a limit=10`
- Expected: Downloads CSV/XLSX files from OCC, logs parsed items, stores to `data/OK/`
- Verify: `ls data/OK/` shows files organized by operator/doc_type

### VCR Cassette Testing

- Record cassettes: `uv run python backend/tests/scrapers/record_ok_cassettes.py`
- Replay tests: `uv run pytest backend/tests/scrapers/test_ok_spider.py -v`
- Expected: All VCR tests pass offline
- Note: XLSX cassettes contain binary data encoded as base64 in YAML

### Build/Lint/Type Checks

- [ ] `uv run ruff check backend/src/og_scraper/scrapers/spiders/ok_spider.py` passes
- [ ] `uv run ruff format --check backend/src/og_scraper/scrapers/spiders/ok_spider.py` passes
- [ ] `uv run pytest backend/tests/scrapers/test_ok_spider.py` passes

## Skills to Read

- `scrapy-playwright-scraping` - BulkDownloadSpider pattern, BaseOGSpider, VCR testing, Scrapy settings
- `state-regulatory-sites` - OK-specific URLs, OkTAP separation, RBDMS standard, rate limits
- `document-processing-pipeline` - Pipeline integration, XLSX parsing gotchas (merged cells, multi-row headers)

## Research Files to Read

- `.claude/orchestration-og-doc-scraper/research/per-state-scrapers-implementation.md` - Section 3.4 (Oklahoma) for exact URLs, bulk file list, OkTAP details, adapter strategy
- `.claude/orchestration-og-doc-scraper/research/state-regulatory-sites.md` - OK section for data file inventory, GIS data, well browse

## Git

- Branch: `feat/task-4.3-ok-scraper`
- Commit message prefix: `Task 4.3:`
