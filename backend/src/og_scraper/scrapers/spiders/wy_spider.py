"""Wyoming WOGCC spider via WYGISC ArcGIS endpoint.

Returns rich data including cumulative production (oil/gas/water),
total depth, formations, spud dates, and direct WOGCC record links.
"""

import json
import logging

import scrapy

from og_scraper.scrapers.items import DocumentItem, WellItem
from og_scraper.scrapers.spiders.base import BaseOGSpider

logger = logging.getLogger(__name__)

ARCGIS_URL = "https://services.wygisc.org/HostGIS/rest/services/GeoHub/WOGCCActiveWells/MapServer/0/query"


class WyomingWOGCCSpider(BaseOGSpider):
    name = "wy_wogcc"
    state_code = "WY"
    state_name = "Wyoming"
    agency_name = "Wyoming Oil and Gas Conservation Commission"
    base_url = "https://services.wygisc.org"

    custom_settings = {
        "DOWNLOAD_DELAY": 2,
        "CONCURRENT_REQUESTS": 3,
        "AUTOTHROTTLE_ENABLED": True,
    }

    def __init__(self, *args, batch_size=1000, max_records=None, limit=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.batch_size = int(batch_size)
        self.max_records = int(max_records or limit or 0) or None
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

            api_raw = attrs.get("API_NUMBER") or attrs.get("API") or ""
            if not api_raw:
                continue

            api_number = self.normalize_api_number(str(api_raw))
            operator = attrs.get("COMPANY", "") or ""
            well_name = attrs.get("UNIT_LEASE", "") or attrs.get("LEASE_NAME", "") or ""

            # Parse spud date from YYYYMM format
            spud_raw = attrs.get("SPUD")
            spud_date = None
            if spud_raw and str(spud_raw).isdigit() and len(str(spud_raw)) >= 6:
                try:
                    s = str(spud_raw)
                    from datetime import date
                    spud_date = date(int(s[:4]), int(s[4:6]), 1)
                except (ValueError, IndexError):
                    pass

            yield WellItem(
                state_code="WY",
                api_number=api_number,
                well_name=well_name,
                operator_name=operator,
                county=attrs.get("COUNTY", "") or "",
                field_name=attrs.get("FIELD_NAME", "") or "",
                lease_name=attrs.get("UNIT_LEASE", "") or "",
                latitude=attrs.get("LATITUDE") or geom.get("y"),
                longitude=attrs.get("LONGITUDE") or geom.get("x"),
                well_status=attrs.get("STATUS", "") or "unknown",
                well_type=attrs.get("WELL_CLASS", "") or None,
                total_depth=int(attrs["TD"]) if attrs.get("TD") else None,
                spud_date=spud_date,
                metadata={
                    "cumulative_oil_bbl": attrs.get("CUMOIL"),
                    "cumulative_gas_mcf": attrs.get("CUMGAS"),
                    "cumulative_water_bbl": attrs.get("CUMWATER"),
                    "bottom_formation": attrs.get("BOT_FORM"),
                    "permit_number": attrs.get("PERMIT"),
                    "well_number": attrs.get("WN"),
                    "ground_elevation": attrs.get("MEAS_FROM"),
                    "section": attrs.get("SEC"),
                    "township": f"{attrs.get('TWP', '')}{attrs.get('T_DIR', '')}",
                    "range": f"{attrs.get('RGE', '')}{attrs.get('R_DIR', '')}",
                    "wogcc_link": attrs.get("WOGCC_LINK"),
                },
            )

            # Yield a DocumentItem linking to WOGCC record
            wogcc_link = attrs.get("WOGCC_LINK")
            if wogcc_link:
                yield DocumentItem(
                    state_code="WY",
                    source_url=wogcc_link,
                    doc_type="well_permit",
                    api_number=api_number,
                    operator_name=operator,
                    well_name=well_name,
                    raw_metadata={"wogcc_api": attrs.get("APINO")},
                )

            self.documents_found += 1
            self.total_fetched += 1

        if self.max_records and self.total_fetched >= self.max_records:
            return

        if data.get("exceededTransferLimit") or len(features) == self.batch_size:
            yield self._build_request(response.meta["offset"] + self.batch_size)
