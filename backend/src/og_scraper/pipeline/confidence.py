"""
Three-tier confidence scoring system for O&G document pipeline.

Tier 1: OCR Confidence -- from PaddleOCR rec_score (per page, minimum for document)
Tier 2: Field-Level Confidence -- base * specificity, validation penalty, cross-ref bonus
Tier 3: Document-Level Confidence -- composite formula combining all tiers

Disposition:
  >= 0.85  ->  auto-accept
  0.50-0.84 -> review queue
  < 0.50   ->  reject
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

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

# Critical fields -- if ANY is below reject threshold, force document to review
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
    raw_confidence: float  # Base confidence from extraction
    validated: bool  # Whether value passed validation
    validation_reason: str | None  # Reason for validation failure
    adjusted_confidence: float  # After validation penalty / cross-ref bonus
    disposition: Literal["accept", "review", "reject"]
    weight: float  # Field importance weight


@dataclass
class DocumentScore:
    """Complete confidence scoring result for a document."""

    # Tier 1: OCR
    ocr_confidence: float  # Minimum page OCR confidence

    # Tier 2: Fields
    field_confidences: dict[str, FieldConfidenceResult]  # Per-field scores
    weighted_field_confidence: float  # Weighted average of all field confidences

    # Tier 3: Document
    classification_confidence: float
    document_confidence: float  # Final composite score

    # Disposition
    disposition: Literal["accept", "review", "reject"]
    disposition_reasons: list[str] = field(default_factory=list)  # Why this disposition was chosen

    # Critical field overrides
    critical_field_override: bool = False  # True if a critical field forced review/reject


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
            ocr_confidence: Tier 1 -- minimum page OCR confidence (from TextExtractor)
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
            pattern_specificity = getattr(field_val, "pattern_specificity", 1.0)

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
                    field_disposition: Literal["accept", "review", "reject"] = "accept"
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
                    f"Critical field '{field_name}' below reject threshold (confidence={adjusted:.3f})"
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
            weighted_field_confidence = (
                sum(fr.adjusted_confidence * fr.weight for fr in field_results.values()) / total_weight
            )
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
            disposition: Literal["accept", "review", "reject"] = "review"
            disposition_reasons.append("Critical field override -- forced to review queue")
        elif document_confidence >= DOCUMENT_ACCEPT_THRESHOLD:
            disposition = "accept"
            disposition_reasons.append(f"Document confidence {document_confidence:.3f} >= {DOCUMENT_ACCEPT_THRESHOLD}")
        elif document_confidence >= DOCUMENT_REVIEW_THRESHOLD:
            disposition = "review"
            disposition_reasons.append(
                f"Document confidence {document_confidence:.3f} in review range "
                f"[{DOCUMENT_REVIEW_THRESHOLD}, {DOCUMENT_ACCEPT_THRESHOLD})"
            )
        else:
            disposition = "reject"
            disposition_reasons.append(f"Document confidence {document_confidence:.3f} < {DOCUMENT_REVIEW_THRESHOLD}")

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
