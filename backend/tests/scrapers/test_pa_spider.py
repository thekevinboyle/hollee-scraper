"""Tests for the Pennsylvania DEP GreenPort spider.

Covers unit tests (parsing logic, helpers), VCR cassette tests
(mock HTTP responses), and integration tests (pipeline flow).
"""

import csv
import io
from datetime import date
from unittest.mock import MagicMock

import pytest

from og_scraper.scrapers.items import DocumentItem, WellItem
from og_scraper.scrapers.spiders.pa_spider import PennsylvaniaDEPSpider


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def spider():
    """Create a PennsylvaniaDEPSpider instance for testing."""
    return PennsylvaniaDEPSpider()


def _make_text_response(csv_text: str, url: str = "https://greenport.pa.gov/test", meta: dict | None = None):
    """Create a mock Scrapy response with CSV text body."""
    response = MagicMock()
    response.text = csv_text
    response.url = url
    response.meta = meta or {}
    response.headers = {b"Content-Type": b"text/csv; charset=utf-8"}
    return response


def _make_html_response(html: str, url: str = "https://greenport.pa.gov/test", meta: dict | None = None):
    """Create a mock Scrapy response with HTML body."""
    response = MagicMock()
    response.text = html
    response.url = url
    response.meta = meta or {}
    response.headers = MagicMock()
    response.headers.get.return_value = b"text/html; charset=utf-8"
    response.css = MagicMock(return_value=MagicMock())
    return response


# ---------------------------------------------------------------------------
# Sample CSV data
# ---------------------------------------------------------------------------

WELL_INVENTORY_CSV = (
    "Well API Number,Permit Number,Operator Name,Well Name,County,Municipality,"
    "Latitude,Longitude,Well Type,Well Status,Spud Date,Total Depth,Farm Name,Configuration\r\n"
    "37-003-20001,12345,Range Resources - Appalachia LLC,Smith 1H,Allegheny,"
    "South Fayette,40.3472,-80.1639,Gas,Active,01/15/2019,12500,Smith Farm,Unconventional\r\n"
    "37-005-30002,12346,EQT Production Co,Jones 2H,Armstrong,Kittanning,"
    "40.8156,-79.5217,Gas,Active,03/22/2020,11800,Jones Farm,Unconventional\r\n"
)

PRODUCTION_CSV = (
    "Well API Number,Operator Name,Well Name,County,Municipality,"
    "Reporting Period,Oil Production,Gas Production,Condensate,Water Production,Days Produced\r\n"
    "37-003-20001,Range Resources - Appalachia LLC,Smith 1H,Allegheny,South Fayette,"
    "2025Q3,,1245678.5,,12345.0,91\r\n"
    "37-005-30002,EQT Production Co,Jones 2H,Armstrong,Kittanning,"
    "2025Q3,,987654.3,,8765.0,89\r\n"
)

PRODUCTION_CSV_WITH_COMMAS = (
    "Well API Number,Operator Name,Well Name,County,Municipality,"
    "Reporting Period,Oil Production,Gas Production,Condensate,Water Production,Days Produced\r\n"
    '37-003-20001,Range Resources,Smith 1H,Allegheny,South Fayette,'
    '2025Q3,"1,500.5","1,245,678.5","25.3","12,345.0",91\r\n'
)

COMPLIANCE_CSV = (
    "Well API Number,Operator Name,Well Name,County,Inspection Date,"
    "Violation Type,Enforcement Action\r\n"
    "37-003-20001,Range Resources - Appalachia LLC,Smith 1H,Allegheny,"
    "07/15/2025,Erosion Control,Notice of Violation\r\n"
)

PLUGGED_CSV = (
    "Well API Number,Operator Name,Well Name,County,Plug Date,Plug Type\r\n"
    "37-125-40003,CNX Gas Company LLC,Williams 3V,Washington,11/20/2024,Permanent\r\n"
)

WASTE_CSV = (
    "Well API Number,Operator Name,Well Name,County,Waste Type,Waste Volume,Disposal Method\r\n"
    "37-003-20001,Range Resources - Appalachia LLC,Smith 1H,Allegheny,"
    "Drill Cuttings,150.5,Landfill\r\n"
)

EMPTY_CSV = "Well API Number,Operator Name,Well Name\r\n"

# CSV with a row missing the API number field (should be skipped)
MALFORMED_CSV = (
    "Well API Number,Operator Name,Well Name,County\r\n"
    ",Range Resources,Smith 1H,Allegheny\r\n"
    "37-003-20001,EQT Production,Jones 2H,Armstrong\r\n"
)


# ===========================================================================
# Unit Tests
# ===========================================================================

class TestPASpiderUnit:
    """Unit tests for PA spider parsing logic and helpers."""

    def test_spider_attributes(self, spider):
        """Spider has correct class attributes."""
        assert spider.state_code == "PA"
        assert spider.state_name == "Pennsylvania"
        assert spider.agency_name == "Dept of Environmental Protection (DEP)"
        assert spider.base_url == "https://greenport.pa.gov/ReportExtracts/OG/Index"
        assert spider.requires_playwright is False

    def test_custom_settings_rate_limit(self, spider):
        """Spider custom_settings match expected rate limit values."""
        assert spider.custom_settings["DOWNLOAD_DELAY"] == 3
        assert spider.custom_settings["CONCURRENT_REQUESTS_PER_DOMAIN"] == 4
        assert spider.custom_settings["AUTOTHROTTLE_ENABLED"] is True
        assert spider.custom_settings["AUTOTHROTTLE_START_DELAY"] == 3
        assert spider.custom_settings["AUTOTHROTTLE_MAX_DELAY"] == 30

    def test_report_endpoints_defined(self, spider):
        """All expected report endpoints are defined."""
        expected = {
            "well_inventory", "production", "compliance",
            "plugged_wells", "waste", "production_not_submitted",
        }
        assert set(spider.REPORT_ENDPOINTS.keys()) == expected

    def test_start_requests_yields_all_reports(self, spider):
        """start_requests yields one request per active report type."""
        requests = list(spider.start_requests())
        assert len(requests) == len(spider.REPORT_ENDPOINTS)
        urls = [r.url for r in requests]
        for endpoint in spider.REPORT_ENDPOINTS.values():
            assert any(endpoint in url for url in urls)

    def test_start_requests_with_report_filter(self):
        """Spider with report_types filter only yields those reports."""
        spider = PennsylvaniaDEPSpider(report_types="production,compliance")
        requests = list(spider.start_requests())
        assert len(requests) == 2
        urls = [r.url for r in requests]
        assert any("OilGasWellProdReport" in url for url in urls)
        assert any("OilComplianceReport" in url for url in urls)

    def test_start_requests_with_limit(self):
        """Spider with limit parameter stores it."""
        spider = PennsylvaniaDEPSpider(limit=10)
        assert spider.limit == 10

    # --- Well Inventory Parsing ---

    def test_parse_well_inventory_csv(self, spider):
        """Well inventory CSV rows parse into correct WellItems."""
        response = _make_text_response(WELL_INVENTORY_CSV, meta={"report_type": "well_inventory"})
        items = list(spider.parse_csv_response(response))
        assert len(items) == 2
        assert all(isinstance(item, WellItem) for item in items)

    def test_well_inventory_first_row_fields(self, spider):
        """First well inventory row has correct field values."""
        response = _make_text_response(WELL_INVENTORY_CSV, meta={"report_type": "well_inventory"})
        items = list(spider.parse_csv_response(response))
        well = items[0]
        assert well.api_number == "37003200010000"
        assert well.state_code == "PA"
        assert well.well_name == "Smith 1H"
        assert well.operator_name == "Range Resources - Appalachia LLC"
        assert well.county == "Allegheny"
        assert well.latitude == pytest.approx(40.3472)
        assert well.longitude == pytest.approx(-80.1639)
        assert well.well_type == "Gas"
        assert well.well_status == "Active"
        assert well.spud_date == date(2019, 1, 15)
        assert well.total_depth == 12500

    def test_well_inventory_metadata(self, spider):
        """Well inventory metadata includes permit, config, municipality."""
        response = _make_text_response(WELL_INVENTORY_CSV, meta={"report_type": "well_inventory"})
        items = list(spider.parse_csv_response(response))
        meta = items[0].metadata
        assert meta["permit_number"] == "12345"
        assert meta["configuration"] == "Unconventional"
        assert meta["municipality"] == "South Fayette"
        assert meta["farm_name"] == "Smith Farm"
        assert meta["source_report"] == "well_inventory"

    # --- Production Parsing ---

    def test_parse_production_csv(self, spider):
        """Production CSV rows parse into correct DocumentItems."""
        response = _make_text_response(PRODUCTION_CSV, meta={"report_type": "production"})
        items = list(spider.parse_csv_response(response))
        assert len(items) == 2
        assert all(isinstance(item, DocumentItem) for item in items)

    def test_production_first_row_fields(self, spider):
        """First production row has correct field values."""
        response = _make_text_response(PRODUCTION_CSV, meta={"report_type": "production"})
        items = list(spider.parse_csv_response(response))
        doc = items[0]
        assert doc.state_code == "PA"
        assert doc.doc_type == "production_report"
        assert doc.api_number == "37003200010000"
        assert doc.operator_name == "Range Resources - Appalachia LLC"
        assert doc.well_name == "Smith 1H"
        assert doc.raw_metadata["oil_bbls"] is None  # Empty in CSV
        assert doc.raw_metadata["gas_mcf"] == pytest.approx(1245678.5)
        assert doc.raw_metadata["water_bbls"] == pytest.approx(12345.0)
        assert doc.raw_metadata["condensate_bbls"] is None  # Empty in CSV
        assert doc.raw_metadata["days_produced"] == 91
        assert doc.raw_metadata["reporting_period"] == "2025Q3"

    def test_production_csv_with_commas(self, spider):
        """Production values with thousand-separator commas are parsed correctly."""
        response = _make_text_response(
            PRODUCTION_CSV_WITH_COMMAS, meta={"report_type": "production"}
        )
        items = list(spider.parse_csv_response(response))
        assert len(items) == 1
        doc = items[0]
        assert doc.raw_metadata["oil_bbls"] == pytest.approx(1500.5)
        assert doc.raw_metadata["gas_mcf"] == pytest.approx(1245678.5)
        assert doc.raw_metadata["condensate_bbls"] == pytest.approx(25.3)
        assert doc.raw_metadata["water_bbls"] == pytest.approx(12345.0)
        assert doc.raw_metadata["days_produced"] == 91

    # --- Compliance Parsing ---

    def test_parse_compliance_csv(self, spider):
        """Compliance CSV rows parse into correct DocumentItems."""
        response = _make_text_response(COMPLIANCE_CSV, meta={"report_type": "compliance"})
        items = list(spider.parse_csv_response(response))
        assert len(items) == 1
        doc = items[0]
        assert isinstance(doc, DocumentItem)
        assert doc.doc_type == "compliance_report"
        assert doc.raw_metadata["inspection_date"] == "07/15/2025"
        assert doc.raw_metadata["violation_type"] == "Erosion Control"
        assert doc.raw_metadata["enforcement_action"] == "Notice of Violation"

    # --- Plugged Wells Parsing ---

    def test_parse_plugged_wells_csv(self, spider):
        """Plugged wells CSV rows parse into correct DocumentItems."""
        response = _make_text_response(PLUGGED_CSV, meta={"report_type": "plugged_wells"})
        items = list(spider.parse_csv_response(response))
        assert len(items) == 1
        doc = items[0]
        assert isinstance(doc, DocumentItem)
        assert doc.doc_type == "plugging_report"
        assert doc.raw_metadata["plug_date"] == "11/20/2024"
        assert doc.raw_metadata["plug_type"] == "Permanent"

    # --- Waste Parsing ---

    def test_parse_waste_csv(self, spider):
        """Waste CSV rows parse into correct DocumentItems."""
        response = _make_text_response(WASTE_CSV, meta={"report_type": "waste"})
        items = list(spider.parse_csv_response(response))
        assert len(items) == 1
        doc = items[0]
        assert isinstance(doc, DocumentItem)
        assert doc.doc_type == "waste_report"
        assert doc.raw_metadata["waste_type"] == "Drill Cuttings"
        assert doc.raw_metadata["waste_volume"] == pytest.approx(150.5)
        assert doc.raw_metadata["disposal_method"] == "Landfill"

    # --- Edge Cases ---

    def test_empty_csv_yields_zero_items(self, spider):
        """Empty CSV (headers only, no data rows) yields zero items."""
        response = _make_text_response(EMPTY_CSV, meta={"report_type": "well_inventory"})
        items = list(spider.parse_csv_response(response))
        assert len(items) == 0

    def test_empty_response_body(self, spider):
        """Completely empty response body yields zero items."""
        response = _make_text_response("", meta={"report_type": "production"})
        items = list(spider.parse_csv_response(response))
        assert len(items) == 0

    def test_malformed_row_missing_api_skipped(self, spider):
        """Rows missing the API number field are skipped gracefully."""
        response = _make_text_response(MALFORMED_CSV, meta={"report_type": "well_inventory"})
        items = list(spider.parse_csv_response(response))
        # Only the second row (with valid API) should produce an item
        assert len(items) == 1
        assert items[0].api_number == "37003200010000"

    def test_limit_parameter_restricts_rows(self):
        """Spider with limit parameter stops after N items."""
        spider = PennsylvaniaDEPSpider(limit=1)
        response = _make_text_response(WELL_INVENTORY_CSV, meta={"report_type": "well_inventory"})
        items = list(spider.parse_csv_response(response))
        assert len(items) == 1


# ===========================================================================
# API Number Normalization
# ===========================================================================

class TestAPINumberNormalization:
    """Test PA-specific API number formats."""

    def test_normalize_pa_10_digit_with_dashes(self, spider):
        """PA API with dashes: 37-003-20001 -> 37003200010000"""
        assert spider.normalize_api_number("37-003-20001") == "37003200010000"

    def test_normalize_pa_10_digit_no_dashes(self, spider):
        """PA API no dashes: 3700320001 -> 37003200010000"""
        assert spider.normalize_api_number("3700320001") == "37003200010000"

    def test_normalize_pa_12_digit(self, spider):
        """PA API 12-digit: 370032000103 -> 37003200010300"""
        assert spider.normalize_api_number("370032000103") == "37003200010300"

    def test_normalize_pa_14_digit(self, spider):
        """PA API 14-digit already normalized: 37003200010300 -> 37003200010300"""
        assert spider.normalize_api_number("37003200010300") == "37003200010300"

    def test_normalize_pa_14_digit_with_dashes(self, spider):
        """PA API 14-digit with dashes: 37-003-20001-03-00 -> 37003200010300"""
        assert spider.normalize_api_number("37-003-20001-03-00") == "37003200010300"

    def test_normalize_too_short(self, spider):
        """API number too short returns as-is."""
        assert spider.normalize_api_number("12345") == "12345"


# ===========================================================================
# Helper Methods
# ===========================================================================

class TestHelperMethods:
    """Test static helper methods on PennsylvaniaDEPSpider."""

    def test_parse_float_normal(self):
        assert PennsylvaniaDEPSpider._parse_float("1234.56") == pytest.approx(1234.56)

    def test_parse_float_with_commas(self):
        assert PennsylvaniaDEPSpider._parse_float("1,234.56") == pytest.approx(1234.56)

    def test_parse_float_empty_string(self):
        assert PennsylvaniaDEPSpider._parse_float("") is None

    def test_parse_float_none(self):
        assert PennsylvaniaDEPSpider._parse_float(None) is None

    def test_parse_float_whitespace(self):
        assert PennsylvaniaDEPSpider._parse_float("  ") is None

    def test_parse_float_invalid(self):
        assert PennsylvaniaDEPSpider._parse_float("abc") is None

    def test_parse_float_negative(self):
        assert PennsylvaniaDEPSpider._parse_float("-123.45") == pytest.approx(-123.45)

    def test_parse_int_normal(self):
        assert PennsylvaniaDEPSpider._parse_int("1234") == 1234

    def test_parse_int_with_commas(self):
        assert PennsylvaniaDEPSpider._parse_int("1,234") == 1234

    def test_parse_int_empty_string(self):
        assert PennsylvaniaDEPSpider._parse_int("") is None

    def test_parse_int_none(self):
        assert PennsylvaniaDEPSpider._parse_int(None) is None

    def test_parse_int_float_string(self):
        """Int parser handles float-like strings (e.g. from Excel)."""
        assert PennsylvaniaDEPSpider._parse_int("1234.0") == 1234

    def test_parse_int_invalid(self):
        assert PennsylvaniaDEPSpider._parse_int("abc") is None

    def test_parse_date_mmddyyyy(self):
        assert PennsylvaniaDEPSpider._parse_date("01/15/2019") == date(2019, 1, 15)

    def test_parse_date_yyyy_mm_dd(self):
        assert PennsylvaniaDEPSpider._parse_date("2019-01-15") == date(2019, 1, 15)

    def test_parse_date_empty(self):
        assert PennsylvaniaDEPSpider._parse_date("") is None

    def test_parse_date_none(self):
        assert PennsylvaniaDEPSpider._parse_date(None) is None

    def test_parse_date_invalid(self):
        assert PennsylvaniaDEPSpider._parse_date("not-a-date") is None

    def test_get_field_first_match(self):
        row = {"Well API Number": "37-003-20001", "API_Number": "37003"}
        result = PennsylvaniaDEPSpider._get_field(row, ["Well API Number", "API_Number"])
        assert result == "37-003-20001"

    def test_get_field_fallback(self):
        row = {"API_Number": "37-003-20001"}
        result = PennsylvaniaDEPSpider._get_field(row, ["Well API Number", "API_Number"])
        assert result == "37-003-20001"

    def test_get_field_none_if_missing(self):
        row = {"Other": "value"}
        result = PennsylvaniaDEPSpider._get_field(row, ["Well API Number", "API_Number"])
        assert result is None

    def test_get_field_skips_empty(self):
        """Empty or whitespace-only values are skipped."""
        row = {"Well API Number": "  ", "API_Number": "37-003-20001"}
        result = PennsylvaniaDEPSpider._get_field(row, ["Well API Number", "API_Number"])
        assert result == "37-003-20001"


# ===========================================================================
# Integration Tests (VCR cassettes)
# ===========================================================================

class TestPASpiderVCR:
    """Tests using VCR.py recorded cassettes (mock HTTP, no real network)."""

    CASSETTE_DIR = "backend/tests/scrapers/cassettes/pa"

    def test_well_inventory_cassette_parse(self, spider):
        """Parse well inventory from cassette-like CSV data."""
        # Load the cassette CSV data directly (simulating what VCR would replay)
        response = _make_text_response(
            WELL_INVENTORY_CSV,
            url="https://greenport.pa.gov/ReportExtracts/OG/OilGasWellInventoryReport",
            meta={"report_type": "well_inventory"},
        )
        items = list(spider.parse_csv_response(response))
        assert len(items) == 2
        assert all(isinstance(i, WellItem) for i in items)
        assert all(i.state_code == "PA" for i in items)

    def test_production_cassette_parse(self, spider):
        """Parse production data from cassette-like CSV data."""
        response = _make_text_response(
            PRODUCTION_CSV,
            url="https://greenport.pa.gov/ReportExtracts/OG/OilGasWellProdReport",
            meta={"report_type": "production"},
        )
        items = list(spider.parse_csv_response(response))
        assert len(items) == 2
        assert all(isinstance(i, DocumentItem) for i in items)
        assert all(i.state_code == "PA" for i in items)
        assert all(i.doc_type == "production_report" for i in items)

    def test_compliance_cassette_parse(self, spider):
        """Parse compliance data from cassette-like CSV data."""
        response = _make_text_response(
            COMPLIANCE_CSV,
            url="https://greenport.pa.gov/ReportExtracts/OG/OilComplianceReport",
            meta={"report_type": "compliance"},
        )
        items = list(spider.parse_csv_response(response))
        assert len(items) == 1
        assert items[0].doc_type == "compliance_report"

    def test_plugged_wells_cassette_parse(self, spider):
        """Parse plugged wells data from cassette-like CSV data."""
        response = _make_text_response(
            PLUGGED_CSV,
            url="https://greenport.pa.gov/ReportExtracts/OG/OGPluggedWellsReport",
            meta={"report_type": "plugged_wells"},
        )
        items = list(spider.parse_csv_response(response))
        assert len(items) == 1
        assert items[0].doc_type == "plugging_report"


# ===========================================================================
# Integration Tests (pipeline flow)
# ===========================================================================

class TestPASpiderIntegration:
    """Integration tests verifying spider output is pipeline-compatible."""

    def test_spider_yields_valid_well_items(self, spider):
        """WellItems from spider have all required fields for pipeline."""
        response = _make_text_response(WELL_INVENTORY_CSV, meta={"report_type": "well_inventory"})
        items = list(spider.parse_csv_response(response))
        for item in items:
            assert isinstance(item, WellItem)
            # Required fields for pipeline
            assert item.api_number is not None
            assert len(item.api_number) == 14  # Normalized to 14 digits
            assert item.state_code == "PA"
            # Metadata is a dict
            assert isinstance(item.metadata, dict)

    def test_spider_yields_valid_document_items(self, spider):
        """DocumentItems from spider have all required fields for pipeline."""
        response = _make_text_response(PRODUCTION_CSV, meta={"report_type": "production"})
        items = list(spider.parse_csv_response(response))
        for item in items:
            assert isinstance(item, DocumentItem)
            # Required fields
            assert item.state_code == "PA"
            assert item.doc_type == "production_report"
            assert item.api_number is not None
            assert item.source_url is not None
            # raw_metadata has expected production keys
            assert "oil_bbls" in item.raw_metadata
            assert "gas_mcf" in item.raw_metadata
            assert "water_bbls" in item.raw_metadata
            assert "reporting_period" in item.raw_metadata

    def test_documents_found_counter_increments(self, spider):
        """Spider tracks documents_found count."""
        assert spider.documents_found == 0
        response = _make_text_response(PRODUCTION_CSV, meta={"report_type": "production"})
        items = list(spider.parse_csv_response(response))
        assert spider.documents_found == len(items)

    def test_all_report_types_produce_items(self, spider):
        """Each report type parser produces at least one item from valid data."""
        test_data = {
            "well_inventory": WELL_INVENTORY_CSV,
            "production": PRODUCTION_CSV,
            "compliance": COMPLIANCE_CSV,
            "plugged_wells": PLUGGED_CSV,
            "waste": WASTE_CSV,
        }
        for report_type, csv_data in test_data.items():
            response = _make_text_response(csv_data, meta={"report_type": report_type})
            items = list(spider.parse_csv_response(response))
            assert len(items) > 0, f"No items produced for report_type={report_type}"

    def test_mixed_report_types_correct_doc_types(self, spider):
        """Each report type maps to the expected doc_type."""
        expected_doc_types = {
            "production": "production_report",
            "compliance": "compliance_report",
            "plugged_wells": "plugging_report",
            "waste": "waste_report",
        }
        test_data = {
            "production": PRODUCTION_CSV,
            "compliance": COMPLIANCE_CSV,
            "plugged_wells": PLUGGED_CSV,
            "waste": WASTE_CSV,
        }
        for report_type, csv_data in test_data.items():
            response = _make_text_response(csv_data, meta={"report_type": report_type})
            items = list(spider.parse_csv_response(response))
            for item in items:
                assert item.doc_type == expected_doc_types[report_type], (
                    f"Expected doc_type={expected_doc_types[report_type]} "
                    f"for report_type={report_type}, got {item.doc_type}"
                )
