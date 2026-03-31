"""Oklahoma OCC spider via ArcGIS RBDMS endpoint.

Returns well data with well type, legal location, and direct links
to OCC well record documents.
"""

import json
import logging

import scrapy

from og_scraper.scrapers.items import DocumentItem, WellItem
from og_scraper.scrapers.spiders.base import BaseOGSpider

logger = logging.getLogger(__name__)

ARCGIS_URL = "https://gis.occ.ok.gov/server/rest/services/Hosted/RBDMS_WELLS/FeatureServer/220/query"


class OklahomaArcGISSpider(BaseOGSpider):
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
            "outFields": "*",
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

            api_str = str(int(float(api_raw)))
            api_number = self.normalize_api_number(api_str)
            operator = attrs.get("operator", "") or ""
            well_name = attrs.get("well_name", "") or ""

            lat = attrs.get("sh_lat")
            lon = attrs.get("sh_lon")

            yield WellItem(
                state_code="OK",
                api_number=api_number,
                well_name=well_name,
                well_number=attrs.get("well_num", "") or None,
                operator_name=operator,
                county=attrs.get("county", "") or "",
                latitude=float(lat) if lat else None,
                longitude=float(lon) if lon else None,
                well_status=attrs.get("wellstatus", "") or "unknown",
                well_type=attrs.get("welltype", "") or None,
                metadata={
                    "well_type_label": attrs.get("welltype"),
                    "symbol_class": attrs.get("symbol_class"),
                    "section": attrs.get("section"),
                    "township": attrs.get("township"),
                    "range": attrs.get("range"),
                    "quarter1": attrs.get("qtr1"),
                    "quarter2": attrs.get("qtr2"),
                    "quarter3": attrs.get("qtr3"),
                    "principal_meridian": attrs.get("pm"),
                    "footage_ns": attrs.get("footage_ns"),
                    "footage_ew": attrs.get("footage_ew"),
                    "direction_ns": attrs.get("ns"),
                    "direction_ew": attrs.get("ew"),
                    "occ_docs_link": attrs.get("well_records_docs"),
                },
            )

            # Yield DocumentItem with link to OCC well records
            docs_link = attrs.get("well_records_docs")
            if docs_link:
                yield DocumentItem(
                    state_code="OK",
                    source_url=docs_link,
                    doc_type="well_permit",
                    api_number=api_number,
                    operator_name=operator,
                    well_name=well_name,
                    raw_metadata={"welltype": attrs.get("welltype")},
                )

            self.documents_found += 1
            self.total_fetched += 1

        if self.max_records and self.total_fetched >= self.max_records:
            return

        if data.get("exceededTransferLimit") or len(features) == self.batch_size:
            yield self._build_request(response.meta["offset"] + self.batch_size)
