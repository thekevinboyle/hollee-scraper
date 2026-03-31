"""Oklahoma OCC spider using working ArcGIS RBDMS endpoint."""

import json
import logging

import scrapy

from og_scraper.scrapers.items import WellItem
from og_scraper.scrapers.spiders.base import BaseOGSpider

logger = logging.getLogger(__name__)

ARCGIS_URL = "https://gis.occ.ok.gov/server/rest/services/Hosted/RBDMS_WELLS/FeatureServer/220/query"


class OklahomaArcGISSpider(BaseOGSpider):
    """Spider for Oklahoma OCC well data via ArcGIS RBDMS."""

    name = "ok_arcgis"
    state_code = "OK"
    state_name = "Oklahoma"
    agency_name = "Corporation Commission (OCC)"
    base_url = "https://gis.occ.ok.gov"

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
            "outFields": "api,well_name,operator,sh_lat,sh_lon,wellstatus,welltype,county",
            "returnGeometry": "false",
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

            api_raw = attrs.get("api")
            if not api_raw:
                continue

            # OK API numbers come as doubles — convert to int string
            api_str = str(int(float(api_raw)))

            lat = attrs.get("sh_lat")
            lon = attrs.get("sh_lon")

            yield WellItem(
                state_code="OK",
                api_number=self.normalize_api_number(api_str),
                well_name=attrs.get("well_name", "") or "",
                operator_name=attrs.get("operator", "") or "",
                county=attrs.get("county", "") or "",
                latitude=float(lat) if lat else None,
                longitude=float(lon) if lon else None,
                well_status=attrs.get("wellstatus", "") or "unknown",
                well_type=attrs.get("welltype", "") or None,
                metadata={k: v for k, v in attrs.items() if v is not None},
            )
            self.documents_found += 1
            self.total_fetched += 1

        if self.max_records and self.total_fetched >= self.max_records:
            return

        if data.get("exceededTransferLimit") or len(features) == self.batch_size:
            yield self._build_request(response.meta["offset"] + self.batch_size)
