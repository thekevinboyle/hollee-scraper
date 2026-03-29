# Task 1.3: Base Scraper Framework

## Objective

Create the `BaseOGSpider` abstract base class that all 10 state spiders will inherit from, the Scrapy settings with scrapy-playwright integration, the download pipeline that saves files to the organized folder structure, rate limiting middleware, and the per-state configuration registry. This establishes the scraping framework that Phase 4 and Phase 6 will use to implement actual state-specific spiders.

## Context

Task 1.1 created the project scaffolding and empty `backend/src/og_scraper/scrapers/` directory. This task fills that directory with the core scraping infrastructure. No actual state spiders are implemented here -- only the base class, shared settings, and supporting code. The actual state spiders (PA, CO, OK first, then the remaining 7) come in Phases 4 and 6.

Key constraints from DISCOVERY.md:
- Scrapy + Playwright hybrid -- Scrapy for static sites, Playwright for JS-heavy (D4, D20)
- Per-state adapter pattern -- base class with state-specific subclasses (D20)
- On-demand scraping only, triggered from dashboard (D3)
- File organization: `data/{state}/{operator}/{doc_type}/{filename}` (D22)
- Respectful crawling: obey robots.txt, conservative rate limiting, user-agent identification
- 10 target states: TX, NM, ND, OK, CO (Tier 1), WY, LA, PA, CA, AK (Tier 2)

## Dependencies

- Task 1.1 - Project structure with Scrapy + scrapy-playwright in dependencies

## Blocked By

- Task 1.1

## Research Findings

Key findings from research files relevant to this task:

- From `scrapy-playwright-scraping` skill: BaseOGSpider pattern with abstract methods, per-request Playwright routing via `meta={"playwright": True}`, AutoThrottle settings, ITEM_PIPELINES with priority ordering (validation:100, normalization:200, deduplication:300, storage:400, database:500), Playwright settings (browser type, max pages, abort unnecessary resources).
- From `scrapy-playwright-scraping` skill: Per-state rate limits range from 3s (PA, OK) to 15s (ND, LA). State registry maps state_code to config including spider class, base URL, delay, concurrency, whether Playwright is required.
- From `architecture-storage.md`: File organization pattern `data/{state}/{operator}/{doc_type}/{sha256_prefix}.{ext}`. SHA-256 hash for deduplication with UNIQUE constraint on `documents.file_hash`.

## Implementation Plan

### Step 1: Create Scrapy Settings

Create `backend/src/og_scraper/scrapers/settings.py`:

```python
"""Scrapy settings for the Oil & Gas Document Scraper."""

# --- Bot identity ---
BOT_NAME = "og-doc-scraper"
USER_AGENT = "OGDocScraper/1.0 (Research tool; oil-gas-regulatory-data)"

# --- Spider modules ---
SPIDER_MODULES = ["og_scraper.scrapers.spiders"]
NEWSPIDER_MODULE = "og_scraper.scrapers.spiders"

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

# --- AutoThrottle ---
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

# --- Item Pipelines (ordered by priority) ---
ITEM_PIPELINES = {
    "og_scraper.scrapers.pipelines.validation.ValidationPipeline": 100,
    "og_scraper.scrapers.pipelines.deduplication.DeduplicationPipeline": 300,
    "og_scraper.scrapers.pipelines.storage.FileStoragePipeline": 400,
}

# --- File Storage ---
FILES_STORE = "data/"

# --- Logging ---
LOG_LEVEL = "INFO"
LOG_FORMAT = "%(asctime)s [%(name)s] %(levelname)s: %(message)s"

# --- Downloader Middlewares ---
DOWNLOADER_MIDDLEWARES = {
    "og_scraper.scrapers.middlewares.rate_limiter.PerDomainRateLimitMiddleware": 100,
    "og_scraper.scrapers.middlewares.user_agent.UserAgentRotatorMiddleware": 200,
}
```

### Step 2: Create DocumentItem Data Model

Create `backend/src/og_scraper/scrapers/items.py`:

```python
"""Scrapy item definitions for the Oil & Gas Document Scraper."""

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any


@dataclass
class DocumentItem:
    """Represents a scraped document before database persistence.

    Yielded by state spiders, processed through the pipeline.
    """
    # Required fields
    state_code: str  # 2-letter code, e.g. "TX"
    source_url: str  # URL the document was scraped from
    doc_type: str  # e.g. "production_report", "well_permit"

    # Well identification (at least one should be populated)
    api_number: str | None = None  # 14-digit normalized
    operator_name: str | None = None
    well_name: str | None = None
    lease_name: str | None = None

    # File info (populated by download pipeline)
    file_path: str | None = None
    file_hash: str | None = None  # SHA-256
    file_format: str | None = None  # "pdf", "csv", "xlsx", "html"
    file_size_bytes: int | None = None
    file_content: bytes | None = None  # Raw file bytes (before save)

    # Dates
    document_date: date | None = None
    scraped_at: datetime = field(default_factory=datetime.utcnow)

    # Location (if available from scrape)
    latitude: float | None = None
    longitude: float | None = None

    # County/basin/field
    county: str | None = None
    basin: str | None = None
    field_name: str | None = None

    # Raw metadata from the source page
    raw_metadata: dict[str, Any] = field(default_factory=dict)

    # Scrape job tracking
    scrape_job_id: str | None = None


@dataclass
class WellItem:
    """Represents a well discovered during scraping."""
    api_number: str  # 14-digit normalized
    state_code: str
    well_name: str | None = None
    well_number: str | None = None
    operator_name: str | None = None
    county: str | None = None
    basin: str | None = None
    field_name: str | None = None
    lease_name: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    well_status: str | None = None
    well_type: str | None = None
    spud_date: date | None = None
    completion_date: date | None = None
    total_depth: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    alternate_ids: dict[str, str] = field(default_factory=dict)
```

### Step 3: Create BaseOGSpider

Create `backend/src/og_scraper/scrapers/spiders/base.py`:

```python
"""Base spider class for all state oil & gas regulatory site scrapers."""

import hashlib
import re
from abc import abstractmethod

import scrapy
from scrapy import signals

from og_scraper.scrapers.items import DocumentItem


class BaseOGSpider(scrapy.Spider):
    """Abstract base class for all state oil & gas spiders.

    Subclasses MUST set:
        - state_code (str): 2-letter state code, e.g. "TX"
        - state_name (str): Full state name
        - agency_name (str): Regulatory agency name
        - base_url (str): Primary site URL

    Subclasses MUST implement:
        - start_requests(): Define scraping entry points

    Subclasses MAY override:
        - requires_playwright (bool): Whether this spider needs Playwright
        - rate_limit_delay (float): Base delay between requests
        - max_concurrent (int): Max concurrent requests for this state
        - custom_settings (dict): Scrapy settings overrides
    """

    # --- Subclasses MUST override ---
    state_code: str = None
    state_name: str = None
    agency_name: str = None
    base_url: str = None

    # --- Subclasses MAY override ---
    requires_playwright: bool = False
    rate_limit_delay: float = 5.0
    max_concurrent: int = 2

    custom_settings = {
        "AUTOTHROTTLE_ENABLED": True,
        "AUTOTHROTTLE_START_DELAY": 5,
        "AUTOTHROTTLE_MAX_DELAY": 60,
        "AUTOTHROTTLE_TARGET_CONCURRENCY": 1.0,
    }

    def __init__(self, *args, scrape_job_id: str | None = None, **kwargs):
        super().__init__(*args, **kwargs)
        self.scrape_job_id = scrape_job_id
        self.documents_found = 0
        self.documents_downloaded = 0
        self.errors = 0
        self._validate_config()

    def _validate_config(self):
        """Ensure subclass has set all required attributes."""
        for attr in ("state_code", "state_name", "agency_name", "base_url"):
            if getattr(self, attr) is None:
                raise ValueError(f"{self.__class__.__name__} must set '{attr}'")

    @classmethod
    def from_crawler(cls, crawler, *args, **kwargs):
        spider = super().from_crawler(crawler, *args, **kwargs)
        crawler.signals.connect(spider.spider_closed, signal=signals.spider_closed)
        return spider

    def spider_closed(self, reason):
        """Log summary when spider finishes."""
        self.logger.info(
            f"[{self.state_code}] Spider closed: reason={reason}, "
            f"found={self.documents_found}, downloaded={self.documents_downloaded}, "
            f"errors={self.errors}"
        )

    @abstractmethod
    def start_requests(self):
        """Subclasses must define their own scraping entry points.

        Yield scrapy.Request objects. For JS-heavy pages, set
        meta={"playwright": True, "playwright_page_methods": [...]}.
        """
        pass

    def normalize_api_number(self, raw: str) -> str:
        """Normalize an API number to 14-digit format without dashes.

        Strips all non-digit characters, then zero-pads to 14 digits
        on the right (unknown sidetrack/event codes become 00).

        Examples:
            "42-501-20130-03-00" -> "42501201300300"
            "42501201300300"     -> "42501201300300"
            "4250120130"         -> "42501201300000"
            "425012013003"       -> "42501201300300"
        """
        digits = re.sub(r"[^0-9]", "", raw)
        if len(digits) < 10:
            return raw  # Too short to be valid, return as-is
        return digits.ljust(14, "0")[:14]

    def compute_file_hash(self, content: bytes) -> str:
        """Compute SHA-256 hash of file content for deduplication."""
        return hashlib.sha256(content).hexdigest()

    def build_document_item(
        self,
        source_url: str,
        doc_type: str,
        api_number: str | None = None,
        operator_name: str | None = None,
        well_name: str | None = None,
        file_content: bytes | None = None,
        file_format: str | None = None,
        raw_metadata: dict | None = None,
        **kwargs,
    ) -> DocumentItem:
        """Construct a DocumentItem with common fields pre-filled."""
        item = DocumentItem(
            state_code=self.state_code,
            source_url=source_url,
            doc_type=doc_type,
            api_number=self.normalize_api_number(api_number) if api_number else None,
            operator_name=operator_name,
            well_name=well_name,
            file_content=file_content,
            file_format=file_format,
            file_hash=self.compute_file_hash(file_content) if file_content else None,
            file_size_bytes=len(file_content) if file_content else None,
            raw_metadata=raw_metadata or {},
            scrape_job_id=self.scrape_job_id,
            **kwargs,
        )
        self.documents_found += 1
        return item

    def errback_handler(self, failure):
        """Common error handler for failed requests.

        Closes Playwright pages on failure to prevent resource leaks.
        """
        self.errors += 1
        self.logger.error(f"[{self.state_code}] Request failed: {failure.value}")
        page = failure.request.meta.get("playwright_page")
        if page:
            page.close()

    def make_playwright_request(self, url: str, callback, page_methods=None, **kwargs):
        """Helper to create a Playwright-enabled request.

        Args:
            url: Target URL
            callback: Response parse method
            page_methods: List of PageMethod objects for browser interaction
            **kwargs: Additional scrapy.Request kwargs
        """
        meta = {
            "playwright": True,
            "playwright_include_page": True,
        }
        if page_methods:
            meta["playwright_page_methods"] = page_methods

        return scrapy.Request(
            url=url,
            callback=callback,
            errback=self.errback_handler,
            meta=meta,
            **kwargs,
        )
```

### Step 4: Create Download Pipelines

Create `backend/src/og_scraper/scrapers/pipelines/validation.py`:

```python
"""Validation pipeline -- ensures required fields are present."""

import logging

from scrapy.exceptions import DropItem

from og_scraper.scrapers.items import DocumentItem

logger = logging.getLogger(__name__)


class ValidationPipeline:
    """Validates that scraped items have required fields."""

    REQUIRED_FIELDS = ["state_code", "source_url", "doc_type"]

    def process_item(self, item, spider):
        if not isinstance(item, DocumentItem):
            return item

        for field_name in self.REQUIRED_FIELDS:
            value = getattr(item, field_name, None)
            if not value:
                raise DropItem(f"Missing required field '{field_name}' in item from {spider.state_code}")

        # Validate state code is one of the 10 supported states
        valid_states = {"TX", "NM", "ND", "OK", "CO", "WY", "LA", "PA", "CA", "AK"}
        if item.state_code not in valid_states:
            raise DropItem(f"Invalid state_code '{item.state_code}'")

        return item
```

Create `backend/src/og_scraper/scrapers/pipelines/deduplication.py`:

```python
"""Deduplication pipeline -- skips documents with duplicate content hashes."""

import logging

from scrapy.exceptions import DropItem

from og_scraper.scrapers.items import DocumentItem

logger = logging.getLogger(__name__)


class DeduplicationPipeline:
    """Deduplicates items based on SHA-256 content hash.

    Maintains an in-memory set of seen hashes for the current crawl.
    Database-level deduplication is also enforced via UNIQUE constraint
    on documents.file_hash.
    """

    def __init__(self):
        self.seen_hashes: set[str] = set()

    def process_item(self, item, spider):
        if not isinstance(item, DocumentItem):
            return item

        if not item.file_hash:
            return item  # No hash yet (content not downloaded), pass through

        if item.file_hash in self.seen_hashes:
            raise DropItem(f"Duplicate content hash: {item.file_hash[:16]}...")

        self.seen_hashes.add(item.file_hash)
        return item
```

Create `backend/src/og_scraper/scrapers/pipelines/storage.py`:

```python
"""File storage pipeline -- saves documents to organized folder structure."""

import hashlib
import logging
import os
import re
from pathlib import Path

from og_scraper.scrapers.items import DocumentItem

logger = logging.getLogger(__name__)

# Base directory for document storage
DATA_DIR = os.environ.get("DOCUMENTS_DIR", "data/documents")


def slugify(text: str) -> str:
    """Convert text to a filesystem-safe slug."""
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[-\s]+", "-", text)
    return text[:100]  # Limit length


class FileStoragePipeline:
    """Saves document files to the organized folder structure.

    Path format: data/documents/{state_code}/{operator_slug}/{doc_type}/{hash}.{ext}

    If operator_name is unknown, uses '_unknown' as the operator slug.
    """

    def process_item(self, item, spider):
        if not isinstance(item, DocumentItem):
            return item

        if not item.file_content:
            return item  # No file content to save

        # Compute hash if not already set
        if not item.file_hash:
            item.file_hash = hashlib.sha256(item.file_content).hexdigest()

        # Build the directory path
        operator_slug = slugify(item.operator_name) if item.operator_name else "_unknown"
        doc_type_slug = item.doc_type.replace("_", "-")
        ext = item.file_format or "bin"

        dir_path = Path(DATA_DIR) / item.state_code / operator_slug / doc_type_slug
        dir_path.mkdir(parents=True, exist_ok=True)

        # Filename is first 16 chars of SHA-256 hash + extension
        filename = f"{item.file_hash[:16]}.{ext}"
        file_path = dir_path / filename

        # Write the file
        if not file_path.exists():
            file_path.write_bytes(item.file_content)
            logger.info(f"Saved document: {file_path}")
        else:
            logger.debug(f"File already exists: {file_path}")

        # Update item with the file path (relative to DATA_DIR)
        item.file_path = str(file_path)
        item.file_size_bytes = len(item.file_content)

        # Clear file_content from memory after saving
        item.file_content = None

        return item
```

### Step 5: Create Middlewares

Create `backend/src/og_scraper/scrapers/middlewares/rate_limiter.py`:

```python
"""Per-domain rate limiting middleware."""

import logging
import random
import time
from collections import defaultdict

logger = logging.getLogger(__name__)


class PerDomainRateLimitMiddleware:
    """Adds per-domain rate limiting with jitter.

    Tracks the last request time per domain and enforces a minimum
    delay with +/- 30% random jitter to avoid detection patterns.
    """

    def __init__(self):
        self._last_request_time: dict[str, float] = defaultdict(float)

    @classmethod
    def from_crawler(cls, crawler):
        return cls()

    def process_request(self, request, spider):
        domain = request.url.split("//")[-1].split("/")[0]
        delay = getattr(spider, "rate_limit_delay", 5.0)

        # Add jitter: +/- 30%
        jitter = delay * 0.3 * (2 * random.random() - 1)
        actual_delay = max(0.5, delay + jitter)

        elapsed = time.time() - self._last_request_time[domain]
        if elapsed < actual_delay:
            wait = actual_delay - elapsed
            logger.debug(f"Rate limiting {domain}: waiting {wait:.1f}s")
            time.sleep(wait)

        self._last_request_time[domain] = time.time()
        return None
```

Create `backend/src/og_scraper/scrapers/middlewares/user_agent.py`:

```python
"""User-Agent rotation middleware."""

import random


# Realistic browser User-Agent strings
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:133.0) Gecko/20100101 Firefox/133.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.2 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
]

# The bot identifier used when robots.txt requires it
BOT_USER_AGENT = "OGDocScraper/1.0 (Research tool; oil-gas-regulatory-data)"


class UserAgentRotatorMiddleware:
    """Rotates User-Agent strings for non-Playwright requests.

    Playwright requests already have a real browser UA, so this
    middleware only applies to standard Scrapy HTTP requests.
    For robots.txt requests, the bot UA is always used.
    """

    @classmethod
    def from_crawler(cls, crawler):
        return cls()

    def process_request(self, request, spider):
        # Don't override for Playwright requests (they have real browser UAs)
        if request.meta.get("playwright"):
            return None

        # Use bot UA for robots.txt
        if "robots.txt" in request.url:
            request.headers["User-Agent"] = BOT_USER_AGENT
            return None

        # Rotate UA for regular requests
        request.headers["User-Agent"] = random.choice(USER_AGENTS)
        return None
```

Create `backend/src/og_scraper/scrapers/middlewares/__init__.py` (empty).

### Step 6: Create State Configuration Registry

Create `backend/src/og_scraper/scrapers/state_registry.py`:

```python
"""Per-state scraper configuration registry.

Maps each state code to its scraping configuration. Spider classes
are set to None as placeholders until actual spiders are implemented
in Phase 4 (PA, CO, OK) and Phase 6 (remaining 7 states).
"""

from dataclasses import dataclass, field


@dataclass
class StateConfig:
    """Configuration for a single state's scraping setup."""
    code: str
    name: str
    agency: str
    base_url: str
    requires_playwright: bool = False
    scrape_type: str = "bulk_download"  # bulk_download, arcgis_api, browser_form
    rate_limit_seconds: float = 5.0
    max_concurrent: int = 2
    data_formats: list[str] = field(default_factory=list)
    spider_class: str | None = None  # Dotted path to spider class (None = not yet implemented)
    tier: int = 1
    notes: str = ""


STATE_REGISTRY: dict[str, StateConfig] = {
    "TX": StateConfig(
        code="TX",
        name="Texas",
        agency="Railroad Commission of Texas (RRC)",
        base_url="https://www.rrc.texas.gov/",
        requires_playwright=False,
        scrape_type="bulk_download",
        rate_limit_seconds=10.0,
        max_concurrent=2,
        data_formats=["EBCDIC", "ASCII", "CSV", "JSON", "dBase", "PDF", "Shapefile"],
        spider_class=None,
        tier=1,
        notes="DO NOT scrape the PDQ web interface. Use bulk downloads only.",
    ),
    "NM": StateConfig(
        code="NM",
        name="New Mexico",
        agency="Oil Conservation Division (OCD)",
        base_url="https://ocdimage.emnrd.nm.gov/",
        requires_playwright=False,
        scrape_type="arcgis_api",
        rate_limit_seconds=5.0,
        max_concurrent=2,
        data_formats=["ArcGIS JSON", "PDF", "CSV"],
        spider_class=None,
        tier=1,
        notes="Data spread across OCD Hub, OCD Permitting, ONGARD, and GO-TECH.",
    ),
    "ND": StateConfig(
        code="ND",
        name="North Dakota",
        agency="Dept of Mineral Resources (DMR)",
        base_url="https://www.dmr.nd.gov/oilgas/",
        requires_playwright=True,
        scrape_type="browser_form",
        rate_limit_seconds=15.0,
        max_concurrent=1,
        data_formats=["PDF", "CSV", "HTML"],
        spider_class=None,
        tier=1,
        notes="Subscription portal -- free data limited to PDFs and basic well search.",
    ),
    "OK": StateConfig(
        code="OK",
        name="Oklahoma",
        agency="Corporation Commission (OCC)",
        base_url="https://imaging.occeweb.com/",
        requires_playwright=False,
        scrape_type="bulk_download",
        rate_limit_seconds=3.0,
        max_concurrent=4,
        data_formats=["CSV", "XLSX", "PDF"],
        spider_class=None,
        tier=1,
        notes="Production data from OkTAP (Tax Commission), not OCC.",
    ),
    "CO": StateConfig(
        code="CO",
        name="Colorado",
        agency="Energy & Carbon Management Commission (ECMC)",
        base_url="https://ecmc.colorado.gov/",
        requires_playwright=False,
        scrape_type="bulk_download",
        rate_limit_seconds=8.0,
        max_concurrent=2,
        data_formats=["CSV", "PDF", "Shapefile"],
        spider_class=None,
        tier=1,
        notes="Dual domains: ecmc.colorado.gov (new) and ecmc.state.co.us (legacy).",
    ),
    "WY": StateConfig(
        code="WY",
        name="Wyoming",
        agency="Oil & Gas Conservation Commission (WOGCC)",
        base_url="https://wogcc.wyo.gov/",
        requires_playwright=True,
        scrape_type="browser_form",
        rate_limit_seconds=10.0,
        max_concurrent=1,
        data_formats=["CSV", "PDF", "ArcGIS JSON"],
        spider_class=None,
        tier=2,
        notes="Data Explorer is JS-heavy. Legacy portal uses ColdFusion.",
    ),
    "LA": StateConfig(
        code="LA",
        name="Louisiana",
        agency="Dept of Conservation & Energy (SONRIS)",
        base_url="https://www.sonris.com/",
        requires_playwright=True,
        scrape_type="browser_form",
        rate_limit_seconds=15.0,
        max_concurrent=1,
        data_formats=["Excel", "PDF", "HTML"],
        spider_class=None,
        tier=2,
        notes="Hardest to scrape. Oracle backend, complex JS, no REST API.",
    ),
    "PA": StateConfig(
        code="PA",
        name="Pennsylvania",
        agency="Dept of Environmental Protection (DEP)",
        base_url="https://greenport.pa.gov/ReportExtracts/OG/Index",
        requires_playwright=False,
        scrape_type="bulk_download",
        rate_limit_seconds=3.0,
        max_concurrent=4,
        data_formats=["CSV"],
        spider_class=None,
        tier=2,
        notes="Easiest to scrape. All data as on-demand CSV exports.",
    ),
    "CA": StateConfig(
        code="CA",
        name="California",
        agency="Geologic Energy Management Division (CalGEM)",
        base_url="https://gis.conservation.ca.gov/",
        requires_playwright=False,
        scrape_type="arcgis_api",
        rate_limit_seconds=3.0,
        max_concurrent=3,
        data_formats=["ArcGIS JSON", "CSV"],
        spider_class=None,
        tier=2,
        notes="ArcGIS returns Web Mercator (EPSG:3857). Convert to WGS84.",
    ),
    "AK": StateConfig(
        code="AK",
        name="Alaska",
        agency="Oil & Gas Conservation Commission (AOGCC)",
        base_url="http://aogweb.state.ak.us/",
        requires_playwright=True,
        scrape_type="browser_form",
        rate_limit_seconds=5.0,
        max_concurrent=2,
        data_formats=["HTML", "PDF", "CSV"],
        spider_class=None,
        tier=2,
        notes="Data Miner on plain HTTP. ASP.NET WebForms with ViewState.",
    ),
}


def get_state_config(state_code: str) -> StateConfig:
    """Get configuration for a state. Raises KeyError if state not found."""
    state_code = state_code.upper()
    if state_code not in STATE_REGISTRY:
        raise KeyError(f"Unknown state code: {state_code}. Valid: {list(STATE_REGISTRY.keys())}")
    return STATE_REGISTRY[state_code]


def get_all_states() -> list[StateConfig]:
    """Get configurations for all 10 states."""
    return list(STATE_REGISTRY.values())


def get_states_by_tier(tier: int) -> list[StateConfig]:
    """Get state configurations filtered by tier (1 or 2)."""
    return [s for s in STATE_REGISTRY.values() if s.tier == tier]


def get_implemented_states() -> list[StateConfig]:
    """Get state configurations that have spider implementations."""
    return [s for s in STATE_REGISTRY.values() if s.spider_class is not None]
```

### Step 7: Create API Number Utility

Create `backend/src/og_scraper/utils/api_number.py`:

```python
"""API number normalization and validation utilities.

API numbers are the primary identifier for oil and gas wells in the US.
Format: SS-CCC-NNNNN-SS-SS (state-county-unique-sidetrack-event)
Stored as 14-digit VARCHAR without dashes, zero-padded.
"""

import re


def normalize_api_number(raw: str) -> str:
    """Normalize an API number to 14-digit format without dashes.

    Strips all non-digit characters, then right-pads with zeros to 14 digits.

    Args:
        raw: Raw API number in any format (with dashes, spaces, etc.)

    Returns:
        14-digit string without dashes, or the original string if < 10 digits.

    Examples:
        >>> normalize_api_number("42-501-20130-03-00")
        '42501201300300'
        >>> normalize_api_number("42501201300300")
        '42501201300300'
        >>> normalize_api_number("4250120130")
        '42501201300000'
        >>> normalize_api_number("425012013003")
        '42501201300300'
    """
    digits = re.sub(r"[^0-9]", "", raw.strip())

    if len(digits) < 10:
        return raw  # Too short to be a valid API number

    # Right-pad to 14 digits
    return digits.ljust(14, "0")[:14]


def format_api_number(normalized: str) -> str:
    """Format a 14-digit API number with dashes for display.

    Args:
        normalized: 14-digit API number without dashes

    Returns:
        Formatted string: SS-CCC-NNNNN-SS-SS

    Example:
        >>> format_api_number("42501201300300")
        '42-501-20130-03-00'
    """
    if len(normalized) != 14 or not normalized.isdigit():
        return normalized
    return f"{normalized[:2]}-{normalized[2:5]}-{normalized[5:10]}-{normalized[10:12]}-{normalized[12:14]}"


def extract_api_10(api_number: str) -> str:
    """Extract the first 10 digits of an API number for cross-referencing.

    The 10-digit prefix (state + county + unique well number) is the
    most common format used for matching across systems.

    Args:
        api_number: Normalized 14-digit API number

    Returns:
        First 10 digits
    """
    digits = re.sub(r"[^0-9]", "", api_number)
    return digits[:10]


def validate_api_number(api_number: str) -> bool:
    """Check if a string looks like a valid API number.

    Validates that it contains at least 10 digits after stripping
    non-digit characters.

    Args:
        api_number: Raw or normalized API number

    Returns:
        True if valid, False otherwise
    """
    digits = re.sub(r"[^0-9]", "", api_number)
    return 10 <= len(digits) <= 14


# Known state codes for the first 2 digits of API numbers
API_STATE_CODES = {
    "02": "AK", "04": "CA", "05": "CO", "17": "LA", "30": "NM",
    "33": "ND", "35": "OK", "37": "PA", "42": "TX", "49": "WY",
}


def state_from_api_number(api_number: str) -> str | None:
    """Extract the state code from an API number's first 2 digits.

    Args:
        api_number: Raw or normalized API number

    Returns:
        2-letter state code, or None if not recognized
    """
    digits = re.sub(r"[^0-9]", "", api_number)
    if len(digits) >= 2:
        return API_STATE_CODES.get(digits[:2])
    return None
```

### Step 8: Create Tests

Create `backend/tests/scrapers/__init__.py` (empty).

Create `backend/tests/scrapers/test_base_spider.py`:

```python
"""Tests for BaseOGSpider."""

import pytest

from og_scraper.scrapers.spiders.base import BaseOGSpider
from og_scraper.scrapers.items import DocumentItem


class ConcreteSpider(BaseOGSpider):
    """Concrete implementation for testing."""
    name = "test_spider"
    state_code = "TX"
    state_name = "Texas"
    agency_name = "Railroad Commission of Texas"
    base_url = "https://www.rrc.texas.gov/"

    def start_requests(self):
        yield None  # Not testing actual requests


class TestBaseOGSpider:
    def test_enforces_abstract_methods(self):
        """BaseOGSpider cannot be instantiated directly."""
        with pytest.raises(TypeError):
            BaseOGSpider()

    def test_validates_required_attributes(self):
        """Spider without required attributes raises ValueError."""
        class BadSpider(BaseOGSpider):
            name = "bad"
            state_code = None  # Missing!
            state_name = "Test"
            agency_name = "Test"
            base_url = "http://test.com"
            def start_requests(self): pass

        with pytest.raises(ValueError, match="state_code"):
            BadSpider()

    def test_concrete_spider_instantiates(self):
        """Properly configured spider instantiates."""
        spider = ConcreteSpider()
        assert spider.state_code == "TX"
        assert spider.documents_found == 0

    def test_normalize_api_number_14_digits(self):
        spider = ConcreteSpider()
        assert spider.normalize_api_number("42-501-20130-03-00") == "42501201300300"

    def test_normalize_api_number_10_digits(self):
        spider = ConcreteSpider()
        assert spider.normalize_api_number("4250120130") == "42501201300000"

    def test_normalize_api_number_12_digits(self):
        spider = ConcreteSpider()
        assert spider.normalize_api_number("425012013003") == "42501201300300"

    def test_normalize_api_number_already_normalized(self):
        spider = ConcreteSpider()
        assert spider.normalize_api_number("42501201300300") == "42501201300300"

    def test_normalize_api_number_too_short(self):
        spider = ConcreteSpider()
        assert spider.normalize_api_number("12345") == "12345"

    def test_compute_file_hash(self):
        spider = ConcreteSpider()
        content = b"test content"
        hash1 = spider.compute_file_hash(content)
        hash2 = spider.compute_file_hash(content)
        assert hash1 == hash2
        assert len(hash1) == 64  # SHA-256 hex digest

    def test_build_document_item(self):
        spider = ConcreteSpider()
        item = spider.build_document_item(
            source_url="https://example.com/doc.pdf",
            doc_type="production_report",
            api_number="42-501-20130-03-00",
            operator_name="Devon Energy",
        )
        assert isinstance(item, DocumentItem)
        assert item.state_code == "TX"
        assert item.api_number == "42501201300300"
        assert item.operator_name == "Devon Energy"
        assert spider.documents_found == 1
```

Create `backend/tests/scrapers/test_state_registry.py`:

```python
"""Tests for state configuration registry."""

import pytest

from og_scraper.scrapers.state_registry import (
    STATE_REGISTRY,
    get_state_config,
    get_all_states,
    get_states_by_tier,
    get_implemented_states,
)


class TestStateRegistry:
    def test_registry_has_10_states(self):
        assert len(STATE_REGISTRY) == 10

    def test_all_state_codes_present(self):
        expected = {"TX", "NM", "ND", "OK", "CO", "WY", "LA", "PA", "CA", "AK"}
        assert set(STATE_REGISTRY.keys()) == expected

    def test_get_state_config_valid(self):
        config = get_state_config("TX")
        assert config.code == "TX"
        assert config.name == "Texas"
        assert config.agency == "Railroad Commission of Texas (RRC)"
        assert config.rate_limit_seconds == 10.0

    def test_get_state_config_case_insensitive(self):
        config = get_state_config("tx")
        assert config.code == "TX"

    def test_get_state_config_invalid(self):
        with pytest.raises(KeyError, match="Unknown state code"):
            get_state_config("ZZ")

    def test_get_all_states(self):
        states = get_all_states()
        assert len(states) == 10

    def test_tier_1_has_5_states(self):
        tier1 = get_states_by_tier(1)
        assert len(tier1) == 5
        assert all(s.tier == 1 for s in tier1)

    def test_tier_2_has_5_states(self):
        tier2 = get_states_by_tier(2)
        assert len(tier2) == 5
        assert all(s.tier == 2 for s in tier2)

    def test_no_states_implemented_yet(self):
        """All spider_class values should be None in Phase 1."""
        implemented = get_implemented_states()
        assert len(implemented) == 0

    def test_pa_is_easiest(self):
        """PA should have the lowest rate limit (easiest to scrape)."""
        pa = get_state_config("PA")
        assert pa.rate_limit_seconds == 3.0
        assert pa.requires_playwright is False
        assert pa.scrape_type == "bulk_download"

    def test_la_is_hardest(self):
        """LA should require Playwright and have high rate limit."""
        la = get_state_config("LA")
        assert la.rate_limit_seconds == 15.0
        assert la.requires_playwright is True
        assert la.scrape_type == "browser_form"
```

Create `backend/tests/utils/__init__.py` (empty).

Create `backend/tests/utils/test_api_number.py`:

```python
"""Tests for API number normalization utilities."""

from og_scraper.utils.api_number import (
    normalize_api_number,
    format_api_number,
    extract_api_10,
    validate_api_number,
    state_from_api_number,
)


class TestNormalizeAPINumber:
    def test_strip_dashes(self):
        assert normalize_api_number("42-501-20130-03-00") == "42501201300300"

    def test_already_normalized(self):
        assert normalize_api_number("42501201300300") == "42501201300300"

    def test_10_digit_pads_to_14(self):
        assert normalize_api_number("4250120130") == "42501201300000"

    def test_12_digit_pads_to_14(self):
        assert normalize_api_number("425012013003") == "42501201300300"

    def test_too_short_returns_original(self):
        assert normalize_api_number("12345") == "12345"

    def test_strips_spaces(self):
        assert normalize_api_number("42 501 20130 03 00") == "42501201300300"

    def test_mixed_separators(self):
        assert normalize_api_number("42.501.20130.03.00") == "42501201300300"


class TestFormatAPINumber:
    def test_format_14_digit(self):
        assert format_api_number("42501201300300") == "42-501-20130-03-00"

    def test_invalid_length_returns_original(self):
        assert format_api_number("4250120130") == "4250120130"


class TestExtractApi10:
    def test_extract_from_14(self):
        assert extract_api_10("42501201300300") == "4250120130"

    def test_extract_from_formatted(self):
        assert extract_api_10("42-501-20130-03-00") == "4250120130"


class TestValidateAPINumber:
    def test_valid_14_digit(self):
        assert validate_api_number("42501201300300") is True

    def test_valid_10_digit(self):
        assert validate_api_number("4250120130") is True

    def test_valid_with_dashes(self):
        assert validate_api_number("42-501-20130-03-00") is True

    def test_too_short(self):
        assert validate_api_number("12345") is False


class TestStateFromAPINumber:
    def test_texas(self):
        assert state_from_api_number("42501201300300") == "TX"

    def test_alaska(self):
        assert state_from_api_number("02501201300300") == "AK"

    def test_unknown_state(self):
        assert state_from_api_number("99501201300300") is None
```

Create `backend/tests/scrapers/test_pipelines.py`:

```python
"""Tests for scraper pipelines."""

import os
import tempfile

import pytest
from scrapy.exceptions import DropItem

from og_scraper.scrapers.items import DocumentItem
from og_scraper.scrapers.pipelines.validation import ValidationPipeline
from og_scraper.scrapers.pipelines.deduplication import DeduplicationPipeline
from og_scraper.scrapers.pipelines.storage import FileStoragePipeline, slugify


class TestValidationPipeline:
    def setup_method(self):
        self.pipeline = ValidationPipeline()

    def test_valid_item_passes(self):
        item = DocumentItem(state_code="TX", source_url="https://example.com", doc_type="well_permit")
        result = self.pipeline.process_item(item, None)
        assert result is item

    def test_missing_state_code_drops(self):
        item = DocumentItem(state_code="", source_url="https://example.com", doc_type="well_permit")
        with pytest.raises(DropItem, match="state_code"):
            self.pipeline.process_item(item, type("Spider", (), {"state_code": "TX"}))

    def test_invalid_state_drops(self):
        item = DocumentItem(state_code="ZZ", source_url="https://example.com", doc_type="well_permit")
        with pytest.raises(DropItem, match="Invalid state_code"):
            self.pipeline.process_item(item, type("Spider", (), {"state_code": "ZZ"}))


class TestDeduplicationPipeline:
    def setup_method(self):
        self.pipeline = DeduplicationPipeline()

    def test_first_hash_passes(self):
        item = DocumentItem(state_code="TX", source_url="https://example.com", doc_type="well_permit", file_hash="abc123")
        result = self.pipeline.process_item(item, None)
        assert result is item

    def test_duplicate_hash_drops(self):
        item1 = DocumentItem(state_code="TX", source_url="https://example.com/1", doc_type="well_permit", file_hash="abc123")
        item2 = DocumentItem(state_code="TX", source_url="https://example.com/2", doc_type="well_permit", file_hash="abc123")
        self.pipeline.process_item(item1, None)
        with pytest.raises(DropItem, match="Duplicate"):
            self.pipeline.process_item(item2, None)

    def test_no_hash_passes_through(self):
        item = DocumentItem(state_code="TX", source_url="https://example.com", doc_type="well_permit")
        result = self.pipeline.process_item(item, None)
        assert result is item


class TestFileStoragePipeline:
    def test_creates_correct_directory_structure(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            os.environ["DOCUMENTS_DIR"] = tmpdir
            pipeline = FileStoragePipeline()

            item = DocumentItem(
                state_code="TX",
                source_url="https://example.com",
                doc_type="production_report",
                operator_name="Devon Energy",
                file_content=b"test pdf content",
                file_format="pdf",
            )
            result = pipeline.process_item(item, None)

            assert result.file_path is not None
            assert "TX" in result.file_path
            assert "devon-energy" in result.file_path
            assert "production-report" in result.file_path
            assert result.file_path.endswith(".pdf")
            assert os.path.exists(result.file_path)
            assert result.file_content is None  # Cleared after save


class TestSlugify:
    def test_basic(self):
        assert slugify("Devon Energy") == "devon-energy"

    def test_special_chars(self):
        assert slugify("Devon Energy Corp.") == "devon-energy-corp"

    def test_long_name_truncated(self):
        result = slugify("A" * 200)
        assert len(result) <= 100
```

## Files to Create

- `backend/src/og_scraper/scrapers/settings.py` - Scrapy + Playwright settings
- `backend/src/og_scraper/scrapers/items.py` - DocumentItem and WellItem dataclasses
- `backend/src/og_scraper/scrapers/spiders/base.py` - BaseOGSpider abstract class
- `backend/src/og_scraper/scrapers/pipelines/validation.py` - Required field validation
- `backend/src/og_scraper/scrapers/pipelines/deduplication.py` - SHA-256 dedup
- `backend/src/og_scraper/scrapers/pipelines/storage.py` - File storage pipeline
- `backend/src/og_scraper/scrapers/middlewares/rate_limiter.py` - Per-domain rate limiting
- `backend/src/og_scraper/scrapers/middlewares/user_agent.py` - UA rotation
- `backend/src/og_scraper/scrapers/state_registry.py` - 10-state config registry
- `backend/src/og_scraper/utils/api_number.py` - API number normalization
- `backend/tests/scrapers/__init__.py` - Test package
- `backend/tests/scrapers/test_base_spider.py` - BaseOGSpider tests
- `backend/tests/scrapers/test_state_registry.py` - Registry tests
- `backend/tests/scrapers/test_pipelines.py` - Pipeline tests
- `backend/tests/utils/__init__.py` - Test package
- `backend/tests/utils/test_api_number.py` - API number tests

## Files to Modify

- None

## Contracts

### Provides (for downstream tasks)

- **BaseOGSpider**: Abstract class at `og_scraper.scrapers.spiders.base.BaseOGSpider` -- all state spiders inherit from this
- **DocumentItem**: Dataclass at `og_scraper.scrapers.items.DocumentItem` -- spider yield type
- **WellItem**: Dataclass at `og_scraper.scrapers.items.WellItem` -- well discovery yield type
- **State registry**: `og_scraper.scrapers.state_registry.get_state_config(code)` returns `StateConfig`
- **File storage path**: `data/documents/{state_code}/{operator_slug}/{doc_type_slug}/{hash[:16]}.{ext}`
- **API number utility**: `og_scraper.utils.api_number.normalize_api_number(raw)` returns 14-digit string
- **Scrapy settings**: `og_scraper.scrapers.settings` -- import path for Scrapy configuration

### Consumes (from upstream tasks)

- Task 1.1: Package structure at `backend/src/og_scraper/scrapers/`, Scrapy + scrapy-playwright dependencies

## Acceptance Criteria

- [ ] `BaseOGSpider` is abstract and cannot be instantiated directly
- [ ] `BaseOGSpider` enforces that subclasses set `state_code`, `state_name`, `agency_name`, `base_url`
- [ ] A concrete spider subclass can be instantiated and yields `DocumentItem` objects
- [ ] `DocumentItem` dataclass has all required fields: state_code, source_url, doc_type, api_number, file_hash, etc.
- [ ] Download pipeline creates correct directory structure: `data/documents/{state}/{operator}/{doc_type}/`
- [ ] Deduplication pipeline rejects items with duplicate SHA-256 hashes
- [ ] State registry contains entries for all 10 states
- [ ] State registry returns correct config (rate limit, playwright requirement) for each state
- [ ] API number normalization handles 10, 12, and 14-digit inputs with dashes
- [ ] Scrapy settings enable AutoThrottle and respectful crawling (ROBOTSTXT_OBEY = True)
- [ ] All tests pass: `uv run pytest backend/tests/scrapers/ backend/tests/utils/ -v`

## Testing Protocol

### Unit/Integration Tests

- Test file: `backend/tests/scrapers/test_base_spider.py`
  - [ ] BaseOGSpider raises TypeError if instantiated directly
  - [ ] Missing required attributes raise ValueError
  - [ ] API number normalization: 14-digit, 10-digit, 12-digit, with-dashes, too-short
  - [ ] File hash computation returns consistent SHA-256
  - [ ] `build_document_item()` constructs correct DocumentItem

- Test file: `backend/tests/scrapers/test_state_registry.py`
  - [ ] Registry has exactly 10 states
  - [ ] All expected state codes are present
  - [ ] get_state_config returns correct data for each state
  - [ ] get_state_config is case-insensitive
  - [ ] Invalid state code raises KeyError
  - [ ] Tier 1 and Tier 2 each have 5 states
  - [ ] No spiders implemented yet (all spider_class is None)

- Test file: `backend/tests/scrapers/test_pipelines.py`
  - [ ] Validation pipeline passes valid items
  - [ ] Validation pipeline drops items with missing fields
  - [ ] Validation pipeline drops items with invalid state codes
  - [ ] Deduplication drops duplicate hashes, passes unique ones
  - [ ] Storage pipeline creates correct directory structure and saves files

- Test file: `backend/tests/utils/test_api_number.py`
  - [ ] normalize, format, extract_api_10, validate, state_from_api_number

### Build/Lint/Type Checks

- [ ] `cd backend && uv run ruff check src/og_scraper/scrapers/ src/og_scraper/utils/` passes
- [ ] `cd backend && uv run pytest tests/scrapers/ tests/utils/ -v` passes

## Skills to Read

- `scrapy-playwright-scraping` - BaseOGSpider pattern, Playwright integration, per-state configs, rate limits
- `state-regulatory-sites` - Per-state site URLs, scraping strategies, data formats

## Research Files to Read

- `.claude/orchestration-og-doc-scraper/research/scraping-strategies.md` - Scrapy+Playwright architecture, anti-bot, retry patterns
- `.claude/orchestration-og-doc-scraper/research/per-state-scrapers-implementation.md` - State-by-state URLs, formats, rate limits

## Git

- Branch: `task/1.3-base-scraper-framework`
- Commit message prefix: `Task 1.3:`
