"""Colorado COGCC/ECMC spider using working DNR ArcGIS endpoint."""

import json
import logging

import scrapy

from og_scraper.scrapers.items import WellItem
from og_scraper.scrapers.spiders.base import BaseOGSpider

logger = logging.getLogger(__name__)

ARCGIS_URL = "https://data.dnrgis.state.co.us/arcgis/rest/services/DNR_Public/OGCC_Wells/FeatureServer/0/query"


class ColoradoArcGISSpider(BaseOGSpider):
    """Spider for Colorado COGCC well data via DNR ArcGIS."""

    name = "co_arcgis"
    state_code = "CO"
    state_name = "Colorado"
    agency_name = "Energy & Carbon Management Commission (ECMC)"
    base_url = "https://data.dnrgis.state.co.us"

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
            "outFields": "API,Operator,Well_Name,Well_Num,Latitude,Longitude,Facil_Stat,Facil_Type,Field_Name,Spud_Date,Max_MD,Max_TVD,API_County",
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

            api_raw = attrs.get("API")
            if not api_raw:
                continue

            lat = attrs.get("Latitude")
            lon = attrs.get("Longitude")

            yield WellItem(
                state_code="CO",
                api_number=self.normalize_api_number(str(api_raw)),
                well_name=attrs.get("Well_Name", "") or "",
                well_number=attrs.get("Well_Num", "") or None,
                operator_name=attrs.get("Operator", "") or "",
                county=attrs.get("API_County", "") or "",
                field_name=attrs.get("Field_Name", "") or "",
                latitude=float(lat) if lat else None,
                longitude=float(lon) if lon else None,
                well_status=attrs.get("Facil_Stat", "") or "unknown",
                well_type=attrs.get("Facil_Type", "") or None,
                total_depth=int(attrs["Max_MD"]) if attrs.get("Max_MD") else None,
                metadata={k: v for k, v in attrs.items() if v is not None},
            )
            self.documents_found += 1
            self.total_fetched += 1

        if self.max_records and self.total_fetched >= self.max_records:
            return

        if data.get("exceededTransferLimit") or len(features) == self.batch_size:
            yield self._build_request(response.meta["offset"] + self.batch_size)
