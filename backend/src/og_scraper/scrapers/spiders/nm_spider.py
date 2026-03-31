"""New Mexico OCD/ONGARD spider using ArcGIS API endpoints.

NM Oil Conservation Division provides well data through ArcGIS MapServer
endpoints with JSON pagination support.
"""

import json
import logging
from datetime import datetime

import scrapy

from og_scraper.scrapers.items import WellItem
from og_scraper.scrapers.spiders.base import BaseOGSpider

logger = logging.getLogger(__name__)

ARCGIS_BASE = "https://gis.emnrd.nm.gov/arcgis/rest/services/OCD/Wells/MapServer/0/query"


class NewMexicoOCDSpider(BaseOGSpider):
    """Spider for New Mexico OCD well data via ArcGIS API."""

    name = "nm_ocd"
    state_code = "NM"
    state_name = "New Mexico"
    agency_name = "Oil Conservation Division"
    base_url = "https://wwwapps.emnrd.nm.gov/ocd/ocdpermitting"

    custom_settings = {
        "DOWNLOAD_DELAY": 2,
        "CONCURRENT_REQUESTS": 3,
        "AUTOTHROTTLE_ENABLED": True,
    }

    def __init__(self, *args, batch_size=1000, max_records=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.batch_size = int(batch_size)
        self.max_records = int(max_records) if max_records else None
        self.offset = 0
        self.total_fetched = 0

    def start_requests(self):
        yield self._build_query_request(0)

    def _build_query_request(self, offset):
        params = {
            "where": "1=1",
            "outFields": "*",
            "returnGeometry": "true",
            "resultOffset": str(offset),
            "resultRecordCount": str(self.batch_size),
            "f": "json",
        }
        url = f"{ARCGIS_BASE}?{'&'.join(f'{k}={v}' for k, v in params.items())}"
        return scrapy.Request(url=url, callback=self.parse_results, meta={"offset": offset})

    def parse_results(self, response):
        try:
            data = json.loads(response.text)
        except json.JSONDecodeError:
            logger.error("Failed to parse ArcGIS response as JSON")
            return

        features = data.get("features", [])
        if not features:
            return

        for feature in features:
            attrs = feature.get("attributes", {})
            geom = feature.get("geometry", {})

            api_raw = attrs.get("API_NUMBER") or attrs.get("api_number") or ""
            if not api_raw:
                continue

            api_number = self.normalize_api_number(str(api_raw))

            yield WellItem(
                state_code="NM",
                api_number=api_number,
                well_name=attrs.get("WELL_NAME", "") or "",
                operator_name=attrs.get("OPERATOR_NAME", "") or attrs.get("OPERATOR", "") or "",
                county=attrs.get("COUNTY", "") or "",
                latitude=geom.get("y"),
                longitude=geom.get("x"),
                well_status=attrs.get("WELL_STATUS", "") or "unknown",
                
                metadata={k: v for k, v in attrs.items() if v is not None},
            )
            self.documents_found += 1
            self.total_fetched += 1

        if self.max_records and self.total_fetched >= self.max_records:
            return

        exceeded_transfer = data.get("exceededTransferLimit", False)
        if exceeded_transfer or len(features) == self.batch_size:
            next_offset = response.meta["offset"] + self.batch_size
            yield self._build_query_request(next_offset)
