"""Alaska Oil and Gas Conservation Commission (AOGCC) spider.

AK provides data through ArcGIS Open Data portal and Data Miner exports.
Smaller dataset — simpler spider.
"""

import json
import logging
from datetime import datetime

import scrapy

from og_scraper.scrapers.items import WellItem
from og_scraper.scrapers.spiders.base import BaseOGSpider

logger = logging.getLogger(__name__)

ARCGIS_URL = "https://services.arcgis.com/AOGCC/arcgis/rest/services/Wells/FeatureServer/0/query"


class AlaskaAOGCCSpider(BaseOGSpider):
    """Spider for Alaska AOGCC well data via ArcGIS."""

    name = "ak_aogcc"
    state_code = "AK"
    state_name = "Alaska"
    agency_name = "Alaska Oil and Gas Conservation Commission"
    base_url = "https://www.commerce.alaska.gov/web/aogcc"

    custom_settings = {
        "DOWNLOAD_DELAY": 2,
        "CONCURRENT_REQUESTS": 2,
        "AUTOTHROTTLE_ENABLED": True,
    }

    def __init__(self, *args, batch_size=1000, max_records=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.batch_size = int(batch_size)
        self.max_records = int(max_records) if max_records else None
        self.total_fetched = 0

    def start_requests(self):
        yield self._build_request(0)

    def _build_request(self, offset):
        params = {
            "where": "1=1",
            "outFields": "*",
            "returnGeometry": "true",
            "resultOffset": str(offset),
            "resultRecordCount": str(self.batch_size),
            "f": "json",
        }
        url = f"{ARCGIS_URL}?{'&'.join(f'{k}={v}' for k, v in params.items())}"
        return scrapy.Request(url=url, callback=self.parse_results, meta={"offset": offset})

    def parse_results(self, response):
        try:
            data = json.loads(response.text)
        except json.JSONDecodeError:
            logger.error("Failed to parse ArcGIS JSON")
            return

        features = data.get("features", [])
        if not features:
            return

        for feature in features:
            attrs = feature.get("attributes", {})
            geom = feature.get("geometry", {})

            api_raw = attrs.get("API_NUMBER") or attrs.get("API") or attrs.get("WELL_NO") or ""
            if not api_raw:
                continue

            yield WellItem(
                state_code="AK",
                api_number=self.normalize_api_number(str(api_raw)),
                well_name=attrs.get("WELL_NAME", "") or "",
                operator_name=attrs.get("OPERATOR", "") or "",
                county=attrs.get("AREA", "") or "",  # AK uses areas, not counties
                latitude=geom.get("y"),
                longitude=geom.get("x"),
                well_status=attrs.get("WELL_STATUS", "") or "unknown",
                
                metadata={k: v for k, v in attrs.items() if v is not None},
            )
            self.documents_found += 1
            self.total_fetched += 1

        if self.max_records and self.total_fetched >= self.max_records:
            return

        if data.get("exceededTransferLimit") or len(features) == self.batch_size:
            yield self._build_request(response.meta["offset"] + self.batch_size)
