"""Colorado ECMC spider for bulk CSV downloads and COGIS database queries.

Targets both the ECMC downloadable data page (bulk CSVs) and the COGIS
database query interface. Colorado provides downloadable CSV files for
well spots, permits, and production data. COGIS adds facility details
and completions not available in bulk files.

Spider type: MixedSpider (bulk CSV primary, COGIS forms secondary).
Domains: ecmc.colorado.gov (new) and ecmc.state.co.us (legacy).
"""

import csv
import io
import logging
import zipfile

import scrapy

from og_scraper.scrapers.items import DocumentItem, WellItem
from og_scraper.scrapers.spiders.base import BaseOGSpider

logger = logging.getLogger(__name__)


class ColoradoECMCSpider(BaseOGSpider):
    """Spider for Colorado Energy & Carbon Management Commission (ECMC).

    Primary data source: Bulk CSV downloads from the ECMC downloadable
    data page covering well spots, permits, and production data.

    Secondary data source: COGIS database form queries for facility
    details and completions.
    """

    name = "co_ecmc"
    state_code = "CO"
    state_name = "Colorado"
    agency_name = "Energy & Carbon Management Commission (ECMC)"
    base_url = "https://ecmc.colorado.gov/"
    requires_playwright = False

    rate_limit_delay = 8.0
    max_concurrent = 2

    custom_settings = {
        "DOWNLOAD_DELAY": 8,
        "CONCURRENT_REQUESTS_PER_DOMAIN": 2,
        "AUTOTHROTTLE_ENABLED": True,
        "AUTOTHROTTLE_START_DELAY": 8,
        "AUTOTHROTTLE_MAX_DELAY": 60,
        "AUTOTHROTTLE_TARGET_CONCURRENCY": 1.0,
    }

    # Allowed domains for this spider (both new and legacy)
    allowed_domains = ["ecmc.colorado.gov", "ecmc.state.co.us"]

    # Bulk CSV download categories
    BULK_DOWNLOADS = {
        "well_spots": {
            "description": "Well Spots (APIs) - active/plugged wells + permits",
            "format": "csv",
        },
        "well_permits": {
            "description": "Active well permits",
            "format": "csv",
        },
        "pending_permits": {
            "description": "Pending well permits",
            "format": "csv",
        },
        "production": {
            "description": "Production data - all wells since 1999",
            "format": "csv",
        },
        "well_analytical": {
            "description": "Oil & Gas Well Analytical Data",
            "format": "csv",
        },
    }

    def start_requests(self):
        """Entry point: fetch the downloadable data page and legacy page."""
        yield scrapy.Request(
            url="https://ecmc.colorado.gov/data-maps-reports/downloadable-data-documents",
            callback=self.parse_download_page,
            errback=self.errback_handler,
        )
        yield scrapy.Request(
            url="https://ecmc.state.co.us/data2.html",
            callback=self.parse_legacy_download_page,
            errback=self.errback_handler,
        )

    def parse_download_page(self, response):
        """Parse the ECMC downloadable data page to find CSV download links."""
        for link in response.css("a[href]"):
            href = link.attrib.get("href", "")
            text = link.css("::text").get("").strip().lower()

            if href.endswith(".csv") or href.endswith(".zip"):
                report_type = self._classify_download_link(text, href)
                if report_type:
                    full_url = response.urljoin(href)
                    self.logger.info(f"Found {report_type} download: {full_url}")
                    yield scrapy.Request(
                        url=full_url,
                        callback=self.parse_csv_file,
                        errback=self.errback_handler,
                        meta={
                            "report_type": report_type,
                            "source_url": full_url,
                        },
                    )

    def parse_legacy_download_page(self, response):
        """Parse the legacy ECMC data page for additional CSV download links."""
        for link in response.css("a[href]"):
            href = link.attrib.get("href", "")
            text = link.css("::text").get("").strip().lower()

            if href.endswith(".csv") or href.endswith(".zip"):
                report_type = self._classify_download_link(text, href)
                if report_type:
                    full_url = response.urljoin(href)
                    self.logger.info(f"Found legacy {report_type} download: {full_url}")
                    yield scrapy.Request(
                        url=full_url,
                        callback=self.parse_csv_file,
                        errback=self.errback_handler,
                        meta={
                            "report_type": report_type,
                            "source_url": full_url,
                        },
                    )

    def _classify_download_link(self, text: str, href: str) -> str | None:
        """Classify a download link by its text/URL into a report type.

        Args:
            text: Anchor text (lowercased).
            href: The href attribute value.

        Returns:
            Report type string or None if unrecognized.
        """
        href_lower = href.lower()

        if "well spot" in text or "wellspot" in text or "well_spot" in href_lower:
            return "well_spots"
        elif "pending" in text and "permit" in text:
            return "pending_permits"
        elif "permit" in text or "permit" in href_lower:
            return "well_permits"
        elif "production" in text or "prod" in href_lower:
            return "production"
        elif "analytical" in text or "analytical" in href_lower:
            return "well_analytical"
        return None

    def parse_csv_file(self, response):
        """Parse a downloaded CSV file (or ZIP containing CSVs) into items.

        Dispatches to the appropriate row parser based on report_type
        stored in response.meta.
        """
        report_type = response.meta["report_type"]

        # Handle ZIP files containing CSVs
        if response.url.endswith(".zip") or self._is_zip_content(response):
            yield from self._parse_zipped_csv(response)
            return

        # Parse as plain CSV
        try:
            text = response.text
        except UnicodeDecodeError:
            text = response.body.decode("utf-8", errors="replace")

        reader = csv.DictReader(io.StringIO(text))
        row_count = 0

        for row in reader:
            try:
                items = list(self._dispatch_row(report_type, row, response))
                for item in items:
                    row_count += 1
                    yield item
            except Exception:
                self.errors += 1
                self.logger.warning(
                    f"Error parsing {report_type} row: {row!r:.200}",
                    exc_info=True,
                )

        self.logger.info(f"Parsed {row_count} items from {report_type} CSV: {response.url}")

    def _is_zip_content(self, response) -> bool:
        """Check if response body starts with ZIP magic bytes."""
        return response.body[:4] == b"PK\x03\x04"

    def _dispatch_row(self, report_type: str, row: dict, response):
        """Route a CSV row to the correct parser based on report type."""
        source_url = response.meta.get("source_url", response.url)

        if report_type == "well_spots":
            yield from self._parse_well_spot_row(row, source_url)
        elif report_type == "production":
            yield from self._parse_production_row(row, source_url)
        elif report_type in ("well_permits", "pending_permits"):
            yield from self._parse_permit_row(row, source_url, report_type)
        elif report_type == "well_analytical":
            yield from self._parse_analytical_row(row, source_url)

    def _parse_zipped_csv(self, response):
        """Extract CSVs from a ZIP response and parse each one."""
        report_type = response.meta["report_type"]
        source_url = response.meta.get("source_url", response.url)

        try:
            zip_buffer = io.BytesIO(response.body)
            with zipfile.ZipFile(zip_buffer) as zf:
                for name in zf.namelist():
                    if name.lower().endswith(".csv"):
                        self.logger.info(f"Extracting {name} from ZIP archive")
                        with zf.open(name) as csv_file:
                            text = csv_file.read().decode("utf-8", errors="replace")
                            reader = csv.DictReader(io.StringIO(text))
                            row_count = 0
                            for row in reader:
                                try:
                                    items = list(self._dispatch_row(report_type, row, response))
                                    for item in items:
                                        row_count += 1
                                        yield item
                                except Exception:
                                    self.errors += 1
                                    self.logger.warning(
                                        f"Error parsing {report_type} row from {name}: {row!r:.200}",
                                        exc_info=True,
                                    )
                            self.logger.info(f"Parsed {row_count} items from {name}")
        except zipfile.BadZipFile:
            self.errors += 1
            self.logger.error(f"Invalid ZIP file at {source_url}")

    # --- Row Parsers ---

    def _parse_well_spot_row(self, row: dict, source_url: str):
        """Parse a well spots CSV row into a WellItem."""
        api_raw = self._get_field(row, "API_Number", "api_number", "API", "Api")
        if not api_raw:
            return

        yield WellItem(
            api_number=self.normalize_api_number(api_raw),
            state_code=self.state_code,
            well_name=self._get_field(row, "Well_Name", "well_name", "WellName") or "",
            operator_name=self._get_field(row, "Operator_Name", "operator_name", "OperatorName") or "",
            county=self._get_field(row, "County", "county") or "",
            latitude=self._parse_float(self._get_field(row, "Latitude", "latitude", "Lat")),
            longitude=self._parse_float(self._get_field(row, "Longitude", "longitude", "Long", "Lon")),
            well_status=self._get_field(row, "Well_Status", "well_status", "WellStatus") or "",
            well_type=self._get_field(row, "Well_Type", "well_type", "WellType") or "",
            spud_date=None,  # Would need date parsing from string
            total_depth=self._parse_int(self._get_field(row, "Total_Depth", "total_depth", "TotalDepth")),
            field_name=self._get_field(row, "Field_Name", "field_name", "FieldName") or "",
            metadata={
                "formation": self._get_field(row, "Formation", "formation") or "",
                "elevation": self._parse_float(
                    self._get_field(row, "Elevation", "elevation")
                ),
                "spud_date_raw": self._get_field(row, "Spud_Date", "spud_date", "SpudDate") or "",
                "first_prod_date_raw": self._get_field(
                    row, "First_Prod_Date", "first_prod_date", "FirstProdDate"
                )
                or "",
            },
        )
        self.documents_found += 1

    def _parse_production_row(self, row: dict, source_url: str):
        """Parse a production CSV row into a DocumentItem."""
        api_raw = self._get_field(row, "API_Number", "api_number", "API", "Api")
        if not api_raw:
            return

        year_str = self._get_field(row, "Year", "year", "Yr") or ""
        month_str = self._get_field(row, "Month", "month", "Mo") or ""

        yield self.build_document_item(
            source_url=source_url,
            doc_type="production_report",
            api_number=api_raw,
            operator_name=self._get_field(row, "Operator_Name", "operator_name", "OperatorName") or None,
            well_name=self._get_field(row, "Well_Name", "well_name", "WellName") or None,
            raw_metadata={
                "oil_bbls": self._parse_float(self._get_field(row, "Oil_BBL", "oil_bbl", "OilBBL", "Oil")),
                "gas_mcf": self._parse_float(self._get_field(row, "Gas_MCF", "gas_mcf", "GasMCF", "Gas")),
                "water_bbls": self._parse_float(
                    self._get_field(row, "Water_BBL", "water_bbl", "WaterBBL", "Water")
                ),
                "days_produced": self._parse_int(
                    self._get_field(row, "Days_Produced", "days_produced", "DaysProduced", "Days")
                ),
                "year": year_str.strip() if year_str else "",
                "month": month_str.strip() if month_str else "",
                "formation": (self._get_field(row, "Formation", "formation") or "").strip(),
            },
        )

    def _parse_permit_row(self, row: dict, source_url: str, report_type: str = "well_permits"):
        """Parse a well permit CSV row into a WellItem."""
        api_raw = self._get_field(row, "API_Number", "api_number", "API", "Api")
        if not api_raw:
            return

        yield WellItem(
            api_number=self.normalize_api_number(api_raw),
            state_code=self.state_code,
            well_name=self._get_field(row, "Well_Name", "well_name", "WellName") or "",
            operator_name=self._get_field(row, "Operator_Name", "operator_name", "OperatorName") or "",
            county=self._get_field(row, "County", "county") or "",
            latitude=self._parse_float(self._get_field(row, "Latitude", "latitude", "Lat")),
            longitude=self._parse_float(self._get_field(row, "Longitude", "longitude", "Long", "Lon")),
            well_status="Permitted" if report_type == "well_permits" else "Pending Permit",
            well_type=self._get_field(row, "Well_Type", "well_type", "WellType") or "",
            metadata={
                "permit_type": report_type,
                "permit_date_raw": self._get_field(
                    row, "Permit_Date", "permit_date", "PermitDate", "Date_Approved"
                )
                or "",
                "proposed_depth": self._parse_int(
                    self._get_field(row, "Proposed_Depth", "proposed_depth", "ProposedDepth")
                ),
                "formation": self._get_field(row, "Formation", "formation") or "",
            },
        )
        self.documents_found += 1

    def _parse_analytical_row(self, row: dict, source_url: str):
        """Parse a well analytical data CSV row into a DocumentItem."""
        api_raw = self._get_field(row, "API_Number", "api_number", "API", "Api")
        if not api_raw:
            return

        yield self.build_document_item(
            source_url=source_url,
            doc_type="well_analytical",
            api_number=api_raw,
            operator_name=self._get_field(row, "Operator_Name", "operator_name", "OperatorName") or None,
            well_name=self._get_field(row, "Well_Name", "well_name", "WellName") or None,
            raw_metadata={k: v for k, v in row.items() if v},
        )

    # --- COGIS Form Queries (Secondary Data Source) ---

    def query_cogis_facility(self, api_number: str):
        """Query COGIS Facility Search for detailed well info.

        This is the secondary data source. Yields a request to the
        COGIS facility search form.
        """
        yield scrapy.Request(
            url="https://ecmc.state.co.us/cogisdb/Facility/FacilitySearch",
            callback=self.parse_cogis_form,
            errback=self.errback_handler,
            meta={"api_number": api_number, "query_type": "facility"},
        )

    def parse_cogis_form(self, response):
        """Submit the COGIS search form with an API number."""
        api_number = response.meta["api_number"]
        # Extract county and sequence portions from normalized API
        digits = api_number.replace("-", "")
        county_code = digits[2:5] if len(digits) >= 5 else ""
        sequence = digits[5:10] if len(digits) >= 10 else ""

        yield scrapy.FormRequest.from_response(
            response,
            formdata={
                "ApiCounty": county_code,
                "ApiSequence": sequence,
            },
            callback=self.parse_cogis_results,
            errback=self.errback_handler,
            meta=response.meta,
        )

    def parse_cogis_results(self, response):
        """Parse COGIS query results HTML table."""
        for row in response.css("table.results tr")[1:]:  # Skip header row
            cells = row.css("td::text").getall()
            if not cells:
                continue

            api_text = cells[0].strip() if cells else ""
            if not api_text:
                continue

            yield WellItem(
                api_number=self.normalize_api_number(api_text),
                state_code=self.state_code,
                well_name=cells[1].strip() if len(cells) > 1 else "",
                operator_name=cells[2].strip() if len(cells) > 2 else "",
                county=cells[3].strip() if len(cells) > 3 else "",
                well_status=cells[4].strip() if len(cells) > 4 else "",
                metadata={"source": "cogis_facility_search"},
            )
            self.documents_found += 1

    # --- Utility Methods ---

    @staticmethod
    def _get_field(row: dict, *keys: str) -> str | None:
        """Get the first matching field from a CSV row, trying multiple key names.

        Returns the stripped string value or None if no key matches or value is empty.
        """
        for key in keys:
            val = row.get(key)
            if val is not None:
                stripped = str(val).strip()
                if stripped:
                    return stripped
        return None

    @staticmethod
    def _parse_float(value: str | None) -> float | None:
        """Safely parse a string to float, returning None on failure."""
        if value is None:
            return None
        try:
            return float(value)
        except (ValueError, TypeError):
            return None

    @staticmethod
    def _parse_int(value: str | None) -> int | None:
        """Safely parse a string to int, returning None on failure."""
        if value is None:
            return None
        try:
            return int(float(value))
        except (ValueError, TypeError):
            return None
