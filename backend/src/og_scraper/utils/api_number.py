"""API number normalization and validation utilities.

API numbers are the primary identifier for oil and gas wells in the US.
Format: SS-CCC-NNNNN-SS-SS (state-county-unique-sidetrack-event)
Stored as 14-digit VARCHAR without dashes, zero-padded.
"""

import re


def normalize_api_number(raw: str) -> str:
    """Normalize an API number to 14-digit format without dashes.

    Strips all non-digit characters, then right-pads with zeros to 14 digits.

    Args:
        raw: Raw API number in any format (with dashes, spaces, etc.)

    Returns:
        14-digit string without dashes, or the original string if < 10 digits.

    Examples:
        >>> normalize_api_number("42-501-20130-03-00")
        '42501201300300'
        >>> normalize_api_number("42501201300300")
        '42501201300300'
        >>> normalize_api_number("4250120130")
        '42501201300000'
        >>> normalize_api_number("425012013003")
        '42501201300300'
    """
    digits = re.sub(r"[^0-9]", "", raw.strip())

    if len(digits) < 10:
        return raw  # Too short to be a valid API number

    # Right-pad to 14 digits
    return digits.ljust(14, "0")[:14]


def format_api_number(normalized: str) -> str:
    """Format a 14-digit API number with dashes for display.

    Args:
        normalized: 14-digit API number without dashes

    Returns:
        Formatted string: SS-CCC-NNNNN-SS-SS

    Example:
        >>> format_api_number("42501201300300")
        '42-501-20130-03-00'
    """
    if len(normalized) != 14 or not normalized.isdigit():
        return normalized
    return f"{normalized[:2]}-{normalized[2:5]}-{normalized[5:10]}-{normalized[10:12]}-{normalized[12:14]}"


def extract_api_10(api_number: str) -> str:
    """Extract the first 10 digits of an API number for cross-referencing.

    The 10-digit prefix (state + county + unique well number) is the
    most common format used for matching across systems.

    Args:
        api_number: Normalized 14-digit API number

    Returns:
        First 10 digits
    """
    digits = re.sub(r"[^0-9]", "", api_number)
    return digits[:10]


def validate_api_number(api_number: str) -> bool:
    """Check if a string looks like a valid API number.

    Validates that it contains at least 10 digits after stripping
    non-digit characters.

    Args:
        api_number: Raw or normalized API number

    Returns:
        True if valid, False otherwise
    """
    digits = re.sub(r"[^0-9]", "", api_number)
    return 10 <= len(digits) <= 14


# Known state codes for the first 2 digits of API numbers
API_STATE_CODES = {
    "02": "AK",
    "04": "CA",
    "05": "CO",
    "17": "LA",
    "30": "NM",
    "33": "ND",
    "35": "OK",
    "37": "PA",
    "42": "TX",
    "49": "WY",
}


def state_from_api_number(api_number: str) -> str | None:
    """Extract the state code from an API number's first 2 digits.

    Args:
        api_number: Raw or normalized API number

    Returns:
        2-letter state code, or None if not recognized
    """
    digits = re.sub(r"[^0-9]", "", api_number)
    if len(digits) >= 2:
        return API_STATE_CODES.get(digits[:2])
    return None
