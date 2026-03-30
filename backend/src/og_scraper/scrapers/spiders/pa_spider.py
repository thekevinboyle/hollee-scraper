"""Pennsylvania DEP GreenPort spider for bulk CSV data downloads.

PA DEP provides all oil and gas data as on-demand CSV exports from the
GreenPort Report Extracts portal. This spider downloads CSV files for
production, well inventory, compliance, plugging, and waste reports,
parses them, and yields structured DocumentItem/WellItem objects for
the document processing pipeline.

GreenPort: https://greenport.pa.gov/ReportExtracts/OG/Index
Data Dictionary: https://files.dep.state.pa.us/oilgas/bogm/bogmportalfiles/
    oilgasreports/HelpDocs/SSRS_Report_Data_Dictionary/
    DEP_Oil_and_GAS_Reports_Data_Dictionary.pdf
"""

import csv
import io
import logging
from datetime import date, datetime

import scrapy

from og_scraper.scrapers.items import WellItem
from og_scraper.scrapers.spiders.base import BaseOGSpider

logger = logging.getLogger(__name__)


class PennsylvaniaDEPSpider(BaseOGSpider):
    """Spider for Pennsylvania DEP GreenPort CSV report exports.

    This is a BulkDownloadSpider -- no Playwright needed. GreenPort
    report pages are ASP.NET server-rendered. The spider fetches each
    report page, extracts the form action and hidden fields (ViewState),
    then submits the form to trigger CSV generation and download.
    """

    name = "pa_dep"
    state_code = "PA"
    state_name = "Pennsylvania"
    agency_name = "Dept of Environmental Protection (DEP)"
    base_url = "https://greenport.pa.gov/ReportExtracts/OG/Index"
    requires_playwright = False

    custom_settings = {
        "DOWNLOAD_DELAY": 3,
        "CONCURRENT_REQUESTS_PER_DOMAIN": 4,
        "AUTOTHROTTLE_ENABLED": True,
        "AUTOTHROTTLE_START_DELAY": 3,
        "AUTOTHROTTLE_MAX_DELAY": 30,
        "AUTOTHROTTLE_TARGET_CONCURRENCY": 2.0,
    }

    # GreenPort report endpoints
    REPORT_ENDPOINTS = {
        "well_inventory": "OilGasWellInventoryReport",
        "production": "OilGasWellProdReport",
        "compliance": "OilComplianceReport",
        "plugged_wells": "OGPluggedWellsReport",
        "waste": "OilGasWellWasteReport",
        "production_not_submitted": "WellNotSubReport",
    }

    GREENPORT_BASE = "https://greenport.pa.gov/ReportExtracts/OG"

    def __init__(self, *args, report_types: str | None = None, limit: int | None = None, **kwargs):
        """Initialize the PA spider.

        Args:
            report_types: Comma-separated list of report types to scrape.
                Defaults to all. Valid: well_inventory, production, compliance,
                plugged_wells, waste, production_not_submitted.
            limit: Maximum number of CSV rows to process per report (for testing).
        """
        super().__init__(*args, **kwargs)
        self.limit = int(limit) if limit else None
        if report_types:
            self.active_reports = [r.strip() for r in report_types.split(",")]
        else:
            self.active_reports = list(self.REPORT_ENDPOINTS.keys())

    def start_requests(self):
        """Generate requests for each configured report type.

        Each request fetches the report page HTML, which contains the
        ASP.NET form with ViewState and export controls.
        """
        for report_type in self.active_reports:
            endpoint = self.REPORT_ENDPOINTS.get(report_type)
            if not endpoint:
                self.logger.warning(f"Unknown report type: {report_type}")
                continue
            url = f"{self.GREENPORT_BASE}/{endpoint}"
            yield scrapy.Request(
                url=url,
                callback=self.parse_report_page,
                errback=self.errback_handler,
                meta={"report_type": report_type},
                dont_filter=True,
            )

    def parse_report_page(self, response):
        """Parse the GreenPort report page and submit the export form.

        GreenPort report pages use ASP.NET with ViewState. This method
        extracts hidden form fields and submits the form to trigger a
        CSV export. If the response is already CSV data (Content-Type
        text/csv), it is parsed directly.
        """
        report_type = response.meta["report_type"]
        content_type = response.headers.get("Content-Type", b"").decode("utf-8", errors="replace")

        # If we already got CSV data back (direct download), parse it
        if "text/csv" in content_type or "application/csv" in content_type:
            yield from self.parse_csv_response(response)
            return

        # Check if the response body looks like CSV (starts with a header row)
        text = response.text.strip()
        if text and not text.startswith("<!") and not text.startswith("<"):
            # Likely CSV data returned directly
            yield from self.parse_csv_response(response)
            return

        # Extract ASP.NET hidden form fields
        viewstate = response.css("input#__VIEWSTATE::attr(value)").get("")
        viewstate_gen = response.css("input#__VIEWSTATEGENERATOR::attr(value)").get("")
        event_validation = response.css("input#__EVENTVALIDATION::attr(value)").get("")

        # Build form data for the export submission
        formdata = {}
        if viewstate:
            formdata["__VIEWSTATE"] = viewstate
        if viewstate_gen:
            formdata["__VIEWSTATEGENERATOR"] = viewstate_gen
        if event_validation:
            formdata["__EVENTVALIDATION"] = event_validation

        # Look for export/download button
        export_btn = response.css(
            'input[type="submit"][value*="Export"]::attr(name), '
            'input[type="submit"][value*="Download"]::attr(name), '
            'input[type="submit"][value*="CSV"]::attr(name), '
            'input[type="submit"][value*="Generate"]::attr(name)'
        ).get()

        if export_btn:
            formdata[export_btn] = "Export"

        self.logger.info(
            f"[{self.state_code}] Submitting export form for {report_type} "
            f"(has_viewstate={bool(viewstate)}, has_export_btn={bool(export_btn)})"
        )

        yield scrapy.FormRequest.from_response(
            response,
            formdata=formdata,
            callback=self.parse_csv_response,
            errback=self.errback_handler,
            meta={"report_type": report_type},
            dont_filter=True,
        )

    def parse_csv_response(self, response):
        """Parse a CSV response and yield DocumentItem or WellItem objects.

        Dispatches to the appropriate parser based on the report_type
        stored in response.meta.
        """
        report_type = response.meta.get("report_type", "unknown")
        text = response.text

        if not text or not text.strip():
            self.logger.warning(f"[{self.state_code}] Empty CSV response for {report_type}")
            return

        try:
            reader = csv.DictReader(io.StringIO(text))
        except Exception as e:
            self.logger.error(f"[{self.state_code}] Failed to parse CSV for {report_type}: {e}")
            return

        row_count = 0
        error_count = 0

        for row in reader:
            if self.limit and row_count >= self.limit:
                break
            try:
                items = list(self._parse_row(report_type, row, response.url))
                for item in items:
                    yield item
                    row_count += 1
            except Exception as e:
                error_count += 1
                self.logger.error(
                    f"[{self.state_code}] Error parsing {report_type} row: {e} "
                    f"(row data: {dict(row) if row else 'None'})"
                )
                if error_count > 100:
                    self.logger.error(
                        f"[{self.state_code}] Too many errors ({error_count}) parsing {report_type}, stopping"
                    )
                    return

        self.logger.info(f"[{self.state_code}] Parsed {row_count} rows from {report_type} ({error_count} errors)")

    def _parse_row(self, report_type: str, row: dict, source_url: str):
        """Parse a single CSV row based on report type.

        Yields DocumentItem or WellItem depending on the report type.
        """
        if report_type == "well_inventory":
            yield from self._parse_well_inventory_row(row, source_url)
        elif report_type == "production":
            yield from self._parse_production_row(row, source_url)
        elif report_type == "compliance":
            yield from self._parse_compliance_row(row, source_url)
        elif report_type == "plugged_wells":
            yield from self._parse_plugged_wells_row(row, source_url)
        elif report_type == "waste":
            yield from self._parse_waste_row(row, source_url)
        elif report_type == "production_not_submitted":
            yield from self._parse_production_not_submitted_row(row, source_url)
        else:
            self.logger.warning(f"[{self.state_code}] Unknown report type: {report_type}")

    def _parse_well_inventory_row(self, row: dict, source_url: str):
        """Parse a well inventory CSV row into a WellItem."""
        api_raw = self._get_field(row, ["Well API Number", "API_Number", "API Number", "API"])
        if not api_raw:
            return

        api_number = self.normalize_api_number(api_raw)

        well_item = WellItem(
            api_number=api_number,
            state_code=self.state_code,
            well_name=self._get_field(row, ["Well Name", "WellName", "Well_Name"]),
            operator_name=self._get_field(row, ["Operator Name", "OperatorName", "Operator"]),
            county=self._get_field(row, ["County", "County Name", "CountyName"]),
            latitude=self._parse_float(self._get_field(row, ["Latitude", "Lat", "Well_Latitude"])),
            longitude=self._parse_float(self._get_field(row, ["Longitude", "Lon", "Long", "Well_Longitude"])),
            well_type=self._get_field(row, ["Well Type", "WellType", "Well_Type"]),
            well_status=self._get_field(row, ["Well Status", "WellStatus", "Well_Status"]),
            spud_date=self._parse_date(self._get_field(row, ["Spud Date", "SpudDate", "Spud_Date"])),
            total_depth=self._parse_int(self._get_field(row, ["Total Depth", "TotalDepth", "Total_Depth"])),
            metadata={
                "permit_number": self._get_field(row, ["Permit Number", "PermitNumber", "Permit_Number"]),
                "configuration": self._get_field(row, ["Configuration", "Well Configuration"]),
                "municipality": self._get_field(row, ["Municipality", "MunicipalityName"]),
                "farm_name": self._get_field(row, ["Farm Name", "FarmName"]),
                "source_report": "well_inventory",
            },
        )
        yield well_item

    def _parse_production_row(self, row: dict, source_url: str):
        """Parse a production report CSV row into a DocumentItem."""
        api_raw = self._get_field(row, ["Well API Number", "API_Number", "API Number", "API"])
        if not api_raw:
            return

        reporting_period = self._get_field(row, ["Reporting Period", "ReportingPeriod", "Period"])

        yield self.build_document_item(
            source_url=source_url,
            doc_type="production_report",
            api_number=api_raw,
            operator_name=self._get_field(row, ["Operator Name", "OperatorName", "Operator"]),
            well_name=self._get_field(row, ["Well Name", "WellName", "Well_Name"]),
            file_format="csv",
            raw_metadata={
                "oil_bbls": self._parse_float(self._get_field(row, ["Oil Production", "OilProduction", "Oil_BBL"])),
                "gas_mcf": self._parse_float(self._get_field(row, ["Gas Production", "GasProduction", "Gas_MCF"])),
                "water_bbls": self._parse_float(
                    self._get_field(row, ["Water Production", "WaterProduction", "Water_BBL"])
                ),
                "condensate_bbls": self._parse_float(
                    self._get_field(row, ["Condensate", "CondensateProduction", "Condensate_BBL"])
                ),
                "days_produced": self._parse_int(self._get_field(row, ["Days Produced", "DaysProduced"])),
                "reporting_period": reporting_period,
                "county": self._get_field(row, ["County", "CountyName"]),
                "municipality": self._get_field(row, ["Municipality", "MunicipalityName"]),
                "source_report": "production",
            },
        )

    def _parse_compliance_row(self, row: dict, source_url: str):
        """Parse a compliance report CSV row into a DocumentItem."""
        api_raw = self._get_field(row, ["Well API Number", "API_Number", "API Number", "API"])
        if not api_raw:
            return

        yield self.build_document_item(
            source_url=source_url,
            doc_type="compliance_report",
            api_number=api_raw,
            operator_name=self._get_field(row, ["Operator Name", "OperatorName", "Operator"]),
            well_name=self._get_field(row, ["Well Name", "WellName", "Well_Name"]),
            file_format="csv",
            raw_metadata={
                "inspection_date": self._get_field(row, ["Inspection Date", "InspectionDate"]),
                "violation_type": self._get_field(row, ["Violation Type", "ViolationType"]),
                "enforcement_action": self._get_field(row, ["Enforcement Action", "EnforcementAction"]),
                "county": self._get_field(row, ["County", "CountyName"]),
                "source_report": "compliance",
            },
        )

    def _parse_plugged_wells_row(self, row: dict, source_url: str):
        """Parse a plugged wells CSV row into a DocumentItem."""
        api_raw = self._get_field(row, ["Well API Number", "API_Number", "API Number", "API"])
        if not api_raw:
            return

        yield self.build_document_item(
            source_url=source_url,
            doc_type="plugging_report",
            api_number=api_raw,
            operator_name=self._get_field(row, ["Operator Name", "OperatorName", "Operator"]),
            well_name=self._get_field(row, ["Well Name", "WellName", "Well_Name"]),
            file_format="csv",
            raw_metadata={
                "plug_date": self._get_field(row, ["Plug Date", "PlugDate"]),
                "plug_type": self._get_field(row, ["Plug Type", "PlugType"]),
                "county": self._get_field(row, ["County", "CountyName"]),
                "source_report": "plugged_wells",
            },
        )

    def _parse_waste_row(self, row: dict, source_url: str):
        """Parse a waste report CSV row into a DocumentItem."""
        api_raw = self._get_field(row, ["Well API Number", "API_Number", "API Number", "API"])
        if not api_raw:
            return

        yield self.build_document_item(
            source_url=source_url,
            doc_type="waste_report",
            api_number=api_raw,
            operator_name=self._get_field(row, ["Operator Name", "OperatorName", "Operator"]),
            well_name=self._get_field(row, ["Well Name", "WellName", "Well_Name"]),
            file_format="csv",
            raw_metadata={
                "waste_type": self._get_field(row, ["Waste Type", "WasteType"]),
                "waste_volume": self._parse_float(self._get_field(row, ["Waste Volume", "WasteVolume"])),
                "disposal_method": self._get_field(row, ["Disposal Method", "DisposalMethod"]),
                "county": self._get_field(row, ["County", "CountyName"]),
                "source_report": "waste",
            },
        )

    def _parse_production_not_submitted_row(self, row: dict, source_url: str):
        """Parse a production-not-submitted CSV row into a DocumentItem."""
        api_raw = self._get_field(row, ["Well API Number", "API_Number", "API Number", "API"])
        if not api_raw:
            return

        yield self.build_document_item(
            source_url=source_url,
            doc_type="production_not_submitted",
            api_number=api_raw,
            operator_name=self._get_field(row, ["Operator Name", "OperatorName", "Operator"]),
            well_name=self._get_field(row, ["Well Name", "WellName", "Well_Name"]),
            file_format="csv",
            raw_metadata={
                "reporting_period": self._get_field(row, ["Reporting Period", "ReportingPeriod"]),
                "county": self._get_field(row, ["County", "CountyName"]),
                "source_report": "production_not_submitted",
            },
        )

    # ----------------------------------------------------------------
    # Helper methods
    # ----------------------------------------------------------------

    @staticmethod
    def _get_field(row: dict, possible_names: list[str]) -> str | None:
        """Get a field value trying multiple possible column names.

        GreenPort CSV column headers may vary slightly between report
        versions. This method tries each candidate name and returns the
        first non-empty match.
        """
        for name in possible_names:
            value = row.get(name)
            if value is not None:
                stripped = value.strip()
                if stripped:
                    return stripped
        return None

    @staticmethod
    def _parse_float(value: str | None) -> float | None:
        """Parse a float value, returning None for empty/invalid.

        Handles comma-separated thousands (e.g. '1,234.56').
        """
        if not value or not value.strip():
            return None
        try:
            return float(value.strip().replace(",", ""))
        except (ValueError, TypeError):
            return None

    @staticmethod
    def _parse_int(value: str | None) -> int | None:
        """Parse an integer value, returning None for empty/invalid.

        Handles comma-separated thousands (e.g. '1,234').
        """
        if not value or not value.strip():
            return None
        try:
            cleaned = value.strip().replace(",", "")
            # Handle float-like strings (e.g. "1234.0")
            return int(float(cleaned))
        except (ValueError, TypeError):
            return None

    @staticmethod
    def _parse_date(value: str | None) -> date | None:
        """Parse a date string into a date object.

        Handles common formats: MM/DD/YYYY, YYYY-MM-DD, M/D/YYYY.
        """
        if not value or not value.strip():
            return None
        value = value.strip()
        formats = ["%m/%d/%Y", "%Y-%m-%d", "%m/%d/%y", "%Y/%m/%d"]
        for fmt in formats:
            try:
                return datetime.strptime(value, fmt).date()
            except ValueError:
                continue
        return None
