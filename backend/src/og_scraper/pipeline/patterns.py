"""
Regex patterns for extracting structured data from O&G documents.

Pattern naming convention: <field>_<specificity>
- "labeled" = preceded by a label like "API No:" (highest confidence)
- "hyphenated" = standard hyphenated format (medium confidence)
- "flat" = bare digit sequence (lowest confidence)
"""

from __future__ import annotations

import re
from datetime import datetime

# ============================================================
# API NUMBER PATTERNS
# Format: SS-CCC-WWWWW-SS-EE (state-county-well-sidetrack-event)
# ============================================================

API_NUMBER_PATTERNS = {
    # Labeled API numbers (highest confidence: 0.95)
    "api_labeled": r"(?:API\s*(?:No\.?|Number|#|Num)?\s*[:.]?\s*)(\d{2}[-\s]?\d{3}[-\s]?\d{5}(?:[-\s]?\d{2})?(?:[-\s]?\d{2})?)",
    # Full 14-digit with hyphens (confidence: 0.90)
    "api_14_hyphen": r"\b(\d{2}-\d{3}-\d{5}-\d{2}-\d{2})\b",
    # 12-digit with hyphens (confidence: 0.88)
    "api_12_hyphen": r"\b(\d{2}-\d{3}-\d{5}-\d{2})\b",
    # 10-digit with hyphens (confidence: 0.85)
    "api_10_hyphen": r"\b(\d{2}-\d{3}-\d{5})\b",
    # Flat digits — only accept if state code is valid (confidence: 0.70)
    "api_14_flat": r"\b(\d{14})\b",
    "api_12_flat": r"\b(\d{12})\b",
    "api_10_flat": r"\b(\d{10})\b",
}

API_PATTERN_CONFIDENCE = {
    "api_labeled": 0.95,
    "api_14_hyphen": 0.90,
    "api_12_hyphen": 0.88,
    "api_10_hyphen": 0.85,
    "api_14_flat": 0.70,
    "api_12_flat": 0.68,
    "api_10_flat": 0.65,
}

# Valid state codes for the 10 target states (plus neighbors for validation)
VALID_API_STATE_CODES = {
    "02": "AK",  # Alaska
    "04": "CA",  # California
    "05": "CO",  # Colorado
    "17": "LA",  # Louisiana
    "32": "NM",  # New Mexico
    "35": "ND",  # North Dakota
    "37": "OK",  # Oklahoma
    "39": "PA",  # Pennsylvania
    "42": "TX",  # Texas
    "49": "WY",  # Wyoming
}


def extract_api_number(text: str) -> dict | None:
    """
    Extract the best API number from document text.

    Returns dict with:
    {
        "raw": str,           # Original matched text
        "normalized": str,    # 14-digit zero-padded, no dashes
        "formatted": str,     # Standard format: SS-CCC-WWWWW-SS-EE
        "state_code": str,    # 2-digit state code
        "county_code": str,   # 3-digit county code
        "well_id": str,       # 5-digit well identifier
        "sidetrack": str,     # 2-digit sidetrack code
        "event": str,         # 2-digit event code
        "confidence": float,  # Pattern-based confidence
        "pattern": str,       # Which pattern matched
    }
    or None if no API number found.
    """
    best_match = None
    best_confidence = 0.0

    for pattern_name, pattern in API_NUMBER_PATTERNS.items():
        for match in re.finditer(pattern, text, re.IGNORECASE):
            raw = match.group(1)
            normalized = re.sub(r"[-\s]", "", raw)
            confidence = API_PATTERN_CONFIDENCE[pattern_name]

            # Validate state code for flat patterns (high false positive risk)
            if "flat" in pattern_name:
                state_code = normalized[:2]
                if state_code not in VALID_API_STATE_CODES:
                    continue

            # Zero-pad to 14 digits
            if len(normalized) == 10:
                normalized += "0000"
            elif len(normalized) == 12:
                normalized += "00"
            elif len(normalized) != 14:
                continue  # Invalid length

            if confidence > best_confidence:
                best_confidence = confidence
                best_match = {
                    "raw": raw,
                    "normalized": normalized,
                    "formatted": (
                        f"{normalized[:2]}-{normalized[2:5]}-{normalized[5:10]}-{normalized[10:12]}-{normalized[12:14]}"
                    ),
                    "state_code": normalized[:2],
                    "county_code": normalized[2:5],
                    "well_id": normalized[5:10],
                    "sidetrack": normalized[10:12],
                    "event": normalized[12:14],
                    "confidence": confidence,
                    "pattern": pattern_name,
                }

    return best_match


# ============================================================
# PRODUCTION VOLUME PATTERNS
# ============================================================


def extract_production_volumes(text: str) -> dict[str, dict | None]:
    """
    Extract oil, gas, water production volumes and days produced.

    Returns dict of field_name -> {"value": float, "raw": str, "confidence": float, "pattern": str}
    """
    results: dict[str, dict | None] = {
        "production_oil_bbl": None,
        "production_gas_mcf": None,
        "production_water_bbl": None,
        "days_produced": None,
    }

    # Oil (barrels)
    oil_patterns = [
        (
            r"(?:oil|crude)\s*(?:production|prod\.?)?\s*[:.]?\s*([\d,]+\.?\d*)\s*(?:bbl|bbls?|barrels?)",
            0.90,
        ),
        (
            r"([\d,]+\.?\d*)\s*(?:bbl|bbls?|barrels?)\s*(?:of\s+)?(?:oil|crude)",
            0.85,
        ),
        (r"(?:oil|crude)\s*(?:\(bbl\))?\s*[:|\t]\s*([\d,]+\.?\d*)", 0.80),
    ]
    for pattern, conf in oil_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            results["production_oil_bbl"] = {
                "value": _parse_number(match.group(1)),
                "raw": match.group(0),
                "confidence": conf,
                "pattern": pattern,
            }
            break

    # Gas (MCF) — IMPORTANT: detect MMCF and convert to MCF (* 1000)
    gas_patterns = [
        (
            r"(?:gas|natural\s*gas|casinghead)\s*(?:production|prod\.?)?\s*[:.]?\s*([\d,]+\.?\d*)\s*(mmcf|mcf|cf)",
            0.90,
        ),
        (
            r"([\d,]+\.?\d*)\s*(mmcf|mcf)\s*(?:of\s+)?(?:gas|natural)",
            0.85,
        ),
        (r"(?:gas)\s*(?:\(mcf\))?\s*[:|\t]\s*([\d,]+\.?\d*)", 0.80),
    ]
    for pattern, conf in gas_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            value = _parse_number(match.group(1))
            # MMCF -> MCF conversion
            groups = match.groups()
            unit = groups[1].lower() if len(groups) > 1 else ""
            if unit == "mmcf":
                value *= 1000
            results["production_gas_mcf"] = {
                "value": value,
                "raw": match.group(0),
                "confidence": conf,
                "pattern": pattern,
            }
            break

    # Water (barrels)
    water_patterns = [
        (
            r"(?:water|produced\s*water|brine)\s*(?:production|prod\.?)?\s*[:.]?\s*([\d,]+\.?\d*)\s*(?:bbl|bbls?|barrels?)",
            0.90,
        ),
        (
            r"([\d,]+\.?\d*)\s*(?:bbl|bbls?)\s*(?:of\s+)?(?:water|produced\s*water)",
            0.85,
        ),
        (r"(?:water)\s*(?:\(bbl\))?\s*[:|\t]\s*([\d,]+\.?\d*)", 0.80),
    ]
    for pattern, conf in water_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            results["production_water_bbl"] = {
                "value": _parse_number(match.group(1)),
                "raw": match.group(0),
                "confidence": conf,
                "pattern": pattern,
            }
            break

    # Days produced
    days_patterns = [
        (r"(?:days?\s*(?:produced|producing|on))\s*[:.]?\s*(\d+)", 0.90),
        (r"(\d+)\s*(?:days?\s*(?:produced|producing|on))", 0.85),
        (r"(?:producing\s*days?)\s*[:.]?\s*(\d+)", 0.85),
    ]
    for pattern, conf in days_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            results["days_produced"] = {
                "value": int(match.group(1)),
                "raw": match.group(0),
                "confidence": conf,
                "pattern": pattern,
            }
            break

    return results


# ============================================================
# DATE PATTERNS
# ============================================================

# Labeled date patterns specific to O&G documents
LABELED_DATE_PATTERNS = {
    "spud_date": (
        r"(?:spud\s*date)\s*[:.]?\s*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})",
        0.92,
    ),
    "completion_date": (
        r"(?:completion\s*date|date\s*completed)\s*[:.]?\s*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})",
        0.92,
    ),
    "first_production_date": (
        r"(?:first\s*(?:production|prod\.?)\s*date)\s*[:.]?\s*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})",
        0.90,
    ),
    "permit_date": (
        r"(?:permit\s*date|date\s*(?:of\s+)?permit)\s*[:.]?\s*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})",
        0.92,
    ),
    "reporting_period": (
        r"(?:report(?:ing)?\s*period|production\s*(?:month|period))\s*[:.]?\s*(\w+\s*\d{4}|\d{1,2}[/-]\d{4})",
        0.90,
    ),
    "plug_date": (
        r"(?:plug(?:ging)?\s*date|date\s*plugged)\s*[:.]?\s*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})",
        0.92,
    ),
    "inspection_date": (
        r"(?:inspection\s*date|date\s*(?:of\s+)?inspection)\s*[:.]?\s*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})",
        0.92,
    ),
}

# Supported date format strings for parsing
DATE_PARSE_FORMATS = [
    "%m/%d/%Y",
    "%m-%d-%Y",
    "%m/%d/%y",
    "%m-%d-%y",
    "%Y-%m-%d",
    "%d-%b-%Y",
    "%d-%b-%y",
    "%B %d, %Y",
    "%B %d %Y",
]


def extract_dates(text: str) -> dict[str, dict | None]:
    """
    Extract labeled dates from O&G document text.

    Returns dict of field_name -> {"value": str (ISO), "raw": str, "confidence": float, "pattern": str}
    """
    results: dict[str, dict | None] = {}

    for field_name, (pattern, confidence) in LABELED_DATE_PATTERNS.items():
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            raw_date = match.group(1)
            parsed = _try_parse_date(raw_date)
            results[field_name] = {
                "value": parsed if parsed else raw_date,
                "raw": raw_date,
                "confidence": confidence if parsed else confidence * 0.7,  # Penalty if unparseable
                "pattern": pattern,
                "parsed_successfully": parsed is not None,
            }

    return results


def _try_parse_date(date_str: str) -> str | None:
    """Try to parse a date string into ISO 8601 (YYYY-MM-DD)."""
    for fmt in DATE_PARSE_FORMATS:
        try:
            dt = datetime.strptime(date_str.strip(), fmt)
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None


# ============================================================
# OPERATOR / WELL NAME / LOCATION PATTERNS
# ============================================================


def extract_operator_name(text: str) -> dict | None:
    """Extract operator name from document text."""
    patterns = [
        (
            r"(?:operator|lessee|company)\s*(?:name)?\s*[:.]?\s*([A-Z][A-Za-z\s&.,\'()\-]+?)(?:\n|\r|operator|lease|well|api|county)",
            0.88,
        ),
        (
            r"(?:filed\s*by|submitted\s*by|reported\s*by)\s*[:.]?\s*([A-Z][A-Za-z\s&.,\'()\-]+?)(?:\n|\r)",
            0.85,
        ),
    ]
    for pattern, confidence in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            name = match.group(1).strip().rstrip(",.")
            if 3 < len(name) < 100:
                return {
                    "value": name,
                    "raw": match.group(0).strip(),
                    "confidence": confidence,
                    "pattern": pattern,
                }
    return None


def extract_well_name(text: str) -> dict | None:
    """Extract well name from document text."""
    patterns = [
        (
            r"(?:well\s*name|well)\s*[:.]?\s*([A-Za-z0-9\s#\'\-]+?)(?:\n|\r|well\s*(?:no|number)|api)",
            0.85,
        ),
        (
            r"(?:lease\s*(?:name|&\s*well))\s*[:.]?\s*([A-Za-z0-9\s#\'\-]+?)(?:\n|\r)",
            0.82,
        ),
    ]
    for pattern, confidence in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            name = match.group(1).strip()
            if 1 < len(name) < 80:
                return {
                    "value": name,
                    "raw": match.group(0).strip(),
                    "confidence": confidence,
                    "pattern": pattern,
                }
    return None


def extract_county(text: str) -> dict | None:
    """Extract county name from document text."""
    pattern = r"(?:county)\s*[:.]?\s*([A-Za-z\s]+?)(?:\n|,|\s+state|\s+district)"
    match = re.search(pattern, text, re.IGNORECASE)
    if match:
        county = match.group(1).strip()
        if 2 < len(county) < 50:
            return {
                "value": county,
                "raw": match.group(0).strip(),
                "confidence": 0.85,
                "pattern": pattern,
            }
    return None


def extract_coordinates(text: str) -> dict | None:
    """
    Extract latitude/longitude coordinates from document text.
    Handles decimal degrees and DMS (degrees-minutes-seconds) formats.
    """
    # Decimal degrees (e.g., "Lat: 31.9505, Long: -102.0775")
    dd_pattern = (
        r"(?:lat(?:itude)?)\s*[:.]?\s*(-?\d{1,3}\.\d{2,7})\s*[,;/\s]+\s*"
        r"(?:lon(?:g(?:itude)?)?)\s*[:.]?\s*(-?\d{1,3}\.\d{2,7})"
    )
    match = re.search(dd_pattern, text, re.IGNORECASE)
    if match:
        lat = float(match.group(1))
        lon = float(match.group(2))
        # Basic sanity check for continental US + Alaska
        if 24.0 <= lat <= 72.0 and -180.0 <= lon <= -66.0:
            return {
                "latitude": lat,
                "longitude": lon,
                "raw": match.group(0),
                "confidence": 0.90,
                "pattern": "decimal_degrees",
            }

    # DMS format (e.g., "31deg 57' 02" N, 102deg 04' 39" W")
    dms_pattern = (
        r"(\d{1,3})\s*[°]\s*(\d{1,2})\s*['\u2019]\s*"
        r"(\d{1,2}(?:\.\d+)?)\s*[\"\"]\s*([NS])\s*[,;/\s]+\s*"
        r"(\d{1,3})\s*[°]\s*(\d{1,2})\s*['\u2019]\s*"
        r"(\d{1,2}(?:\.\d+)?)\s*[\"\"]\s*([EW])"
    )
    match = re.search(dms_pattern, text)
    if match:
        lat = _dms_to_dd(
            int(match.group(1)),
            int(match.group(2)),
            float(match.group(3)),
            match.group(4),
        )
        lon = _dms_to_dd(
            int(match.group(5)),
            int(match.group(6)),
            float(match.group(7)),
            match.group(8),
        )
        if 24.0 <= lat <= 72.0 and -180.0 <= lon <= -66.0:
            return {
                "latitude": lat,
                "longitude": lon,
                "raw": match.group(0),
                "confidence": 0.85,
                "pattern": "dms",
            }

    return None


def _dms_to_dd(degrees: int, minutes: int, seconds: float, direction: str) -> float:
    """Convert degrees-minutes-seconds to decimal degrees."""
    dd = degrees + minutes / 60 + seconds / 3600
    if direction in ("S", "W"):
        dd = -dd
    return round(dd, 7)


def extract_permit_number(text: str) -> dict | None:
    """Extract permit number from document text."""
    pattern = r"(?:permit\s*(?:no\.?|number|#))\s*[:.]?\s*(\d{3,12})"
    match = re.search(pattern, text, re.IGNORECASE)
    if match:
        return {
            "value": match.group(1),
            "raw": match.group(0).strip(),
            "confidence": 0.88,
            "pattern": pattern,
        }
    return None


def extract_well_depth(text: str) -> dict | None:
    """Extract well depth (total depth or measured depth) in feet."""
    patterns = [
        (
            r"(?:total\s*depth|td|measured\s*depth|md)\s*[:.]?\s*([\d,]+)\s*(?:ft|feet|\')",
            0.88,
        ),
        (r"([\d,]+)\s*(?:ft|feet)\s*(?:total\s*depth|td)", 0.85),
    ]
    for pattern, confidence in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return {
                "value": _parse_number(match.group(1)),
                "raw": match.group(0).strip(),
                "confidence": confidence,
                "pattern": pattern,
            }
    return None


def _parse_number(s: str) -> float:
    """Parse a number string, handling commas and whitespace."""
    cleaned = s.replace(",", "").replace(" ", "").strip()
    try:
        return float(cleaned)
    except ValueError:
        return 0.0
