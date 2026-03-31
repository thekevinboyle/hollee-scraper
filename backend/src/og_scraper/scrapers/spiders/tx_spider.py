"""Texas Railroad Commission (RRC) spider for bulk CSV/data downloads.

TX RRC provides monthly production data queries (PDQ) and bulk data files.
This spider targets the CSV dumps available from the RRC data portal.
"""

import csv
import io
import logging
from datetime import datetime

import scrapy

from og_scraper.scrapers.items import DocumentItem, WellItem
from og_scraper.scrapers.spiders.base import BaseOGSpider

logger = logging.getLogger(__name__)

BULK_DATASETS = [
    {"name": "wells", "url": "https://mft.rrc.texas.gov/link/dbf4a6d5-2430-4e2c-b46f-8a1fb7a1b03c", "format": "csv", "doc_type": "well_permit"},
    {"name": "production", "url": "https://mft.rrc.texas.gov/link/ba3c1e0c-b8a7-4f3d-abc3-a7f8de1c04b7", "format": "csv", "doc_type": "production_report"},
    {"name": "completions", "url": "https://mft.rrc.texas.gov/link/c5e2d7f1-9b4a-4d8e-a6c3-2f1e8b7d9a0c", "format": "csv", "doc_type": "completion_report"},
]


class TexasRRCSpider(BaseOGSpider):
    """Spider for Texas Railroad Commission bulk data downloads."""

    name = "tx_rrc"
    state_code = "TX"
    state_name = "Texas"
    agency_name = "Railroad Commission of Texas"
    base_url = "https://www.rrc.texas.gov"

    custom_settings = {
        "DOWNLOAD_DELAY": 3,
        "CONCURRENT_REQUESTS": 2,
        "AUTOTHROTTLE_ENABLED": True,
    }

    def __init__(self, *args, datasets=None, limit=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.datasets = datasets.split(",") if datasets else [d["name"] for d in BULK_DATASETS]
        self.limit = int(limit) if limit else None

    def start_requests(self):
        for dataset in BULK_DATASETS:
            if dataset["name"] in self.datasets:
                yield scrapy.Request(
                    url=dataset["url"],
                    callback=self.parse_csv,
                    meta={"dataset": dataset},
                    dont_filter=True,
                )

    def parse_csv(self, response):
        dataset = response.meta["dataset"]
        text = response.text
        reader = csv.DictReader(io.StringIO(text))
        count = 0

        for row in reader:
            if self.limit and count >= self.limit:
                break

            api_raw = self._get_field(row, ["API_NO", "API_NUMBER", "API", "WELL_NO"])
            if not api_raw:
                continue

            api_number = self.normalize_api_number(str(api_raw))

            if dataset["name"] == "wells":
                yield WellItem(
                    state_code="TX",
                    api_number=api_number,
                    well_name=self._get_field(row, ["WELL_NAME", "LEASE_NAME"]) or "",
                    operator_name=self._get_field(row, ["OPERATOR_NAME", "OPERATOR"]) or "",
                    county=self._get_field(row, ["COUNTY_NAME", "COUNTY"]) or "",
                    latitude=self._parse_float(self._get_field(row, ["LATITUDE", "LAT"])),
                    longitude=self._parse_float(self._get_field(row, ["LONGITUDE", "LONG", "LON"])),
                    well_status=self._get_field(row, ["WELL_STATUS", "STATUS"]) or "unknown",
                    
                )
            else:
                yield DocumentItem(
                    state_code="TX",
                    source_url=response.url,
                    api_number=api_number,
                    doc_type=dataset["doc_type"],
                    operator_name=self._get_field(row, ["OPERATOR_NAME", "OPERATOR"]) or "",
                    well_name=self._get_field(row, ["WELL_NAME", "LEASE_NAME"]) or "",
                    raw_metadata={k: v for k, v in row.items() if v},
                    scraped_at=datetime.utcnow(),
                )
            count += 1
            self.documents_found += 1

    @staticmethod
    def _get_field(row, candidates):
        for key in candidates:
            val = row.get(key, "").strip()
            if val:
                return val
        for key in row:
            for candidate in candidates:
                if candidate.lower() in key.lower():
                    val = row[key].strip()
                    if val:
                        return val
        return None

    @staticmethod
    def _parse_float(val):
        if not val:
            return None
        try:
            return float(str(val).replace(",", ""))
        except (ValueError, TypeError):
            return None
