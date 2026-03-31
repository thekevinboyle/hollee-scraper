"""California CalGEM WellSTAR spider via ArcGIS API.

CA Geologic Energy Management Division provides well data through the
WellSTAR system with ArcGIS endpoints. Coordinates in EPSG:3857 need
conversion to WGS84 (EPSG:4326).
"""

import json
import logging
from datetime import datetime

import scrapy

from og_scraper.scrapers.items import WellItem
from og_scraper.scrapers.spiders.base import BaseOGSpider

logger = logging.getLogger(__name__)

WELLSTAR_URL = "https://gis.conservation.ca.gov/server/rest/services/WellSTAR/Wells/MapServer/0/query"


class CaliforniaCalGEMSpider(BaseOGSpider):
    """Spider for California CalGEM WellSTAR data."""

    name = "ca_calgem"
    state_code = "CA"
    state_name = "California"
    agency_name = "California Geologic Energy Management Division"
    base_url = "https://www.conservation.ca.gov/calgem"

    custom_settings = {
        "DOWNLOAD_DELAY": 2,
        "CONCURRENT_REQUESTS": 3,
        "AUTOTHROTTLE_ENABLED": True,
    }

    def __init__(self, *args, batch_size=5000, max_records=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.batch_size = int(batch_size)
        self.max_records = int(max_records) if max_records else None
        self.total_fetched = 0

    @staticmethod
    def _convert_3857_to_4326(x, y):
        """Convert EPSG:3857 (Web Mercator) to EPSG:4326 (WGS84)."""
        try:
            from pyproj import Transformer
            transformer = Transformer.from_crs("EPSG:3857", "EPSG:4326", always_xy=True)
            lon, lat = transformer.transform(x, y)
            return lat, lon
        except ImportError:
            import math
            lon = x * 180.0 / 20037508.34
            lat = math.atan(math.exp(y * math.pi / 20037508.34)) * 360.0 / math.pi - 90.0
            return lat, lon

    def start_requests(self):
        yield self._build_request(0)

    def _build_request(self, offset):
        params = {
            "where": "1=1",
            "outFields": "*",
            "returnGeometry": "true",
            "outSR": "3857",
            "resultOffset": str(offset),
            "resultRecordCount": str(self.batch_size),
            "f": "json",
        }
        url = f"{WELLSTAR_URL}?{'&'.join(f'{k}={v}' for k, v in params.items())}"
        return scrapy.Request(url=url, callback=self.parse_results, meta={"offset": offset})

    def parse_results(self, response):
        try:
            data = json.loads(response.text)
        except json.JSONDecodeError:
            logger.error("Failed to parse WellSTAR JSON")
            return

        features = data.get("features", [])
        if not features:
            return

        for feature in features:
            attrs = feature.get("attributes", {})
            geom = feature.get("geometry", {})

            api_raw = attrs.get("APINumber") or attrs.get("API") or ""
            if not api_raw:
                continue

            lat, lon = None, None
            if geom.get("x") and geom.get("y"):
                lat, lon = self._convert_3857_to_4326(geom["x"], geom["y"])

            yield WellItem(
                state_code="CA",
                api_number=self.normalize_api_number(str(api_raw)),
                well_name=attrs.get("WellDesignation", "") or attrs.get("WellName", "") or "",
                operator_name=attrs.get("OperatorName", "") or attrs.get("Operator", "") or "",
                county=attrs.get("CountyName", "") or "",
                field_name=attrs.get("Place", "") or "",
                lease_name=attrs.get("LeaseName", "") or "",
                latitude=lat,
                longitude=lon,
                well_status=attrs.get("WellStatus", "") or "unknown",
                well_type=attrs.get("WellTypeLabel", "") or attrs.get("WellType", "") or None,
                metadata={
                    "well_type": attrs.get("WellType"),
                    "well_type_label": attrs.get("WellTypeLabel"),
                    "well_symbol": attrs.get("WellSymbol"),
                    "well_designation": attrs.get("WellDesignation"),
                    "well_number": attrs.get("WellNumber"),
                    "operator_code": attrs.get("OperatorCode"),
                    "lease_name": attrs.get("LeaseName"),
                    "district": attrs.get("District"),
                    "section": attrs.get("Section"),
                    "township": attrs.get("Township"),
                    "range": attrs.get("Range"),
                    "base_meridian": attrs.get("BaseMeridian"),
                    "gis_source": attrs.get("GISSource"),
                    "spud_date": attrs.get("SpudDate"),
                    "is_directionally_drilled": attrs.get("isDirectionallyDrilled"),
                    "is_confidential": attrs.get("isConfidential"),
                    "in_hpz": attrs.get("inHPZ"),
                },
            )
            self.documents_found += 1
            self.total_fetched += 1

        if self.max_records and self.total_fetched >= self.max_records:
            return

        if data.get("exceededTransferLimit") or len(features) == self.batch_size:
            yield self._build_request(response.meta["offset"] + self.batch_size)
