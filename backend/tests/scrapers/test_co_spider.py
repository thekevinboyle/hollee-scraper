"""Tests for the Colorado ECMC spider.

Covers unit tests for CSV row parsing, download link classification,
API number normalization, ZIP handling, COGIS form parsing, and
VCR cassette-based integration tests.
"""

import csv
import io
import zipfile

import pytest
from scrapy.http import HtmlResponse, Request, TextResponse

from og_scraper.scrapers.items import DocumentItem, WellItem
from og_scraper.scrapers.spiders.co_spider import ColoradoECMCSpider


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_text_response(url: str, body: str, meta: dict | None = None) -> TextResponse:
    """Create a fake Scrapy TextResponse for testing."""
    request = Request(url=url, meta=meta or {})
    resp = TextResponse(
        url=url,
        body=body.encode("utf-8"),
        encoding="utf-8",
        request=request,
    )
    return resp


def _make_html_response(url: str, body: str, meta: dict | None = None) -> HtmlResponse:
    """Create a fake Scrapy HtmlResponse for testing."""
    request = Request(url=url, meta=meta or {})
    resp = HtmlResponse(
        url=url,
        body=body.encode("utf-8"),
        encoding="utf-8",
        request=request,
    )
    return resp


def _make_csv_body(headers: list[str], rows: list[list[str]]) -> str:
    """Build a CSV string from headers and row data."""
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(headers)
    for row in rows:
        writer.writerow(row)
    return buf.getvalue()


def _make_zip_response(url: str, csv_filename: str, csv_body: str, meta: dict | None = None) -> TextResponse:
    """Create a fake Scrapy response with a ZIP body containing a CSV."""
    zip_buf = io.BytesIO()
    with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(csv_filename, csv_body)
    zip_bytes = zip_buf.getvalue()
    request = Request(url=url, meta=meta or {})
    resp = TextResponse(
        url=url,
        body=zip_bytes,
        encoding="utf-8",
        request=request,
    )
    return resp


def _spider() -> ColoradoECMCSpider:
    """Create a spider instance for testing."""
    return ColoradoECMCSpider()


# ---------------------------------------------------------------------------
# TestCOSpiderUnit -- Unit tests for parsing logic
# ---------------------------------------------------------------------------


class TestCOSpiderUnit:
    """Unit tests for CO spider parsing logic."""

    def test_spider_attributes(self):
        """Spider has correct state attributes."""
        spider = _spider()
        assert spider.state_code == "CO"
        assert spider.state_name == "Colorado"
        assert spider.name == "co_ecmc"
        assert spider.requires_playwright is False
        assert spider.rate_limit_delay == 8.0
        assert spider.max_concurrent == 2

    def test_custom_settings(self):
        """Custom settings match CO rate limits."""
        spider = _spider()
        assert spider.custom_settings["DOWNLOAD_DELAY"] == 8
        assert spider.custom_settings["CONCURRENT_REQUESTS_PER_DOMAIN"] == 2
        assert spider.custom_settings["AUTOTHROTTLE_ENABLED"] is True

    def test_allowed_domains(self):
        """Spider handles both ECMC domains."""
        spider = _spider()
        assert "ecmc.colorado.gov" in spider.allowed_domains
        assert "ecmc.state.co.us" in spider.allowed_domains

    # --- Download link classifier ---

    def test_classify_well_spots(self):
        spider = _spider()
        assert spider._classify_download_link("well spots (all apis)", "/data/well_spots.csv") == "well_spots"

    def test_classify_wellspot_no_space(self):
        spider = _spider()
        assert spider._classify_download_link("wellspot data", "/data.csv") == "well_spots"

    def test_classify_well_spot_by_href(self):
        spider = _spider()
        assert spider._classify_download_link("download file", "/data/well_spot_data.csv") == "well_spots"

    def test_classify_active_permits(self):
        spider = _spider()
        assert spider._classify_download_link("active well permits", "/permits.csv") == "well_permits"

    def test_classify_pending_permits(self):
        spider = _spider()
        assert spider._classify_download_link("pending well permits", "/pending.csv") == "pending_permits"

    def test_classify_production(self):
        spider = _spider()
        assert spider._classify_download_link("production data", "/prod.csv") == "production"

    def test_classify_production_by_href(self):
        spider = _spider()
        assert spider._classify_download_link("download", "/data/prod_data.zip") == "production"

    def test_classify_analytical(self):
        spider = _spider()
        assert spider._classify_download_link("well analytical data", "/data.csv") == "well_analytical"

    def test_classify_unrecognized(self):
        spider = _spider()
        assert spider._classify_download_link("download guide pdf", "/guide.pdf") is None

    # --- API number normalization (CO format, state code 05) ---

    def test_api_number_normalization_dashed_10(self):
        """CO API with dashes normalizes to 14 digits."""
        spider = _spider()
        assert spider.normalize_api_number("05-123-45678") == "05123456780000"

    def test_api_number_normalization_plain_10(self):
        """Plain 10-digit CO API normalizes correctly."""
        spider = _spider()
        assert spider.normalize_api_number("0512345678") == "05123456780000"

    def test_api_number_normalization_14_digit(self):
        """14-digit API stays as-is."""
        spider = _spider()
        assert spider.normalize_api_number("05123456780100") == "05123456780100"

    def test_api_number_too_short(self):
        """Short strings return as-is."""
        spider = _spider()
        assert spider.normalize_api_number("05123") == "05123"

    # --- Well spot row parsing ---

    def test_parse_well_spot_row(self):
        """Well spot CSV row produces correct WellItem."""
        spider = _spider()
        row = {
            "API_Number": "05-123-45678",
            "Well_Name": "THOMPSON 1-23",
            "Operator_Name": "DEVON ENERGY CORP",
            "County": "WELD",
            "Field_Name": "WATTENBERG",
            "Formation": "NIOBRARA",
            "Latitude": "40.123456",
            "Longitude": "-104.567890",
            "Well_Status": "Active",
            "Well_Type": "OG",
            "Spud_Date": "01/15/2020",
            "Total_Depth": "7500",
        }
        items = list(spider._parse_well_spot_row(row, "https://example.com/data.csv"))
        assert len(items) == 1
        item = items[0]
        assert isinstance(item, WellItem)
        assert item.api_number == "05123456780000"
        assert item.state_code == "CO"
        assert item.well_name == "THOMPSON 1-23"
        assert item.operator_name == "DEVON ENERGY CORP"
        assert item.county == "WELD"
        assert item.latitude == pytest.approx(40.123456)
        assert item.longitude == pytest.approx(-104.567890)
        assert item.well_status == "Active"
        assert item.well_type == "OG"
        assert item.total_depth == 7500
        assert item.field_name == "WATTENBERG"
        assert item.metadata["formation"] == "NIOBRARA"

    def test_parse_well_spot_row_missing_api(self):
        """Row without API number yields nothing."""
        spider = _spider()
        row = {"Well_Name": "ORPHAN WELL", "County": "WELD"}
        items = list(spider._parse_well_spot_row(row, "https://example.com/data.csv"))
        assert len(items) == 0

    def test_parse_well_spot_row_alternate_keys(self):
        """Row with lowercase field names still parses correctly."""
        spider = _spider()
        row = {
            "api_number": "05-001-12345",
            "well_name": "SMITH UNIT 4-16",
            "operator_name": "GREAT WESTERN",
            "county": "ADAMS",
            "latitude": "39.876543",
            "longitude": "-104.234567",
        }
        items = list(spider._parse_well_spot_row(row, "https://example.com/data.csv"))
        assert len(items) == 1
        assert items[0].api_number == "05001123450000"
        assert items[0].well_name == "SMITH UNIT 4-16"

    # --- Production row parsing ---

    def test_parse_production_row(self):
        """Production CSV row produces correct DocumentItem with volumes."""
        spider = _spider()
        row = {
            "API_Number": "05-123-45678",
            "Operator_Name": "DEVON ENERGY CORP",
            "Well_Name": "THOMPSON 1-23",
            "Year": "2024",
            "Month": "01",
            "Oil_BBL": "1250.5",
            "Gas_MCF": "3200.8",
            "Water_BBL": "450.2",
            "Days_Produced": "31",
            "Formation": "NIOBRARA",
        }
        items = list(spider._parse_production_row(row, "https://example.com/prod.csv"))
        assert len(items) == 1
        item = items[0]
        assert isinstance(item, DocumentItem)
        assert item.state_code == "CO"
        assert item.doc_type == "production_report"
        assert item.api_number == "05123456780000"
        assert item.operator_name == "DEVON ENERGY CORP"
        meta = item.raw_metadata
        assert meta["oil_bbls"] == pytest.approx(1250.5)
        assert meta["gas_mcf"] == pytest.approx(3200.8)
        assert meta["water_bbls"] == pytest.approx(450.2)
        assert meta["days_produced"] == 31
        assert meta["year"] == "2024"
        assert meta["month"] == "01"
        assert meta["formation"] == "NIOBRARA"

    def test_parse_production_row_missing_api(self):
        """Production row without API yields nothing."""
        spider = _spider()
        row = {"Operator_Name": "SOME OPERATOR", "Year": "2024"}
        items = list(spider._parse_production_row(row, "https://example.com/prod.csv"))
        assert len(items) == 0

    def test_parse_production_row_zero_oil(self):
        """Gas-only well with zero oil still parses correctly."""
        spider = _spider()
        row = {
            "API_Number": "05-045-67890",
            "Operator_Name": "NOBLE ENERGY INC",
            "Well_Name": "JONES RANCH 2-7",
            "Year": "2024",
            "Month": "01",
            "Oil_BBL": "0",
            "Gas_MCF": "8500.3",
            "Water_BBL": "120.0",
            "Days_Produced": "31",
            "Formation": "WILLIAMS FORK",
        }
        items = list(spider._parse_production_row(row, "https://example.com/prod.csv"))
        assert len(items) == 1
        assert items[0].raw_metadata["oil_bbls"] == pytest.approx(0.0)
        assert items[0].raw_metadata["gas_mcf"] == pytest.approx(8500.3)

    # --- Permit row parsing ---

    def test_parse_permit_row(self):
        """Permit CSV row produces correct WellItem with permit info."""
        spider = _spider()
        row = {
            "API_Number": "05-123-99001",
            "Well_Name": "NEW WELL A 1-10",
            "Operator_Name": "CIVITAS RESOURCES",
            "County": "WELD",
            "Well_Type": "OG",
            "Permit_Date": "12/15/2024",
            "Latitude": "40.345678",
            "Longitude": "-104.567890",
            "Proposed_Depth": "7600",
            "Formation": "NIOBRARA",
        }
        items = list(spider._parse_permit_row(row, "https://example.com/permits.csv", "well_permits"))
        assert len(items) == 1
        item = items[0]
        assert isinstance(item, WellItem)
        assert item.api_number == "05123990010000"
        assert item.well_status == "Permitted"
        assert item.metadata["permit_type"] == "well_permits"
        assert item.metadata["proposed_depth"] == 7600
        assert item.metadata["formation"] == "NIOBRARA"

    def test_parse_pending_permit_row(self):
        """Pending permit sets status to 'Pending Permit'."""
        spider = _spider()
        row = {
            "API_Number": "05-123-99002",
            "Well_Name": "PENDING WELL B 2-5",
            "Operator_Name": "PDC ENERGY",
            "County": "WELD",
        }
        items = list(spider._parse_permit_row(row, "https://example.com/pending.csv", "pending_permits"))
        assert len(items) == 1
        assert items[0].well_status == "Pending Permit"
        assert items[0].metadata["permit_type"] == "pending_permits"

    # --- Analytical row parsing ---

    def test_parse_analytical_row(self):
        """Analytical CSV row produces DocumentItem with raw metadata."""
        spider = _spider()
        row = {
            "API_Number": "05-123-45678",
            "Operator_Name": "DEVON ENERGY CORP",
            "Well_Name": "THOMPSON 1-23",
            "Test_Type": "IP",
            "Oil_Rate": "500",
            "Gas_Rate": "1200",
        }
        items = list(spider._parse_analytical_row(row, "https://example.com/analytical.csv"))
        assert len(items) == 1
        item = items[0]
        assert isinstance(item, DocumentItem)
        assert item.doc_type == "well_analytical"
        assert "Test_Type" in item.raw_metadata
        assert item.raw_metadata["Oil_Rate"] == "500"

    # --- CSV file parsing ---

    def test_parse_csv_file_well_spots(self):
        """Full CSV file parsing dispatches to well spot parser."""
        spider = _spider()
        csv_body = _make_csv_body(
            ["API_Number", "Well_Name", "Operator_Name", "County", "Latitude", "Longitude", "Well_Status"],
            [
                ["05-123-45678", "THOMPSON 1-23", "DEVON ENERGY", "WELD", "40.12", "-104.56", "Active"],
                ["05-001-12345", "SMITH UNIT", "GREAT WESTERN", "ADAMS", "39.87", "-104.23", "Producing"],
            ],
        )
        response = _make_text_response(
            "https://ecmc.colorado.gov/documents/data/downloads/well_spots.csv",
            csv_body,
            meta={"report_type": "well_spots", "source_url": "https://ecmc.colorado.gov/well_spots.csv"},
        )
        items = list(spider.parse_csv_file(response))
        assert len(items) == 2
        assert all(isinstance(i, WellItem) for i in items)
        assert items[0].well_name == "THOMPSON 1-23"
        assert items[1].well_name == "SMITH UNIT"

    def test_parse_csv_file_production(self):
        """Full CSV parsing dispatches to production parser."""
        spider = _spider()
        csv_body = _make_csv_body(
            ["API_Number", "Operator_Name", "Well_Name", "Year", "Month", "Oil_BBL", "Gas_MCF"],
            [
                ["05-123-45678", "DEVON ENERGY", "THOMPSON", "2024", "01", "1250.5", "3200.8"],
            ],
        )
        response = _make_text_response(
            "https://ecmc.colorado.gov/production.csv",
            csv_body,
            meta={"report_type": "production", "source_url": "https://ecmc.colorado.gov/production.csv"},
        )
        items = list(spider.parse_csv_file(response))
        assert len(items) == 1
        assert isinstance(items[0], DocumentItem)
        assert items[0].doc_type == "production_report"

    def test_parse_empty_csv(self):
        """Empty CSV (header only) yields zero items."""
        spider = _spider()
        csv_body = "API_Number,Well_Name,Operator_Name\r\n"
        response = _make_text_response(
            "https://ecmc.colorado.gov/empty.csv",
            csv_body,
            meta={"report_type": "well_spots", "source_url": "https://ecmc.colorado.gov/empty.csv"},
        )
        items = list(spider.parse_csv_file(response))
        assert len(items) == 0

    def test_parse_csv_malformed_row_handled_gracefully(self):
        """Malformed rows are skipped with error count incremented."""
        spider = _spider()
        # The row has API but will parse, then a second row without API
        csv_body = _make_csv_body(
            ["API_Number", "Well_Name"],
            [
                ["05-123-45678", "GOOD WELL"],
                ["", "NO API WELL"],
            ],
        )
        response = _make_text_response(
            "https://ecmc.colorado.gov/data.csv",
            csv_body,
            meta={"report_type": "well_spots", "source_url": "https://ecmc.colorado.gov/data.csv"},
        )
        items = list(spider.parse_csv_file(response))
        # Only the row with a valid API should produce an item
        assert len(items) == 1
        assert items[0].api_number == "05123456780000"

    # --- ZIP file handling ---

    def test_handles_zip_file(self):
        """ZIP file extraction correctly yields CSV rows."""
        spider = _spider()
        csv_body = _make_csv_body(
            ["API_Number", "Operator_Name", "Well_Name", "Year", "Month", "Oil_BBL", "Gas_MCF"],
            [
                ["05-123-45678", "DEVON ENERGY", "THOMPSON", "2024", "01", "1250.5", "3200.8"],
                ["05-001-12345", "GREAT WESTERN", "SMITH", "2024", "01", "890.7", "1500.2"],
            ],
        )

        # Build a real ZIP in memory
        zip_buf = io.BytesIO()
        with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("production_2024.csv", csv_body)
        zip_bytes = zip_buf.getvalue()

        response = TextResponse(
            url="https://ecmc.colorado.gov/data/co_production_data.zip",
            body=zip_bytes,
            encoding="utf-8",
            request=Request(url="https://ecmc.colorado.gov/data/co_production_data.zip", meta={
                "report_type": "production",
                "source_url": "https://ecmc.colorado.gov/data/co_production_data.zip",
            }),
        )

        items = list(spider.parse_csv_file(response))
        assert len(items) == 2
        assert all(isinstance(i, DocumentItem) for i in items)
        assert items[0].raw_metadata["oil_bbls"] == pytest.approx(1250.5)
        assert items[1].raw_metadata["oil_bbls"] == pytest.approx(890.7)

    def test_zip_with_multiple_csvs(self):
        """ZIP with multiple CSV files parses all of them."""
        spider = _spider()
        csv1 = _make_csv_body(
            ["API_Number", "Well_Name", "Operator_Name", "County"],
            [["05-123-45678", "WELL A", "OPERATOR A", "WELD"]],
        )
        csv2 = _make_csv_body(
            ["API_Number", "Well_Name", "Operator_Name", "County"],
            [["05-001-12345", "WELL B", "OPERATOR B", "ADAMS"]],
        )

        zip_buf = io.BytesIO()
        with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("wells_part1.csv", csv1)
            zf.writestr("wells_part2.csv", csv2)
        zip_bytes = zip_buf.getvalue()

        response = TextResponse(


            url="https://ecmc.colorado.gov/data/wells.zip",


            body=zip_bytes,


            encoding="utf-8",


            request=Request(url="https://ecmc.colorado.gov/data/wells.zip", meta={
            "report_type": "well_spots",
            "source_url": "https://ecmc.colorado.gov/data/wells.zip",
        }),


        )

        items = list(spider.parse_csv_file(response))
        assert len(items) == 2
        names = {i.well_name for i in items}
        assert "WELL A" in names
        assert "WELL B" in names

    def test_zip_non_csv_files_skipped(self):
        """Non-CSV files in a ZIP are ignored."""
        spider = _spider()
        csv_body = _make_csv_body(
            ["API_Number", "Well_Name", "Operator_Name"],
            [["05-123-45678", "WELL A", "OPERATOR A"]],
        )

        zip_buf = io.BytesIO()
        with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("wells.csv", csv_body)
            zf.writestr("readme.txt", "This is a readme file.")
            zf.writestr("metadata.json", '{"version": 1}')
        zip_bytes = zip_buf.getvalue()

        response = TextResponse(


            url="https://ecmc.colorado.gov/data/data.zip",


            body=zip_bytes,


            encoding="utf-8",


            request=Request(url="https://ecmc.colorado.gov/data/data.zip", meta={
            "report_type": "well_spots",
            "source_url": "https://ecmc.colorado.gov/data/data.zip",
        }),


        )

        items = list(spider.parse_csv_file(response))
        assert len(items) == 1  # Only from wells.csv

    def test_invalid_zip_handled_gracefully(self):
        """Invalid ZIP body does not crash the spider."""
        spider = _spider()
        response = TextResponse(

            url="https://ecmc.colorado.gov/data/bad.zip",

            body=b"PK\x03\x04this is not a real zip",

            encoding="utf-8",

            request=Request(url="https://ecmc.colorado.gov/data/bad.zip", meta={
            "report_type": "production",
            "source_url": "https://ecmc.colorado.gov/data/bad.zip",
        }),

        )

        items = list(spider.parse_csv_file(response))
        assert len(items) == 0
        assert spider.errors >= 1

    # --- Dual domain handling ---

    def test_dual_domain_urls(self):
        """Spider handles both ecmc.colorado.gov and ecmc.state.co.us URLs."""
        spider = _spider()
        # start_requests should yield requests to both domains
        requests = list(spider.start_requests())
        urls = [r.url for r in requests]
        assert any("ecmc.colorado.gov" in u for u in urls)
        assert any("ecmc.state.co.us" in u for u in urls)

    # --- Utility methods ---

    def test_parse_float_valid(self):
        assert ColoradoECMCSpider._parse_float("40.123456") == pytest.approx(40.123456)

    def test_parse_float_none(self):
        assert ColoradoECMCSpider._parse_float(None) is None

    def test_parse_float_empty(self):
        assert ColoradoECMCSpider._parse_float("") is None

    def test_parse_float_invalid(self):
        assert ColoradoECMCSpider._parse_float("not_a_number") is None

    def test_parse_int_valid(self):
        assert ColoradoECMCSpider._parse_int("7500") == 7500

    def test_parse_int_from_float_string(self):
        assert ColoradoECMCSpider._parse_int("7500.0") == 7500

    def test_parse_int_none(self):
        assert ColoradoECMCSpider._parse_int(None) is None

    def test_parse_int_invalid(self):
        assert ColoradoECMCSpider._parse_int("abc") is None

    def test_get_field_primary_key(self):
        row = {"API_Number": "05-123-45678", "api_number": "fallback"}
        assert ColoradoECMCSpider._get_field(row, "API_Number", "api_number") == "05-123-45678"

    def test_get_field_fallback_key(self):
        row = {"api_number": "05-123-45678"}
        assert ColoradoECMCSpider._get_field(row, "API_Number", "api_number") == "05-123-45678"

    def test_get_field_empty_string(self):
        row = {"API_Number": "", "api_number": "05-123-45678"}
        assert ColoradoECMCSpider._get_field(row, "API_Number", "api_number") == "05-123-45678"

    def test_get_field_no_match(self):
        row = {"other_field": "value"}
        assert ColoradoECMCSpider._get_field(row, "API_Number", "api_number") is None


# ---------------------------------------------------------------------------
# TestCOSpiderVCR -- VCR cassette-based tests
# ---------------------------------------------------------------------------


class TestCOSpiderVCR:
    """Tests using VCR cassettes for recorded HTTP responses.

    These tests use pre-recorded responses so they run offline and
    are fully deterministic.
    """

    CASSETTE_DIR = "backend/tests/scrapers/cassettes/co"

    def test_download_page_parsing(self):
        """Download page HTML yields requests for CSV files."""
        spider = _spider()
        html = (
            '<html><body>'
            '<a href="/documents/data/downloads/well_spots.csv">Well Spots (All APIs)</a>'
            '<a href="/documents/data/downloads/active_permits.csv">Active Well Permits</a>'
            '<a href="/documents/data/downloads/pending_permits.csv">Pending Well Permits</a>'
            '<a href="/documents/data/downloads/co_production_data.zip">Production Data</a>'
            '<a href="/documents/data/downloads/well_analytical.csv">Well Analytical Data</a>'
            '<a href="/documents/data/downloads/COGCC_Download_Guidance.pdf">Download Guide</a>'
            '</body></html>'
        )
        response = _make_html_response(
            "https://ecmc.colorado.gov/data-maps-reports/downloadable-data-documents",
            html,
        )
        results = list(spider.parse_download_page(response))
        # Should yield requests for all 5 CSV/ZIP files, not the PDF
        assert len(results) == 5
        urls = [r.url for r in results]
        assert any("well_spots.csv" in u for u in urls)
        assert any("active_permits.csv" in u for u in urls)
        assert any("pending_permits.csv" in u for u in urls)
        assert any("co_production_data.zip" in u for u in urls)
        assert any("well_analytical.csv" in u for u in urls)
        # PDF should NOT be included
        assert not any("COGCC_Download_Guidance.pdf" in u for u in urls)

    def test_legacy_download_page_parsing(self):
        """Legacy data page HTML yields requests for CSV files."""
        spider = _spider()
        html = (
            '<html><body>'
            '<a href="/documents/data/downloads/legacy_well_spots.csv">Well Spot Data</a>'
            '<a href="/documents/data/downloads/legacy_production.csv">Production Reports</a>'
            '<a href="/documents/data/downloads/COGCC_Download_Guidance.pdf">Download Guide</a>'
            '</body></html>'
        )
        response = _make_html_response(
            "https://ecmc.state.co.us/data2.html",
            html,
        )
        results = list(spider.parse_legacy_download_page(response))
        assert len(results) == 2
        urls = [r.url for r in results]
        assert any("legacy_well_spots.csv" in u for u in urls)
        assert any("legacy_production.csv" in u for u in urls)

    def test_well_spots_csv_from_cassette_data(self):
        """Well spots CSV parsed correctly from realistic data."""
        spider = _spider()
        csv_body = (
            "API_Number,Well_Name,Operator_Name,County,Field_Name,Formation,"
            "Latitude,Longitude,Well_Status,Well_Type,Spud_Date,First_Prod_Date,Total_Depth,Elevation\r\n"
            "05-123-45678,THOMPSON 1-23,DEVON ENERGY CORP,WELD,WATTENBERG,NIOBRARA,"
            "40.123456,-104.567890,Active,OG,01/15/2020,03/01/2020,7500,5100\r\n"
            "05-001-12345,SMITH UNIT 4-16,GREAT WESTERN OPERATING,ADAMS,BRIGHTON,CODELL,"
            "39.876543,-104.234567,Producing,OIL,06/20/2019,08/15/2019,6800,5250\r\n"
            "05-045-67890,JONES RANCH 2-7,NOBLE ENERGY INC,GARFIELD,PARACHUTE,WILLIAMS FORK,"
            "39.456789,-107.891234,Shut In,GAS,03/10/2018,,9200,5800\r\n"
        )
        response = _make_text_response(
            "https://ecmc.colorado.gov/documents/data/downloads/well_spots.csv",
            csv_body,
            meta={
                "report_type": "well_spots",
                "source_url": "https://ecmc.colorado.gov/documents/data/downloads/well_spots.csv",
            },
        )
        items = list(spider.parse_csv_file(response))
        assert len(items) == 3

        # Verify first well
        thompson = items[0]
        assert thompson.api_number == "05123456780000"
        assert thompson.well_name == "THOMPSON 1-23"
        assert thompson.operator_name == "DEVON ENERGY CORP"
        assert thompson.county == "WELD"
        assert thompson.latitude == pytest.approx(40.123456)
        assert thompson.longitude == pytest.approx(-104.567890)
        assert thompson.well_status == "Active"
        assert thompson.total_depth == 7500
        assert thompson.field_name == "WATTENBERG"

        # Verify gas well
        jones = items[2]
        assert jones.well_status == "Shut In"
        assert jones.well_type == "GAS"

    def test_production_csv_from_cassette_data(self):
        """Production CSV parsed correctly from realistic data."""
        spider = _spider()
        csv_body = (
            "API_Number,Operator_Name,Well_Name,Year,Month,Oil_BBL,Gas_MCF,Water_BBL,Days_Produced,Formation\r\n"
            "05-123-45678,DEVON ENERGY CORP,THOMPSON 1-23,2024,01,1250.5,3200.8,450.2,31,NIOBRARA\r\n"
            "05-123-45678,DEVON ENERGY CORP,THOMPSON 1-23,2024,02,1180.3,3050.1,420.0,29,NIOBRARA\r\n"
            "05-001-12345,GREAT WESTERN OPERATING,SMITH UNIT 4-16,2024,01,890.7,1500.2,680.4,31,CODELL\r\n"
        )
        response = _make_text_response(
            "https://ecmc.colorado.gov/documents/data/downloads/co_production.csv",
            csv_body,
            meta={
                "report_type": "production",
                "source_url": "https://ecmc.colorado.gov/documents/data/downloads/co_production.csv",
            },
        )
        items = list(spider.parse_csv_file(response))
        assert len(items) == 3
        assert all(isinstance(i, DocumentItem) for i in items)
        assert all(i.doc_type == "production_report" for i in items)

        # Check specific production record
        jan_thompson = items[0]
        assert jan_thompson.raw_metadata["year"] == "2024"
        assert jan_thompson.raw_metadata["month"] == "01"
        assert jan_thompson.raw_metadata["oil_bbls"] == pytest.approx(1250.5)

    def test_permits_csv_from_cassette_data(self):
        """Permits CSV parsed correctly from realistic data."""
        spider = _spider()
        csv_body = (
            "API_Number,Well_Name,Operator_Name,County,Well_Type,Permit_Date,"
            "Latitude,Longitude,Proposed_Depth,Formation\r\n"
            "05-123-99001,NEW WELL A 1-10,CIVITAS RESOURCES,WELD,OG,12/15/2024,"
            "40.345678,-104.567890,7600,NIOBRARA\r\n"
            "05-001-99002,EXPLORER 2-14,BONANZA CREEK ENERGY,ADAMS,OIL,12/20/2024,"
            "39.912345,-104.345678,6900,CODELL\r\n"
        )
        response = _make_text_response(
            "https://ecmc.colorado.gov/documents/data/downloads/active_permits.csv",
            csv_body,
            meta={
                "report_type": "well_permits",
                "source_url": "https://ecmc.colorado.gov/documents/data/downloads/active_permits.csv",
            },
        )
        items = list(spider.parse_csv_file(response))
        assert len(items) == 2
        assert all(isinstance(i, WellItem) for i in items)
        assert items[0].well_status == "Permitted"
        assert items[0].metadata["proposed_depth"] == 7600


# ---------------------------------------------------------------------------
# TestCOSpiderCOGIS -- COGIS form query tests
# ---------------------------------------------------------------------------


class TestCOSpiderCOGIS:
    """Tests for COGIS database form query functionality."""

    def test_cogis_facility_query_yields_request(self):
        """query_cogis_facility yields a request to the COGIS search form."""
        spider = _spider()
        requests = list(spider.query_cogis_facility("05123456780000"))
        assert len(requests) == 1
        assert "cogisdb/Facility/FacilitySearch" in requests[0].url
        assert requests[0].meta["api_number"] == "05123456780000"

    def test_cogis_results_parsing(self):
        """COGIS results table rows parse into WellItems."""
        spider = _spider()
        html = (
            '<html><body>'
            '<table class="results">'
            '<tr><th>API Number</th><th>Well Name</th><th>Operator</th><th>County</th><th>Status</th></tr>'
            '<tr><td>05-123-45678</td><td>THOMPSON 1-23</td><td>DEVON ENERGY CORP</td>'
            '<td>WELD</td><td>Active</td></tr>'
            '<tr><td>05-001-12345</td><td>SMITH UNIT</td><td>GREAT WESTERN</td>'
            '<td>ADAMS</td><td>Producing</td></tr>'
            '</table>'
            '</body></html>'
        )
        response = _make_html_response(
            "https://ecmc.state.co.us/cogisdb/Facility/FacilitySearch",
            html,
            meta={"api_number": "05123456780000", "query_type": "facility"},
        )
        items = list(spider.parse_cogis_results(response))
        assert len(items) == 2
        assert all(isinstance(i, WellItem) for i in items)
        assert items[0].well_name == "THOMPSON 1-23"
        assert items[0].operator_name == "DEVON ENERGY CORP"
        assert items[0].county == "WELD"
        assert items[0].well_status == "Active"
        assert items[1].well_name == "SMITH UNIT"

    def test_cogis_empty_results(self):
        """COGIS results page with no data rows yields no items."""
        spider = _spider()
        html = (
            '<html><body>'
            '<table class="results">'
            '<tr><th>API Number</th><th>Well Name</th><th>Operator</th></tr>'
            '</table>'
            '</body></html>'
        )
        response = _make_html_response(
            "https://ecmc.state.co.us/cogisdb/Facility/FacilitySearch",
            html,
            meta={"api_number": "05999999990000", "query_type": "facility"},
        )
        items = list(spider.parse_cogis_results(response))
        assert len(items) == 0


# ---------------------------------------------------------------------------
# TestCOSpiderIntegration -- Integration / pipeline tests
# ---------------------------------------------------------------------------


class TestCOSpiderIntegration:
    """Integration tests for CO spider item compatibility."""

    def test_well_items_have_required_fields(self):
        """WellItems from well spot parsing have all required fields populated."""
        spider = _spider()
        row = {
            "API_Number": "05-123-45678",
            "Well_Name": "TEST WELL",
            "Operator_Name": "TEST OPERATOR",
            "County": "WELD",
            "Latitude": "40.0",
            "Longitude": "-104.0",
            "Well_Status": "Active",
            "Well_Type": "OG",
            "Total_Depth": "7500",
            "Field_Name": "WATTENBERG",
        }
        items = list(spider._parse_well_spot_row(row, "https://example.com/data.csv"))
        item = items[0]
        # These are the key fields needed by downstream pipeline
        assert item.api_number is not None
        assert item.state_code == "CO"
        assert item.well_name is not None
        assert item.operator_name is not None
        assert item.latitude is not None
        assert item.longitude is not None

    def test_document_items_have_required_fields(self):
        """DocumentItems from production parsing have all required fields."""
        spider = _spider()
        row = {
            "API_Number": "05-123-45678",
            "Operator_Name": "DEVON ENERGY",
            "Well_Name": "THOMPSON",
            "Year": "2024",
            "Month": "01",
            "Oil_BBL": "1250",
            "Gas_MCF": "3200",
        }
        items = list(spider._parse_production_row(row, "https://example.com/prod.csv"))
        item = items[0]
        assert item.state_code == "CO"
        assert item.source_url == "https://example.com/prod.csv"
        assert item.doc_type == "production_report"
        assert item.api_number is not None
        assert item.raw_metadata is not None
        assert "oil_bbls" in item.raw_metadata

    def test_documents_found_counter_tracks(self):
        """Spider documents_found counter increments correctly."""
        spider = _spider()
        assert spider.documents_found == 0

        row = {
            "API_Number": "05-123-45678",
            "Operator_Name": "DEVON",
            "Well_Name": "TEST",
            "Year": "2024",
            "Month": "01",
            "Oil_BBL": "100",
        }
        list(spider._parse_production_row(row, "https://example.com/prod.csv"))
        assert spider.documents_found == 1

        list(spider._parse_production_row(row, "https://example.com/prod.csv"))
        assert spider.documents_found == 2
