"""North Dakota Industrial Commission (NDIC) spider.

ND provides limited free data — monthly production PDFs and daily activity.
Full data requires a paid subscription ($100-500/yr). This spider implements
the free tier with graceful degradation.
"""

import csv
import io
import logging
from datetime import datetime

import scrapy

from og_scraper.scrapers.items import DocumentItem, WellItem
from og_scraper.scrapers.spiders.base import BaseOGSpider

logger = logging.getLogger(__name__)


class NorthDakotaNDICSpider(BaseOGSpider):
    """Spider for North Dakota NDIC — free tier data only."""

    name = "nd_ndic"
    state_code = "ND"
    state_name = "North Dakota"
    agency_name = "North Dakota Industrial Commission"
    base_url = "https://www.dmr.nd.gov/oilgas"

    custom_settings = {
        "DOWNLOAD_DELAY": 3,
        "CONCURRENT_REQUESTS": 2,
        "AUTOTHROTTLE_ENABLED": True,
    }

    FREE_ENDPOINTS = [
        {"name": "daily_activity", "url": "https://www.dmr.nd.gov/oilgas/dailyactivity.asp", "doc_type": "well_permit"},
        {"name": "monthly_production", "url": "https://www.dmr.nd.gov/oilgas/mpr/", "doc_type": "production_report"},
    ]

    def __init__(self, *args, limit=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.limit = int(limit) if limit else None

    def start_requests(self):
        for endpoint in self.FREE_ENDPOINTS:
            yield scrapy.Request(
                url=endpoint["url"],
                callback=self.parse_page,
                meta={"endpoint": endpoint},
                dont_filter=True,
            )

    def parse_page(self, response):
        endpoint = response.meta["endpoint"]
        if endpoint["name"] == "daily_activity":
            yield from self._parse_daily_activity(response)
        else:
            yield from self._parse_production_index(response)

    def _parse_daily_activity(self, response):
        """Parse daily activity HTML page for well permit data."""
        rows = response.css("table tr")
        count = 0
        for row in rows[1:]:  # skip header
            cells = row.css("td::text").getall()
            if len(cells) < 4:
                continue
            if self.limit and count >= self.limit:
                break

            yield DocumentItem(
                state_code="ND",
                doc_type="well_permit",
                source_url=response.url,
                raw_metadata={"cells": [c.strip() for c in cells]},
                scraped_at=datetime.utcnow(),
            )
            count += 1
            self.documents_found += 1

    def _parse_production_index(self, response):
        """Parse monthly production report index page."""
        links = response.css("a[href$='.pdf']::attr(href), a[href$='.csv']::attr(href)").getall()
        count = 0
        for link in links:
            if self.limit and count >= self.limit:
                break
            full_url = response.urljoin(link)
            yield DocumentItem(
                state_code="ND",
                doc_type="production_report",
                source_url=full_url,
                raw_metadata={"filename": link.split("/")[-1]},
                scraped_at=datetime.utcnow(),
            )
            count += 1
            self.documents_found += 1
