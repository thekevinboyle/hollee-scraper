"""
Data extraction from O&G document text using regex patterns.

This module provides the DataExtractor class that pulls structured fields
(API numbers, production volumes, dates, operator names, etc.) from raw
document text. Each extracted field carries a confidence score based on
pattern specificity and extraction method.

The FieldExtractionResult is deliberately named to avoid collision with
the text-extraction ExtractionResult from text_extractor.py.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from og_scraper.pipeline.patterns import (
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

logger = logging.getLogger(__name__)


@dataclass
class FieldValue:
    """A single extracted field with provenance and confidence."""

    value: Any  # The extracted value (string, float, int, etc.)
    confidence: float  # 0.0-1.0 field-level confidence
    source_text: str  # The raw text snippet this was extracted from
    pattern_used: str  # Which regex pattern matched (for debugging)
    extraction_method: str  # "regex", "text", "ocr", "table"
    pattern_specificity: float  # 0.0-1.0, how specific the pattern was (labeled > bare)


@dataclass
class FieldExtractionResult:
    """Result of extracting structured fields from document text.

    Named FieldExtractionResult to distinguish from the text-extraction
    ExtractionResult in text_extractor.py.
    """

    fields: dict[str, FieldValue]  # field_name -> FieldValue
    raw_text: str  # Original text that was parsed
    doc_type: str  # Document type (from classifier)
    state: str  # State code
    extraction_errors: list[str] = field(default_factory=list)  # Non-fatal errors


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
            "api_number",
            "operator_name",
            "production_oil_bbl",
            "production_gas_mcf",
            "production_water_bbl",
            "days_produced",
            "reporting_period",
        ],
        "well_permit": [
            "api_number",
            "operator_name",
            "well_name",
            "county",
            "permit_number",
            "permit_date",
            "well_depth_ft",
        ],
        "completion_report": [
            "api_number",
            "operator_name",
            "well_name",
            "completion_date",
            "well_depth_ft",
        ],
        "plugging_report": [
            "api_number",
            "operator_name",
            "well_name",
            "plug_date",
        ],
        "spacing_order": [
            "operator_name",
            "county",
        ],
        "inspection_record": [
            "api_number",
            "operator_name",
            "inspection_date",
        ],
        "incident_report": [
            "api_number",
            "operator_name",
        ],
    }

    def extract(self, text: str, doc_type: str, state: str = "") -> FieldExtractionResult:
        """
        Extract structured data fields from document text.

        Args:
            text: Raw extracted text from TextExtractor
            doc_type: Document type from DocumentClassifier (e.g., "production_report")
            state: State code (e.g., "TX") -- used for state-specific patterns

        Returns:
            FieldExtractionResult with extracted fields and confidence scores
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

        return FieldExtractionResult(
            fields=fields,
            raw_text=text,
            doc_type=doc_type,
            state=state,
            extraction_errors=errors,
        )
