import pytest

from og_scraper.pipeline.validator import (
    validate_api_number,
    validate_coordinates,
    validate_date,
    validate_days_produced,
    validate_operator_name,
    validate_production_volume,
)


class TestAPINumberValidation:
    def test_valid_14_digit(self):
        is_valid, reason = validate_api_number("42501201300000")
        assert is_valid
        assert reason is None

    def test_valid_14_digit_with_hyphens(self):
        is_valid, reason = validate_api_number("42-501-20130-00-00")
        assert is_valid
        assert reason is None

    def test_invalid_state_code(self):
        is_valid, reason = validate_api_number("99501201300000")
        assert not is_valid
        assert "state code" in reason.lower()

    def test_wrong_length(self):
        is_valid, reason = validate_api_number("4250120130")
        assert not is_valid
        assert "14 digits" in reason

    def test_empty(self):
        is_valid, reason = validate_api_number("")
        assert not is_valid

    def test_none(self):
        is_valid, reason = validate_api_number(None)
        assert not is_valid

    def test_zero_county_code(self):
        is_valid, reason = validate_api_number("42000201300000")
        assert not is_valid
        assert "county" in reason.lower()

    def test_zero_well_id(self):
        is_valid, reason = validate_api_number("42501000000000")
        assert not is_valid
        assert "well" in reason.lower()

    def test_valid_colorado(self):
        is_valid, reason = validate_api_number("05123456780000")
        assert is_valid

    def test_valid_north_dakota(self):
        is_valid, reason = validate_api_number("35053123450000")
        assert is_valid


class TestProductionVolumeValidation:
    def test_valid_oil(self):
        is_valid, _ = validate_production_volume(1234.5, "production_oil_bbl")
        assert is_valid

    def test_zero_is_valid(self):
        is_valid, _ = validate_production_volume(0, "production_oil_bbl")
        assert is_valid

    def test_negative_invalid(self):
        is_valid, reason = validate_production_volume(-100, "production_oil_bbl")
        assert not is_valid
        assert "negative" in reason.lower()

    def test_over_limit_oil_invalid(self):
        is_valid, reason = validate_production_volume(200_000, "production_oil_bbl")
        assert not is_valid
        assert "exceeds" in reason.lower()

    def test_over_limit_gas_invalid(self):
        is_valid, reason = validate_production_volume(2_000_000, "production_gas_mcf")
        assert not is_valid
        assert "exceeds" in reason.lower()

    def test_over_limit_water_invalid(self):
        is_valid, reason = validate_production_volume(200_000, "production_water_bbl")
        assert not is_valid
        assert "exceeds" in reason.lower()

    def test_non_numeric_invalid(self):
        is_valid, reason = validate_production_volume("not a number", "production_oil_bbl")
        assert not is_valid

    def test_valid_gas(self):
        is_valid, _ = validate_production_volume(500_000, "production_gas_mcf")
        assert is_valid

    def test_string_number_valid(self):
        is_valid, _ = validate_production_volume("1234.5", "production_oil_bbl")
        assert is_valid

    def test_unknown_field_name_no_limit(self):
        """Unknown production fields should still validate positive values."""
        is_valid, _ = validate_production_volume(999_999, "production_unknown")
        assert is_valid


class TestDateValidation:
    def test_valid_iso_date(self):
        is_valid, _ = validate_date("2026-03-15")
        assert is_valid

    def test_future_date_invalid(self):
        is_valid, reason = validate_date("2099-01-01")
        assert not is_valid
        assert "future" in reason.lower()

    def test_ancient_date_invalid(self):
        is_valid, reason = validate_date("1800-01-01")
        assert not is_valid
        assert "1900" in reason

    def test_non_iso_format_invalid(self):
        is_valid, reason = validate_date("03/15/2026")
        assert not is_valid
        assert "ISO" in reason

    def test_empty_invalid(self):
        is_valid, _ = validate_date("")
        assert not is_valid

    def test_valid_old_date(self):
        is_valid, _ = validate_date("1950-06-15")
        assert is_valid

    def test_boundary_year_1900(self):
        is_valid, _ = validate_date("1900-01-01")
        assert is_valid

    def test_invalid_date_string(self):
        is_valid, reason = validate_date("2026-13-45")
        assert not is_valid
        assert "parse" in reason.lower()


class TestCoordinateValidation:
    def test_valid_texas(self):
        is_valid, _ = validate_coordinates(31.9505, -102.0775)
        assert is_valid

    def test_valid_alaska(self):
        is_valid, _ = validate_coordinates(64.0, -150.0)
        assert is_valid

    def test_latitude_too_high(self):
        is_valid, reason = validate_coordinates(75.0, -102.0)
        assert not is_valid
        assert "Latitude" in reason

    def test_latitude_too_low(self):
        is_valid, reason = validate_coordinates(20.0, -102.0)
        assert not is_valid
        assert "Latitude" in reason

    def test_longitude_too_east(self):
        is_valid, reason = validate_coordinates(31.0, -60.0)
        assert not is_valid
        assert "Longitude" in reason

    def test_longitude_too_west(self):
        """Longitude more negative than -180 should fail."""
        is_valid, reason = validate_coordinates(31.0, -185.0)
        assert not is_valid
        assert "Longitude" in reason

    def test_non_numeric_coordinates(self):
        is_valid, reason = validate_coordinates("abc", -102.0)
        assert not is_valid
        assert "Cannot parse" in reason

    def test_boundary_values(self):
        """Test edge coordinates within US range."""
        is_valid, _ = validate_coordinates(24.0, -180.0)
        assert is_valid
        is_valid, _ = validate_coordinates(72.0, -66.0)
        assert is_valid


class TestOperatorNameValidation:
    def test_valid(self):
        is_valid, _ = validate_operator_name("Devon Energy Corporation")
        assert is_valid

    def test_too_short(self):
        is_valid, _ = validate_operator_name("AB")
        assert not is_valid

    def test_no_letters(self):
        is_valid, _ = validate_operator_name("12345")
        assert not is_valid

    def test_empty(self):
        is_valid, _ = validate_operator_name("")
        assert not is_valid

    def test_none(self):
        is_valid, _ = validate_operator_name(None)
        assert not is_valid

    def test_too_long(self):
        is_valid, reason = validate_operator_name("A" * 101)
        assert not is_valid
        assert "too long" in reason.lower()

    def test_minimum_valid_length(self):
        is_valid, _ = validate_operator_name("ABC")
        assert is_valid

    def test_with_special_characters(self):
        is_valid, _ = validate_operator_name("Devon Energy & Production Co., LP")
        assert is_valid


class TestDaysProducedValidation:
    def test_valid(self):
        is_valid, _ = validate_days_produced(31)
        assert is_valid

    def test_zero_valid(self):
        is_valid, _ = validate_days_produced(0)
        assert is_valid

    def test_negative_invalid(self):
        is_valid, _ = validate_days_produced(-1)
        assert not is_valid

    def test_over_366_invalid(self):
        is_valid, _ = validate_days_produced(400)
        assert not is_valid

    def test_boundary_366(self):
        is_valid, _ = validate_days_produced(366)
        assert is_valid

    def test_non_numeric(self):
        is_valid, reason = validate_days_produced("abc")
        assert not is_valid
        assert "Cannot parse" in reason

    def test_string_number_valid(self):
        is_valid, _ = validate_days_produced("31")
        assert is_valid
