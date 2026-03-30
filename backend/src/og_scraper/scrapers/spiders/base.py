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
