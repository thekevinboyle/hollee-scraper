# Per-State Scraper Implementation Guide

**Research Date:** 2026-03-27
**Context:** Second-wave research for Oil & Gas Document Scraper project
**Architecture:** Scrapy + Playwright hybrid, per-state adapter pattern, on-demand triggering
**States:** TX, NM, ND, OK, CO, WY, LA, PA, CA, AK

---

## Table of Contents

1. [Scrapy Project Structure & Adapter Pattern](#1-scrapy-project-structure--adapter-pattern)
2. [scrapy-playwright Integration & Configuration](#2-scrapy-playwright-integration--configuration)
3. [Per-State Adapter Specifications](#3-per-state-adapter-specifications)
   - [3.1 Texas (TX)](#31-texas-tx---railroad-commission-rrc)
   - [3.2 New Mexico (NM)](#32-new-mexico-nm---oil-conservation-division-ocd)
   - [3.3 North Dakota (ND)](#33-north-dakota-nd---department-of-mineral-resources-dmr)
   - [3.4 Oklahoma (OK)](#34-oklahoma-ok---corporation-commission-occ)
   - [3.5 Colorado (CO)](#35-colorado-co---energy--carbon-management-commission-ecmc)
   - [3.6 Wyoming (WY)](#36-wyoming-wy---oil--gas-conservation-commission-wogcc)
   - [3.7 Louisiana (LA)](#37-louisiana-la---sonris)
   - [3.8 Pennsylvania (PA)](#38-pennsylvania-pa---department-of-environmental-protection-dep)
   - [3.9 California (CA)](#39-california-ca---calgem)
   - [3.10 Alaska (AK)](#310-alaska-ak---aogcc)
4. [EBCDIC Handling for Texas Data](#4-ebcdic-handling-for-texas-data)
5. [Rate Limiting Strategies Per State](#5-rate-limiting-strategies-per-state)
6. [Implementation Priority Order](#6-implementation-priority-order)

---

## 1. Scrapy Project Structure & Adapter Pattern

### Recommended Directory Layout

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
      normalization.py             # API number normalization, date parsing, etc.
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
      tx_rrc.py                    # Texas Railroad Commission spider
      nm_ocd.py                    # New Mexico OCD spider
      nd_dmr.py                    # North Dakota DMR spider
      ok_occ.py                    # Oklahoma Corporation Commission spider
      co_ecmc.py                   # Colorado ECMC spider
      wy_wogcc.py                  # Wyoming WOGCC spider
      la_sonris.py                 # Louisiana SONRIS spider
      pa_dep.py                    # Pennsylvania DEP spider
      ca_calgem.py                 # California CalGEM spider
      ak_aogcc.py                  # Alaska AOGCC spider
    adapters/
      __init__.py
      bulk_download.py             # Adapter for HTTP bulk file downloads (TX, OK, PA)
      arcgis_api.py                # Adapter for ArcGIS REST API queries (NM, CO, WY, CA, AK)
      open_data_api.py             # Adapter for CKAN/Open Data portals (CA)
      browser_form.py              # Adapter for JS-heavy form interaction (LA, WY, AK, ND)
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
        wellbore.json
        oil_ledger.json
        gas_ledger.json
        production.json
        drilling_permit.json
```

### BaseOGSpider Pattern

```python
# og_scraper/spiders/base.py
import scrapy
from abc import abstractmethod
from datetime import datetime
from og_scraper.items import WellItem, ProductionItem, DocumentItem


class BaseOGSpider(scrapy.Spider):
    """Base spider for all state oil & gas regulatory sites.

    Provides common functionality:
    - State metadata and configuration
    - Shared item construction helpers
    - API number normalization
    - Error handling and logging
    - Progress tracking for dashboard reporting
    """

    # Subclasses MUST override these
    state_code: str = None          # Two-letter state code (e.g., "TX")
    state_name: str = None          # Full state name
    agency_name: str = None         # Regulatory agency name
    base_url: str = None            # Agency root URL
    requires_playwright: bool = False
    requires_auth: bool = False

    # Subclasses MAY override these
    rate_limit_delay: float = 5.0   # Seconds between requests (default)
    max_concurrent: int = 2         # Max concurrent requests to this domain

    custom_settings = {
        'AUTOTHROTTLE_ENABLED': True,
        'AUTOTHROTTLE_START_DELAY': 5,
        'AUTOTHROTTLE_MAX_DELAY': 60,
        'AUTOTHROTTLE_TARGET_CONCURRENCY': 1.0,
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.scrape_started = datetime.utcnow()
        self.items_scraped = 0
        self.errors = 0
        assert self.state_code, "Subclass must set state_code"
        assert self.base_url, "Subclass must set base_url"

    @abstractmethod
    def start_requests(self):
        """Each state spider must define its own entry points."""
        pass

    def normalize_api_number(self, raw: str) -> str:
        """Normalize API numbers to 14-digit format with dashes."""
        digits = ''.join(c for c in raw if c.isdigit())
        if len(digits) == 10:
            return f"{digits[:2]}-{digits[2:5]}-{digits[5:10]}-00-00"
        elif len(digits) == 12:
            return f"{digits[:2]}-{digits[2:5]}-{digits[5:10]}-{digits[10:12]}-00"
        elif len(digits) == 14:
            return f"{digits[:2]}-{digits[2:5]}-{digits[5:10]}-{digits[10:12]}-{digits[12:14]}"
        return raw  # Return original if unparseable

    def build_well_item(self, **kwargs) -> WellItem:
        """Construct a WellItem with common defaults."""
        kwargs.setdefault('state_code', self.state_code)
        kwargs.setdefault('source_agency', self.agency_name)
        kwargs.setdefault('scraped_at', datetime.utcnow().isoformat())
        return WellItem(**kwargs)

    def build_document_item(self, **kwargs) -> DocumentItem:
        """Construct a DocumentItem with common defaults."""
        kwargs.setdefault('state_code', self.state_code)
        kwargs.setdefault('source_agency', self.agency_name)
        kwargs.setdefault('scraped_at', datetime.utcnow().isoformat())
        return DocumentItem(**kwargs)

    def errback_handler(self, failure):
        """Common error handler for all requests."""
        self.errors += 1
        self.logger.error(f"[{self.state_code}] Request failed: {failure.value}")
        # Close Playwright page if one was opened
        page = failure.request.meta.get("playwright_page")
        if page:
            page.close()
```

### State Configuration Registry

```python
# og_scraper/config/state_registry.py
STATE_REGISTRY = {
    "TX": {
        "name": "Texas",
        "agency": "Railroad Commission of Texas (RRC)",
        "spider_class": "og_scraper.spiders.tx_rrc.TexasRRCSpider",
        "requires_playwright": False,
        "requires_auth": False,
        "scrape_type": "bulk_download",
        "rate_limit_seconds": 10,
        "data_formats": ["EBCDIC", "ASCII", "CSV", "PDF", "JSON", "dBase", "Shapefile"],
    },
    "NM": {
        "name": "New Mexico",
        "agency": "Oil Conservation Division (OCD)",
        "spider_class": "og_scraper.spiders.nm_ocd.NewMexicoOCDSpider",
        "requires_playwright": False,
        "requires_auth": False,
        "scrape_type": "arcgis_api",
        "rate_limit_seconds": 5,
        "data_formats": ["CSV", "GeoJSON", "KML", "Shapefile"],
    },
    "ND": {
        "name": "North Dakota",
        "agency": "Department of Mineral Resources (DMR)",
        "spider_class": "og_scraper.spiders.nd_dmr.NorthDakotaDMRSpider",
        "requires_playwright": True,
        "requires_auth": True,
        "scrape_type": "browser_form",
        "rate_limit_seconds": 15,
        "data_formats": ["PDF", "HTML", "Excel"],
        "subscription_required": True,
        "subscription_cost": "$100-$500/year",
    },
    "OK": {
        "name": "Oklahoma",
        "agency": "Corporation Commission (OCC)",
        "spider_class": "og_scraper.spiders.ok_occ.OklahomaOCCSpider",
        "requires_playwright": False,
        "requires_auth": False,
        "scrape_type": "bulk_download",
        "rate_limit_seconds": 5,
        "data_formats": ["CSV", "XLSX", "Shapefile", "PDF"],
    },
    "CO": {
        "name": "Colorado",
        "agency": "Energy & Carbon Management Commission (ECMC)",
        "spider_class": "og_scraper.spiders.co_ecmc.ColoradoECMCSpider",
        "requires_playwright": True,  # COGIS queries need browser for some forms
        "requires_auth": False,
        "scrape_type": "mixed",
        "rate_limit_seconds": 8,
        "data_formats": ["CSV", "PDF"],
    },
    "WY": {
        "name": "Wyoming",
        "agency": "Oil & Gas Conservation Commission (WOGCC)",
        "spider_class": "og_scraper.spiders.wy_wogcc.WyomingWOGCCSpider",
        "requires_playwright": True,
        "requires_auth": False,
        "scrape_type": "mixed",
        "rate_limit_seconds": 10,
        "data_formats": ["Excel", "PDF", "Shapefile"],
    },
    "LA": {
        "name": "Louisiana",
        "agency": "Dept of Conservation & Energy (SONRIS)",
        "spider_class": "og_scraper.spiders.la_sonris.LouisianaSONRISSpider",
        "requires_playwright": True,
        "requires_auth": False,
        "scrape_type": "browser_form",
        "rate_limit_seconds": 15,
        "data_formats": ["Excel", "PDF", "HTML"],
    },
    "PA": {
        "name": "Pennsylvania",
        "agency": "Dept of Environmental Protection (DEP)",
        "spider_class": "og_scraper.spiders.pa_dep.PennsylvaniaDEPSpider",
        "requires_playwright": False,
        "requires_auth": False,
        "scrape_type": "bulk_download",
        "rate_limit_seconds": 3,
        "data_formats": ["CSV"],
    },
    "CA": {
        "name": "California",
        "agency": "CalGEM (Geologic Energy Management Division)",
        "spider_class": "og_scraper.spiders.ca_calgem.CaliforniaCalGEMSpider",
        "requires_playwright": False,
        "requires_auth": False,
        "scrape_type": "arcgis_api",
        "rate_limit_seconds": 3,
        "data_formats": ["CSV", "GeoJSON", "JSON", "Shapefile"],
    },
    "AK": {
        "name": "Alaska",
        "agency": "Oil & Gas Conservation Commission (AOGCC)",
        "spider_class": "og_scraper.spiders.ak_aogcc.AlaskaAOGCCSpider",
        "requires_playwright": True,  # Data Miner is ASP.NET form-based
        "requires_auth": False,
        "scrape_type": "mixed",
        "rate_limit_seconds": 8,
        "data_formats": ["CSV", "Excel", "PDF"],
    },
}
```

---

## 2. scrapy-playwright Integration & Configuration

### settings.py Configuration

```python
# og_scraper/settings.py

BOT_NAME = "og_scraper"
SPIDER_MODULES = ["og_scraper.spiders"]
NEWSPIDER_MODULE = "og_scraper.spiders"

# --- Scrapy-Playwright Configuration ---
DOWNLOAD_HANDLERS = {
    "http": "scrapy_playwright.handler.ScrapyPlaywrightDownloadHandler",
    "https": "scrapy_playwright.handler.ScrapyPlaywrightDownloadHandler",
}
TWISTED_REACTOR = "twisted.internet.asyncioreactor.AsyncioSelectorReactor"

PLAYWRIGHT_BROWSER_TYPE = "chromium"
PLAYWRIGHT_LAUNCH_OPTIONS = {
    "headless": True,
    "args": [
        "--disable-blink-features=AutomationControlled",
        "--no-sandbox",
    ],
}
PLAYWRIGHT_MAX_PAGES_PER_CONTEXT = 4
PLAYWRIGHT_MAX_CONTEXTS = 4
PLAYWRIGHT_DEFAULT_NAVIGATION_TIMEOUT = 30_000  # 30 seconds

# Block unnecessary resources for Playwright pages (speed + stealth)
PLAYWRIGHT_ABORT_REQUEST = (
    lambda req: req.resource_type in ["image", "stylesheet", "font", "media"]
)

# Auto-restart crashed browsers
PLAYWRIGHT_RESTART_DISCONNECTED_BROWSER = True

# --- Concurrency & Rate Limiting ---
CONCURRENT_REQUESTS = 4
CONCURRENT_REQUESTS_PER_DOMAIN = 2
DOWNLOAD_DELAY = 5
DOWNLOAD_TIMEOUT = 60

# AutoThrottle (adapts per-domain based on server response time)
AUTOTHROTTLE_ENABLED = True
AUTOTHROTTLE_START_DELAY = 5
AUTOTHROTTLE_MAX_DELAY = 60
AUTOTHROTTLE_TARGET_CONCURRENCY = 1.0
AUTOTHROTTLE_DEBUG = False

# --- Retry Configuration ---
RETRY_ENABLED = True
RETRY_TIMES = 5
RETRY_HTTP_CODES = [500, 502, 503, 504, 408, 429]
RETRY_PRIORITY_ADJUST = -1

# --- User Agent Rotation ---
USER_AGENT = "OGDocScraper/1.0 (Educational/Research; contact@example.com)"

# --- Item Pipelines ---
ITEM_PIPELINES = {
    "og_scraper.pipelines.validation.ValidationPipeline": 100,
    "og_scraper.pipelines.normalization.NormalizationPipeline": 200,
    "og_scraper.pipelines.deduplication.DeduplicationPipeline": 300,
    "og_scraper.pipelines.storage.FileStoragePipeline": 400,
    "og_scraper.pipelines.database.DatabasePipeline": 500,
}

# --- File Storage ---
FILES_STORE = "data/"

# --- Logging ---
LOG_LEVEL = "INFO"
LOG_FORMAT = "%(asctime)s [%(name)s] %(levelname)s: %(message)s"
```

### Per-Request Playwright Routing Pattern

The key architectural pattern: most requests use standard HTTP (fast), and only JavaScript-heavy pages opt into Playwright (slower but necessary).

```python
# Example: Selective Playwright usage in a spider
class ExampleStateSpider(BaseOGSpider):

    def start_requests(self):
        # Static page: use default Scrapy HTTP handler (fast)
        yield scrapy.Request(
            url="https://state-site.gov/data-downloads",
            callback=self.parse_downloads,
        )

        # JS-heavy search form: use Playwright (slower but needed)
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

### Playwright Page Methods for Form Interaction

```python
from scrapy_playwright.page import PageMethod

# Fill and submit a search form
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

---

## 3. Per-State Adapter Specifications

---

### 3.1 Texas (TX) - Railroad Commission (RRC)

**Scraping Approach:** Bulk Download (primary), NO web scraping of PDQ

**Agency:** Railroad Commission of Texas (RRC)

#### Exact URLs

| Resource | URL |
|----------|-----|
| Main Site | https://www.rrc.texas.gov/ |
| Data Downloads Index | https://www.rrc.texas.gov/resource-center/research/data-sets-available-for-download/ |
| Production Data Query (DO NOT SCRAPE) | https://webapps2.rrc.texas.gov/EWA/ewaPdqMain.do |
| Well Records Online | https://www.rrc.texas.gov/oil-and-gas/research-and-statistics/obtaining-commission-records/oil-and-gas-well-records-online/ |
| Online Research Queries | https://www.rrc.texas.gov/resource-center/research/research-queries/ |

#### Bulk Download URLs (via mft.rrc.texas.gov)

**Production Data:**

| Dataset | Format | Update Freq | Download URL |
|---------|--------|-------------|--------------|
| Production Data Query Dump | CSV | Last Saturday/month | `https://mft.rrc.texas.gov/link/1f5ddb8d-329a-4459-b7f8-177b4f5ee60d` |
| Production for Pending Leases | CSV | Monthly (by 21st) | `https://mft.rrc.texas.gov/link/941af606-dc16-44ef-9b1e-f942f36fc582` |
| Statewide Production Oil | EBCDIC | Monthly (by 27th) | `https://mft.rrc.texas.gov/link/20ff2205-6579-450f-a2ee-cbd37986b557` |
| Statewide Production Gas | EBCDIC | Monthly (by 27th) | `https://mft.rrc.texas.gov/link/22b56e60-e700-4ee0-a718-9a4bb690f3c8` |
| Oil Ledger (all districts) | EBCDIC | Monthly (by 20th) | `https://mft.rrc.texas.gov/link/c5081c77-d32c-4ded-9b33-5aca3833306c` |
| Gas Ledger (all districts) | EBCDIC | Monthly (by 20th) | `https://mft.rrc.texas.gov/link/c45ee840-9d50-4a74-b6b0-dba0cb4954b7` |
| Historical Ledger Oil | EBCDIC | Monthly (by 27th) | `https://mft.rrc.texas.gov/link/2ba7ecc0-83c6-47ba-b26b-49205d21802d` |
| Historical Ledger Gas | EBCDIC | Monthly (by 27th) | `https://mft.rrc.texas.gov/link/b27e9cd1-00de-4319-a0a8-93aed85c0797` |
| PR (P1/P2) Gas Disposition | ASCII + EBCDIC | Monthly (by 27th) | `https://mft.rrc.texas.gov/link/dffcedaf-a097-471f-a710-345e72975738` |
| P-18 Skim Oil/Condensate | JSON | Monthly | `/resource-center/research/data-sets-available-for-download/p-18-skim-oil-condensate-report/` |

**Well Data:**

| Dataset | Format | Update Freq | Download URL |
|---------|--------|-------------|--------------|
| Full Wellbore | EBCDIC + ASCII | Weekly (Monday) | `https://mft.rrc.texas.gov/link/b070ce28-5c58-4fe2-9eb7-8b70befb7af9` |
| Wellbore Query Data | ASCII | Monthly (2nd workday) | `https://mft.rrc.texas.gov/link/650649b7-e019-4d77-a8e0-d118d6455381` |
| Statewide Oil Well DB | EBCDIC | Monthly (by 27th) | `https://mft.rrc.texas.gov/link/08132ccc-4170-4564-8f32-3aceb0175f0b` |
| Statewide Gas Well DB | EBCDIC | Monthly (by 27th) | `https://mft.rrc.texas.gov/link/ca2a67ff-897a-46a1-b6d4-25c187c52ce2` |
| Completion Info (data) | ASCII | Nightly | `https://mft.rrc.texas.gov/link/ed7ab066-879f-40b6-8144-2ae4b6810c04` |
| Imaged Completion Files | PDF | Nightly | `https://mft.rrc.texas.gov/link/8e91acb8-69cc-4d57-ad72-c7f7d5a7675e` |
| Directional Survey Apps | PDF | Nightly | `https://mft.rrc.texas.gov/link/01769aa7-dee8-4121-bb25-e7557307f6bd` |

**Drilling Permits:**

| Dataset | Format | Update Freq | Download URL |
|---------|--------|-------------|--------------|
| Permit Master | ASCII | Monthly (7th workday) | `https://mft.rrc.texas.gov/link/e99fbe81-40cd-4a79-b992-9fc71d0f06d4` |
| Permit Master + Trailer | ASCII | Monthly (7th workday) | `https://mft.rrc.texas.gov/link/beeeab0c-7d07-4111-af88-783c93677b2c` |
| Permit Daily w/ Coords | ASCII | Nightly | `https://mft.rrc.texas.gov/link/5f07cc72-2e79-4df8-ade1-9aeb792e03fc` |
| Permit (W1) Imaged Files | PDF | Nightly | `https://mft.rrc.texas.gov/link/f11363bb-8120-4e8c-bbc0-a253ec0a85d4` |
| Horizontal Drilling Permits | ASCII | Monthly (3rd Monday) | `https://mft.rrc.texas.gov/link/c725637f-6748-47b9-ad74-e0396879d88b` |
| Permits Pending Approval | ASCII | Twice daily | `https://mft.rrc.texas.gov/link/0ad92a65-4212-49a1-98a7-d667a55fb497` |

**Regulatory / Field Data:**

| Dataset | Format | Update Freq | Download URL |
|---------|--------|-------------|--------------|
| Oil & Gas Field Names | ASCII | Monthly (4th workday) | `https://mft.rrc.texas.gov/link/3122a5ec-eb3b-4ed2-908b-f41fa94ab8ba` |
| Oil & Gas Field Rules | ASCII | Monthly (by 27th) | `https://mft.rrc.texas.gov/link/6b12ba15-d46a-46a9-b0ce-ca743d9cefe6` |
| P5 Organization (operators) | ASCII + EBCDIC | Monthly (by 25th) | `https://mft.rrc.texas.gov/link/04652169-eed6-4396-9019-2e270e790f6c` |
| Inspections/Violations (ICE) | TXT | Weekly (Monday) | `https://mft.rrc.texas.gov/link/c7c28dc9-b218-4f0a-8278-bf15d009def1` |
| Oil & Gas Docket | ASCII | Monthly (by 27th) | `https://mft.rrc.texas.gov/link/e9af053b-28c8-49b2-ad40-bf2f10f4f21a` |
| UIC Database | ASCII + EBCDIC | Monthly (3rd workday) | `https://mft.rrc.texas.gov/link/d2438c05-b42f-45a8-b0c6-edceb0912767` |
| R3 Gas Processing Plants | JSON | Monthly (new 09-2025) | `/resource-center/research/data-sets-available-for-download/r-3-gas-processing-plants-report/` |

**GIS/Map Data:**

| Dataset | Format | Update Freq | Download URL |
|---------|--------|-------------|--------------|
| Well Layers by County | Shapefile | Twice weekly | `https://mft.rrc.texas.gov/link/d551fb20-442e-4b67-84fa-ac3f23ecabb4` |
| Pipeline Layers by County | Shapefile | Twice weekly | `https://mft.rrc.texas.gov/link/c7cbab0c-afe2-4f6f-91ae-e6ed7d3a7ab6` |
| Statewide API Data | ASCII | Twice weekly | `https://mft.rrc.texas.gov/link/701db9a3-32b5-488d-812b-cd6ff7d0fe85` |
| Statewide API Data | dBase | Twice weekly | `https://mft.rrc.texas.gov/link/1eb94d66-461d-4114-93f7-b4bc04a70674` |

#### Authentication
No login required. All bulk downloads are free and public.

#### Document Types Available
Production reports, well permits (W-1), completion reports, directional surveys, spacing/field orders, inspection records (ICE), UIC injection data, operator records (P-5), horizontal drilling permits, field rules, gas processing plant reports (R-3), well status reports (W-10/G-10).

#### Data Formats
EBCDIC (.ebc, .ebc.Z), ASCII fixed-width, CSV, JSON (new for some datasets), dBase (.dbf), PDF, TIFF, ArcView Shapefile (.shp).

#### Anti-Bot Protections
**CRITICAL**: The RRC explicitly detects and blocks automated query tools on the Production Data Query (PDQ) web interface. The RRC warns: "The use of automated tools to retrieve volumes of data can cause severe degradation... if the query system detects automated data retrieval, the RRC will end the session." **Use bulk downloads ONLY** -- do not scrape the PDQ.

#### Known Gotchas
- **EBCDIC encoding**: Many production and well datasets are in IBM mainframe EBCDIC format. Requires conversion to UTF-8 using layout definition files. Some fields use COMP-3 (packed decimal) encoding.
- **Fixed-width ASCII**: No delimiters; fields are at fixed byte positions. RRC provides PDF layout manuals describing field positions for each dataset.
- **Compressed files**: Some downloads are .Z (Unix compress) or .zip archives.
- **File GUIDs change**: The mft.rrc.texas.gov download GUIDs are static per dataset but verify periodically.
- **Multiple districts**: Oil/gas ledger files are split by RRC administrative district.

#### Recommended Adapter Strategy

**Spider Type:** `BulkDownloadSpider` -- no Playwright needed
**Approach:**
1. Download files from mft.rrc.texas.gov URLs via standard HTTP (Scrapy `FilesPipeline`)
2. Route EBCDIC files through `ebcdic-parser` with TX-specific layout JSON definitions
3. Route ASCII fixed-width files through custom fixed-width parser
4. Route CSV files (PDQ dump) through standard pandas/csv parsing
5. Store PDFs (completions, directional surveys, permits) as-is for OCR pipeline

**Pagination:** Not applicable -- bulk file downloads.

#### Existing Open-Source Scrapers
- **rrc-scraper** (github.com/derrickturk/rrc-scraper) -- Python scraper for RRC PDQ web queries. Warns about automated detection.
- **TXRRC_data_harvest** (github.com/mlbelobraydi/TXRRC_data_harvest) -- Python/Jupyter scripts for downloading and organizing TX RRC data. Includes EBCDIC parsing with block size 1200 for oil production records.
- **texas_rrc** (github.com/jsfenfen/texas_rrc) -- Some RRC oil/gas production files.

---

### 3.2 New Mexico (NM) - Oil Conservation Division (OCD)

**Scraping Approach:** ArcGIS REST API (primary) + OCD Permitting portal

**Agency:** Energy, Minerals and Natural Resources Dept - Oil Conservation Division

#### Exact URLs

| Resource | URL |
|----------|-----|
| OCD Main | https://www.emnrd.nm.gov/ocd/ |
| OCD Hub (ArcGIS) | https://ocd-hub-nm-emnrd.hub.arcgis.com/ |
| OCD Permitting Portal | https://wwwapps.emnrd.nm.gov/ocd/ocdpermitting/ |
| Wells Search | https://wwwapps.emnrd.nm.gov/ocd/ocdpermitting/data/wells.aspx |
| Well Details (example) | https://wwwapps.emnrd.nm.gov/ocd/ocdpermitting/Data/WellDetails.aspx?api={API_NUMBER} |
| OCD Oil & Gas Map | https://www.arcgis.com/apps/webappviewer/index.html?id=4d017f2306164de29fd2fb9f8f35ca75 |
| ONGARD (State Land Office) | https://www.nmstatelands.org/divisions/oil-gas-and-minerals/ongard-and-data-resources/ |
| GO-TECH (NM Tech) | https://octane.nmt.edu/gotech/Petroleum_Data/general.aspx |

#### ArcGIS REST API Endpoints

**Oil and Gas Wells Feature Service:**
- Hub Dataset: `https://ocd-hub-nm-emnrd.hub.arcgis.com/datasets/dd971b8e25c54d1a8ab7c549244cf3cc`
- Feature Explorer: `https://ocd-hub-nm-emnrd.hub.arcgis.com/datasets/dd971b8e25c54d1a8ab7c549244cf3cc_0/explore`
- NM State Lands MapServer: `https://mapservice.nmstatelands.org/arcgis/rest/services/Public/NMOCD_Wells_V3/MapServer/5`

**Standard ArcGIS REST query pattern:**
```
https://mapservice.nmstatelands.org/arcgis/rest/services/Public/NMOCD_Wells_V3/MapServer/5/query?
  where=1%3D1
  &outFields=*
  &resultOffset=0
  &resultRecordCount=1000
  &f=json
```

**Download formats from Hub:** CSV, KML, GeoJSON, GeoTIFF, PNG, Zip (Shapefile)

#### Authentication
No login required for most data. Some ONGARD features (State Land Office) may require registration.

#### Document Types Available
- C-101 (Permit to Drill)
- C-102 (Acreage Plat)
- C-103 (Sundries/Notices)
- C-115 (Operator Monthly Production Report)
- C-145 (Operator Change)
- Well header data, location data, pool/zone data
- Production data (via ONGARD)

#### Data Formats
CSV, GeoJSON, KML, Shapefile (ZIP), GeoTIFF, PNG, JSON (ArcGIS REST).

#### Anti-Bot Protections
Moderate. ArcGIS Hub/REST APIs have built-in rate limits. The Feature Service typically returns a maximum of 1,000-2,000 records per query (paginate using `resultOffset`).

#### Known Gotchas
- **Multiple systems**: Data is spread across OCD Hub, OCD Permitting (ASP.NET), ONGARD (State Land Office), and GO-TECH (NM Tech). No single unified source.
- **ArcGIS pagination**: Feature services limit results per query (usually 1,000-2,000 records). Must paginate with `resultOffset` and `resultRecordCount`.
- **ONGARD production data**: Managed by NM State Land Office, separate from OCD. May require different access approach.
- **OCD Permitting is ASP.NET**: Server-side rendered with ViewState. Can use Scrapy `FormRequest` but may need Playwright for complex interactions.

#### Recommended Adapter Strategy

**Spider Type:** `ArcGISAPISpider` (primary) + `FormSpider` (OCD Permitting)
**Approach:**
1. Use ArcGIS REST API to query well data with pagination (`resultOffset` incrementing by `resultRecordCount`). Request `f=json` format for efficient parsing.
2. For permitting data (C-101, C-103, etc.), scrape the OCD Permitting ASP.NET portal using Scrapy `FormRequest` or Playwright for complex form interaction.
3. For production data, access ONGARD or use the ArcGIS hub's production-related datasets.

**Pagination:** ArcGIS offset-based: increment `resultOffset` by batch size (1000) until empty results.

#### Existing Open-Source Scrapers
None identified specific to NM OCD. The ArcGIS REST API is well-documented and straightforward to query programmatically.

---

### 3.3 North Dakota (ND) - Department of Mineral Resources (DMR)

**Scraping Approach:** Free data via static report scraping + Paid subscription for detailed data

**Agency:** ND Department of Mineral Resources, Oil & Gas Division

#### Exact URLs

| Resource | URL |
|----------|-----|
| Oil & Gas Division Home | https://www.dmr.nd.gov/oilgas/ |
| New Portal Home | https://www.dmr.nd.gov/dmr/oilgas |
| Well Search | https://www.dmr.nd.gov/oilgas/findwellsvw.asp |
| GIS Map Server | https://gis.dmr.nd.gov/ |
| Monthly Production Reports (free) | https://www.dmr.nd.gov/oilgas/mprindex.asp |
| Daily Activity Reports (free) | https://www.dmr.nd.gov/oilgas/dailyindex.asp |
| General Statistics (free) | https://www.dmr.nd.gov/oilgas/stats/statisticsvw.asp |
| NorthSTAR System | https://www.dmr.nd.gov/dmr/oilgas/reporting/northstar |
| NorthSTAR FAQ/Training | https://www.dmr.nd.gov/oilgas/northstar.asp |
| Basic Subscription Info | https://www.dmr.nd.gov/oilgas/basicservice.asp |
| Premium Subscription Info | https://www.dmr.nd.gov/oilgas/subscriptionservice.asp |
| Subscription PDF | https://www.dmr.nd.gov/oilgas/Subscription_Services.pdf |

#### Authentication & Subscription

**PAID ACCESS REQUIRED for most detailed data.**

| Tier | Cost (as of Jan 2026) | Includes |
|------|----------------------|----------|
| **Free** | $0 | Monthly production report summaries (PDF), daily activity reports (PDF), general statistics, well search (basic header data), weekly permit listings |
| **Basic** | $100/year | Well Index (Excel), scout ticket data (well info, log tops, completion data, initial production tests, cumulative volumes, drill stem test recoveries), well files (scanned PDFs), production/injection histories by well/unit/field, GIS Map Server |
| **Premium** | $500/year | Everything in Basic PLUS: field orders, full-text case file search, hearing audio, digital/image well logs, cored intervals, core photos, thin section photos, stripper well determinations, unitization statistics, processed gas plant volumes, performance decline curves |

**Note:** Production/injection numbers for confidential wells are excluded even from Premium.

#### Free Data (No Login Required)

| Data | URL Pattern | Format |
|------|-------------|--------|
| Monthly Production Reports | `https://www.dmr.nd.gov/oilgas/mpr{YYYY}{MM}.pdf` | PDF |
| Daily Activity Reports | Indexed at `https://www.dmr.nd.gov/oilgas/dailyindex.asp` | PDF |
| Weekly Permit Listings | Linked from main page | HTML/PDF |
| Well Search (basic headers) | `https://www.dmr.nd.gov/oilgas/findwellsvw.asp` | HTML |
| Annual Production Statistics | `https://www.dmr.nd.gov/oilgas/stats/AnnualProduction/{YYYY}AnnualProductionReport.pdf` | PDF |

#### Document Types Available
Well permits, production reports (monthly/annual), completion reports, scout tickets, well logs, field/hearing orders, daily activity reports, injection data, spacing orders. Most detailed data requires subscription.

#### Data Formats
PDF (monthly reports, well files), HTML (well search, statistics), Excel (well index via subscription).

#### Anti-Bot Protections
Moderate. Subscription login required for key data. The NorthSTAR system is a modern web application that may have additional protections. Classic ASP pages (findwellsvw.asp) are more straightforward.

#### Known Gotchas
- **Subscription paywall**: The most valuable data (per-well production, scout tickets, well logs) requires $100-$500/year subscription. Budget for this.
- **NorthSTAR migration**: ND is migrating to a new NorthSTAR cloud-based system. URLs and interfaces may change. Monitor for updates.
- **Classic ASP backend**: Legacy pages use .asp extensions, indicating older IIS/Classic ASP technology. ViewState and session management may be tricky.
- **PDF-heavy free data**: Free monthly production reports are PDFs requiring OCR/text extraction.
- **Confidential wells**: Production data for confidential wells is withheld even from premium subscribers.

#### Recommended Adapter Strategy

**Spider Type:** `HybridSpider` -- Scrapy for free PDF/HTML reports + Playwright for authenticated subscription portal

**Approach:**
1. **Free tier**: Download monthly production PDFs from indexed URL pattern. Scrape daily activity reports. Parse well search HTML for basic headers.
2. **Subscription tier** (if budget allows): Authenticate via Playwright, navigate subscription portal, download well index Excel files, scout tickets, production histories.
3. **NorthSTAR**: Monitor for API endpoints that may emerge as the new system matures.

**Pagination:** PDF reports are indexed by year/month. Well search uses form POST with ViewState.

#### Existing Open-Source Scrapers
- **oil-and-gas** (github.com/potokrm/oil-and-gas) -- ND web crawler for well data (older, Python).
- **webscrape_monthly_og_data_bakken** (github.com/kperry2215/webscrape_monthly_og_data_bakken) -- Scrapes ND O&G Division monthly Bakken data.

---

### 3.4 Oklahoma (OK) - Corporation Commission (OCC)

**Scraping Approach:** Bulk Download (primary)

**Agency:** Oklahoma Corporation Commission, Oil & Gas Division

#### Exact URLs

| Resource | URL |
|----------|-----|
| Oil & Gas Division | https://oklahoma.gov/occ/divisions/oil-gas.html |
| Data Files Download | https://oklahoma.gov/occ/divisions/oil-gas/oil-gas-data.html |
| GIS Data (ArcGIS Hub) | https://gisdata-occokc.opendata.arcgis.com/ |
| Well Data Finder (GIS Map) | https://gis.occ.ok.gov/portal/apps/webappviewer/index.html?id=ba9b8612132f4106be6e3553dc0b827b |
| Well Browse (Electronic) | https://wellbrowse.occ.ok.gov/ |
| Database Search / Imaged Docs | https://oklahoma.gov/occ/divisions/oil-gas/database-search-imaged-documents.html |
| OK Tax Commission (Production) | https://oktap.tax.ok.gov/OkTAP/web?link=PUBLICPUNLKP |
| Gross Production Portal | https://otcportal.tax.ok.gov/gpx/index.php |

#### Bulk Download Files (all at oklahoma.gov)

**Well Information:**

| File | Format | Frequency | Relative URL |
|------|--------|-----------|--------------|
| RBDMS Well Data | CSV | Nightly | `/content/dam/ok/en/occ/documents/og/ogdatafiles/rbdms-wells.csv` |
| RBDMS Data Dictionary | XLSX | Nightly | `/content/dam/ok/en/occ/documents/og/ogdatafiles/rbdms-wells-data-dictionary.xlsx` |
| RBDMS Wells GIS | Shapefile (ZIP) | Nightly | `/content/dam/ok/en/occ/documents/og/esri/files/RBDMS_WELLS.zip` |
| Incident Report Archive | CSV | Daily | `/content/dam/ok/en/occ/documents/og/ogdatafiles/ogcd-incidents.csv` |
| Orphan Well List | XLSX | Weekly (Thu) | `/content/dam/ok/en/occ/documents/og/ogdatafiles/orphan-well-list.xlsx` |
| State Funds Well List | XLSX | Weekly (Thu) | `/content/dam/ok/en/occ/documents/og/ogdatafiles/stfd-well-list.xlsx` |

**Intent to Drill & Completions:**

| File | Format | Frequency | Relative URL |
|------|--------|-----------|--------------|
| Intent to Drill (7-day) | XLSX | Daily | `/content/dam/ok/en/occ/documents/og/ogdatafiles/ITD-wells-formations-daily.xlsx` |
| Intent to Drill Master | XLSX | Daily | `/content/dam/ok/en/occ/documents/og/ogdatafiles/ITD-wells-formations-base.xlsx` |
| Well Completions Monthly | XLSX | Daily | `/content/dam/ok/en/occ/documents/og/ogdatafiles/completions-wells-formations-base.xlsx` |
| Well Completions (7-day) | XLSX | Daily | `/content/dam/ok/en/occ/documents/og/ogdatafiles/completions-wells-formations-daily.xlsx` |
| Well Completions Legacy | XLSX | Static | `/content/dam/ok/en/occ/documents/og/ogdatafiles/completions-wells-legacy.xlsx` |
| Well Transfer File | XLSX | Daily | `/content/dam/ok/en/occ/documents/og/ogdatafiles/well-transfers-daily.xlsx` |

**Operators/Purchasers:**

| File | Format | Frequency | Relative URL |
|------|--------|-----------|--------------|
| Operator List | XLSX | Daily | `/content/dam/ok/en/occ/documents/og/ogdatafiles/operator-list.xlsx` |
| Purchaser List | XLSX | Daily | `/content/dam/ok/en/occ/documents/og/ogdatafiles/purchaser-list.xlsx` |
| Plugger List | XLSX | Daily | `/content/dam/ok/en/occ/documents/og/ogdatafiles/plugger-list.xlsx` |

**UIC Injection Volumes (by year):**

| File | Format | Relative URL |
|------|--------|--------------|
| All UIC Wells | XLSX | `/content/dam/ok/en/occ/documents/og/ogdatafiles/online-active-well-list.xlsx` |
| 2024 Injection Volumes | XLSX | `/content/dam/ok/en/occ/documents/og/ogdatafiles/2024-uic-injection-volumes.xlsx` |
| 2025 Injection Volumes | XLSX | `/content/dam/ok/en/occ/documents/og/ogdatafiles/2025-uic-injection-volumes.xlsx` |
| 2026 Arbuckle 1012D | XLSX | `/content/dam/ok/en/occ/documents/og/ogdatafiles/dly1012d_2026.xlsx` |

**Base URL for all downloads:** `https://oklahoma.gov`

#### Authentication
No login required. All bulk downloads are free and public.

#### Document Types Available
Well data (RBDMS), drilling permits (Intent to Drill), completions, incidents, orphan wells, operator/purchaser lists, UIC injection volumes, well transfers, imaged documents (via Well Browse).

**IMPORTANT:** Production data is maintained by the **Oklahoma Tax Commission**, NOT the OCC. Production volumes by lease are available through OkTAP (oktap.tax.ok.gov).

#### Data Formats
CSV (RBDMS wells, incidents), XLSX (permits, completions, operators, UIC), Shapefile (GIS), PDF (imaged documents, forms).

#### Anti-Bot Protections
Low. Standard government website. Direct file downloads do not require any interaction.

#### Known Gotchas
- **Production data is separate**: The OCC handles well/permit/completion data. Production data comes from the Oklahoma Tax Commission via OkTAP. Must scrape two different systems.
- **OkTAP**: The Tax Commission's production lookup at `oktap.tax.ok.gov/OkTAP/web?link=PUBLICPUNLKP` may require form interaction for queries.
- **RBDMS standard**: Oklahoma uses RBDMS (Risk Based Data Management System) for its well database, which means data structure is somewhat standardized.
- **Data dictionaries provided**: XLSX data dictionaries accompany most download files, making parsing straightforward.

#### Recommended Adapter Strategy

**Spider Type:** `BulkDownloadSpider` (no Playwright)
**Approach:**
1. Download all CSV/XLSX files from static URLs using standard HTTP GET.
2. Parse RBDMS CSV with data dictionary for field mapping.
3. Parse XLSX files with openpyxl or pandas.
4. For production data, separately query OkTAP (may need Playwright for form interaction) or use the Gross Production portal.
5. For imaged documents, use Well Browse at `wellbrowse.occ.ok.gov`.

**Pagination:** Not applicable for bulk files. OkTAP production queries may need form-based pagination.

#### Existing Open-Source Scrapers
None identified specific to Oklahoma OCC. The bulk download approach makes custom scrapers unnecessary for most data.

---

### 3.5 Colorado (CO) - Energy & Carbon Management Commission (ECMC)

**Scraping Approach:** Mixed -- Bulk downloads + COGIS query interface

**Agency:** Colorado Energy & Carbon Management Commission (ECMC, formerly COGCC)

#### Exact URLs

| Resource | URL |
|----------|-----|
| ECMC Main | https://ecmc.colorado.gov/ |
| ECMC Legacy | https://ecmc.state.co.us/ |
| COGIS Database Home | https://ecmc.colorado.gov/data-maps/cogis-database |
| COGIS System | https://ecmc.state.co.us/OGIS/ |
| Production Data Inquiry | https://ecmc.colorado.gov/data-maps-reports/cogis-database/cogis-production-data-inquiry |
| Facility Search | https://ecmc.state.co.us/cogisdb/Facility/FacilitySearch |
| Downloadable Data | https://ecmc.colorado.gov/data-maps-reports/downloadable-data-documents |
| Well Analytical Data (monthly) | https://ecmc.colorado.gov/data-maps/downloadable-data-documents/prod-well-download |
| ECMC Interactive Map | https://ecmc.colorado.gov/data-maps-reports/ecmc-interactive-map |
| Dashboard | https://ecmc.state.co.us/dashboard.html |
| Data Download Guide (PDF) | https://ecmc.state.co.us/documents/data/downloads/COGCC_Download_Guidance.pdf |
| Operator Search | https://ecmc.colorado.gov/data-maps-reports/cogis-database/cogis-operator-name-address-and-financial-assurance |
| Data Page (legacy) | https://ecmc.state.co.us/data2.html |

#### Downloadable Data

| Dataset | Format | Frequency | Notes |
|---------|--------|-----------|-------|
| Well Spots (APIs) | CSV | Regular | Active and plugged wells + active/expired permits |
| Well Permits | CSV | Regular | Active well permits |
| Pending Well Permits | CSV | Regular | Permits awaiting approval |
| Production Data (all wells since 1999) | CSV (zipped + uncompressed) | Monthly | Every production report received by commission |
| Oil & Gas Well Analytical Data | CSV | Monthly | Comprehensive well analytics |

#### COGIS Query Interfaces

The COGIS database allows interactive queries for:
- **Production Data Inquiry**: Query by API number, operator, county, field -- exports results
- **Facility/Well Search**: Search by API number, location, well name
- **Operator Search**: Search operators by name, address, financial assurance

These query interfaces use server-side rendering and may require form interaction.

#### Authentication
No login required.

#### Document Types Available
Well permits (pending + approved), production data (annual oil/gas/water per formation per well), well completions (spud date, TD date, status, first production), facility data, inspection reports, operator data, financial assurance records.

#### Data Formats
CSV (primary for downloadable data), PDF (reports, guide documents).

#### Anti-Bot Protections
Low to moderate. Standard government site. COGIS query pages are server-rendered ASP.NET.

#### Known Gotchas
- **Dual domains**: ECMC uses both `ecmc.colorado.gov` (new) and `ecmc.state.co.us` (legacy). Some features live on one or the other.
- **COGIS ASP.NET forms**: Query interfaces require form submission. May need Playwright for some complex queries, though many are standard form POSTs.
- **Production data CSV is comprehensive**: The downloadable production CSV contains ALL production reports since 1999, making it a large single file.
- **Data Download Guide**: ECMC provides a detailed PDF guide for data access at the URL above.

#### Recommended Adapter Strategy

**Spider Type:** `MixedSpider` -- bulk CSV downloads + COGIS form queries
**Approach:**
1. **Primary**: Download production CSV, well spots CSV, and permits CSV from the downloadable data page. These cover the bulk of needed data.
2. **Secondary**: For well details, completions, and facility-specific queries not in bulk files, query the COGIS database via Scrapy `FormRequest`. Some forms may need Playwright.
3. Parse all CSVs with pandas. Reference the Data Download Guide for field definitions.

**Pagination:** Bulk CSVs are single files. COGIS query results paginate server-side.

#### Existing Open-Source Scrapers
None identified specific to Colorado ECMC/COGCC. The bulk CSV downloads make custom scrapers straightforward.

---

### 3.6 Wyoming (WY) - Oil & Gas Conservation Commission (WOGCC)

**Scraping Approach:** Mixed -- Data Explorer (browser) + ArcGIS data + bulk header download

**Agency:** Wyoming Oil and Gas Conservation Commission (WOGCC)

#### Exact URLs

| Resource | URL |
|----------|-----|
| WOGCC Main | https://wogcc.wyo.gov/ |
| Data Explorer | https://dataexplorer.wogcc.wyo.gov/ |
| Oil & Gas Resources | https://wogcc.wyo.gov/public-resources/oil-gas-resources |
| WellFinder App | https://wogcc.wyo.gov/wogcc-information/wogcc-news/wellfinder-app |
| Legacy Portal (ColdFusion) | https://pipeline.wyo.gov/legacywogcce.cfm |
| Legacy Download (DB5) | http://wogcc.state.wy.us/ (download menu) |
| ArcGIS Wells MapServer | https://gis.deq.wyoming.gov/arcgis_443/rest/services/WOGCC_WELLS/MapServer |
| Geospatial Hub | https://data.geospatialhub.org/ |
| Well Data on Hub | https://data.geospatialhub.org/datasets/46d3629e4e3b4ef6978cb5e6598f97bb_0 |
| Bottom Hole Data | https://data.geospatialhub.org/datasets/290e6b5d473f47f783ef08691f613c87_0/geoservice |
| WSGS Oil & Gas MapServer | https://portal.wsgs.wyo.gov/ags/rest/services/OilGas/Data_layers/MapServer |

#### ArcGIS REST API Endpoints

**WOGCC Wells (updated nightly):**
```
https://gis.deq.wyoming.gov/arcgis_443/rest/services/WOGCC_WELLS/MapServer/query?
  where=1%3D1
  &outFields=*
  &resultOffset=0
  &resultRecordCount=1000
  &f=json
```

**Wyoming Geospatial Hub:**
- Active Wells: `https://data.geospatialhub.org/datasets/46d3629e4e3b4ef6978cb5e6598f97bb_0`
- Bottom Hole Well Data: `https://data.geospatialhub.org/datasets/290e6b5d473f47f783ef08691f613c87_0`

#### Bulk Well Header Download
The WOGCC provides statewide well header data in Excel format via the "Well Header DB5 (Zipped)" file accessible from the download menu on their legacy site. This contains approximately 114,000 wells.

#### Authentication
No login required.

#### Document Types Available
Well headers (permits, locations, operators), production data, completion data, spacing orders (PDF), inspection reports, directional surveys, well logs (limited).

#### Data Formats
Excel (DB5 well header), Shapefile, PDF (orders, reports), ArcGIS REST (JSON, GeoJSON).

#### Anti-Bot Protections
Moderate. The Data Explorer is a modern web application that may have JavaScript-based protections. The legacy ColdFusion portal is more straightforward. ArcGIS services have standard rate limits.

#### Known Gotchas
- **ColdFusion legacy**: The legacy portal at pipeline.wyo.gov uses ColdFusion (.cfm), an aging technology with quirky session management.
- **Data Explorer is JS-heavy**: The primary modern interface at dataexplorer.wogcc.wyo.gov requires Playwright for browser automation.
- **Multiple data sources**: Data is spread across Data Explorer, legacy portal, ArcGIS services, and Geospatial Hub. No single unified download.
- **ArcGIS nightly refresh**: The WOGCC_WELLS feature class on the ArcGIS service is recreated nightly from WOGCC data via Python scripts, providing current data.

#### Recommended Adapter Strategy

**Spider Type:** `MixedSpider` -- ArcGIS API (primary) + Playwright for Data Explorer
**Approach:**
1. **Primary**: Query the WOGCC_WELLS ArcGIS MapServer REST API for well location and header data. Paginate with `resultOffset`. Updated nightly.
2. **Secondary**: Download the Well Header DB5 Excel file for comprehensive well header data.
3. **Tertiary**: Use Playwright to interact with the Data Explorer for production data, completion data, and well details not available via API.
4. **GIS data**: Download from Geospatial Hub for spatial analysis.

**Pagination:** ArcGIS offset-based pagination. Data Explorer has JavaScript-driven pagination requiring Playwright.

#### Existing Open-Source Scrapers
None identified specific to Wyoming WOGCC.

---

### 3.7 Louisiana (LA) - SONRIS

**Scraping Approach:** Browser automation (Playwright) -- complex web application

**Agency:** Louisiana Department of Conservation and Energy (formerly DNR, renamed Oct 2025)

#### Exact URLs

| Resource | URL |
|----------|-----|
| SONRIS Main | https://www.sonris.com/ |
| SONRIS Integrated Apps | https://www.sonris.com/homemain.htm |
| SONRIS IDR Index by Topic | https://www.dnr.louisiana.gov/page/cons-sonris-idr-index-by-topic |
| SONRIS Guides | https://www.dce.louisiana.gov/page/sonris-guides |
| SONRIS GIS Map | https://sonris-gis.dnr.la.gov/gis/agsweb/IE/JSViewer/index.html?TemplateID=181 |
| Production Data | https://www.dnr.louisiana.gov/page/oil-and-gas-production-data |
| SONRIS Data Entry | https://www.dnr.louisiana.gov/page/sonris-data-entry |
| Dept of Conservation & Energy | https://www.dce.louisiana.gov/ |
| SONRIS on EDX (DOE) | https://edx.netl.doe.gov/dataset/sonris |
| DOTD ArcGIS MapServer | https://giswebnew.dotd.la.gov/arcgis/rest/services/LTRC/SONRIS/MapServer |

#### IDR Reports (Interactive Data Reports)

SONRIS IDR reports are the primary means of extracting data. They replaced the legacy ROD system and are Java-free. IDR reports can be exported to Excel.

**Key IDR Topics:**
- Well Information (by serial number, operator, field)
- Production Data (oil, gas, condensate by well/field/parish)
- Injection Data
- Scout Reports (Conservation Scout Reports)
- Permit Data
- Well Test Data
- Plugging & Abandonment

#### Authentication
No login required for most data. Some data entry features require an account.

#### Document Types Available
Well data (serial number-based), production data (oil/gas/condensate), injection data, scout reports, permits, well tests, P&A records, field data, hearing orders.

#### Data Formats
Excel (IDR export), HTML (online reports), PDF (orders, hearing decisions).

#### Anti-Bot Protections
**Moderate-High.** SONRIS is a complex web application backed by an Oracle database. The IDR system uses dynamic JavaScript for report generation and filtering. Recently redesigned (Oct 2025) for accessibility compliance. Expect:
- Session-based state management
- JavaScript-heavy dynamic content
- Potential CAPTCHAs or rate limiting on heavy use
- Oracle database query timeouts on complex requests

#### Known Gotchas
- **Oracle backend**: SONRIS is backed by millions of Oracle records. Complex queries can time out.
- **Recent reorganization**: As of Oct 2025, the agency was renamed from DENR to Department of Conservation and Energy (C&E). URLs and documentation are in flux -- some at `denr.louisiana.gov`, some at `dce.louisiana.gov`, some at `dnr.louisiana.gov`.
- **No REST API**: Unlike states with ArcGIS REST APIs, SONRIS does not expose a documented REST API for data queries. All access is through the web application.
- **IDR reports are the key**: Interactive Data Reports with Excel export are the primary extraction method. Must automate report parameter selection and export.
- **Serial number system**: Louisiana uses its own serial number system for wells (not just API numbers), adding an extra identifier to track.
- **GIS map**: The SONRIS GIS Viewer uses a custom JavaScript viewer, not standard ArcGIS Hub. The DOTD provides an ArcGIS MapServer at `giswebnew.dotd.la.gov`.

#### Recommended Adapter Strategy

**Spider Type:** `PlaywrightFormSpider` -- Playwright required throughout
**Approach:**
1. Use Playwright to navigate SONRIS, select IDR report parameters, generate reports, and trigger Excel export.
2. Download exported Excel files via Playwright's download handling.
3. Parse Excel files with openpyxl/pandas.
4. For GIS data, query the DOTD ArcGIS MapServer REST API.
5. Implement robust session management and retry logic for Oracle timeouts.

**Pagination:** IDR reports may paginate within the application. Use Playwright to navigate result pages.

**Critical Warning:** SONRIS is the hardest state site to scrape. Expect significant development effort for browser automation, session management, and error handling.

#### Existing Open-Source Scrapers
None identified. SONRIS's complexity likely deters open-source efforts.

---

### 3.8 Pennsylvania (PA) - Department of Environmental Protection (DEP)

**Scraping Approach:** Bulk CSV Download -- the easiest state

**Agency:** PA Dept of Environmental Protection, Office of Oil and Gas Management

#### Exact URLs

| Resource | URL |
|----------|-----|
| Oil & Gas Reports | https://www.pa.gov/agencies/dep/data-and-tools/reports/oil-and-gas-reports |
| GreenPort Report Extracts Index | https://greenport.pa.gov/ReportExtracts/OG/Index |
| Production Report | https://greenport.pa.gov/ReportExtracts/OG/OilGasWellProdReport |
| Well Inventory Report | https://greenport.pa.gov/ReportExtracts/OG/OilGasWellInventoryReport |
| Compliance Report | https://greenport.pa.gov/ReportExtracts/OG/OilComplianceReport |
| Plugged Wells Report | https://greenport.pa.gov/ReportExtracts/OG/OGPluggedWellsReport |
| Well Waste Report | https://greenport.pa.gov/ReportExtracts/OG/OilGasWellWasteReport |
| Production Not Submitted | https://greenport.pa.gov/ReportExtracts/OG/WellNotSubReport |
| GIS Mapping | https://gis.dep.pa.gov/PaOilAndGasMapping/ |
| Data Dictionary (PDF) | https://files.dep.state.pa.us/oilgas/bogm/bogmportalfiles/oilgasreports/HelpDocs/SSRS_Report_Data_Dictionary/DEP_Oil_and_GAS_Reports_Data_Dictionary.pdf |

#### GreenPort Report Extracts

Each report is available as on-demand CSV export with live data. Select reporting period parameters and click "Export Report" for statewide data.

| Report | What It Contains |
|--------|-----------------|
| Production Report | Monthly oil, gas, condensate production by well for selected period |
| Well Inventory | Permits, locations, operators, well status, spud dates |
| Compliance Report | Inspections, violations, enforcement actions |
| Plugged Wells | Plugging and abandonment records |
| Well Waste Report | Waste generation and disposal data |
| Production Not Submitted | Wells with missing production reports |

#### Authentication
No login required.

#### Document Types Available
Production reports, well permits/inventory, compliance/inspection records, plugging reports, waste reports.

#### Data Formats
CSV (all GreenPort exports). Data dictionary provided in PDF.

#### Anti-Bot Protections
Very low. GreenPort is designed for public data access. Standard CSV downloads.

#### Known Gotchas
- **Report parameters required**: Each GreenPort report requires selecting a reporting period (e.g., year/quarter). Must automate parameter selection to download historical data across all periods.
- **Live data**: Reports are generated on-demand from live data. Values may change between report generations.
- **Data dictionary**: The PDF data dictionary at the URL above defines all fields -- essential for parsing.
- **Marcellus Shale focus**: Pennsylvania's primary O&G activity is unconventional gas (Marcellus/Utica Shale), not oil. Production reports reflect this.
- **No spacing/pooling orders**: Unlike western states, PA does not have spacing orders in the same sense. Compliance and permitting are the key regulatory documents.

#### Recommended Adapter Strategy

**Spider Type:** `BulkDownloadSpider` -- no Playwright needed
**Approach:**
1. For each report type, send HTTP requests to GreenPort with reporting period parameters.
2. Download the CSV response.
3. Iterate across all reporting periods (quarterly or annual) for historical data.
4. Parse CSVs with pandas. Use the data dictionary for field mapping.
5. May need to handle ASP.NET form submission with ViewState for parameter selection, or use Playwright if forms are JavaScript-dependent.

**Pagination:** Parameter-driven (reporting period selection). No result pagination -- exports are statewide per period.

#### Existing Open-Source Scrapers
None identified specific to PA GreenPort. The straightforward CSV export design makes custom development trivial.

---

### 3.9 California (CA) - CalGEM

**Scraping Approach:** ArcGIS REST API + Open Data Portal API

**Agency:** CalGEM (Geologic Energy Management Division), Dept of Conservation

#### Exact URLs

| Resource | URL |
|----------|-----|
| CalGEM Main | https://www.conservation.ca.gov/calgem/ |
| Well Finder (interactive map) | https://www.conservation.ca.gov/calgem/Pages/WellFinder.aspx |
| WellSTAR Info | https://www.conservation.ca.gov/calgem/for_operators/Pages/WellSTAR.aspx |
| WellSTAR Data Dashboard | https://www.conservation.ca.gov/calgem/Online_Data/Pages/WellSTAR-Data-Dashboard.aspx |
| Online Data Tools | https://www.conservation.ca.gov/calgem/Online_Data |
| CA Open Data - Wells | https://data.ca.gov/dataset/wellstar-oil-and-gas-wells |
| CA Open Data - Facilities | https://data.ca.gov/dataset/wellstar-oil-and-gas-facilities |
| CA Open Data - Notices | https://data.ca.gov/dataset/wellstar-notices |
| CA Natural Resources Open Data - Wells | https://data.cnra.ca.gov/dataset/wellstar-oil-and-gas-wells |
| CA Open Data - Well Finder | https://data.ca.gov/dataset/well-finder1 |
| Oil & Gas Map | https://maps.conservation.ca.gov/oilgas/ |

#### ArcGIS REST API Endpoint

**WellSTAR Wells MapServer:**
```
https://gis.conservation.ca.gov/server/rest/services/WellSTAR/Wells/MapServer/0
```

**Key parameters:**
- Display Field: `LeaseName`
- Geometry Type: Point (esriGeometryPoint)
- Max Record Count: 5,000
- Max Selection Count: 2,000
- Supported Formats: JSON, GeoJSON, PBF
- Spatial Reference: EPSG:3857 (Web Mercator)
- Supports Advanced Queries: Yes
- Supports Statistics: Yes

**Query pattern:**
```
https://gis.conservation.ca.gov/server/rest/services/WellSTAR/Wells/MapServer/0/query?
  where=WellStatus%3D%27Active%27
  &outFields=*
  &resultOffset=0
  &resultRecordCount=5000
  &f=json
```

#### California Open Data Portal (CKAN)

The data.ca.gov portal provides CKAN-based API access. Datasets can be downloaded as CSV, Shapefile, GeoJSON, or KML directly from the portal.

**Available WellSTAR Datasets:**
- Oil and Gas Wells
- Oil and Gas Facilities
- Oil and Gas Facilities Boundaries
- Underground Gas Storage Project Wells
- Notices (NOIs, etc.)
- Well Finder data

#### Authentication
No login required. All data is public under Creative Commons Attribution license.

#### Document Types Available
Well data (header, status, location, operator), facility data, production data (via WellSTAR Dashboard), notices of intention (NOI), permits, well logs (limited).

#### Data Formats
CSV, GeoJSON, Shapefile (ZIP), KML, JSON (ArcGIS REST), PBF.

#### Anti-Bot Protections
Low. ArcGIS REST API has standard rate limits. Open Data portal is designed for programmatic access. MaxRecordCount of 5,000 per query is the main constraint.

#### Known Gotchas
- **WellSTAR is under active development**: CalGEM continuously updates WellSTAR. Check for new datasets and API changes.
- **Well Finder updated Jan 2026**: Added new layers, share features, and tutorials.
- **Max 5,000 records per query**: Must paginate through results using `resultOffset`. California has many wells.
- **Spatial reference**: API returns data in Web Mercator (EPSG:3857). Convert to WGS84 for standard lat/long display.
- **Production data separate**: Well location/status data is readily available via API, but production data is primarily accessible through the WellSTAR Dashboard (may require Playwright for export).

#### Recommended Adapter Strategy

**Spider Type:** `ArcGISAPISpider` -- no Playwright needed for most data
**Approach:**
1. **Primary**: Query the WellSTAR ArcGIS REST API for well data. Paginate with `resultOffset` in increments of 5,000 until exhausted.
2. **Bulk**: Download full datasets as CSV from the CA Open Data portal (data.ca.gov).
3. **Production**: Access WellSTAR Data Dashboard for production data. May need Playwright if dashboard requires JavaScript interaction for export.
4. Parse JSON responses from ArcGIS API; parse CSVs from Open Data portal.

**Pagination:** ArcGIS offset-based: `resultOffset` + `resultRecordCount=5000`.

#### Existing Open-Source Scrapers
None identified specific to CalGEM. The well-documented ArcGIS REST API makes custom development straightforward.

---

### 3.10 Alaska (AK) - AOGCC

**Scraping Approach:** Mixed -- Data Miner (ASP.NET forms) + ArcGIS Open Data

**Agency:** Alaska Oil and Gas Conservation Commission (AOGCC)

#### Exact URLs

| Resource | URL |
|----------|-----|
| AOGCC Main | https://www.commerce.alaska.gov/web/aogcc/ |
| AOGCC Data Page | https://www.commerce.alaska.gov/web/aogcc/Data.aspx |
| Data Miner Home | http://aogweb.state.ak.us/DataMiner4/Forms/Home.aspx |
| Data Miner - Wells | http://aogweb.state.ak.us/DataMiner4/Forms/Wells.aspx |
| Data Miner - Well Data | http://aogweb.state.ak.us/DataMiner4/Forms/WellData.aspx |
| Data Miner - Well History | http://aogweb.state.ak.us/DataMiner4/Forms/WellHistory.aspx |
| Data Miner - Production | http://aogweb.state.ak.us/DataMiner4/Forms/Production.aspx |
| AK Div of Oil & Gas Open Data | https://dog-soa-dnr.opendata.arcgis.com/ |
| AK DNR Open Data - AOGCC Wells | https://data-soa-dnr.opendata.arcgis.com/maps/00a886f1c8954dc49e674881a3018000 |
| AOGCC Help | https://www.commerce.alaska.gov/web/aogcc/help.aspx |
| Locating O&G Data in Alaska (PDF) | https://dog.dnr.alaska.gov/Documents/Programs/Locating_Oil_and_Gas_Data_in_Alaska.pdf |

#### Data Miner System

The Data Miner is an ASP.NET web application (based on RBDMS) that provides interactive data access with filtering and export capabilities.

**Data Miner Forms:**

| Form | URL | Data Available |
|------|-----|----------------|
| Wells | `http://aogweb.state.ak.us/DataMiner4/Forms/Wells.aspx` | Well list, filter by operator/name/area/permit/date |
| Well Data | `http://aogweb.state.ak.us/DataMiner4/Forms/WellData.aspx` | Detailed well info, location, pools encountered |
| Well History | `http://aogweb.state.ak.us/DataMiner4/Forms/WellHistory.aspx` | Event history with descriptions |
| Production | `http://aogweb.state.ak.us/DataMiner4/Forms/Production.aspx` | Monthly production data (oil, gas, water) |

**Export:** Each form has an "Export As..." button for CSV (comma-delimited) or Excel format. Larger datasets may need to be downloaded in portions using filters.

**Full Table Downloads:** AOGCC also provides links to download entire Data Miner tables. An MS Access database is available for bulk importing.

#### ArcGIS Open Data

**Alaska Division of Oil and Gas:** `https://dog-soa-dnr.opendata.arcgis.com/`
**AOGCC Well Surface Locations:** `https://data-soa-dnr.opendata.arcgis.com/maps/00a886f1c8954dc49e674881a3018000`

#### Authentication
No login required.

#### Document Types Available
Well data (headers, locations, pools), well history (events), production data (monthly oil/gas/water), injection data, facility data, NGL records, permits, well logs (limited).

#### Data Formats
CSV (Data Miner export), Excel (Data Miner export), MS Access (bulk download), PDF, ArcGIS formats (GeoJSON, Shapefile from Open Data).

#### Anti-Bot Protections
Low. Data Miner is a standard ASP.NET WebForms application. The "Export As..." functionality is designed for public data access.

#### Known Gotchas
- **HTTP (not HTTPS)**: Data Miner runs on plain HTTP (`http://aogweb.state.ak.us`), which is unusual. May cause issues with some HTTP clients that enforce HTTPS.
- **ASP.NET WebForms**: Uses ViewState and PostBack patterns. Export buttons trigger server-side processing. May need Playwright to click "Export As..." and handle file downloads, or reverse-engineer the POST parameters.
- **Smaller dataset**: Alaska has far fewer wells than Texas or New Mexico, making full-table exports more feasible.
- **Two agencies**: AOGCC (Commerce Dept) handles conservation/regulatory data. Division of Oil and Gas (DNR) handles leasing/exploration. Both have separate portals.
- **AOGCC database upgrade**: As of late 2025, AOGCC was seeking a free update/upgrade to their database system. The Data Miner interface may change.

#### Recommended Adapter Strategy

**Spider Type:** `MixedSpider` -- Playwright for Data Miner export + ArcGIS API
**Approach:**
1. **Primary**: Use Playwright to navigate Data Miner forms, set filters (or select all), click "Export As..." CSV, and download the result.
2. **Bulk Alternative**: Download the full MS Access database for bulk import, then parse with `pyodbc` or `mdbtools`.
3. **GIS**: Query ArcGIS Open Data for well surface locations and spatial data.
4. Parse exported CSVs with pandas.

**Pagination:** Data Miner supports filtering to break large exports into manageable chunks (by area, operator, date range).

#### Existing Open-Source Scrapers
None identified specific to Alaska AOGCC.

---

## 4. EBCDIC Handling for Texas Data

### The Challenge

Texas RRC provides many of its most valuable datasets (production ledgers, well databases, field data) in EBCDIC format -- a legacy encoding from IBM mainframes. EBCDIC files use different character encoding than ASCII/UTF-8 and often include packed decimal (COMP-3) fields that encode multiple digits per byte.

### Python Libraries for EBCDIC Conversion

#### Option 1: ebcdic-parser (Recommended)

**Install:** `pip install ebcdic-parser`

**Features:**
- Converts mainframe EBCDIC data into Unicode ASCII delimited text files
- Supports: single-schema fixed records, multi-schema fixed/variable records
- Handles COMP-3 (packed decimal) fields
- Layout definitions via JSON files
- Handles headers/footers, invalid characters, field filtering
- Debug mode for troubleshooting layouts

**Usage:**
```python
from ebcdic_parser.convert import run

return_code = run(
    input_file="data/raw/tx/dbf900.ebc",        # EBCDIC input file
    output_folder="data/processed/tx/",           # Output directory
    layout_file="config/tx_layouts/wellbore.json", # Layout definition
    output_delimiter=",",                          # CSV output
    logfolder="logs/",
)
```

**Layout JSON Example (for TX RRC wellbore data):**
```json
{
  "record_length": 1200,
  "encoding": "cp037",
  "fields": [
    {"name": "API_NUMBER", "type": "string", "start": 1, "length": 14},
    {"name": "OPERATOR_NUMBER", "type": "string", "start": 15, "length": 6},
    {"name": "LEASE_NAME", "type": "string", "start": 21, "length": 32},
    {"name": "WELL_NUMBER", "type": "string", "start": 53, "length": 6},
    {"name": "OIL_PRODUCTION", "type": "packedDecimal", "start": 59, "length": 5},
    {"name": "GAS_PRODUCTION", "type": "packedDecimal", "start": 64, "length": 5}
  ]
}
```

**Note:** The exact field positions must be derived from the RRC-provided layout manuals (PDFs). Each dataset has its own layout PDF describing field names, positions, lengths, and types.

#### Option 2: Python Built-in codecs

**For simple character conversion (no packed decimal):**
```python
import codecs

with open("input.ebc", "rb") as f:
    raw_bytes = f.read()

# Common EBCDIC code pages for US mainframes:
# cp037 - US/Canada (most common for TX RRC)
# cp500 - International
# cp1140 - US with Euro sign
text = raw_bytes.decode("cp037")
```

#### Option 3: ebcdic PyPI Package

**Install:** `pip install ebcdic`

**Usage:**
```python
import ebcdic
# Registers additional EBCDIC codec variants with Python's codecs system
# Then use standard codecs.decode() with the EBCDIC codec names
```

### Handling COMP-3 (Packed Decimal) Fields

Many numeric fields in TX RRC EBCDIC files use COMP-3 encoding, where each byte holds two digits (one in each nibble), with the last nibble as a sign indicator.

```python
def decode_comp3(raw_bytes: bytes) -> float:
    """Decode COMP-3 (packed decimal) bytes to a Python number."""
    result = 0
    for byte in raw_bytes[:-1]:
        high = (byte >> 4) & 0x0F
        low = byte & 0x0F
        result = result * 100 + high * 10 + low
    # Last byte: high nibble is digit, low nibble is sign
    last = raw_bytes[-1]
    high = (last >> 4) & 0x0F
    sign = last & 0x0F
    result = result * 10 + high
    if sign in (0x0D, 0x0B):  # Negative signs
        result = -result
    return result
```

### Recommended Workflow for TX EBCDIC Data

1. **Download** EBCDIC files from mft.rrc.texas.gov
2. **Decompress** if .Z format (use Python `subprocess` with `uncompress` or `gzip`)
3. **Obtain layout definitions** from RRC-provided PDF manuals for each dataset
4. **Convert layout PDFs to JSON** configuration files (one-time manual effort per dataset)
5. **Parse** with ebcdic-parser using the JSON layout files
6. **Output** to CSV for pipeline consumption
7. **Prefer CSV alternatives when available**: The PDQ dump (CSV, monthly) and some newer datasets (JSON) bypass EBCDIC entirely

### Priority: Use CSV/ASCII When Available

For production data specifically, the **Production Data Query Dump** (CSV, last Saturday of each month) provides the same data as the EBCDIC ledger files in a far easier format. Use the CSV dump as the primary source and only fall back to EBCDIC for datasets not available in other formats.

---

## 5. Rate Limiting Strategies Per State

### Per-State Rate Limit Configuration

| State | Base Delay (s) | Max Concurrent | Strategy | Notes |
|-------|---------------|----------------|----------|-------|
| **TX** | 10 | 2 | Bulk download, generous delays between files | DO NOT scrape PDQ. Bulk files are large; space downloads to avoid bandwidth issues |
| **NM** | 5 | 2 | ArcGIS API standard | ArcGIS has built-in rate limits; respect `Retry-After` headers |
| **ND** | 15 | 1 | Conservative, session-based | Subscription portal; avoid triggering account lockout |
| **OK** | 3 | 4 | Bulk download, relaxed | Static file downloads; minimal rate limiting needed |
| **CO** | 8 | 2 | Mixed: relaxed for downloads, conservative for COGIS queries | COGIS forms hit a database; be gentle |
| **WY** | 10 | 1 | Conservative for Data Explorer | Legacy ColdFusion/modern JS; servers may be resource-constrained |
| **LA** | 15 | 1 | Very conservative | Oracle-backed SONRIS; complex queries stress the server |
| **PA** | 3 | 4 | Relaxed | GreenPort CSV export is designed for bulk use |
| **CA** | 3 | 3 | ArcGIS API standard | MaxRecordCount=5000; respect API limits |
| **AK** | 5 | 2 | Moderate | Smaller dataset; Data Miner is government-hosted ASP.NET |

### Scrapy AutoThrottle Configuration

```python
# Global settings (conservative baseline)
AUTOTHROTTLE_ENABLED = True
AUTOTHROTTLE_START_DELAY = 5      # Initial delay
AUTOTHROTTLE_MAX_DELAY = 60       # Max delay if server is slow
AUTOTHROTTLE_TARGET_CONCURRENCY = 1.0  # 1 concurrent request per domain

# Per-spider override (in spider class)
class TexasRRCSpider(BaseOGSpider):
    custom_settings = {
        'DOWNLOAD_DELAY': 10,
        'CONCURRENT_REQUESTS_PER_DOMAIN': 2,
        'AUTOTHROTTLE_TARGET_CONCURRENCY': 1.0,
    }

class PennsylvaniaDEPSpider(BaseOGSpider):
    custom_settings = {
        'DOWNLOAD_DELAY': 3,
        'CONCURRENT_REQUESTS_PER_DOMAIN': 4,
        'AUTOTHROTTLE_TARGET_CONCURRENCY': 2.0,
    }
```

### Additional Rate Limiting Strategies

**1. Request Jitter:**
```python
import random

# Add +/- 30% jitter to base delay
base_delay = self.rate_limit_delay
jitter = base_delay * 0.3
actual_delay = base_delay + random.uniform(-jitter, jitter)
```

**2. Circuit Breaker (per state):**
```python
import pybreaker

state_breakers = {
    "TX": pybreaker.CircuitBreaker(fail_max=5, reset_timeout=300),
    "LA": pybreaker.CircuitBreaker(fail_max=3, reset_timeout=600),  # More sensitive for SONRIS
    # ...
}
```

**3. Respect robots.txt:**
```python
# settings.py
ROBOTSTXT_OBEY = True  # Default; enable for all spiders
```

**4. Polite User-Agent:**
```python
USER_AGENT = "OGDocScraper/1.0 (Research tool; contact@example.com)"
```

**5. Time-of-Day Awareness:**
Government sites have lower traffic overnight. Schedule heavy scraping for off-peak hours (e.g., 11 PM - 6 AM local time for the state).

---

## 6. Implementation Priority Order

Based on difficulty, data value, and the architecture decisions in DISCOVERY.md:

### Phase 1: Easiest, Highest Value (Bulk Downloads)

| Priority | State | Difficulty | Why First |
|----------|-------|-----------|-----------|
| 1 | **PA** | Easy | Cleanest data (CSV), minimal development, validates pipeline |
| 2 | **OK** | Easy | Extensive nightly CSV/XLSX downloads, data dictionaries included |
| 3 | **TX** | Easy-Medium | Largest dataset, most bulk downloads. EBCDIC parsing is extra work but CSV alternatives exist |

**Milestone:** These three states prove out the BulkDownloadSpider pattern and the full pipeline (download -> parse -> normalize -> validate -> store).

### Phase 2: API-Based Access

| Priority | State | Difficulty | Why Second |
|----------|-------|-----------|------------|
| 4 | **CA** | Easy | Well-documented ArcGIS REST API + Open Data portal |
| 5 | **NM** | Medium | ArcGIS Hub + OCD Permitting (ASP.NET forms). Multiple systems to integrate |
| 6 | **CO** | Medium | Mix of bulk CSV downloads + COGIS query forms |

**Milestone:** These three states prove out the ArcGISAPISpider pattern and mixed-source aggregation.

### Phase 3: Browser Automation Required

| Priority | State | Difficulty | Why Third |
|----------|-------|-----------|-----------|
| 7 | **AK** | Easy-Medium | ASP.NET Data Miner with export buttons. Small dataset. Good Playwright testbed |
| 8 | **WY** | Medium-Hard | Data Explorer (JS) + ColdFusion legacy. ArcGIS API available as partial alternative |
| 9 | **ND** | Hard | Subscription paywall ($100-500/yr). Free data is PDF-heavy (needs OCR). NorthSTAR migration |
| 10 | **LA** | Hard | SONRIS is the hardest site. Oracle backend, complex JS app, no API. Budget significant effort |

**Milestone:** These four states prove out the PlaywrightFormSpider pattern and handle the hardest edge cases.

### Development Time Estimates

| State | Estimated Dev Time | Notes |
|-------|-------------------|-------|
| PA | 1-2 days | Trivial CSV downloads |
| OK | 2-3 days | Many files but straightforward |
| TX | 3-5 days | EBCDIC layout definitions are the main effort |
| CA | 2-3 days | Clean API, well-documented |
| NM | 3-4 days | Multiple systems to integrate |
| CO | 3-4 days | Mixed approach, COGIS forms |
| AK | 2-3 days | ASP.NET form automation |
| WY | 3-5 days | Multiple data sources, JS-heavy explorer |
| ND | 4-6 days | Subscription setup, PDF parsing, NorthSTAR |
| LA | 5-8 days | SONRIS complexity, Oracle timeouts, session management |
| **Total** | **28-43 days** | For one developer |

---

## Sources

### State Agency Portals
- [Texas RRC Data Downloads](https://www.rrc.texas.gov/resource-center/research/data-sets-available-for-download/)
- [New Mexico OCD Hub](https://ocd-hub-nm-emnrd.hub.arcgis.com/)
- [North Dakota DMR Oil & Gas Division](https://www.dmr.nd.gov/oilgas/)
- [North Dakota Subscription Services](https://www.dmr.nd.gov/oilgas/subscriptionservice.asp)
- [Oklahoma OCC Data Files](https://oklahoma.gov/occ/divisions/oil-gas/oil-gas-data.html)
- [Colorado ECMC Downloadable Data](https://ecmc.colorado.gov/data-maps-reports/downloadable-data-documents)
- [Wyoming WOGCC Data Explorer](https://dataexplorer.wogcc.wyo.gov/)
- [Louisiana SONRIS](https://www.sonris.com/)
- [Pennsylvania GreenPort Report Extracts](https://greenport.pa.gov/ReportExtracts/OG/Index)
- [California WellSTAR Open Data](https://data.ca.gov/dataset/wellstar-oil-and-gas-wells)
- [Alaska AOGCC Data Miner](http://aogweb.state.ak.us/DataMiner4/Forms/Home.aspx)

### ArcGIS REST API Endpoints
- [NM OCD Wells MapServer](https://mapservice.nmstatelands.org/arcgis/rest/services/Public/NMOCD_Wells_V3/MapServer/5)
- [CA WellSTAR Wells MapServer](https://gis.conservation.ca.gov/server/rest/services/WellSTAR/Wells/MapServer/0)
- [WY WOGCC Wells MapServer](https://gis.deq.wyoming.gov/arcgis_443/rest/services/WOGCC_WELLS/MapServer)
- [AK Division of Oil & Gas Open Data](https://dog-soa-dnr.opendata.arcgis.com/)

### Technical Tools & Libraries
- [ebcdic-parser (PyPI)](https://pypi.org/project/ebcdic-parser/)
- [ebcdic-parser (GitHub)](https://github.com/larandvit/ebcdic-parser)
- [scrapy-playwright (GitHub)](https://github.com/scrapy-plugins/scrapy-playwright)
- [Scrapy AutoThrottle Documentation](https://docs.scrapy.org/en/latest/topics/autothrottle.html)
- [Scrapy Common Practices](https://docs.scrapy.org/en/latest/topics/practices.html)

### Existing Open-Source Scrapers
- [rrc-scraper (TX RRC)](https://github.com/derrickturk/rrc-scraper)
- [TXRRC_data_harvest](https://github.com/mlbelobraydi/TXRRC_data_harvest)
- [public-oil-gas-data (multi-state guide)](https://github.com/derrickturk/public-oil-gas-data)
- [drilling-data-tools (CMU, 34 states)](https://github.com/CMU-CREATE-Lab/drilling-data-tools)
- [webscrape_monthly_og_data_bakken (ND)](https://github.com/kperry2215/webscrape_monthly_og_data_bakken)

### Data Standards
- [RBDMS (Risk Based Data Management System)](https://www.rbdms.org/)
- [FracFocus Chemical Disclosure](https://fracfocus.org/data-download)
- [Oklahoma Tax Commission Gross Production](https://otcportal.tax.ok.gov/gpx/index.php)
