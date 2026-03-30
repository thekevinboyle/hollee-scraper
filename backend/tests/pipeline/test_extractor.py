"""Tests for data extraction patterns and the DataExtractor class.

Tests cover API number extraction from 10+ format variations, production
volumes with unit conversion, date parsing from 5+ formats, coordinate
extraction, operator/well name extraction, and full document extraction.
"""

import pytest

from og_scraper.pipeline.extractor import DataExtractor, FieldValue
from og_scraper.pipeline.patterns import (
    _try_parse_date,
    extract_api_number,
    extract_coordinates,
    extract_county,
    extract_dates,
    extract_operator_name,
    extract_permit_number,
    extract_production_volumes,
    extract_well_depth,
    extract_well_name,
)


# ============================================================
# API Number Extraction
# ============================================================


class TestAPINumberExtraction:
    def test_labeled_14_digit(self):
        result = extract_api_number("API No: 42-501-20130-00-00")
        assert result is not None
        assert result["normalized"] == "42501201300000"
        assert result["confidence"] == 0.95
        assert result["state_code"] == "42"

    def test_labeled_10_digit(self):
        result = extract_api_number("API Number: 42-501-20130")
        assert result is not None
        assert result["normalized"] == "42501201300000"  # Zero-padded to 14

    def test_labeled_with_hash(self):
        result = extract_api_number("API# 42-501-20130-01-00")
        assert result is not None
        assert result["confidence"] == 0.95

    def test_labeled_no_separator(self):
        result = extract_api_number("API No. 42 501 20130 00 00")
        assert result is not None
        assert result["normalized"] == "42501201300000"

    def test_hyphenated_14(self):
        result = extract_api_number("Well 42-501-20130-00-00 in Ector County")
        assert result is not None
        assert result["formatted"] == "42-501-20130-00-00"

    def test_hyphenated_12(self):
        result = extract_api_number("Well 42-501-20130-03 completed")
        assert result is not None
        assert result["normalized"] == "42501201300300"
        assert result["confidence"] == 0.88

    def test_hyphenated_10(self):
        result = extract_api_number("Well 42-501-20130 in Texas")
        assert result is not None
        assert result["normalized"] == "42501201300000"

    def test_flat_14_valid_state(self):
        result = extract_api_number("Well ID 42501201300000 production")
        assert result is not None
        assert result["state_code"] == "42"

    def test_flat_12_valid_state(self):
        result = extract_api_number("Record 425012013003 found")
        assert result is not None
        assert result["normalized"] == "42501201300300"

    def test_flat_10_valid_state(self):
        result = extract_api_number("Well 4250120130 in district")
        assert result is not None
        assert result["normalized"] == "42501201300000"

    def test_flat_invalid_state_rejected(self):
        result = extract_api_number("Number 99501201300000 is not valid")
        # Should be None because 99 is not a valid state code
        assert result is None

    def test_no_api_number(self):
        result = extract_api_number("This document has no API number")
        assert result is None

    def test_multiple_api_numbers_best_confidence(self):
        text = "API No: 42-501-20130-00-00\nAlso mentioned: 42-501-20130"
        result = extract_api_number(text)
        assert result is not None
        assert result["confidence"] == 0.95  # Labeled has highest confidence

    def test_api_components_parsed(self):
        result = extract_api_number("API No: 42-501-20130-01-02")
        assert result["state_code"] == "42"
        assert result["county_code"] == "501"
        assert result["well_id"] == "20130"
        assert result["sidetrack"] == "01"
        assert result["event"] == "02"

    @pytest.mark.parametrize(
        "state_code,state",
        [
            ("02", "AK"),
            ("05", "CO"),
            ("17", "LA"),
            ("32", "NM"),
            ("35", "ND"),
            ("37", "OK"),
            ("39", "PA"),
            ("42", "TX"),
            ("49", "WY"),
        ],
    )
    def test_valid_state_codes(self, state_code, state):
        result = extract_api_number(f"API No: {state_code}-001-00001")
        assert result is not None
        assert result["state_code"] == state_code


# ============================================================
# Production Volume Extraction
# ============================================================


class TestProductionVolumeExtraction:
    def test_oil_bbls(self):
        result = extract_production_volumes("Oil Production: 1,234 BBL")
        assert result["production_oil_bbl"] is not None
        assert result["production_oil_bbl"]["value"] == 1234.0

    def test_oil_barrels(self):
        result = extract_production_volumes("Oil: 500 barrels")
        assert result["production_oil_bbl"] is not None
        assert result["production_oil_bbl"]["value"] == 500.0

    def test_oil_with_decimal(self):
        result = extract_production_volumes("Crude Production: 1,234.56 BBL")
        assert result["production_oil_bbl"] is not None
        assert result["production_oil_bbl"]["value"] == 1234.56

    def test_gas_mcf(self):
        result = extract_production_volumes("Gas Production: 5,678 MCF")
        assert result["production_gas_mcf"] is not None
        assert result["production_gas_mcf"]["value"] == 5678.0

    def test_gas_mmcf_conversion(self):
        result = extract_production_volumes("Gas: 5.5 MMCF")
        assert result["production_gas_mcf"] is not None
        assert result["production_gas_mcf"]["value"] == 5500.0  # 5.5 * 1000

    def test_gas_mmcf_large_value(self):
        result = extract_production_volumes("Natural Gas Production: 12 MMCF")
        assert result["production_gas_mcf"] is not None
        assert result["production_gas_mcf"]["value"] == 12000.0

    def test_water_bbls(self):
        result = extract_production_volumes("Water Production: 890 BBL")
        assert result["production_water_bbl"] is not None
        assert result["production_water_bbl"]["value"] == 890.0

    def test_produced_water(self):
        result = extract_production_volumes("Produced Water: 450 barrels")
        assert result["production_water_bbl"] is not None
        assert result["production_water_bbl"]["value"] == 450.0

    def test_days_produced(self):
        result = extract_production_volumes("Days Produced: 31")
        assert result["days_produced"] is not None
        assert result["days_produced"]["value"] == 31

    def test_days_on(self):
        result = extract_production_volumes("Days on: 28")
        assert result["days_produced"] is not None
        assert result["days_produced"]["value"] == 28

    def test_no_volumes(self):
        result = extract_production_volumes("No production data here")
        assert all(v is None for v in result.values())


# ============================================================
# Date Extraction
# ============================================================


class TestDateExtraction:
    def test_spud_date(self):
        result = extract_dates("Spud Date: 03/15/2026")
        assert "spud_date" in result
        assert result["spud_date"]["value"] == "2026-03-15"

    def test_completion_date(self):
        result = extract_dates("Completion Date: 02/28/2026")
        assert "completion_date" in result
        assert result["completion_date"]["value"] == "2026-02-28"

    def test_date_completed(self):
        result = extract_dates("Date Completed: 11/30/2025")
        assert "completion_date" in result
        assert result["completion_date"]["value"] == "2025-11-30"

    def test_permit_date(self):
        result = extract_dates("Permit Date: 01-15-2026")
        assert "permit_date" in result
        assert result["permit_date"]["value"] == "2026-01-15"

    def test_reporting_period(self):
        result = extract_dates("Reporting Period: January 2026")
        assert "reporting_period" in result

    def test_plug_date(self):
        result = extract_dates("Plugging Date: 06/01/2025")
        assert "plug_date" in result
        assert result["plug_date"]["value"] == "2025-06-01"

    def test_inspection_date(self):
        result = extract_dates("Inspection Date: 12/20/2025")
        assert "inspection_date" in result
        assert result["inspection_date"]["value"] == "2025-12-20"

    def test_no_dates(self):
        result = extract_dates("No dates in this text")
        assert len(result) == 0


class TestDateParsing:
    @pytest.mark.parametrize(
        "input_date,expected",
        [
            ("03/15/2026", "2026-03-15"),
            ("03-15-2026", "2026-03-15"),
            ("2026-03-15", "2026-03-15"),
            ("15-Mar-2026", "2026-03-15"),
            ("March 15, 2026", "2026-03-15"),
        ],
    )
    def test_date_formats(self, input_date, expected):
        assert _try_parse_date(input_date) == expected

    def test_two_digit_year(self):
        result = _try_parse_date("03/15/26")
        assert result is not None

    def test_invalid_date(self):
        assert _try_parse_date("not a date") is None


# ============================================================
# Operator, Well Name, County Extraction
# ============================================================


class TestOperatorAndWellExtraction:
    def test_operator_name(self):
        result = extract_operator_name("Operator: Devon Energy Corporation\nWell Name:")
        assert result is not None
        assert "Devon Energy" in result["value"]

    def test_operator_lessee(self):
        result = extract_operator_name("Lessee: Pioneer Natural Resources\nCounty:")
        assert result is not None
        assert "Pioneer" in result["value"]

    def test_operator_company(self):
        result = extract_operator_name("Company Name: ConocoPhillips Corp\nAPI")
        assert result is not None
        assert "ConocoPhillips" in result["value"]

    def test_well_name(self):
        result = extract_well_name("Well Name: Permian Basin Unit #42\nAPI")
        assert result is not None
        assert "Permian Basin" in result["value"]

    def test_well_name_with_number(self):
        result = extract_well_name("Well: Smith Ranch #1-14\nWell Number")
        assert result is not None
        assert "Smith Ranch" in result["value"]

    def test_county(self):
        result = extract_county("County: Ector\nState: Texas")
        assert result is not None
        assert result["value"] == "Ector"

    def test_county_with_comma(self):
        result = extract_county("County: Midland, TX")
        assert result is not None
        assert result["value"] == "Midland"


# ============================================================
# Coordinate Extraction
# ============================================================


class TestCoordinateExtraction:
    def test_decimal_degrees(self):
        result = extract_coordinates("Latitude: 31.9505, Longitude: -102.0775")
        assert result is not None
        assert abs(result["latitude"] - 31.9505) < 0.001
        assert abs(result["longitude"] - (-102.0775)) < 0.001

    def test_decimal_degrees_abbreviation(self):
        result = extract_coordinates("Lat: 35.4676, Long: -97.5164")
        assert result is not None
        assert abs(result["latitude"] - 35.4676) < 0.001

    def test_invalid_coordinates_rejected(self):
        result = extract_coordinates("Latitude: 91.0, Longitude: -102.0")
        assert result is None  # Latitude > 72 for US

    def test_no_coordinates(self):
        result = extract_coordinates("No location data")
        assert result is None


# ============================================================
# Permit Number and Well Depth Extraction
# ============================================================


class TestPermitNumberExtraction:
    def test_permit_number(self):
        result = extract_permit_number("Permit No. 12345")
        assert result is not None
        assert result["value"] == "12345"

    def test_permit_number_hash(self):
        result = extract_permit_number("Permit # 987654")
        assert result is not None
        assert result["value"] == "987654"

    def test_no_permit(self):
        result = extract_permit_number("No permit information")
        assert result is None


class TestWellDepthExtraction:
    def test_total_depth_feet(self):
        result = extract_well_depth("Total Depth: 10,500 ft")
        assert result is not None
        assert result["value"] == 10500.0

    def test_td_abbreviation(self):
        result = extract_well_depth("TD: 8,000 feet")
        assert result is not None
        assert result["value"] == 8000.0

    def test_no_depth(self):
        result = extract_well_depth("No depth information")
        assert result is None


# ============================================================
# DataExtractor Integration
# ============================================================


class TestDataExtractor:
    def test_full_extraction_production_report(self):
        text = """
        Operator: Devon Energy Corporation
        Well Name: Permian Unit #42
        API Number: 42-501-20130-00-00
        County: Ector
        Reporting Period: January 2026
        Oil Production: 1,234 BBL
        Gas Production: 5,678 MCF
        Days Produced: 31
        """
        extractor = DataExtractor()
        result = extractor.extract(text, doc_type="production_report", state="TX")
        assert "api_number" in result.fields
        assert "operator_name" in result.fields
        assert "production_oil_bbl" in result.fields
        assert "production_gas_mcf" in result.fields
        assert result.fields["api_number"].confidence >= 0.85

    def test_full_extraction_well_permit(self):
        text = """
        Operator: Pioneer Natural Resources
        Well Name: Spraberry Unit #7
        API No: 42-329-33456
        County: Midland
        Permit No. 456789
        Permit Date: 01/10/2026
        Total Depth: 12,000 ft
        """
        extractor = DataExtractor()
        result = extractor.extract(text, doc_type="well_permit", state="TX")
        assert "api_number" in result.fields
        assert "permit_number" in result.fields
        assert "well_depth_ft" in result.fields
        assert "permit_date" in result.fields

    def test_missing_fields_logged(self):
        extractor = DataExtractor()
        result = extractor.extract("No useful data here", doc_type="production_report")
        assert len(result.extraction_errors) > 0

    def test_production_not_extracted_for_permits(self):
        """Production volumes should not be extracted for well_permit documents."""
        text = """
        API No: 42-501-20130
        Operator: Devon Energy Corp
        Oil Production: 500 BBL
        """
        extractor = DataExtractor()
        result = extractor.extract(text, doc_type="well_permit", state="TX")
        assert "production_oil_bbl" not in result.fields

    def test_extraction_result_metadata(self):
        extractor = DataExtractor()
        result = extractor.extract("API No: 42-501-20130", doc_type="well_permit", state="TX")
        assert result.doc_type == "well_permit"
        assert result.state == "TX"
        assert "API No: 42-501-20130" in result.raw_text

    def test_field_value_attributes(self):
        text = "API No: 42-501-20130-00-00"
        extractor = DataExtractor()
        result = extractor.extract(text, doc_type="production_report", state="TX")
        fv = result.fields["api_number"]
        assert isinstance(fv, FieldValue)
        assert fv.extraction_method == "regex"
        assert fv.pattern_specificity == 1.0  # labeled pattern
        assert fv.confidence == 0.95
        assert fv.source_text is not None
