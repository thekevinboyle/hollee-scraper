---
name: scrapy-playwright-scraping
description: Scrapy + Playwright hybrid web scraping with per-state adapter pattern. Use when implementing scrapers, adding states, or debugging scraping issues.
---

# Scrapy + Playwright Hybrid Web Scraping

## What This Is

A hybrid web scraping architecture combining **Scrapy** for high-performance static site crawling with **Playwright** for JavaScript-heavy state regulatory sites. The system scrapes oil and gas regulatory documents from 10 US state agencies using a **per-state adapter pattern** where every state spider inherits from a shared `BaseOGSpider` base class.

**States covered (Tier 1):** Texas, New Mexico, North Dakota, Oklahoma, Colorado
**States covered (Tier 2):** Wyoming, Louisiana, Pennsylvania, California, Alaska

**Core approach:** 60-70% of state sites serve static HTML (Scrapy handles via direct HTTP). 30-40% require JavaScript rendering (Playwright handles via `scrapy-playwright` middleware). Each request opts into Playwright individually using `meta={"playwright": True}`.

---

## When to Use This Skill

- Implementing a new state spider or modifying an existing one
- Adding a new state to the scraper system
- Debugging scraping failures, timeouts, or anti-bot blocks
- Configuring rate limiting, retry logic, or concurrency settings
- Working with EBCDIC encoding (Texas bulk data)
- Setting up the Scrapy + Playwright development environment
- Writing or updating scraper tests with VCR.py cassettes

---

## Setup and Dependencies

### Required Python Packages

```bash
pip install scrapy scrapy-playwright playwright httpx
pip install ebcdic-parser    # For Texas EBCDIC data
pip install pybreaker         # Circuit breaker pattern
pip install tenacity          # Retry with exponential backoff
pip install pydantic          # Data validation
pip install vcrpy             # Test cassettes
```

### Playwright Browser Install

```bash
playwright install chromium
```

This downloads the Chromium binary that `scrapy-playwright` uses. Must be run once per environment (including CI and Docker).

### Verify Installation

```python
import scrapy
from scrapy_playwright.page import PageMethod
from playwright.sync_api import sync_playwright

# Quick check that Playwright can launch
with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    browser.close()
```

---

## Project Structure

```
scraper/
  scrapy.cfg
  og_scraper/
    __init__.py
    settings.py                    # Global Scrapy settings + scrapy-playwright config
    items.py                       # Shared Item classes (WellItem, ProductionItem, etc.)
    pipelines/
      __init__.py
      validation.py                # Pydantic-based field validation
      normalization.py             # API number normalization, date parsing
      storage.py                   # File storage to data/{state}/{operator}/{doc_type}/
      database.py                  # PostgreSQL persistence
      deduplication.py             # Content-hash dedup pipeline
    middlewares/
      __init__.py
      rate_limiter.py              # Per-domain rate limiting middleware
      retry_enhanced.py            # Enhanced retry with circuit breaker
      user_agent_rotator.py        # UA rotation middleware
    spiders/
      __init__.py
      base.py                      # BaseOGSpider - shared logic for all states
      tx_rrc.py                    # Texas Railroad Commission
      nm_ocd.py                    # New Mexico OCD
      nd_dmr.py                    # North Dakota DMR
      ok_occ.py                    # Oklahoma Corporation Commission
      co_ecmc.py                   # Colorado ECMC
      wy_wogcc.py                  # Wyoming WOGCC
      la_sonris.py                 # Louisiana SONRIS
      pa_dep.py                    # Pennsylvania DEP
      ca_calgem.py                 # California CalGEM
      ak_aogcc.py                  # Alaska AOGCC
    adapters/
      __init__.py
      bulk_download.py             # HTTP bulk file downloads (TX, OK, PA)
      arcgis_api.py                # ArcGIS REST API queries (NM, CO, WY, CA, AK)
      open_data_api.py             # CKAN/Open Data portals (CA)
      browser_form.py              # JS-heavy form interaction (LA, WY, AK, ND)
    parsers/
      __init__.py
      ebcdic_parser.py             # Texas EBCDIC-to-UTF8 converter
      fixed_width.py               # ASCII fixed-width record parser
      csv_parser.py                # CSV/XLSX normalization
      dbase_parser.py              # dBase (.dbf) file reader
    utils/
      __init__.py
      api_number.py                # API number normalization (10/12/14-digit)
      coordinate_transform.py      # NAD27/NAD83/WGS84 conversion
      file_hash.py                 # SHA-256 content hashing
    config/
      state_registry.py            # Per-state configuration registry
      tx_layouts/                  # Texas EBCDIC/ASCII layout definitions (JSON)
```

---

## Key Patterns

### 1. BaseOGSpider Adapter Pattern

All state spiders inherit from `BaseOGSpider`. The base class provides shared configuration, API number normalization, item construction helpers, error handling, and progress tracking. Subclasses override `state_code`, `base_url`, `requires_playwright`, and implement `start_requests()` with state-specific logic.

```python
# og_scraper/spiders/base.py
class BaseOGSpider(scrapy.Spider):
    """Base spider for all state oil & gas regulatory sites."""

    # Subclasses MUST override
    state_code: str = None          # e.g., "TX"
    state_name: str = None
    agency_name: str = None
    base_url: str = None
    requires_playwright: bool = False
    requires_auth: bool = False

    # Subclasses MAY override
    rate_limit_delay: float = 5.0
    max_concurrent: int = 2

    custom_settings = {
        'AUTOTHROTTLE_ENABLED': True,
        'AUTOTHROTTLE_START_DELAY': 5,
        'AUTOTHROTTLE_MAX_DELAY': 60,
        'AUTOTHROTTLE_TARGET_CONCURRENCY': 1.0,
    }

    @abstractmethod
    def start_requests(self):
        """Each state spider must define its own entry points."""
        pass

    def normalize_api_number(self, raw: str) -> str:
        """Normalize API numbers to 14-digit format: SS-CCC-NNNNN-SS-SS"""
        digits = ''.join(c for c in raw if c.isdigit())
        if len(digits) == 10:
            return f"{digits[:2]}-{digits[2:5]}-{digits[5:10]}-00-00"
        elif len(digits) == 12:
            return f"{digits[:2]}-{digits[2:5]}-{digits[5:10]}-{digits[10:12]}-00"
        elif len(digits) == 14:
            return f"{digits[:2]}-{digits[2:5]}-{digits[5:10]}-{digits[10:12]}-{digits[12:14]}"
        return raw

    def errback_handler(self, failure):
        """Common error handler -- closes Playwright pages on failure."""
        self.errors += 1
        self.logger.error(f"[{self.state_code}] Request failed: {failure.value}")
        page = failure.request.meta.get("playwright_page")
        if page:
            page.close()
```

### 2. Per-State Spider Structure

Each state spider defines its own URLs, selectors, pagination, and scraping strategy. Three main spider types exist:

**BulkDownloadSpider** (TX, OK, PA) -- download static files via HTTP:
```python
class PennsylvaniaDEPSpider(BaseOGSpider):
    state_code = "PA"
    base_url = "https://greenport.pa.gov/ReportExtracts/OG/Index"
    requires_playwright = False

    custom_settings = {
        'DOWNLOAD_DELAY': 3,
        'CONCURRENT_REQUESTS_PER_DOMAIN': 4,
    }

    def start_requests(self):
        yield scrapy.Request(
            url="https://greenport.pa.gov/ReportExtracts/OG/OilGasWellProdReport",
            callback=self.parse_production,
        )
```

**ArcGISAPISpider** (NM, CA, CO, WY, AK) -- paginated REST API queries:
```python
class CaliforniaCalGEMSpider(BaseOGSpider):
    state_code = "CA"
    base_url = "https://gis.conservation.ca.gov/server/rest/services/WellSTAR/Wells/MapServer/0"

    def start_requests(self):
        yield scrapy.Request(
            url=f"{self.base_url}/query?where=1%3D1&outFields=*&resultOffset=0&resultRecordCount=5000&f=json",
            callback=self.parse_api_response,
        )

    def parse_api_response(self, response):
        data = response.json()
        for feature in data.get("features", []):
            yield self.build_well_item(**feature["attributes"])
        # Paginate if more records exist
        if data.get("exceededTransferLimit"):
            offset = response.meta.get("offset", 0) + 5000
            yield scrapy.Request(
                url=f"{self.base_url}/query?where=1%3D1&outFields=*&resultOffset={offset}&resultRecordCount=5000&f=json",
                callback=self.parse_api_response,
                meta={"offset": offset},
            )
```

**PlaywrightFormSpider** (LA, ND, WY, AK) -- browser automation for JS-heavy sites:
```python
class LouisianaSONRISSpider(BaseOGSpider):
    state_code = "LA"
    base_url = "https://www.sonris.com/"
    requires_playwright = True

    custom_settings = {
        'DOWNLOAD_DELAY': 15,
        'CONCURRENT_REQUESTS_PER_DOMAIN': 1,
    }

    def start_requests(self):
        yield scrapy.Request(
            url="https://www.sonris.com/...",
            meta={
                "playwright": True,
                "playwright_include_page": True,
                "playwright_page_methods": [
                    PageMethod("wait_for_selector", "#report-form"),
                    PageMethod("select_option", "#report-type", "Production"),
                    PageMethod("click", "#generate-report"),
                    PageMethod("wait_for_selector", ".results-table", timeout=15000),
                ],
            },
            callback=self.parse_report,
            errback=self.errback_handler,
        )
```

### 3. Scrapy Settings Configuration

```python
# og_scraper/settings.py

# --- scrapy-playwright Download Handlers ---
DOWNLOAD_HANDLERS = {
    "http": "scrapy_playwright.handler.ScrapyPlaywrightDownloadHandler",
    "https": "scrapy_playwright.handler.ScrapyPlaywrightDownloadHandler",
}
TWISTED_REACTOR = "twisted.internet.asyncioreactor.AsyncioSelectorReactor"

# --- Playwright Browser Config ---
PLAYWRIGHT_BROWSER_TYPE = "chromium"
PLAYWRIGHT_LAUNCH_OPTIONS = {
    "headless": True,
    "args": ["--disable-blink-features=AutomationControlled", "--no-sandbox"],
}
PLAYWRIGHT_MAX_PAGES_PER_CONTEXT = 4
PLAYWRIGHT_MAX_CONTEXTS = 4
PLAYWRIGHT_DEFAULT_NAVIGATION_TIMEOUT = 30_000  # 30 seconds
PLAYWRIGHT_ABORT_REQUEST = lambda req: req.resource_type in ["image", "stylesheet", "font", "media"]
PLAYWRIGHT_RESTART_DISCONNECTED_BROWSER = True

# --- Concurrency & Rate Limiting ---
CONCURRENT_REQUESTS = 4
CONCURRENT_REQUESTS_PER_DOMAIN = 2
DOWNLOAD_DELAY = 5
DOWNLOAD_TIMEOUT = 60

# --- AutoThrottle (adapts per-domain based on server response time) ---
AUTOTHROTTLE_ENABLED = True
AUTOTHROTTLE_START_DELAY = 5
AUTOTHROTTLE_MAX_DELAY = 60
AUTOTHROTTLE_TARGET_CONCURRENCY = 1.0

# --- Retry ---
RETRY_ENABLED = True
RETRY_TIMES = 5
RETRY_HTTP_CODES = [500, 502, 503, 504, 408, 429]
RETRY_PRIORITY_ADJUST = -1

# --- Respectful Crawling ---
ROBOTSTXT_OBEY = True
USER_AGENT = "OGDocScraper/1.0 (Research tool; contact@example.com)"

# --- Item Pipelines (ordered by priority) ---
ITEM_PIPELINES = {
    "og_scraper.pipelines.validation.ValidationPipeline": 100,
    "og_scraper.pipelines.normalization.NormalizationPipeline": 200,
    "og_scraper.pipelines.deduplication.DeduplicationPipeline": 300,
    "og_scraper.pipelines.storage.FileStoragePipeline": 400,
    "og_scraper.pipelines.database.DatabasePipeline": 500,
}

FILES_STORE = "data/"
```

### 4. Playwright Integration for JS-Heavy Sites

The key pattern is **per-request Playwright routing**: most requests use standard HTTP (fast), and only pages that require JavaScript opt into Playwright (slower but necessary).

**Selective Playwright usage:**
```python
def start_requests(self):
    # Static page -- default Scrapy HTTP handler (fast)
    yield scrapy.Request(
        url="https://state-site.gov/data-downloads",
        callback=self.parse_downloads,
    )

    # JS-heavy page -- Playwright browser rendering (slower)
    yield scrapy.Request(
        url="https://state-site.gov/well-search",
        meta={
            "playwright": True,
            "playwright_page_methods": [
                PageMethod("wait_for_selector", "#search-form"),
            ],
        },
        callback=self.parse_search,
        errback=self.errback_handler,
    )
```

**Form interaction with Playwright PageMethods:**
```python
from scrapy_playwright.page import PageMethod

yield scrapy.Request(
    url="https://state-site.gov/search",
    meta={
        "playwright": True,
        "playwright_include_page": True,  # Keep page object for complex interaction
        "playwright_page_methods": [
            PageMethod("wait_for_selector", "#operator-name"),
            PageMethod("fill", "#operator-name", "Devon Energy"),
            PageMethod("select_option", "#state-select", "TX"),
            PageMethod("click", "#search-button"),
            PageMethod("wait_for_selector", ".results-table", timeout=15000),
        ],
    },
    callback=self.parse_results,
    errback=self.errback_handler,
)
```

**Key Playwright settings:**

| Setting | Purpose | Value |
|---------|---------|-------|
| `PLAYWRIGHT_BROWSER_TYPE` | Browser engine | `"chromium"` |
| `PLAYWRIGHT_MAX_PAGES_PER_CONTEXT` | Concurrent browser pages | 4 |
| `PLAYWRIGHT_MAX_CONTEXTS` | Browser context limit | 4 |
| `PLAYWRIGHT_ABORT_REQUEST` | Block images/fonts/media | Enabled for speed |
| `PLAYWRIGHT_RESTART_DISCONNECTED_BROWSER` | Auto-restart crashed browsers | `True` |

### 5. Download Pipeline and File Organization

Files are saved to: `data/{state}/{operator}/{doc_type}/{filename}`

This matches the project's file organization structure from DISCOVERY.md (D22). The `FileStoragePipeline` at priority 400 handles path construction and file writing. The `DeduplicationPipeline` at priority 300 uses SHA-256 content hashing to prevent duplicate storage.

### 6. State Configuration Registry

The `state_registry.py` defines per-state metadata used to drive spider behavior:

```python
STATE_REGISTRY = {
    "TX": {
        "name": "Texas",
        "agency": "Railroad Commission of Texas (RRC)",
        "requires_playwright": False,
        "scrape_type": "bulk_download",
        "rate_limit_seconds": 10,
        "data_formats": ["EBCDIC", "ASCII", "CSV", "JSON", "dBase", "PDF", "Shapefile"],
    },
    "PA": {
        "name": "Pennsylvania",
        "agency": "Dept of Environmental Protection (DEP)",
        "requires_playwright": False,
        "scrape_type": "bulk_download",
        "rate_limit_seconds": 3,
        "data_formats": ["CSV"],
    },
    "LA": {
        "name": "Louisiana",
        "agency": "Dept of Conservation & Energy (SONRIS)",
        "requires_playwright": True,
        "scrape_type": "browser_form",
        "rate_limit_seconds": 15,
        "data_formats": ["Excel", "PDF", "HTML"],
    },
    # ... all 10 states
}
```

---

## Rate Limits and Constraints

### Per-State Rate Limit Configuration

| State | Base Delay | Max Concurrent | Strategy |
|-------|-----------|----------------|----------|
| **TX** | 10s | 2 | Bulk download only. DO NOT scrape the PDQ web interface -- RRC detects and blocks automated tools. |
| **NM** | 5s | 2 | ArcGIS API standard. Paginate with `resultOffset` in batches of 1,000. |
| **ND** | 15s | 1 | Conservative. Subscription portal -- avoid triggering account lockout. |
| **OK** | 3s | 4 | Relaxed. Static file downloads with minimal rate limiting. |
| **CO** | 8s | 2 | Mixed: relaxed for CSV downloads, conservative for COGIS form queries. |
| **WY** | 10s | 1 | Conservative. Legacy ColdFusion + modern JS servers may be resource-constrained. |
| **LA** | 15s | 1 | Very conservative. Oracle-backed SONRIS; complex queries stress the server. |
| **PA** | 3s | 4 | Relaxed. GreenPort CSV export is designed for bulk access. |
| **CA** | 3s | 3 | ArcGIS API standard. MaxRecordCount=5,000 per query. |
| **AK** | 5s | 2 | Moderate. Smaller dataset; government-hosted ASP.NET. |

### AutoThrottle

AutoThrottle is always enabled. It automatically adjusts request delays based on server response time. The `AUTOTHROTTLE_TARGET_CONCURRENCY` of 1.0 means one concurrent request per domain as a safe baseline. Individual spiders override via `custom_settings`.

### Respectful Crawling Practices

- **Always obey `robots.txt`**: `ROBOTSTXT_OBEY = True` in settings
- **Identify the scraper**: User-Agent includes contact info
- **Add request jitter**: +/- 30% randomization on base delays to avoid detection patterns
- **Prefer bulk downloads and APIs**: Only scrape HTML when no bulk/API alternative exists
- **Schedule heavy scraping off-peak**: Government sites have lower traffic overnight (11 PM - 6 AM local time)

### Anti-Bot Handling

Government sites have less aggressive anti-bot protections than commercial sites, but some employ:
- Basic IP-based rate limiting
- Session-based access controls
- Simple headless browser detection

**Layer 1 (always apply):** Realistic User-Agent rotation, complete HTTP headers, conservative rate limiting, request jitter.

**Layer 2 (Playwright requests):** Use `playwright-stealth` to remove `navigator.webdriver` flag, spoof browser plugins, mock Chrome runtime. Block unnecessary resources (images, fonts, media) via `PLAYWRIGHT_ABORT_REQUEST`.

**Layer 3 (if needed):** Separate sessions per state site, cookie rotation.

### Circuit Breaker Pattern

Prevent hammering a site that is clearly down:
```python
import pybreaker

state_breakers = {
    "TX": pybreaker.CircuitBreaker(fail_max=5, reset_timeout=300),
    "LA": pybreaker.CircuitBreaker(fail_max=3, reset_timeout=600),  # More sensitive for SONRIS
}
```

States: CLOSED (normal) -> OPEN (fail immediately after N failures) -> HALF-OPEN (test one request after timeout).

---

## Common Pitfalls

### Texas: EBCDIC Encoding for Bulk Downloads

Many TX RRC datasets (production ledgers, well databases) use IBM mainframe EBCDIC encoding with COMP-3 (packed decimal) fields. Use `ebcdic-parser` with JSON layout definitions. Code page is `cp037` (US/Canada). Layout field positions come from RRC-provided PDF manuals -- these must be converted to JSON layout files once per dataset.

**Always prefer CSV alternatives when available.** The Production Data Query Dump (CSV, last Saturday of each month) provides the same data as the EBCDIC ledger files in a far easier format. Only use EBCDIC for datasets not available in CSV/ASCII.

```python
from ebcdic_parser.convert import run

return_code = run(
    input_file="data/raw/tx/dbf900.ebc",
    output_folder="data/processed/tx/",
    layout_file="config/tx_layouts/wellbore.json",
    output_delimiter=",",
)
```

### North Dakota: Paywalled Data

The most valuable ND data (per-well production, scout tickets, well logs) requires a paid subscription:
- **Basic**: $100/year (well index, scout tickets, production histories)
- **Premium**: $500/year (everything in Basic + field orders, well logs, decline curves)

Free data is limited to monthly production report PDFs, daily activity reports, and basic well search. Free PDFs require OCR. The NorthSTAR system migration may change URLs and interfaces.

### Louisiana SONRIS: Hardest to Scrape

SONRIS is backed by an Oracle database with millions of records. It has no REST API -- all access is through a complex JavaScript web application. Expect:
- Oracle query timeouts on complex requests
- Session-based state management requiring Playwright throughout
- Recent URL flux (agency renamed from DENR to Dept of Conservation and Energy in Oct 2025 -- URLs exist across `denr.louisiana.gov`, `dce.louisiana.gov`, and `dnr.louisiana.gov`)
- Louisiana uses its own serial number system for wells in addition to API numbers
- IDR (Interactive Data Reports) with Excel export are the primary extraction method

Budget 5-8 days of development time for this state alone.

### Pennsylvania GreenPort: Easiest to Scrape

PA provides all data as on-demand CSV exports from GreenPort. No Playwright needed. Each report requires selecting a reporting period parameter, then downloading the resulting CSV. Production, well inventory, compliance, plugging, and waste reports are all available. The data dictionary PDF defines all fields. Development time: 1-2 days.

### Site Layout Changes

Government sites redesign without warning. Industry-wide, 10-15% of crawlers need weekly fixes due to DOM changes. Mitigate with:
- **Schema validation** in the pipeline: alert when required fields come back empty
- **Success rate monitoring**: alert when spider success rate drops below 90%
- **Fallback selectors**: define primary + backup CSS selectors for critical elements
- **Weekly health check spider**: validate all state sites are accessible and returning expected page structures

### Other State-Specific Gotchas

- **TX**: DO NOT scrape the Production Data Query (PDQ) web interface. RRC explicitly detects and blocks automated tools. Use bulk downloads only.
- **NM**: Data is spread across OCD Hub, OCD Permitting (ASP.NET), ONGARD (State Land Office), and GO-TECH (NM Tech). No single unified source.
- **OK**: Production data is maintained by the Oklahoma Tax Commission (OkTAP), NOT the OCC. Must scrape two separate systems.
- **CO**: Dual domains -- `ecmc.colorado.gov` (new) and `ecmc.state.co.us` (legacy). Some features live on one or the other.
- **WY**: Data Explorer is JS-heavy (needs Playwright). Legacy portal uses ColdFusion (.cfm). ArcGIS API is available as a partial alternative.
- **AK**: Data Miner runs on plain HTTP (not HTTPS). ASP.NET WebForms with ViewState/PostBack patterns.
- **CA**: ArcGIS returns data in Web Mercator (EPSG:3857). Convert to WGS84 for standard lat/long. MaxRecordCount is 5,000 per query.

---

## Testing Strategy

### VCR.py Cassettes for HTTP Response Recording

Use VCR.py to record real HTTP responses as "cassettes" (YAML/JSON files), then replay them in tests without hitting live servers. This makes tests fast, deterministic, and independent of network availability.

```python
import vcr

@vcr.use_cassette('tests/cassettes/pa_greenport_production.yaml')
def test_pa_production_parse():
    """Test PA production CSV parsing against recorded real response."""
    spider = PennsylvaniaDEPSpider()
    # Response is replayed from cassette, not fetched live
    results = list(spider.parse_production(fake_response))
    assert len(results) > 0
    assert all(item['state_code'] == 'PA' for item in results)
```

### Mock Playwright Pages

For spiders that use Playwright, mock the page object to test parsing logic without launching a real browser:

```python
from unittest.mock import AsyncMock, MagicMock

def test_la_sonris_parse():
    """Test LA SONRIS report parsing with mocked Playwright page."""
    mock_page = AsyncMock()
    mock_page.content.return_value = load_fixture("la_sonris_report.html")
    mock_response = MagicMock()
    mock_response.meta = {"playwright_page": mock_page}

    spider = LouisianaSONRISSpider()
    results = list(spider.parse_report(mock_response))
    assert len(results) > 0
```

### Test Organization

```
tests/
  cassettes/                # VCR.py recorded HTTP responses
    pa_greenport_production.yaml
    ca_calgem_wells.yaml
    tx_rrc_bulk_download.yaml
  fixtures/                 # Static HTML/JSON fixtures for parsing tests
    la_sonris_report.html
    nm_ocd_arcgis_response.json
  test_spiders/
    test_base_spider.py     # BaseOGSpider unit tests
    test_tx_rrc.py
    test_pa_dep.py
    test_la_sonris.py
    ...
  test_pipelines/
    test_validation.py
    test_normalization.py
    test_deduplication.py
  test_parsers/
    test_ebcdic_parser.py
    test_api_number.py
```

---

## Cost Implications

- **Scraping infrastructure**: Free. No paid proxies needed for government sites at this scale. Direct connections with respectful rate limiting are sufficient.
- **North Dakota subscription**: $100-$500/year depending on tier. This is the only required paid data access. Basic ($100/yr) covers most needs; Premium ($500/yr) adds well logs and field orders.
- **CAPTCHA solving**: Not expected to be needed. Government sites rarely use CAPTCHAs. Budget $0 initially; add CapSolver or 2Captcha (~$1-3/1000 solves) only if specific sites require it.
- **Proxy services**: Not needed initially. If a specific state blocks direct connections, start with ScraperAPI ($49-99/month).

**Total expected cost: $100-$500/year** (ND subscription only).

---

## Implementation Priority Order

Build states in this order based on difficulty and data value:

### Phase 1: Bulk Downloads (validates pipeline)
1. **PA** (1-2 days) -- Cleanest data, CSV exports, minimal development
2. **OK** (2-3 days) -- Extensive nightly CSV/XLSX downloads
3. **TX** (3-5 days) -- Largest dataset, EBCDIC parsing is extra work but CSV alternatives exist

### Phase 2: API-Based Access
4. **CA** (2-3 days) -- Well-documented ArcGIS REST API + Open Data portal
5. **NM** (3-4 days) -- ArcGIS Hub + OCD Permitting (ASP.NET forms)
6. **CO** (3-4 days) -- Bulk CSVs + COGIS query forms

### Phase 3: Browser Automation
7. **AK** (2-3 days) -- ASP.NET Data Miner with export. Good Playwright testbed
8. **WY** (3-5 days) -- Data Explorer (JS) + ColdFusion legacy
9. **ND** (4-6 days) -- Subscription paywall, PDF-heavy free data, NorthSTAR migration
10. **LA** (5-8 days) -- SONRIS is the hardest. Oracle backend, complex JS, no API

**Total estimated development time: 28-43 days** for one developer across all 10 states.

---

## Adding a New State

To add a new state scraper:

1. Add an entry to `state_registry.py` with URLs, rate limits, scrape type, and data formats
2. Create a new spider file in `og_scraper/spiders/` inheriting from `BaseOGSpider`
3. Set required class attributes: `state_code`, `state_name`, `agency_name`, `base_url`, `requires_playwright`
4. Override `custom_settings` with state-specific rate limits and concurrency
5. Implement `start_requests()` with state-specific entry points
6. Implement parse callbacks for each page type
7. Add VCR.py cassettes or HTML fixtures for tests
8. Test with a limited crawl before enabling full scraping

---

## References

- **DISCOVERY.md**: `.claude/orchestration-og-doc-scraper/DISCOVERY.md` -- Project scope, tech stack decisions, architecture choices
- **Scraping Strategies Research**: `.claude/orchestration-og-doc-scraper/research/scraping-strategies.md` -- Framework comparison, anti-bot evasion, retry patterns, site change detection, legal considerations, full system architecture
- **Per-State Implementation Guide**: `.claude/orchestration-og-doc-scraper/research/per-state-scrapers-implementation.md` -- Detailed per-state URLs, data formats, gotchas, adapter strategies, EBCDIC handling, rate limits, implementation priority
- **scrapy-playwright GitHub**: https://github.com/scrapy-plugins/scrapy-playwright
- **Playwright Python docs**: https://playwright.dev/python/
- **Scrapy docs**: https://docs.scrapy.org/
