# Task 2.3: Data Extraction & Normalization

## Objective

Implement structured data field extraction from document text using regex patterns, and normalize the extracted values across all 10 states into a consistent schema. This covers: API number extraction/normalization, production volumes with unit conversion, dates in multiple formats to ISO 8601, operator and well names, county, and coordinates. Each extracted field carries a confidence score based on pattern specificity and extraction method.

## Context

This is the third task in Phase 2 (Document Pipeline). It depends on Task 2.1 (text extraction) for the raw text and Task 2.2 (classification) to know which document type to target extraction patterns for. The extracted fields flow into Task 2.4 (Validation & Confidence Scoring) which validates, scores, and routes the document. The database schema from Task 1.2 defines the target field names and types that the normalizer must produce.

## Dependencies

- Task 2.1 - Provides `ExtractionResult.text` (raw extracted text) and `ExtractionResult.pages` (per-page text and confidence)
- Task 1.2 - Defines target database columns: `api_number` (VARCHAR 14), production fields, date fields, location fields

## Blocked By

- Task 2.1, Task 1.2

## Research Findings

Key findings from research files relevant to this task:

- From `document-pipeline-implementation.md`: API numbers follow the format SS-CCC-WWWWW-SS-EE (state-county-well-sidetrack-event). Support 10, 12, and 14 digit variants. Labeled patterns ("API No: ...") have higher confidence (0.95) than bare digit sequences (0.70).
- From `document-pipeline-implementation.md`: Production volumes need MMCF-to-MCF conversion (multiply by 1,000). Watch for unit confusion between MCF, MMCF, and BCF.
- From `document-pipeline-implementation.md`: Dates appear in 5+ formats: MM/DD/YYYY, YYYY-MM-DD, DD-Mon-YYYY, "Month DD, YYYY", MM/YYYY. All must normalize to ISO 8601 (YYYY-MM-DD).
- From `confidence-scoring` skill: Field-level confidence uses base confidence by method (text=0.95, OCR=raw score, regex=0.80-0.90), multiplied by pattern specificity, with 0.7x penalty for failed validation and 1.1x bonus for cross-reference match.
- From DISCOVERY D22: File organization uses `data/{state}/{operator}/{doc_type}/{filename}` — the normalizer must produce slugified operator names.

## Implementation Plan

### Step 1: Define Extraction Data Models

**In `backend/src/og_scraper/pipeline/extractor.py`:**

```python
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class FieldValue:
    """A single extracted field with provenance and confidence."""
    value: Any                    # The extracted value (string, float, int, etc.)
    confidence: float             # 0.0-1.0 field-level confidence
    source_text: str              # The raw text snippet this was extracted from
    pattern_used: str             # Which regex pattern matched (for debugging)
    extraction_method: str        # "regex", "text", "ocr", "table"
    pattern_specificity: float    # 0.0-1.0, how specific the pattern was (labeled > bare)


@dataclass
class ExtractionResult:
    """Result of extracting structured fields from document text."""
    fields: dict[str, FieldValue]  # field_name -> FieldValue
    raw_text: str                   # Original text that was parsed
    doc_type: str                   # Document type (from classifier)
    state: str                      # State code
    extraction_errors: list[str] = field(default_factory=list)  # Non-fatal errors
```

### Step 2: Implement API Number Extraction

**In `backend/src/og_scraper/pipeline/patterns.py`:**

This file contains all regex patterns and extraction functions for O&G data fields.

```python
"""
Regex patterns for extracting structured data from O&G documents.

Pattern naming convention: <field>_<specificity>
- "labeled" = preceded by a label like "API No:" (highest confidence)
- "hyphenated" = standard hyphenated format (medium confidence)
- "flat" = bare digit sequence (lowest confidence)
"""

import re
from typing import Optional

# ============================================================
# API NUMBER PATTERNS
# Format: SS-CCC-WWWWW-SS-EE (state-county-well-sidetrack-event)
# ============================================================

API_NUMBER_PATTERNS = {
    # Labeled API numbers (highest confidence: 0.95)
    "api_labeled": r'(?:API\s*(?:No\.?|Number|#|Num)?\s*[:.]?\s*)(\d{2}[-\s]?\d{3}[-\s]?\d{5}(?:[-\s]?\d{2})?(?:[-\s]?\d{2})?)',
    # Full 14-digit with hyphens (confidence: 0.90)
    "api_14_hyphen": r'\b(\d{2}-\d{3}-\d{5}-\d{2}-\d{2})\b',
    # 12-digit with hyphens (confidence: 0.88)
    "api_12_hyphen": r'\b(\d{2}-\d{3}-\d{5}-\d{2})\b',
    # 10-digit with hyphens (confidence: 0.85)
    "api_10_hyphen": r'\b(\d{2}-\d{3}-\d{5})\b',
    # Flat digits — only accept if state code is valid (confidence: 0.70)
    "api_14_flat": r'\b(\d{14})\b',
    "api_12_flat": r'\b(\d{12})\b',
    "api_10_flat": r'\b(\d{10})\b',
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


def extract_api_number(text: str) -> Optional[dict]:
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
            normalized = re.sub(r'[-\s]', '', raw)
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
                    "formatted": f"{normalized[:2]}-{normalized[2:5]}-{normalized[5:10]}-{normalized[10:12]}-{normalized[12:14]}",
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

def extract_production_volumes(text: str) -> dict[str, Optional[dict]]:
    """
    Extract oil, gas, water production volumes and days produced.

    Returns dict of field_name -> {"value": float, "raw": str, "confidence": float, "pattern": str}
    """
    results: dict[str, Optional[dict]] = {
        "production_oil_bbl": None,
        "production_gas_mcf": None,
        "production_water_bbl": None,
        "days_produced": None,
    }

    # Oil (barrels)
    oil_patterns = [
        (r'(?:oil|crude)\s*(?:production|prod\.?)?\s*[:.]?\s*([\d,]+\.?\d*)\s*(?:bbl|bbls?|barrels?)', 0.90),
        (r'([\d,]+\.?\d*)\s*(?:bbl|bbls?|barrels?)\s*(?:of\s+)?(?:oil|crude)', 0.85),
        (r'(?:oil|crude)\s*(?:\(bbl\))?\s*[:|\t]\s*([\d,]+\.?\d*)', 0.80),
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
        (r'(?:gas|natural\s*gas|casinghead)\s*(?:production|prod\.?)?\s*[:.]?\s*([\d,]+\.?\d*)\s*(mmcf|mcf|cf)', 0.90),
        (r'([\d,]+\.?\d*)\s*(mmcf|mcf)\s*(?:of\s+)?(?:gas|natural)', 0.85),
        (r'(?:gas)\s*(?:\(mcf\))?\s*[:|\t]\s*([\d,]+\.?\d*)', 0.80),
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
        (r'(?:water|produced\s*water|brine)\s*(?:production|prod\.?)?\s*[:.]?\s*([\d,]+\.?\d*)\s*(?:bbl|bbls?|barrels?)', 0.90),
        (r'([\d,]+\.?\d*)\s*(?:bbl|bbls?)\s*(?:of\s+)?(?:water|produced\s*water)', 0.85),
        (r'(?:water)\s*(?:\(bbl\))?\s*[:|\t]\s*([\d,]+\.?\d*)', 0.80),
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
        (r'(?:days?\s*(?:produced|producing|on))\s*[:.]?\s*(\d+)', 0.90),
        (r'(\d+)\s*(?:days?\s*(?:produced|producing|on))', 0.85),
        (r'(?:producing\s*days?)\s*[:.]?\s*(\d+)', 0.85),
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

from datetime import datetime

# Labeled date patterns specific to O&G documents
LABELED_DATE_PATTERNS = {
    "spud_date": (
        r'(?:spud\s*date)\s*[:.]?\s*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})',
        0.92,
    ),
    "completion_date": (
        r'(?:completion\s*date|date\s*completed)\s*[:.]?\s*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})',
        0.92,
    ),
    "first_production_date": (
        r'(?:first\s*(?:production|prod\.?)\s*date)\s*[:.]?\s*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})',
        0.90,
    ),
    "permit_date": (
        r'(?:permit\s*date|date\s*(?:of\s+)?permit)\s*[:.]?\s*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})',
        0.92,
    ),
    "reporting_period": (
        r'(?:report(?:ing)?\s*period|production\s*(?:month|period))\s*[:.]?\s*(\w+\s*\d{4}|\d{1,2}[/-]\d{4})',
        0.90,
    ),
    "plug_date": (
        r'(?:plug(?:ging)?\s*date|date\s*plugged)\s*[:.]?\s*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})',
        0.92,
    ),
    "inspection_date": (
        r'(?:inspection\s*date|date\s*(?:of\s+)?inspection)\s*[:.]?\s*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})',
        0.92,
    ),
}

# Supported date format strings for parsing
DATE_PARSE_FORMATS = [
    "%m/%d/%Y", "%m-%d-%Y",
    "%m/%d/%y", "%m-%d-%y",
    "%Y-%m-%d",
    "%d-%b-%Y", "%d-%b-%y",
    "%B %d, %Y", "%B %d %Y",
]


def extract_dates(text: str) -> dict[str, Optional[dict]]:
    """
    Extract labeled dates from O&G document text.

    Returns dict of field_name -> {"value": str (ISO), "raw": str, "confidence": float, "pattern": str}
    """
    results: dict[str, Optional[dict]] = {}

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


def _try_parse_date(date_str: str) -> Optional[str]:
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

def extract_operator_name(text: str) -> Optional[dict]:
    """Extract operator name from document text."""
    patterns = [
        (r'(?:operator|lessee|company)\s*(?:name)?\s*[:.]?\s*([A-Z][A-Za-z\s&.,\'()\-]+?)(?:\n|\r|operator|lease|well|api|county)', 0.88),
        (r'(?:filed\s*by|submitted\s*by|reported\s*by)\s*[:.]?\s*([A-Z][A-Za-z\s&.,\'()\-]+?)(?:\n|\r)', 0.85),
    ]
    for pattern, confidence in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            name = match.group(1).strip().rstrip(',.')
            if 3 < len(name) < 100:
                return {
                    "value": name,
                    "raw": match.group(0).strip(),
                    "confidence": confidence,
                    "pattern": pattern,
                }
    return None


def extract_well_name(text: str) -> Optional[dict]:
    """Extract well name from document text."""
    patterns = [
        (r'(?:well\s*name|well)\s*[:.]?\s*([A-Za-z0-9\s#\'\-]+?)(?:\n|\r|well\s*(?:no|number)|api)', 0.85),
        (r'(?:lease\s*(?:name|&\s*well))\s*[:.]?\s*([A-Za-z0-9\s#\'\-]+?)(?:\n|\r)', 0.82),
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


def extract_county(text: str) -> Optional[dict]:
    """Extract county name from document text."""
    pattern = r'(?:county)\s*[:.]?\s*([A-Za-z\s]+?)(?:\n|,|\s+state|\s+district)'
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


def extract_coordinates(text: str) -> Optional[dict]:
    """
    Extract latitude/longitude coordinates from document text.
    Handles decimal degrees and DMS (degrees-minutes-seconds) formats.
    """
    # Decimal degrees (e.g., "Lat: 31.9505, Long: -102.0775")
    dd_pattern = r'(?:lat(?:itude)?)\s*[:.]?\s*(-?\d{1,3}\.\d{2,7})\s*[,;/\s]+\s*(?:lon(?:g(?:itude)?)?)\s*[:.]?\s*(-?\d{1,3}\.\d{2,7})'
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

    # DMS format (e.g., "31° 57' 02\" N, 102° 04' 39\" W")
    dms_pattern = r"(\d{1,3})\s*[°]\s*(\d{1,2})\s*['\u2019]\s*(\d{1,2}(?:\.\d+)?)\s*[\"\"]\s*([NS])\s*[,;/\s]+\s*(\d{1,3})\s*[°]\s*(\d{1,2})\s*['\u2019]\s*(\d{1,2}(?:\.\d+)?)\s*[\"\"]\s*([EW])"
    match = re.search(dms_pattern, text)
    if match:
        lat = _dms_to_dd(
            int(match.group(1)), int(match.group(2)),
            float(match.group(3)), match.group(4)
        )
        lon = _dms_to_dd(
            int(match.group(5)), int(match.group(6)),
            float(match.group(7)), match.group(8)
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


def extract_permit_number(text: str) -> Optional[dict]:
    """Extract permit number from document text."""
    pattern = r'(?:permit\s*(?:no\.?|number|#))\s*[:.]?\s*(\d{3,12})'
    match = re.search(pattern, text, re.IGNORECASE)
    if match:
        return {
            "value": match.group(1),
            "raw": match.group(0).strip(),
            "confidence": 0.88,
            "pattern": pattern,
        }
    return None


def extract_well_depth(text: str) -> Optional[dict]:
    """Extract well depth (total depth or measured depth) in feet."""
    patterns = [
        (r'(?:total\s*depth|td|measured\s*depth|md)\s*[:.]?\s*([\d,]+)\s*(?:ft|feet|\')', 0.88),
        (r'([\d,]+)\s*(?:ft|feet)\s*(?:total\s*depth|td)', 0.85),
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
```

### Step 3: Implement the DataExtractor Class

**In `backend/src/og_scraper/pipeline/extractor.py`:**

```python
import logging
from pathlib import Path

from og_scraper.pipeline.patterns import (
    extract_api_number,
    extract_production_volumes,
    extract_dates,
    extract_operator_name,
    extract_well_name,
    extract_county,
    extract_coordinates,
    extract_permit_number,
    extract_well_depth,
)

logger = logging.getLogger(__name__)


class DataExtractor:
    """
    Extract structured data fields from O&G document text.

    Uses regex patterns to extract fields. The doc_type from the classifier
    determines which fields are expected (production reports need volumes,
    permits need proposed depth, etc.).
    """

    # Fields expected per document type (for completeness checking)
    EXPECTED_FIELDS: dict[str, list[str]] = {
        "production_report": [
            "api_number", "operator_name", "production_oil_bbl",
            "production_gas_mcf", "production_water_bbl", "days_produced",
            "reporting_period",
        ],
        "well_permit": [
            "api_number", "operator_name", "well_name", "county",
            "permit_number", "permit_date", "well_depth_ft",
        ],
        "completion_report": [
            "api_number", "operator_name", "well_name",
            "completion_date", "well_depth_ft",
        ],
        "plugging_report": [
            "api_number", "operator_name", "well_name", "plug_date",
        ],
        "spacing_order": [
            "operator_name", "county",
        ],
        "inspection_record": [
            "api_number", "operator_name", "inspection_date",
        ],
        "incident_report": [
            "api_number", "operator_name",
        ],
    }

    def extract(
        self, text: str, doc_type: str, state: str = ""
    ) -> ExtractionResult:
        """
        Extract structured data fields from document text.

        Args:
            text: Raw extracted text from TextExtractor
            doc_type: Document type from DocumentClassifier (e.g., "production_report")
            state: State code (e.g., "TX") — used for state-specific patterns

        Returns:
            ExtractionResult with extracted fields and confidence scores
        """
        fields: dict[str, FieldValue] = {}
        errors: list[str] = []

        # Extract API number
        api_result = extract_api_number(text)
        if api_result:
            fields["api_number"] = FieldValue(
                value=api_result["normalized"],
                confidence=api_result["confidence"],
                source_text=api_result["raw"],
                pattern_used=api_result["pattern"],
                extraction_method="regex",
                pattern_specificity=1.0 if api_result["pattern"] == "api_labeled" else 0.8,
            )

        # Extract operator name
        op_result = extract_operator_name(text)
        if op_result:
            fields["operator_name"] = FieldValue(
                value=op_result["value"],
                confidence=op_result["confidence"],
                source_text=op_result["raw"],
                pattern_used=op_result["pattern"],
                extraction_method="regex",
                pattern_specificity=0.85,
            )

        # Extract well name
        well_result = extract_well_name(text)
        if well_result:
            fields["well_name"] = FieldValue(
                value=well_result["value"],
                confidence=well_result["confidence"],
                source_text=well_result["raw"],
                pattern_used=well_result["pattern"],
                extraction_method="regex",
                pattern_specificity=0.80,
            )

        # Extract county
        county_result = extract_county(text)
        if county_result:
            fields["county"] = FieldValue(
                value=county_result["value"],
                confidence=county_result["confidence"],
                source_text=county_result["raw"],
                pattern_used=county_result["pattern"],
                extraction_method="regex",
                pattern_specificity=0.80,
            )

        # Extract coordinates
        coord_result = extract_coordinates(text)
        if coord_result:
            fields["latitude"] = FieldValue(
                value=coord_result["latitude"],
                confidence=coord_result["confidence"],
                source_text=coord_result["raw"],
                pattern_used=coord_result["pattern"],
                extraction_method="regex",
                pattern_specificity=0.90,
            )
            fields["longitude"] = FieldValue(
                value=coord_result["longitude"],
                confidence=coord_result["confidence"],
                source_text=coord_result["raw"],
                pattern_used=coord_result["pattern"],
                extraction_method="regex",
                pattern_specificity=0.90,
            )

        # Extract production volumes (if applicable document type)
        if doc_type in ("production_report", "completion_report", "unknown"):
            volumes = extract_production_volumes(text)
            for field_name, vol_result in volumes.items():
                if vol_result:
                    fields[field_name] = FieldValue(
                        value=vol_result["value"],
                        confidence=vol_result["confidence"],
                        source_text=vol_result["raw"],
                        pattern_used=vol_result["pattern"],
                        extraction_method="regex",
                        pattern_specificity=0.85,
                    )

        # Extract dates
        dates = extract_dates(text)
        for field_name, date_result in dates.items():
            if date_result:
                fields[field_name] = FieldValue(
                    value=date_result["value"],
                    confidence=date_result["confidence"],
                    source_text=date_result["raw"],
                    pattern_used=date_result["pattern"],
                    extraction_method="regex",
                    pattern_specificity=0.90 if date_result.get("parsed_successfully") else 0.65,
                )

        # Extract permit number
        permit_result = extract_permit_number(text)
        if permit_result:
            fields["permit_number"] = FieldValue(
                value=permit_result["value"],
                confidence=permit_result["confidence"],
                source_text=permit_result["raw"],
                pattern_used=permit_result["pattern"],
                extraction_method="regex",
                pattern_specificity=0.85,
            )

        # Extract well depth
        depth_result = extract_well_depth(text)
        if depth_result:
            fields["well_depth_ft"] = FieldValue(
                value=depth_result["value"],
                confidence=depth_result["confidence"],
                source_text=depth_result["raw"],
                pattern_used=depth_result["pattern"],
                extraction_method="regex",
                pattern_specificity=0.85,
            )

        # Log missing expected fields
        expected = self.EXPECTED_FIELDS.get(doc_type, [])
        for expected_field in expected:
            if expected_field not in fields:
                errors.append(f"Missing expected field '{expected_field}' for {doc_type}")

        return ExtractionResult(
            fields=fields,
            raw_text=text,
            doc_type=doc_type,
            state=state,
            extraction_errors=errors,
        )
```

### Step 4: Implement the Normalizer

**In `backend/src/og_scraper/pipeline/normalizer.py`:**

The normalizer converts state-specific field values into a consistent schema.

```python
"""
Cross-state normalization for extracted O&G document data.

Normalizes:
- API numbers → 14-digit zero-padded, no dashes
- Dates → ISO 8601 (YYYY-MM-DD)
- Production volumes → standard units (BBL for oil/water, MCF for gas)
- Depths → feet (convert from meters if needed)
- Operator names → trimmed, title-cased, canonical form
- State names → 2-letter codes
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Any, Optional

from og_scraper.pipeline.extractor import ExtractionResult, FieldValue


@dataclass
class NormalizationResult:
    """Result of normalizing extracted fields."""
    fields: dict[str, Any]           # Normalized field values (ready for database)
    original_fields: dict[str, Any]  # Pre-normalization values for audit
    normalizations_applied: list[str]  # List of normalizations performed
    warnings: list[str]              # Non-fatal normalization issues


class DataNormalizer:
    """
    Normalize extracted field values across states into a consistent schema.
    """

    def normalize(self, extraction: ExtractionResult) -> NormalizationResult:
        """
        Normalize all extracted fields.

        Args:
            extraction: ExtractionResult from DataExtractor

        Returns:
            NormalizationResult with normalized values and audit trail
        """
        normalized: dict[str, Any] = {}
        originals: dict[str, Any] = {}
        applied: list[str] = []
        warnings: list[str] = []

        for field_name, field_val in extraction.fields.items():
            originals[field_name] = field_val.value

            if field_name == "api_number":
                normalized[field_name] = self._normalize_api_number(
                    field_val.value, applied, warnings
                )
            elif field_name in ("production_oil_bbl", "production_water_bbl"):
                normalized[field_name] = self._normalize_volume_bbl(
                    field_val.value, field_name, applied, warnings
                )
            elif field_name == "production_gas_mcf":
                normalized[field_name] = self._normalize_volume_mcf(
                    field_val.value, applied, warnings
                )
            elif field_name.endswith("_date") or field_name == "reporting_period":
                normalized[field_name] = self._normalize_date(
                    field_val.value, field_name, applied, warnings
                )
            elif field_name == "operator_name":
                normalized[field_name] = self._normalize_operator_name(
                    field_val.value, applied, warnings
                )
            elif field_name == "well_name":
                normalized[field_name] = self._normalize_well_name(
                    field_val.value, applied
                )
            elif field_name == "county":
                normalized[field_name] = self._normalize_county(
                    field_val.value, applied
                )
            elif field_name == "well_depth_ft":
                normalized[field_name] = self._normalize_depth(
                    field_val.value, applied, warnings
                )
            elif field_name in ("latitude", "longitude"):
                normalized[field_name] = round(float(field_val.value), 7)
            elif field_name == "days_produced":
                normalized[field_name] = int(field_val.value) if field_val.value else None
            else:
                normalized[field_name] = field_val.value

        return NormalizationResult(
            fields=normalized,
            original_fields=originals,
            normalizations_applied=applied,
            warnings=warnings,
        )

    def _normalize_api_number(
        self, value: str, applied: list, warnings: list
    ) -> str:
        """Normalize API number to 14-digit zero-padded, no dashes."""
        digits = re.sub(r'[-\s]', '', str(value))
        if len(digits) == 10:
            digits += "0000"
            applied.append("api_number: padded 10->14 digits")
        elif len(digits) == 12:
            digits += "00"
            applied.append("api_number: padded 12->14 digits")
        elif len(digits) != 14:
            warnings.append(f"api_number: unexpected length {len(digits)}")
        return digits

    def _normalize_volume_bbl(
        self, value: Any, field_name: str, applied: list, warnings: list
    ) -> Optional[float]:
        """Normalize oil/water volume to BBL."""
        try:
            vol = float(value)
        except (TypeError, ValueError):
            warnings.append(f"{field_name}: could not parse '{value}' as number")
            return None
        if vol < 0:
            warnings.append(f"{field_name}: negative volume {vol}, setting to 0")
            return 0.0
        if field_name == "production_oil_bbl" and vol > 100_000:
            warnings.append(f"{field_name}: unusually high value {vol} BBL")
        if field_name == "production_water_bbl" and vol > 100_000:
            warnings.append(f"{field_name}: unusually high value {vol} BBL")
        applied.append(f"{field_name}: normalized to float BBL")
        return round(vol, 2)

    def _normalize_volume_mcf(
        self, value: Any, applied: list, warnings: list
    ) -> Optional[float]:
        """Normalize gas volume to MCF. MMCF conversion should already be done by extractor."""
        try:
            vol = float(value)
        except (TypeError, ValueError):
            warnings.append(f"production_gas_mcf: could not parse '{value}'")
            return None
        if vol < 0:
            warnings.append(f"production_gas_mcf: negative volume {vol}")
            return 0.0
        if vol > 1_000_000:
            warnings.append(f"production_gas_mcf: unusually high value {vol} MCF")
        applied.append("production_gas_mcf: normalized to float MCF")
        return round(vol, 2)

    def _normalize_date(
        self, value: str, field_name: str, applied: list, warnings: list
    ) -> Optional[str]:
        """Normalize date to ISO 8601 (YYYY-MM-DD). Value may already be ISO from extractor."""
        if not value:
            return None
        # Already ISO format?
        if re.match(r'^\d{4}-\d{2}-\d{2}$', str(value)):
            return str(value)
        # Try additional parsing
        from og_scraper.pipeline.patterns import _try_parse_date
        parsed = _try_parse_date(str(value))
        if parsed:
            applied.append(f"{field_name}: parsed '{value}' -> '{parsed}'")
            return parsed
        warnings.append(f"{field_name}: could not parse date '{value}'")
        return str(value)

    def _normalize_operator_name(
        self, value: str, applied: list, warnings: list
    ) -> str:
        """Normalize operator name: trim, remove extra whitespace, title case."""
        name = str(value).strip()
        name = re.sub(r'\s+', ' ', name)
        # Remove trailing commas, periods, "Inc.", "LLC" normalization
        name = name.rstrip(',.')
        # Preserve standard business suffixes
        applied.append(f"operator_name: normalized '{value}' -> '{name}'")
        return name

    def _normalize_well_name(self, value: str, applied: list) -> str:
        """Normalize well name: trim, collapse whitespace."""
        name = str(value).strip()
        name = re.sub(r'\s+', ' ', name)
        applied.append("well_name: trimmed and collapsed whitespace")
        return name

    def _normalize_county(self, value: str, applied: list) -> str:
        """Normalize county name: trim, title case."""
        county = str(value).strip().title()
        county = re.sub(r'\s+', ' ', county)
        applied.append(f"county: normalized to '{county}'")
        return county

    def _normalize_depth(
        self, value: Any, applied: list, warnings: list
    ) -> Optional[float]:
        """Normalize well depth to feet."""
        try:
            depth = float(value)
        except (TypeError, ValueError):
            warnings.append(f"well_depth_ft: could not parse '{value}'")
            return None
        if depth < 0:
            warnings.append(f"well_depth_ft: negative depth {depth}")
            return None
        if depth > 40_000:
            warnings.append(f"well_depth_ft: unusually deep {depth} ft")
        applied.append("well_depth_ft: normalized to float feet")
        return round(depth, 1)


def slugify(text: str) -> str:
    """
    Convert text to a URL/filesystem-safe slug.
    Used for creating file paths: data/{state}/{operator_slug}/{doc_type}/

    Examples:
        "Devon Energy Corporation" -> "devon-energy-corporation"
        "Pioneer Natural Resources Co." -> "pioneer-natural-resources-co"
    """
    text = unicodedata.normalize("NFKD", text)
    text = text.encode("ascii", "ignore").decode("ascii")
    text = text.lower()
    text = re.sub(r'[^\w\s-]', '', text)
    text = re.sub(r'[-\s]+', '-', text)
    return text.strip('-')
```

### Step 5: Write Comprehensive Tests

**In `backend/tests/pipeline/test_extractor.py`:**

```python
import pytest
from og_scraper.pipeline.patterns import (
    extract_api_number,
    extract_production_volumes,
    extract_dates,
    extract_operator_name,
    extract_well_name,
    extract_county,
    extract_coordinates,
    extract_permit_number,
    extract_well_depth,
    _try_parse_date,
)
from og_scraper.pipeline.extractor import DataExtractor, FieldValue


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

    def test_hyphenated_14(self):
        result = extract_api_number("Well 42-501-20130-00-00 in Ector County")
        assert result is not None
        assert result["formatted"] == "42-501-20130-00-00"

    def test_hyphenated_10(self):
        result = extract_api_number("Well 42-501-20130 in Texas")
        assert result is not None
        assert result["normalized"] == "42501201300000"

    def test_flat_14_valid_state(self):
        result = extract_api_number("Well ID 42501201300000 production")
        assert result is not None
        assert result["state_code"] == "42"

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

    @pytest.mark.parametrize("state_code,state", [
        ("02", "AK"), ("05", "CO"), ("17", "LA"), ("32", "NM"),
        ("35", "ND"), ("37", "OK"), ("39", "PA"), ("42", "TX"), ("49", "WY"),
    ])
    def test_valid_state_codes(self, state_code, state):
        result = extract_api_number(f"API No: {state_code}-001-00001")
        assert result is not None
        assert result["state_code"] == state_code


class TestProductionVolumeExtraction:
    def test_oil_bbls(self):
        result = extract_production_volumes("Oil Production: 1,234 BBL")
        assert result["production_oil_bbl"] is not None
        assert result["production_oil_bbl"]["value"] == 1234.0

    def test_gas_mcf(self):
        result = extract_production_volumes("Gas Production: 5,678 MCF")
        assert result["production_gas_mcf"] is not None
        assert result["production_gas_mcf"]["value"] == 5678.0

    def test_gas_mmcf_conversion(self):
        result = extract_production_volumes("Gas: 5.5 MMCF")
        assert result["production_gas_mcf"] is not None
        assert result["production_gas_mcf"]["value"] == 5500.0  # 5.5 * 1000

    def test_water_bbls(self):
        result = extract_production_volumes("Water Production: 890 BBL")
        assert result["production_water_bbl"] is not None
        assert result["production_water_bbl"]["value"] == 890.0

    def test_days_produced(self):
        result = extract_production_volumes("Days Produced: 31")
        assert result["days_produced"] is not None
        assert result["days_produced"]["value"] == 31

    def test_no_volumes(self):
        result = extract_production_volumes("No production data here")
        assert all(v is None for v in result.values())


class TestDateExtraction:
    def test_spud_date(self):
        result = extract_dates("Spud Date: 03/15/2026")
        assert "spud_date" in result
        assert result["spud_date"]["value"] == "2026-03-15"

    def test_completion_date(self):
        result = extract_dates("Completion Date: 02/28/2026")
        assert "completion_date" in result
        assert result["completion_date"]["value"] == "2026-02-28"

    def test_permit_date(self):
        result = extract_dates("Permit Date: 01-15-2026")
        assert "permit_date" in result
        assert result["permit_date"]["value"] == "2026-01-15"

    def test_reporting_period(self):
        result = extract_dates("Reporting Period: January 2026")
        assert "reporting_period" in result

    def test_no_dates(self):
        result = extract_dates("No dates in this text")
        assert len(result) == 0


class TestDateParsing:
    @pytest.mark.parametrize("input_date,expected", [
        ("03/15/2026", "2026-03-15"),
        ("03-15-2026", "2026-03-15"),
        ("2026-03-15", "2026-03-15"),
        ("15-Mar-2026", "2026-03-15"),
        ("March 15, 2026", "2026-03-15"),
    ])
    def test_date_formats(self, input_date, expected):
        assert _try_parse_date(input_date) == expected

    def test_invalid_date(self):
        assert _try_parse_date("not a date") is None


class TestOperatorAndWellExtraction:
    def test_operator_name(self):
        result = extract_operator_name("Operator: Devon Energy Corporation\nWell Name:")
        assert result is not None
        assert "Devon Energy" in result["value"]

    def test_well_name(self):
        result = extract_well_name("Well Name: Permian Basin Unit #42\nAPI")
        assert result is not None
        assert "Permian Basin" in result["value"]

    def test_county(self):
        result = extract_county("County: Ector\nState: Texas")
        assert result is not None
        assert result["value"] == "Ector"


class TestCoordinateExtraction:
    def test_decimal_degrees(self):
        result = extract_coordinates("Latitude: 31.9505, Longitude: -102.0775")
        assert result is not None
        assert abs(result["latitude"] - 31.9505) < 0.001
        assert abs(result["longitude"] - (-102.0775)) < 0.001

    def test_invalid_coordinates_rejected(self):
        result = extract_coordinates("Latitude: 91.0, Longitude: -102.0")
        assert result is None  # Latitude > 72 for US


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

    def test_missing_fields_logged(self):
        extractor = DataExtractor()
        result = extractor.extract("No useful data here", doc_type="production_report")
        assert len(result.extraction_errors) > 0
```

**In `backend/tests/pipeline/test_normalizer.py`:**

```python
import pytest
from og_scraper.pipeline.normalizer import DataNormalizer, NormalizationResult, slugify
from og_scraper.pipeline.extractor import ExtractionResult, FieldValue


class TestDataNormalizer:
    def _make_extraction(self, fields: dict[str, tuple]) -> ExtractionResult:
        """Helper to create ExtractionResult from simple values."""
        fv = {}
        for name, (value, confidence) in fields.items():
            fv[name] = FieldValue(
                value=value, confidence=confidence,
                source_text="", pattern_used="", extraction_method="regex",
                pattern_specificity=0.85,
            )
        return ExtractionResult(fields=fv, raw_text="", doc_type="production_report", state="TX")

    def test_api_number_normalization_10_to_14(self):
        extraction = self._make_extraction({"api_number": ("4250120130", 0.85)})
        normalizer = DataNormalizer()
        result = normalizer.normalize(extraction)
        assert result.fields["api_number"] == "42501201300000"

    def test_date_normalization(self):
        extraction = self._make_extraction({"spud_date": ("03/15/2026", 0.90)})
        normalizer = DataNormalizer()
        result = normalizer.normalize(extraction)
        assert result.fields["spud_date"] == "2026-03-15"

    def test_operator_name_trimmed(self):
        extraction = self._make_extraction({"operator_name": ("  Devon Energy Corp.  ", 0.85)})
        normalizer = DataNormalizer()
        result = normalizer.normalize(extraction)
        assert result.fields["operator_name"] == "Devon Energy Corp"

    def test_volume_normalization(self):
        extraction = self._make_extraction({"production_oil_bbl": (1234.567, 0.90)})
        normalizer = DataNormalizer()
        result = normalizer.normalize(extraction)
        assert result.fields["production_oil_bbl"] == 1234.57

    def test_negative_volume_warning(self):
        extraction = self._make_extraction({"production_oil_bbl": (-100, 0.90)})
        normalizer = DataNormalizer()
        result = normalizer.normalize(extraction)
        assert result.fields["production_oil_bbl"] == 0.0
        assert any("negative" in w for w in result.warnings)

    def test_county_title_case(self):
        extraction = self._make_extraction({"county": ("ector county", 0.85)})
        normalizer = DataNormalizer()
        result = normalizer.normalize(extraction)
        assert result.fields["county"] == "Ector County"


class TestSlugify:
    def test_basic(self):
        assert slugify("Devon Energy Corporation") == "devon-energy-corporation"

    def test_special_chars(self):
        assert slugify("Pioneer Natural Resources Co.") == "pioneer-natural-resources-co"

    def test_ampersand(self):
        assert slugify("Smith & Jones LLC") == "smith--jones-llc"
```

## Files to Create

- `backend/src/og_scraper/pipeline/extractor.py` - DataExtractor class and FieldValue/ExtractionResult models
- `backend/src/og_scraper/pipeline/patterns.py` - All regex patterns and extraction functions
- `backend/src/og_scraper/pipeline/normalizer.py` - DataNormalizer class and slugify utility
- `backend/tests/pipeline/test_extractor.py` - Extraction pattern tests
- `backend/tests/pipeline/test_normalizer.py` - Normalization tests

## Files to Modify

- `backend/src/og_scraper/pipeline/__init__.py` - Add exports: `DataExtractor`, `DataNormalizer`, `FieldValue`, `ExtractionResult` (note: ExtractionResult here is the field extraction result, different from Task 2.1's text ExtractionResult — consider naming it `FieldExtractionResult` to avoid collision)

## Contracts

### Provides (for downstream tasks)

- **Class**: `DataExtractor` with `extract(text: str, doc_type: str, state: str) -> ExtractionResult`
- **Class**: `DataNormalizer` with `normalize(extraction: ExtractionResult) -> NormalizationResult`
- **Data Model**: `FieldValue` — `{value: Any, confidence: float, source_text: str, pattern_used: str, extraction_method: str, pattern_specificity: float}`
- **Data Model**: `ExtractionResult` (field extraction) — `{fields: dict[str, FieldValue], raw_text: str, doc_type: str, state: str, extraction_errors: list[str]}`
- **Data Model**: `NormalizationResult` — `{fields: dict[str, Any], original_fields: dict[str, Any], normalizations_applied: list[str], warnings: list[str]}`
- **Function**: `slugify(text: str) -> str` — For file path construction
- **Functions**: Individual extraction functions (`extract_api_number`, `extract_production_volumes`, etc.) in `patterns.py`

### Consumes (from upstream tasks)

- Task 2.1: `TextExtractor.extract()` -> text content to parse
- Task 2.2: `DocumentClassifier.classify()` -> `doc_type` to select expected fields
- Task 1.2: Database column definitions for target field names and types

## Acceptance Criteria

- [ ] Extracts API numbers in 10+ format variations (labeled, hyphenated, flat; 10/12/14 digit)
- [ ] Extracts production volumes with unit detection (BBL, MCF, MMCF with conversion)
- [ ] Extracts dates in 5+ formats, normalizes to ISO 8601
- [ ] Extracts operator name, well name, county from document text
- [ ] Extracts coordinates in decimal degrees and DMS formats
- [ ] Per-field confidence scores based on pattern specificity (labeled > bare)
- [ ] Normalizer produces consistent output regardless of source state
- [ ] MMCF-to-MCF conversion correctly multiplies by 1,000
- [ ] API numbers zero-padded to 14 digits
- [ ] Invalid/negative values caught with warnings
- [ ] All tests pass
- [ ] Build succeeds

## Testing Protocol

### Unit/Integration Tests

- Test file: `backend/tests/pipeline/test_extractor.py`
- Test file: `backend/tests/pipeline/test_normalizer.py`
- Test cases:
  - [ ] API number extraction from 10+ format variations
  - [ ] API number state code validation (rejects invalid codes)
  - [ ] API number component parsing (state, county, well, sidetrack, event)
  - [ ] Oil volume extraction (BBL)
  - [ ] Gas volume extraction (MCF)
  - [ ] Gas MMCF-to-MCF conversion
  - [ ] Water volume extraction
  - [ ] Days produced extraction
  - [ ] Date extraction for spud, completion, permit dates
  - [ ] Date parsing across 5 format variations
  - [ ] Operator name extraction
  - [ ] Well name extraction
  - [ ] County extraction
  - [ ] Coordinate extraction (decimal degrees)
  - [ ] Full production report field extraction
  - [ ] Missing fields logged as errors
  - [ ] Normalizer: API number padding (10->14)
  - [ ] Normalizer: date format conversion
  - [ ] Normalizer: negative volume handling
  - [ ] Normalizer: county title casing
  - [ ] Normalizer: operator name trimming
  - [ ] Slugify function

### Build/Lint/Type Checks

- [ ] `uv run ruff check backend/src/og_scraper/pipeline/extractor.py backend/src/og_scraper/pipeline/patterns.py backend/src/og_scraper/pipeline/normalizer.py` passes
- [ ] `uv run ruff format --check backend/src/og_scraper/pipeline/` passes
- [ ] `uv run pytest backend/tests/pipeline/test_extractor.py backend/tests/pipeline/test_normalizer.py -v` — all tests pass

## Skills to Read

- `document-processing-pipeline` - Regex patterns for API numbers, production volumes, dates, operator names; extraction confidence values
- `confidence-scoring` - Field-level confidence calculation: base * pattern_specificity, validation penalty, cross-reference bonus

## Research Files to Read

- `.claude/orchestration-og-doc-scraper/research/document-pipeline-implementation.md` - Section 2.3 (API number patterns), Section 4 (data extraction patterns for volumes, dates, operators, locations)
- `.claude/orchestration-og-doc-scraper/research/og-data-models.md` - API number format, state codes, production volume ranges, coordinate ranges

## Git

- Branch: `feat/task-2.3-data-extraction`
- Commit message prefix: `Task 2.3:`
