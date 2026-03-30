"""Tests for API number normalization utilities."""

from og_scraper.utils.api_number import (
    normalize_api_number,
    format_api_number,
    extract_api_10,
    validate_api_number,
    state_from_api_number,
)


class TestNormalizeAPINumber:
    def test_strip_dashes(self):
        assert normalize_api_number("42-501-20130-03-00") == "42501201300300"

    def test_already_normalized(self):
        assert normalize_api_number("42501201300300") == "42501201300300"

    def test_10_digit_pads_to_14(self):
        assert normalize_api_number("4250120130") == "42501201300000"

    def test_12_digit_pads_to_14(self):
        assert normalize_api_number("425012013003") == "42501201300300"

    def test_too_short_returns_original(self):
        assert normalize_api_number("12345") == "12345"

    def test_strips_spaces(self):
        assert normalize_api_number("42 501 20130 03 00") == "42501201300300"

    def test_mixed_separators(self):
        assert normalize_api_number("42.501.20130.03.00") == "42501201300300"


class TestFormatAPINumber:
    def test_format_14_digit(self):
        assert format_api_number("42501201300300") == "42-501-20130-03-00"

    def test_invalid_length_returns_original(self):
        assert format_api_number("4250120130") == "4250120130"


class TestExtractApi10:
    def test_extract_from_14(self):
        assert extract_api_10("42501201300300") == "4250120130"

    def test_extract_from_formatted(self):
        assert extract_api_10("42-501-20130-03-00") == "4250120130"


class TestValidateAPINumber:
    def test_valid_14_digit(self):
        assert validate_api_number("42501201300300") is True

    def test_valid_10_digit(self):
        assert validate_api_number("4250120130") is True

    def test_valid_with_dashes(self):
        assert validate_api_number("42-501-20130-03-00") is True

    def test_too_short(self):
        assert validate_api_number("12345") is False


class TestStateFromAPINumber:
    def test_texas(self):
        assert state_from_api_number("42501201300300") == "TX"

    def test_alaska(self):
        assert state_from_api_number("02501201300300") == "AK"

    def test_unknown_state(self):
        assert state_from_api_number("99501201300300") is None
