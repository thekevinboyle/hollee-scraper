"""Louisiana SONRIS spider — hardest state to scrape.

LA Department of Natural Resources SONRIS system has an Oracle backend
with session-based navigation. This spider uses Playwright for form
submission with circuit breaker pattern for timeout handling.
"""

import json
import logging
from datetime import datetime

import scrapy

from og_scraper.scrapers.items import DocumentItem, WellItem
from og_scraper.scrapers.spiders.base import BaseOGSpider

logger = logging.getLogger(__name__)

SONRIS_SEARCH = "http://sonlite.dnr.state.la.us/sundown/cart_prod/cart_con_wellinfo1"
DOTD_ARCGIS = "https://services5.arcgis.com/O5HPYxnKJKMPHYDo/arcgis/rest/services/Wells/FeatureServer/0/query"


class LouisianaSONRISSpider(BaseOGSpider):
    """Spider for Louisiana SONRIS — uses ArcGIS for GIS data, SONRIS for documents."""

    name = "la_sonris"
    state_code = "LA"
    state_name = "Louisiana"
    agency_name = "Louisiana Department of Natural Resources"
    base_url = "http://sonlite.dnr.state.la.us"

    custom_settings = {
        "DOWNLOAD_DELAY": 5,
        "CONCURRENT_REQUESTS": 1,
        "AUTOTHROTTLE_ENABLED": True,
        "DOWNLOAD_TIMEOUT": 120,
    }

    def __init__(self, *args, batch_size=1000, max_records=None, use_arcgis=True, **kwargs):
        super().__init__(*args, **kwargs)
        self.batch_size = int(batch_size)
        self.max_records = int(max_records) if max_records else None
        self.use_arcgis = use_arcgis in (True, "true", "True", "1")
        self.total_fetched = 0
        self._failures = 0
        self._circuit_open = False

    def start_requests(self):
        if self.use_arcgis:
            yield self._build_arcgis_request(0)
        else:
            logger.warning("SONRIS Playwright mode not yet implemented — use ArcGIS mode")

    def _build_arcgis_request(self, offset):
        params = {
            "where": "1=1",
            "outFields": "*",
            "returnGeometry": "true",
            "resultOffset": str(offset),
            "resultRecordCount": str(self.batch_size),
            "f": "json",
        }
        url = f"{DOTD_ARCGIS}?{'&'.join(f'{k}={v}' for k, v in params.items())}"
        return scrapy.Request(
            url=url,
            callback=self.parse_arcgis_results,
            meta={"offset": offset},
            errback=self._handle_error,
        )

    def _handle_error(self, failure):
        self._failures += 1
        if self._failures >= 3:
            self._circuit_open = True
            logger.error("Circuit breaker OPEN — 3 consecutive failures on LA SONRIS")

    def parse_arcgis_results(self, response):
        if self._circuit_open:
            logger.warning("Circuit breaker open — skipping request")
            return

        try:
            data = json.loads(response.text)
        except json.JSONDecodeError:
            self._failures += 1
            logger.error("Failed to parse SONRIS ArcGIS JSON")
            return

        self._failures = 0  # reset on success
        features = data.get("features", [])
        if not features:
            return

        for feature in features:
            attrs = feature.get("attributes", {})
            geom = feature.get("geometry", {})

            serial = attrs.get("WELL_SERIAL_NUM") or attrs.get("Serial_Num") or ""
            api_raw = attrs.get("API_NUMBER") or attrs.get("API_Num") or ""

            if not serial and not api_raw:
                continue

            api_number = self.normalize_api_number(str(api_raw)) if api_raw else ""

            yield WellItem(
                state_code="LA",
                api_number=api_number,
                well_name=attrs.get("WELL_NAME", "") or "",
                operator_name=attrs.get("OPERATOR", "") or "",
                county=attrs.get("PARISH", "") or "",  # LA uses parishes
                latitude=geom.get("y"),
                longitude=geom.get("x"),
                well_status=attrs.get("WELL_STATUS", "") or "unknown",
                
                metadata={
                    "serial_number": str(serial),
                    **{k: v for k, v in attrs.items() if v is not None},
                },
            )
            self.documents_found += 1
            self.total_fetched += 1

        if self.max_records and self.total_fetched >= self.max_records:
            return

        if data.get("exceededTransferLimit") or len(features) == self.batch_size:
            yield self._build_arcgis_request(response.meta["offset"] + self.batch_size)
