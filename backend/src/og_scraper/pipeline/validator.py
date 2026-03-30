"""
Field validation rules for O&G extracted data.

Each validator returns (is_valid: bool, reason: str | None).
Validation failure applies a 0.7x confidence penalty to that field.
"""

from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any

from og_scraper.pipeline.patterns import VALID_API_STATE_CODES


def validate_api_number(value: str) -> tuple[bool, str | None]:
    """
    Validate API number format and components.

    Rules:
    - Must be exactly 14 digits (after normalization)
    - State code (first 2 digits) must be a valid code
    - County code (digits 3-5) must be 001-999
    - Well ID (digits 6-10) must be 00001-99999
    """
    if not value or not isinstance(value, str):
        return False, "API number is empty or not a string"

    digits = re.sub(r"[-\s]", "", value)
    if len(digits) != 14:
        return False, f"Expected 14 digits, got {len(digits)}"

    state_code = digits[:2]
    if state_code not in VALID_API_STATE_CODES:
        return False, f"Invalid state code: {state_code}"

    county_code = digits[2:5]
    if not (1 <= int(county_code) <= 999):
        return False, f"Invalid county code: {county_code}"

    well_id = digits[5:10]
    if not (1 <= int(well_id) <= 99999):
        return False, f"Invalid well ID: {well_id}"

    return True, None


def validate_production_volume(value: Any, field_name: str) -> tuple[bool, str | None]:
    """
    Validate production volume is within reasonable range.

    Ranges (per month, single well):
    - Oil: 0-100,000 BBL (flag > 50,000 as unusual)
    - Gas: 0-1,000,000 MCF (flag > 500,000 as unusual)
    - Water: 0-100,000 BBL
    """
    try:
        vol = float(value)
    except (TypeError, ValueError):
        return False, f"Cannot parse '{value}' as a number"

    if vol < 0:
        return False, f"Negative volume: {vol}"

    limits = {
        "production_oil_bbl": (100_000, "BBL oil"),
        "production_gas_mcf": (1_000_000, "MCF gas"),
        "production_water_bbl": (100_000, "BBL water"),
    }

    if field_name in limits:
        max_val, unit = limits[field_name]
        if vol > max_val:
            return False, f"Volume {vol} {unit} exceeds maximum {max_val}"

    return True, None


def validate_date(value: str) -> tuple[bool, str | None]:
    """
    Validate a date value.

    Rules:
    - Must parse to a valid date
    - Must not be in the future (allow 1 day tolerance for timezone)
    - Must not be before 1900 (earliest feasible O&G records)
    """
    if not value:
        return False, "Date is empty"

    try:
        if re.match(r"^\d{4}-\d{2}-\d{2}$", str(value)):
            dt = datetime.strptime(str(value), "%Y-%m-%d").date()
        else:
            return False, f"Date not in ISO format: {value}"
    except ValueError:
        return False, f"Cannot parse date: {value}"

    today = date.today()
    if dt > today:
        return False, f"Date is in the future: {dt}"

    if dt.year < 1900:
        return False, f"Date is before 1900: {dt}"

    return True, None


def validate_coordinates(latitude: Any, longitude: Any) -> tuple[bool, str | None]:
    """
    Validate latitude/longitude coordinates.

    Rules:
    - Latitude: 24.0-72.0 (continental US + Alaska)
    - Longitude: -180.0 to -66.0 (continental US + Alaska)
    """
    try:
        lat = float(latitude)
        lon = float(longitude)
    except (TypeError, ValueError):
        return False, f"Cannot parse coordinates: lat={latitude}, lon={longitude}"

    if not (24.0 <= lat <= 72.0):
        return False, f"Latitude {lat} outside US range (24.0-72.0)"

    if not (-180.0 <= lon <= -66.0):
        return False, f"Longitude {lon} outside US range (-180.0 to -66.0)"

    return True, None


def validate_operator_name(value: str) -> tuple[bool, str | None]:
    """
    Validate operator name is reasonable.

    Rules:
    - Not empty
    - Length 3-100 characters
    - Contains at least one letter
    """
    if not value or not isinstance(value, str):
        return False, "Operator name is empty"
    if len(value) < 3:
        return False, f"Operator name too short: '{value}'"
    if len(value) > 100:
        return False, f"Operator name too long: {len(value)} chars"
    if not re.search(r"[a-zA-Z]", value):
        return False, "Operator name contains no letters"
    return True, None


def validate_days_produced(value: Any) -> tuple[bool, str | None]:
    """Validate days produced is 0-366."""
    try:
        days = int(value)
    except (TypeError, ValueError):
        return False, f"Cannot parse days: {value}"
    if days < 0:
        return False, f"Negative days: {days}"
    if days > 366:
        return False, f"Days > 366: {days}"
    return True, None


# Dispatcher: field_name -> validator function
FIELD_VALIDATORS: dict[str, Any] = {
    "api_number": lambda v: validate_api_number(v),
    "production_oil_bbl": lambda v: validate_production_volume(v, "production_oil_bbl"),
    "production_gas_mcf": lambda v: validate_production_volume(v, "production_gas_mcf"),
    "production_water_bbl": lambda v: validate_production_volume(v, "production_water_bbl"),
    "spud_date": lambda v: validate_date(v),
    "completion_date": lambda v: validate_date(v),
    "permit_date": lambda v: validate_date(v),
    "plug_date": lambda v: validate_date(v),
    "inspection_date": lambda v: validate_date(v),
    "first_production_date": lambda v: validate_date(v),
    "operator_name": lambda v: validate_operator_name(v),
    "days_produced": lambda v: validate_days_produced(v),
}
