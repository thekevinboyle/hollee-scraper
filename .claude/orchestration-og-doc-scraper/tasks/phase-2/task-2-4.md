# Task 2.4: Validation & Confidence Scoring

## Objective

Implement the three-tier confidence scoring system (OCR confidence, field-level confidence, document-level confidence), field validation rules, and the full document processing pipeline orchestrator that routes documents to auto-accept (>= 0.85), review queue (0.50-0.84), or reject (< 0.50). This is the quality gate that ensures only trustworthy data enters the production database, per DISCOVERY D10's strict rejection policy.

## Context

This is the fourth and final feature task in Phase 2 (Document Pipeline). It integrates all previous pipeline components: Task 2.1 (text extraction with OCR confidence), Task 2.2 (document classification with classification confidence), and Task 2.3 (field extraction with per-field confidence). It also depends on Task 1.2 (database schema for `review_queue` and `extracted_data` tables). The confidence scorer, validator, and pipeline orchestrator built here are consumed by the Huey task workers (Phase 3) and the review queue API/dashboard (Phase 3 and 5).

## Dependencies

- Task 2.1 - Provides `ExtractionResult` with `ocr_confidence` and per-page confidence metadata
- Task 2.2 - Provides `ClassificationResult` with `confidence` score
- Task 2.3 - Provides `FieldExtractionResult` with per-field `FieldValue.confidence` scores
- Task 1.2 - Provides `review_queue` table schema, `extracted_data` table, `documents` table with confidence columns

## Blocked By

- Task 2.3, Task 1.2

## Research Findings

Key findings from research files relevant to this task:

- From `confidence-scoring` skill: Document-level formula: `0.3 * classification_confidence + 0.5 * weighted_field_confidence + 0.2 * min_page_ocr_confidence`. Field weights: api_number=3.0, operator_name=2.5, production_values=2.0, dates=1.5, coordinates=2.0.
- From `confidence-scoring` skill: Field-level confidence = `base * pattern_specificity`. If validation fails, multiply by 0.7. If cross-reference matches, multiply by 1.1 (cap at 0.99). Missing expected fields contribute 0.0 at full weight.
- From `confidence-scoring` skill: Critical field override rule: if ANY critical field (API number, production values) falls below its reject threshold, the entire document goes to review queue regardless of overall confidence.
- From `confidence-scoring` skill: Field thresholds: API number auto-accept >= 0.95, review 0.70-0.94, reject < 0.70. Production values auto-accept >= 0.90, review 0.70-0.89, reject < 0.70.
- From DISCOVERY D10: "Strict — reject uncertain data. Only store data above a confidence threshold. Low-confidence documents go to a review queue."
- From DISCOVERY D23: "Three-level scoring: OCR confidence, field-level confidence, document-level confidence."

## Implementation Plan

### Step 1: Implement Field Validators

**In `backend/src/og_scraper/pipeline/validator.py`:**

Field validators check whether extracted values are structurally valid (correct format, reasonable range). Validation failures apply a 0.7x confidence penalty.

```python
"""
Field validation rules for O&G extracted data.

Each validator returns (is_valid: bool, reason: str | None).
Validation failure applies a 0.7x confidence penalty to that field.
"""

from __future__ import annotations

import re
from datetime import datetime, date
from typing import Any, Optional

from og_scraper.pipeline.patterns import VALID_API_STATE_CODES


def validate_api_number(value: str) -> tuple[bool, Optional[str]]:
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

    digits = re.sub(r'[-\s]', '', value)
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


def validate_production_volume(
    value: Any, field_name: str
) -> tuple[bool, Optional[str]]:
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


def validate_date(value: str) -> tuple[bool, Optional[str]]:
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
        if re.match(r'^\d{4}-\d{2}-\d{2}$', str(value)):
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


def validate_coordinates(
    latitude: Any, longitude: Any
) -> tuple[bool, Optional[str]]:
    """
    Validate latitude/longitude coordinates.

    Rules:
    - Latitude: 24.5-71.5 (continental US + Alaska)
    - Longitude: -180.0 to -66.9 (continental US + Alaska)
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


def validate_operator_name(value: str) -> tuple[bool, Optional[str]]:
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
    if not re.search(r'[a-zA-Z]', value):
        return False, "Operator name contains no letters"
    return True, None


def validate_days_produced(value: Any) -> tuple[bool, Optional[str]]:
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
FIELD_VALIDATORS = {
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
```

### Step 2: Implement Three-Tier Confidence Scoring

**In `backend/src/og_scraper/pipeline/confidence.py`:**

```python
"""
Three-tier confidence scoring system for O&G document pipeline.

Tier 1: OCR Confidence — from PaddleOCR rec_score (per page, minimum for document)
Tier 2: Field-Level Confidence — base * specificity, validation penalty, cross-ref bonus
Tier 3: Document-Level Confidence — composite formula combining all tiers

Disposition:
  >= 0.85  ->  auto-accept
  0.50-0.84 -> review queue
  < 0.50   ->  reject
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Optional

from og_scraper.pipeline.validator import FIELD_VALIDATORS


# ============================================================
# FIELD IMPORTANCE WEIGHTS (used in Tier 3 weighted average)
# ============================================================

FIELD_WEIGHTS: dict[str, float] = {
    "api_number": 3.0,
    "operator_name": 2.5,
    "well_name": 2.0,
    "production_oil_bbl": 2.0,
    "production_gas_mcf": 2.0,
    "production_water_bbl": 1.5,
    "reporting_period": 2.0,
    "county": 1.5,
    "latitude": 2.0,
    "longitude": 2.0,
    "permit_number": 1.5,
    "spud_date": 1.5,
    "completion_date": 1.5,
    "permit_date": 1.5,
    "plug_date": 1.5,
    "inspection_date": 1.5,
    "first_production_date": 1.5,
    "well_depth_ft": 1.5,
    "days_produced": 1.0,
}

# Default weight for unlisted fields
DEFAULT_FIELD_WEIGHT = 1.0


# ============================================================
# FIELD-LEVEL THRESHOLDS
# ============================================================

FIELD_THRESHOLDS: dict[str, dict[str, float]] = {
    "api_number": {"accept": 0.95, "review": 0.70, "reject": 0.70},
    "operator_name": {"accept": 0.90, "review": 0.60, "reject": 0.60},
    "production_oil_bbl": {"accept": 0.90, "review": 0.70, "reject": 0.70},
    "production_gas_mcf": {"accept": 0.90, "review": 0.70, "reject": 0.70},
    "production_water_bbl": {"accept": 0.90, "review": 0.70, "reject": 0.70},
    "latitude": {"accept": 0.95, "review": 0.80, "reject": 0.80},
    "longitude": {"accept": 0.95, "review": 0.80, "reject": 0.80},
    "spud_date": {"accept": 0.90, "review": 0.65, "reject": 0.65},
    "completion_date": {"accept": 0.90, "review": 0.65, "reject": 0.65},
    "permit_date": {"accept": 0.90, "review": 0.65, "reject": 0.65},
}

# Critical fields — if ANY is below reject threshold, force document to review
CRITICAL_FIELDS = {"api_number", "production_oil_bbl", "production_gas_mcf"}


# ============================================================
# DOCUMENT-LEVEL THRESHOLDS
# ============================================================

DOCUMENT_ACCEPT_THRESHOLD = 0.85
DOCUMENT_REVIEW_THRESHOLD = 0.50

# Composite formula weights
CLASSIFICATION_WEIGHT = 0.3
FIELD_WEIGHT = 0.5
OCR_WEIGHT = 0.2


# ============================================================
# RESULT DATA MODELS
# ============================================================

@dataclass
class FieldConfidenceResult:
    """Confidence scoring result for a single field."""
    field_name: str
    raw_confidence: float          # Base confidence from extraction
    validated: bool                # Whether value passed validation
    validation_reason: Optional[str]  # Reason for validation failure
    adjusted_confidence: float     # After validation penalty / cross-ref bonus
    disposition: Literal["accept", "review", "reject"]
    weight: float                  # Field importance weight


@dataclass
class DocumentScore:
    """Complete confidence scoring result for a document."""
    # Tier 1: OCR
    ocr_confidence: float          # Minimum page OCR confidence

    # Tier 2: Fields
    field_confidences: dict[str, FieldConfidenceResult]  # Per-field scores
    weighted_field_confidence: float  # Weighted average of all field confidences

    # Tier 3: Document
    classification_confidence: float
    document_confidence: float     # Final composite score

    # Disposition
    disposition: Literal["accept", "review", "reject"]
    disposition_reasons: list[str]  # Why this disposition was chosen

    # Critical field overrides
    critical_field_override: bool   # True if a critical field forced review/reject


class ConfidenceScorer:
    """
    Three-tier confidence scoring system.

    Tier 1: OCR Confidence
      - Text PDFs: 1.0
      - Scanned PDFs: PaddleOCR rec_score (weighted by region size, min across pages)

    Tier 2: Field-Level Confidence
      - base_confidence * pattern_specificity
      - Validation failure: * 0.7
      - Cross-reference match: * 1.1 (cap 0.99)
      - Missing expected fields contribute 0.0 at full weight

    Tier 3: Document-Level Confidence
      - 0.3 * classification_confidence + 0.5 * weighted_field_avg + 0.2 * min_page_ocr

    Disposition:
      - >= 0.85: auto-accept
      - 0.50-0.84: review queue
      - < 0.50: reject
      - Critical field override: API or production below reject threshold forces review
    """

    # Validation failure penalty multiplier
    VALIDATION_PENALTY = 0.7

    # Cross-reference match bonus multiplier
    CROSS_REF_BONUS = 1.1

    # Maximum confidence cap
    MAX_CONFIDENCE = 0.99

    def score(
        self,
        ocr_confidence: float,
        classification_confidence: float,
        fields: dict[str, Any],  # field_name -> FieldValue from extractor
        expected_fields: list[str] | None = None,
    ) -> DocumentScore:
        """
        Compute three-tier confidence score for a document.

        Args:
            ocr_confidence: Tier 1 — minimum page OCR confidence (from TextExtractor)
            classification_confidence: Classification confidence (from DocumentClassifier)
            fields: Dict of field_name -> FieldValue objects (from DataExtractor)
            expected_fields: Optional list of fields expected for this document type

        Returns:
            DocumentScore with all tier scores and disposition
        """
        # --- Tier 2: Score each field ---
        field_results: dict[str, FieldConfidenceResult] = {}
        disposition_reasons: list[str] = []
        critical_field_override = False

        for field_name, field_val in fields.items():
            raw_confidence = field_val.confidence
            pattern_specificity = getattr(field_val, 'pattern_specificity', 1.0)

            # Base confidence = raw * pattern_specificity
            adjusted = raw_confidence * pattern_specificity

            # Validate
            validated = True
            validation_reason = None
            validator = FIELD_VALIDATORS.get(field_name)
            if validator:
                is_valid, reason = validator(field_val.value)
                if not is_valid:
                    validated = False
                    validation_reason = reason
                    adjusted *= self.VALIDATION_PENALTY

            # Cap at maximum
            adjusted = min(adjusted, self.MAX_CONFIDENCE)
            adjusted = max(adjusted, 0.0)

            # Determine field disposition
            thresholds = FIELD_THRESHOLDS.get(field_name)
            if thresholds:
                if adjusted >= thresholds["accept"]:
                    field_disposition = "accept"
                elif adjusted >= thresholds["review"]:
                    field_disposition = "review"
                else:
                    field_disposition = "reject"
            else:
                # Default thresholds for unlisted fields
                if adjusted >= 0.85:
                    field_disposition = "accept"
                elif adjusted >= 0.50:
                    field_disposition = "review"
                else:
                    field_disposition = "reject"

            weight = FIELD_WEIGHTS.get(field_name, DEFAULT_FIELD_WEIGHT)

            field_results[field_name] = FieldConfidenceResult(
                field_name=field_name,
                raw_confidence=raw_confidence,
                validated=validated,
                validation_reason=validation_reason,
                adjusted_confidence=round(adjusted, 4),
                disposition=field_disposition,
                weight=weight,
            )

            # Critical field override check
            if field_name in CRITICAL_FIELDS and field_disposition == "reject":
                critical_field_override = True
                disposition_reasons.append(
                    f"Critical field '{field_name}' below reject threshold "
                    f"(confidence={adjusted:.3f})"
                )

        # Handle missing expected fields (contribute 0.0 at full weight)
        if expected_fields:
            for expected in expected_fields:
                if expected not in field_results:
                    weight = FIELD_WEIGHTS.get(expected, DEFAULT_FIELD_WEIGHT)
                    field_results[expected] = FieldConfidenceResult(
                        field_name=expected,
                        raw_confidence=0.0,
                        validated=False,
                        validation_reason="Field not found in document",
                        adjusted_confidence=0.0,
                        disposition="reject",
                        weight=weight,
                    )

        # --- Tier 2: Weighted field average ---
        total_weight = sum(fr.weight for fr in field_results.values())
        if total_weight > 0:
            weighted_field_confidence = sum(
                fr.adjusted_confidence * fr.weight
                for fr in field_results.values()
            ) / total_weight
        else:
            weighted_field_confidence = 0.0

        # --- Tier 3: Document-level composite ---
        document_confidence = (
            CLASSIFICATION_WEIGHT * classification_confidence
            + FIELD_WEIGHT * weighted_field_confidence
            + OCR_WEIGHT * ocr_confidence
        )
        document_confidence = round(min(document_confidence, 1.0), 4)

        # --- Disposition ---
        if critical_field_override:
            # Override: force to review regardless of overall score
            disposition = "review"
            disposition_reasons.append("Critical field override — forced to review queue")
        elif document_confidence >= DOCUMENT_ACCEPT_THRESHOLD:
            disposition = "accept"
            disposition_reasons.append(
                f"Document confidence {document_confidence:.3f} >= {DOCUMENT_ACCEPT_THRESHOLD}"
            )
        elif document_confidence >= DOCUMENT_REVIEW_THRESHOLD:
            disposition = "review"
            disposition_reasons.append(
                f"Document confidence {document_confidence:.3f} in review range "
                f"[{DOCUMENT_REVIEW_THRESHOLD}, {DOCUMENT_ACCEPT_THRESHOLD})"
            )
        else:
            disposition = "reject"
            disposition_reasons.append(
                f"Document confidence {document_confidence:.3f} < {DOCUMENT_REVIEW_THRESHOLD}"
            )

        return DocumentScore(
            ocr_confidence=round(ocr_confidence, 4),
            field_confidences=field_results,
            weighted_field_confidence=round(weighted_field_confidence, 4),
            classification_confidence=round(classification_confidence, 4),
            document_confidence=document_confidence,
            disposition=disposition,
            disposition_reasons=disposition_reasons,
            critical_field_override=critical_field_override,
        )
```

### Step 3: Implement the Full Pipeline Orchestrator

**In `backend/src/og_scraper/pipeline/pipeline.py`:**

```python
"""
Document processing pipeline orchestrator.

Runs all 7 stages: extract text -> classify -> extract fields -> normalize -> validate -> score -> route

Usage:
    pipeline = DocumentPipeline()
    result = pipeline.process(Path("document.pdf"), state="TX")
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, Optional

from og_scraper.pipeline.text_extractor import TextExtractor, ExtractionResult as TextExtractionResult
from og_scraper.pipeline.classifier import DocumentClassifier, ClassificationResult
from og_scraper.pipeline.extractor import DataExtractor, ExtractionResult as FieldExtractionResult
from og_scraper.pipeline.normalizer import DataNormalizer, NormalizationResult
from og_scraper.pipeline.confidence import ConfidenceScorer, DocumentScore

logger = logging.getLogger(__name__)


@dataclass
class ProcessingResult:
    """Complete result from processing a document through the full pipeline."""
    # Input
    file_path: str
    state: str

    # Stage 1: Text extraction
    text_extraction: TextExtractionResult
    raw_text: str
    extraction_method: str

    # Stage 2: Classification
    classification: ClassificationResult
    doc_type: str

    # Stage 3: Field extraction
    field_extraction: FieldExtractionResult

    # Stage 4: Normalization
    normalization: NormalizationResult
    normalized_fields: dict[str, Any]

    # Stage 5+6: Validation & scoring
    score: DocumentScore
    disposition: Literal["accept", "review", "reject"]

    # Metadata
    processing_errors: list[str] = field(default_factory=list)
    processing_warnings: list[str] = field(default_factory=list)

    @property
    def overall_confidence(self) -> float:
        return self.score.document_confidence


class DocumentPipeline:
    """
    Orchestrates the full document processing pipeline.

    Stages:
    1. Text Extraction (PyMuPDF4LLM / PaddleOCR)
    2. Classification (form number / header / keyword)
    3. Field Extraction (regex patterns)
    4. Normalization (cross-state standardization)
    5. Validation (format checks, range checks)
    6. Confidence Scoring (three-tier)
    7. Disposition Routing (accept / review / reject)
    """

    def __init__(self):
        self.text_extractor = TextExtractor()
        self.classifier = DocumentClassifier()
        self.data_extractor = DataExtractor()
        self.normalizer = DataNormalizer()
        self.scorer = ConfidenceScorer()

    def process(
        self, file_path: Path | str, state: str = ""
    ) -> ProcessingResult:
        """
        Process a document through all pipeline stages.

        Args:
            file_path: Path to the document file (PDF)
            state: State code hint (e.g., "TX"). Optional but improves classification.

        Returns:
            ProcessingResult with all stage outputs and final disposition.
        """
        file_path = Path(file_path)
        errors: list[str] = []
        warnings: list[str] = []

        logger.info("Pipeline: Starting processing of %s (state=%s)", file_path, state)

        # Stage 1: Text Extraction
        logger.info("Pipeline: Stage 1 — Text Extraction")
        text_result = self.text_extractor.extract(file_path)
        raw_text = text_result.text

        if not raw_text.strip():
            errors.append("No text extracted from document")
            logger.warning("Pipeline: No text extracted from %s", file_path)

        # Stage 2: Classification
        logger.info("Pipeline: Stage 2 — Classification")
        metadata = {"state": state} if state else None
        classification = self.classifier.classify(raw_text, metadata=metadata)
        doc_type = classification.doc_type

        logger.info(
            "Pipeline: Classified as '%s' (confidence=%.3f, strategy=%s)",
            doc_type, classification.confidence, classification.strategy,
        )

        # Stage 3: Field Extraction
        logger.info("Pipeline: Stage 3 — Field Extraction")
        field_extraction = self.data_extractor.extract(raw_text, doc_type, state)

        logger.info(
            "Pipeline: Extracted %d fields, %d errors",
            len(field_extraction.fields), len(field_extraction.extraction_errors),
        )
        errors.extend(field_extraction.extraction_errors)

        # Stage 4: Normalization
        logger.info("Pipeline: Stage 4 — Normalization")
        normalization = self.normalizer.normalize(field_extraction)
        warnings.extend(normalization.warnings)

        # Stage 5+6: Validation & Confidence Scoring
        logger.info("Pipeline: Stage 5+6 — Validation & Confidence Scoring")
        expected_fields = self.data_extractor.EXPECTED_FIELDS.get(doc_type, [])
        score = self.scorer.score(
            ocr_confidence=text_result.ocr_confidence,
            classification_confidence=classification.confidence,
            fields=field_extraction.fields,
            expected_fields=expected_fields,
        )

        logger.info(
            "Pipeline: Score=%.3f, disposition=%s, critical_override=%s",
            score.document_confidence, score.disposition, score.critical_field_override,
        )

        # Stage 7: Build result (routing happens in the caller — Huey task or API)
        return ProcessingResult(
            file_path=str(file_path),
            state=state,
            text_extraction=text_result,
            raw_text=raw_text,
            extraction_method=text_result.method,
            classification=classification,
            doc_type=doc_type,
            field_extraction=field_extraction,
            normalization=normalization,
            normalized_fields=normalization.fields,
            score=score,
            disposition=score.disposition,
            processing_errors=errors,
            processing_warnings=warnings,
        )
```

### Step 4: Write Comprehensive Tests

**In `backend/tests/pipeline/test_validator.py`:**

```python
import pytest
from og_scraper.pipeline.validator import (
    validate_api_number,
    validate_production_volume,
    validate_date,
    validate_coordinates,
    validate_operator_name,
    validate_days_produced,
)


class TestAPINumberValidation:
    def test_valid_14_digit(self):
        is_valid, reason = validate_api_number("42501201300000")
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

    def test_zero_county_code(self):
        is_valid, reason = validate_api_number("42000201300000")
        assert not is_valid
        assert "county" in reason.lower()

    def test_zero_well_id(self):
        is_valid, reason = validate_api_number("42501000000000")
        assert not is_valid
        assert "well" in reason.lower()


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

    def test_over_limit_invalid(self):
        is_valid, reason = validate_production_volume(200_000, "production_oil_bbl")
        assert not is_valid
        assert "exceeds" in reason.lower()

    def test_non_numeric_invalid(self):
        is_valid, reason = validate_production_volume("not a number", "production_oil_bbl")
        assert not is_valid


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

    def test_longitude_too_east(self):
        is_valid, reason = validate_coordinates(31.0, -60.0)
        assert not is_valid
        assert "Longitude" in reason


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
```

**In `backend/tests/pipeline/test_confidence.py`:**

```python
import pytest
from og_scraper.pipeline.confidence import (
    ConfidenceScorer,
    DocumentScore,
    FIELD_WEIGHTS,
    DOCUMENT_ACCEPT_THRESHOLD,
    DOCUMENT_REVIEW_THRESHOLD,
    CRITICAL_FIELDS,
)
from og_scraper.pipeline.extractor import FieldValue


def make_field(value, confidence=0.95, pattern_specificity=1.0):
    """Helper to create a FieldValue for testing."""
    return FieldValue(
        value=value,
        confidence=confidence,
        source_text="",
        pattern_used="test",
        extraction_method="regex",
        pattern_specificity=pattern_specificity,
    )


class TestConfidenceScorer:
    def test_high_confidence_auto_accept(self):
        """Document with all high-confidence fields should auto-accept."""
        scorer = ConfidenceScorer()
        fields = {
            "api_number": make_field("42501201300000", confidence=0.95),
            "operator_name": make_field("Devon Energy", confidence=0.95),
            "production_oil_bbl": make_field(1234.0, confidence=0.95),
        }
        result = scorer.score(
            ocr_confidence=1.0,
            classification_confidence=0.98,
            fields=fields,
        )
        assert result.disposition == "accept"
        assert result.document_confidence >= DOCUMENT_ACCEPT_THRESHOLD

    def test_medium_confidence_review(self):
        """Document with medium confidence should go to review."""
        scorer = ConfidenceScorer()
        fields = {
            "api_number": make_field("42501201300000", confidence=0.75),
            "operator_name": make_field("Devon Energy", confidence=0.70),
        }
        result = scorer.score(
            ocr_confidence=0.70,
            classification_confidence=0.60,
            fields=fields,
        )
        assert result.disposition == "review"
        assert DOCUMENT_REVIEW_THRESHOLD <= result.document_confidence < DOCUMENT_ACCEPT_THRESHOLD

    def test_low_confidence_reject(self):
        """Document with very low confidence should be rejected."""
        scorer = ConfidenceScorer()
        fields = {
            "api_number": make_field("99999999999999", confidence=0.20),
        }
        result = scorer.score(
            ocr_confidence=0.30,
            classification_confidence=0.20,
            fields=fields,
        )
        assert result.disposition == "reject"
        assert result.document_confidence < DOCUMENT_REVIEW_THRESHOLD

    def test_critical_field_override(self):
        """Critical field below reject threshold forces review regardless of overall score."""
        scorer = ConfidenceScorer()
        fields = {
            # API number with invalid state code -> validation fails -> confidence * 0.7
            "api_number": make_field("99501201300000", confidence=0.50, pattern_specificity=0.8),
            "operator_name": make_field("Devon Energy", confidence=0.95),
            "production_oil_bbl": make_field(1234.0, confidence=0.95),
        }
        result = scorer.score(
            ocr_confidence=1.0,
            classification_confidence=0.98,
            fields=fields,
        )
        # The API number validation failure + low confidence should trigger override
        assert result.critical_field_override or result.disposition in ("review", "reject")

    def test_composite_formula(self):
        """Verify the composite formula: 0.3*class + 0.5*fields + 0.2*ocr."""
        scorer = ConfidenceScorer()
        fields = {
            "api_number": make_field("42501201300000", confidence=0.90),
        }
        result = scorer.score(
            ocr_confidence=0.80,
            classification_confidence=0.90,
            fields=fields,
        )
        # Manual calculation: 0.3*0.90 + 0.5*(0.90*1.0) + 0.2*0.80
        # = 0.27 + 0.45 + 0.16 = 0.88
        assert abs(result.document_confidence - 0.88) < 0.05

    def test_missing_expected_fields_penalize(self):
        """Missing expected fields should contribute 0.0 at full weight."""
        scorer = ConfidenceScorer()
        fields = {
            "api_number": make_field("42501201300000", confidence=0.95),
        }
        result_with_expected = scorer.score(
            ocr_confidence=1.0,
            classification_confidence=0.98,
            fields=fields,
            expected_fields=["api_number", "operator_name", "production_oil_bbl"],
        )
        result_without_expected = scorer.score(
            ocr_confidence=1.0,
            classification_confidence=0.98,
            fields=fields,
            expected_fields=None,
        )
        # Missing fields should lower the weighted average
        assert result_with_expected.weighted_field_confidence < result_without_expected.weighted_field_confidence

    def test_validation_failure_penalty(self):
        """Validation failure should apply 0.7x penalty."""
        scorer = ConfidenceScorer()
        # Invalid API number (wrong state code)
        fields = {
            "api_number": make_field("99501201300000", confidence=0.90),
        }
        result = scorer.score(
            ocr_confidence=1.0,
            classification_confidence=0.90,
            fields=fields,
        )
        # The API number should have lower adjusted confidence due to validation failure
        api_field = result.field_confidences["api_number"]
        assert not api_field.validated
        assert api_field.adjusted_confidence < 0.90 * 1.0  # Lower than raw * specificity

    def test_field_weights_applied(self):
        """Verify that field weights affect the weighted average."""
        scorer = ConfidenceScorer()
        # API number (weight 3.0) vs days_produced (weight 1.0)
        fields_api_high = {
            "api_number": make_field("42501201300000", confidence=0.95),
            "days_produced": make_field(31, confidence=0.50),
        }
        fields_api_low = {
            "api_number": make_field("42501201300000", confidence=0.50),
            "days_produced": make_field(31, confidence=0.95),
        }
        result_high = scorer.score(1.0, 0.90, fields_api_high)
        result_low = scorer.score(1.0, 0.90, fields_api_low)
        # Higher API confidence should give higher weighted average
        assert result_high.weighted_field_confidence > result_low.weighted_field_confidence

    def test_all_tier_scores_present(self):
        """Verify all three tier scores are populated."""
        scorer = ConfidenceScorer()
        fields = {"api_number": make_field("42501201300000", confidence=0.90)}
        result = scorer.score(0.85, 0.90, fields)
        assert 0.0 <= result.ocr_confidence <= 1.0
        assert 0.0 <= result.weighted_field_confidence <= 1.0
        assert 0.0 <= result.classification_confidence <= 1.0
        assert 0.0 <= result.document_confidence <= 1.0
        assert result.disposition in ("accept", "review", "reject")
        assert len(result.disposition_reasons) > 0
```

**In `backend/tests/pipeline/test_pipeline.py`:**

```python
import pytest
from pathlib import Path
from og_scraper.pipeline.pipeline import DocumentPipeline, ProcessingResult


class TestDocumentPipeline:
    def test_text_pdf_full_pipeline(self, sample_text_pdf: Path):
        """End-to-end: text PDF with O&G content should auto-accept or review."""
        pipeline = DocumentPipeline()
        result = pipeline.process(sample_text_pdf, state="TX")

        assert isinstance(result, ProcessingResult)
        assert result.disposition in ("accept", "review")
        assert result.doc_type != "unknown"
        assert len(result.raw_text) > 0
        assert result.score.document_confidence > 0.0
        assert result.score.ocr_confidence == 1.0  # Text PDF

    def test_scanned_pdf_full_pipeline(self, sample_scan_pdf: Path):
        """End-to-end: scanned PDF should process with lower confidence."""
        pipeline = DocumentPipeline()
        result = pipeline.process(sample_scan_pdf, state="TX")

        assert isinstance(result, ProcessingResult)
        assert result.disposition in ("accept", "review", "reject")
        assert result.extraction_method in ("paddleocr", "mixed")
        assert result.score.ocr_confidence <= 1.0

    def test_processing_result_has_all_stages(self, sample_text_pdf: Path):
        """Verify all pipeline stages are represented in the result."""
        pipeline = DocumentPipeline()
        result = pipeline.process(sample_text_pdf, state="TX")

        # Stage 1: Text extraction
        assert result.text_extraction is not None
        assert result.raw_text is not None
        # Stage 2: Classification
        assert result.classification is not None
        assert result.doc_type is not None
        # Stage 3: Field extraction
        assert result.field_extraction is not None
        # Stage 4: Normalization
        assert result.normalization is not None
        assert result.normalized_fields is not None
        # Stage 5+6: Scoring
        assert result.score is not None
        assert result.disposition is not None

    def test_overall_confidence_property(self, sample_text_pdf: Path):
        pipeline = DocumentPipeline()
        result = pipeline.process(sample_text_pdf)
        assert 0.0 <= result.overall_confidence <= 1.0
        assert result.overall_confidence == result.score.document_confidence

    def test_state_hint_improves_classification(self, sample_text_pdf: Path):
        pipeline = DocumentPipeline()
        result_with_state = pipeline.process(sample_text_pdf, state="TX")
        result_no_state = pipeline.process(sample_text_pdf, state="")
        # Both should classify, but state hint may boost confidence
        assert result_with_state.doc_type == result_no_state.doc_type
```

### Step 5: Update Pipeline Package Exports

**In `backend/src/og_scraper/pipeline/__init__.py`:**

```python
from og_scraper.pipeline.text_extractor import TextExtractor
from og_scraper.pipeline.text_extractor import ExtractionResult as TextExtractionResult
from og_scraper.pipeline.text_extractor import PageResult
from og_scraper.pipeline.classifier import DocumentClassifier, ClassificationResult
from og_scraper.pipeline.extractor import DataExtractor, FieldValue
from og_scraper.pipeline.extractor import ExtractionResult as FieldExtractionResult
from og_scraper.pipeline.normalizer import DataNormalizer, NormalizationResult
from og_scraper.pipeline.confidence import ConfidenceScorer, DocumentScore
from og_scraper.pipeline.pipeline import DocumentPipeline, ProcessingResult

__all__ = [
    "TextExtractor", "TextExtractionResult", "PageResult",
    "DocumentClassifier", "ClassificationResult",
    "DataExtractor", "FieldValue", "FieldExtractionResult",
    "DataNormalizer", "NormalizationResult",
    "ConfidenceScorer", "DocumentScore",
    "DocumentPipeline", "ProcessingResult",
]
```

## Files to Create

- `backend/src/og_scraper/pipeline/validator.py` - Field validation rules (API number, volumes, dates, coordinates, names)
- `backend/src/og_scraper/pipeline/confidence.py` - Three-tier confidence scoring system (ConfidenceScorer, DocumentScore)
- `backend/src/og_scraper/pipeline/pipeline.py` - Full pipeline orchestrator (DocumentPipeline, ProcessingResult)
- `backend/tests/pipeline/test_validator.py` - Validation rule tests
- `backend/tests/pipeline/test_confidence.py` - Confidence scoring tests
- `backend/tests/pipeline/test_pipeline.py` - End-to-end pipeline tests

## Files to Modify

- `backend/src/og_scraper/pipeline/__init__.py` - Add all exports for the complete pipeline

## Contracts

### Provides (for downstream tasks)

- **Class**: `ConfidenceScorer` with `score(ocr_confidence, classification_confidence, fields, expected_fields) -> DocumentScore`
- **Class**: `DocumentPipeline` with `process(file_path: Path, state: str) -> ProcessingResult`
- **Data Model**: `DocumentScore` — `{ocr_confidence, field_confidences, weighted_field_confidence, classification_confidence, document_confidence, disposition, disposition_reasons, critical_field_override}`
- **Data Model**: `ProcessingResult` — complete pipeline output with all stage results and final disposition
- **Constants**: `FIELD_WEIGHTS`, `FIELD_THRESHOLDS`, `CRITICAL_FIELDS`, `DOCUMENT_ACCEPT_THRESHOLD`, `DOCUMENT_REVIEW_THRESHOLD`
- **Validators**: `validate_api_number()`, `validate_production_volume()`, `validate_date()`, `validate_coordinates()`, etc.

### Consumes (from upstream tasks)

- Task 2.1: `TextExtractor` -> `TextExtractionResult` with `ocr_confidence`
- Task 2.2: `DocumentClassifier` -> `ClassificationResult` with `confidence`
- Task 2.3: `DataExtractor` -> `FieldExtractionResult` with per-field `FieldValue` objects
- Task 2.3: `DataNormalizer` -> `NormalizationResult`
- Task 1.2: Database tables `review_queue`, `extracted_data`, `documents` with confidence columns

## Acceptance Criteria

- [ ] Three-tier scoring produces correct confidence at each level (OCR, field, document)
- [ ] Composite formula: `0.3 * classification + 0.5 * weighted_fields + 0.2 * ocr` is correctly implemented
- [ ] High-quality text PDF scores >= 0.85 (auto-accept disposition)
- [ ] Medium-quality document scores 0.50-0.84 (review disposition)
- [ ] Garbage/unreadable document scores < 0.50 (reject disposition)
- [ ] Field validation catches invalid API numbers (wrong state code, wrong length)
- [ ] Field validation catches impossible dates (future, pre-1900)
- [ ] Field validation catches out-of-range coordinates (outside US)
- [ ] Field validation catches negative/excessive production volumes
- [ ] Validation failure applies 0.7x confidence penalty
- [ ] Missing expected fields contribute 0.0 at full weight to weighted average
- [ ] Critical field override: API/production below reject threshold forces review
- [ ] Field weights (api_number=3.0, operator=2.5, etc.) correctly affect weighted average
- [ ] Full pipeline processes a PDF through all stages and returns ProcessingResult
- [ ] All tests pass
- [ ] Build succeeds

## Testing Protocol

### Unit/Integration Tests

- Test file: `backend/tests/pipeline/test_validator.py`
  - [ ] Valid API number passes
  - [ ] Invalid state code fails
  - [ ] Wrong length API fails
  - [ ] Valid production volume passes
  - [ ] Negative volume fails
  - [ ] Over-limit volume fails
  - [ ] Valid date passes
  - [ ] Future date fails
  - [ ] Pre-1900 date fails
  - [ ] Valid US coordinates pass
  - [ ] Out-of-range coordinates fail
  - [ ] Valid operator name passes
  - [ ] Too-short / empty operator fails

- Test file: `backend/tests/pipeline/test_confidence.py`
  - [ ] High confidence -> auto-accept
  - [ ] Medium confidence -> review
  - [ ] Low confidence -> reject
  - [ ] Critical field override triggers review
  - [ ] Composite formula math correct (manual calculation check)
  - [ ] Missing expected fields penalize score
  - [ ] Validation failure applies 0.7x penalty
  - [ ] Field weights affect weighted average (api_number=3.0 > days_produced=1.0)
  - [ ] All tier scores populated in result

- Test file: `backend/tests/pipeline/test_pipeline.py`
  - [ ] Text PDF -> full pipeline -> result with all stages
  - [ ] Scanned PDF -> full pipeline -> result with OCR confidence
  - [ ] ProcessingResult has all expected attributes
  - [ ] overall_confidence property works

### Build/Lint/Type Checks

- [ ] `uv run ruff check backend/src/og_scraper/pipeline/` passes
- [ ] `uv run ruff format --check backend/src/og_scraper/pipeline/` passes
- [ ] `uv run pytest backend/tests/pipeline/ -v` — all tests pass

## Skills to Read

- `confidence-scoring` - Complete scoring system: three tiers, field weights, thresholds, critical field override, review queue workflow
- `document-processing-pipeline` - Pipeline architecture, stage state machine, disposition routing

## Research Files to Read

- `.claude/orchestration-og-doc-scraper/research/document-pipeline-implementation.md` - Section 5 (Confidence Scoring Implementation), Section 6 (Seven-Stage Pipeline Architecture)
- `.claude/orchestration-og-doc-scraper/research/document-processing.md` - Section 12 (Confidence Scoring for Extracted Data)

## Git

- Branch: `feat/task-2.4-validation-confidence`
- Commit message prefix: `Task 2.4:`
