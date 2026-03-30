import pytest

from og_scraper.pipeline.confidence import (
    CRITICAL_FIELDS,
    DOCUMENT_ACCEPT_THRESHOLD,
    DOCUMENT_REVIEW_THRESHOLD,
    FIELD_WEIGHTS,
    ConfidenceScorer,
    DocumentScore,
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
        # Use a non-critical field to avoid critical field override forcing review
        fields = {
            "well_name": make_field("???", confidence=0.20, pattern_specificity=0.5),
        }
        result = scorer.score(
            ocr_confidence=0.30,
            classification_confidence=0.20,
            fields=fields,
        )
        # 0.3*0.20 + 0.5*(0.20*0.5) + 0.2*0.30 = 0.06 + 0.05 + 0.06 = 0.17
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
        # 0.50 * 0.8 = 0.40, then * 0.7 (validation penalty) = 0.28
        # This is below the api_number reject threshold (0.70), so override triggers
        assert result.critical_field_override
        assert result.disposition == "review"

    def test_critical_field_production(self):
        """Production volume below reject threshold also forces review."""
        scorer = ConfidenceScorer()
        fields = {
            "api_number": make_field("42501201300000", confidence=0.95),
            "operator_name": make_field("Devon Energy", confidence=0.95),
            # Negative volume fails validation -> confidence * 0.7
            "production_oil_bbl": make_field(-100, confidence=0.50, pattern_specificity=0.8),
        }
        result = scorer.score(
            ocr_confidence=1.0,
            classification_confidence=0.98,
            fields=fields,
        )
        # 0.50 * 0.8 = 0.40, * 0.7 = 0.28, below 0.70 reject threshold
        assert result.critical_field_override
        assert result.disposition == "review"

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

    def test_composite_formula_precise(self):
        """More precise composite formula check with known weights."""
        scorer = ConfidenceScorer()
        # Use a field with no validator to avoid validation penalty
        fields = {
            "well_name": make_field("Test Well #1", confidence=0.80, pattern_specificity=1.0),
        }
        result = scorer.score(
            ocr_confidence=0.60,
            classification_confidence=0.70,
            fields=fields,
        )
        # 0.3*0.70 + 0.5*0.80 + 0.2*0.60 = 0.21 + 0.40 + 0.12 = 0.73
        assert abs(result.document_confidence - 0.73) < 0.01

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

    def test_missing_fields_contribute_zero(self):
        """Missing expected fields should be present in results with 0.0 confidence."""
        scorer = ConfidenceScorer()
        fields = {
            "api_number": make_field("42501201300000", confidence=0.95),
        }
        result = scorer.score(
            ocr_confidence=1.0,
            classification_confidence=0.98,
            fields=fields,
            expected_fields=["api_number", "operator_name"],
        )
        assert "operator_name" in result.field_confidences
        assert result.field_confidences["operator_name"].adjusted_confidence == 0.0
        assert result.field_confidences["operator_name"].disposition == "reject"

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
        # Should be 0.90 * 1.0 * 0.7 = 0.63
        assert abs(api_field.adjusted_confidence - 0.63) < 0.01

    def test_validation_success_no_penalty(self):
        """Valid field should NOT receive the 0.7x penalty."""
        scorer = ConfidenceScorer()
        fields = {
            "api_number": make_field("42501201300000", confidence=0.90),
        }
        result = scorer.score(
            ocr_confidence=1.0,
            classification_confidence=0.90,
            fields=fields,
        )
        api_field = result.field_confidences["api_number"]
        assert api_field.validated
        # Should be 0.90 * 1.0 = 0.90 (no penalty)
        assert abs(api_field.adjusted_confidence - 0.90) < 0.01

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
        # because api_number has weight 3.0 vs days_produced weight 1.0
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

    def test_empty_fields(self):
        """Scoring with no fields should still produce a valid result."""
        scorer = ConfidenceScorer()
        result = scorer.score(
            ocr_confidence=1.0,
            classification_confidence=0.90,
            fields={},
        )
        assert result.weighted_field_confidence == 0.0
        # 0.3*0.90 + 0.5*0.0 + 0.2*1.0 = 0.27 + 0.0 + 0.20 = 0.47
        assert abs(result.document_confidence - 0.47) < 0.01
        assert result.disposition == "reject"

    def test_pattern_specificity_affects_confidence(self):
        """Pattern specificity multiplier should reduce adjusted confidence."""
        scorer = ConfidenceScorer()
        fields_high_specificity = {
            "api_number": make_field("42501201300000", confidence=0.90, pattern_specificity=1.0),
        }
        fields_low_specificity = {
            "api_number": make_field("42501201300000", confidence=0.90, pattern_specificity=0.7),
        }
        result_high = scorer.score(1.0, 0.90, fields_high_specificity)
        result_low = scorer.score(1.0, 0.90, fields_low_specificity)
        assert result_high.field_confidences["api_number"].adjusted_confidence > \
            result_low.field_confidences["api_number"].adjusted_confidence

    def test_confidence_capped_at_max(self):
        """Confidence should not exceed 0.99."""
        scorer = ConfidenceScorer()
        fields = {
            "well_name": make_field("Test Well", confidence=1.0, pattern_specificity=1.0),
        }
        result = scorer.score(1.0, 1.0, fields)
        assert result.field_confidences["well_name"].adjusted_confidence <= 0.99

    def test_field_thresholds(self):
        """Verify field-level dispositions use field-specific thresholds."""
        scorer = ConfidenceScorer()
        # API number: accept >= 0.95, review >= 0.70, reject < 0.70
        fields = {
            "api_number": make_field("42501201300000", confidence=0.80),
        }
        result = scorer.score(1.0, 0.90, fields)
        api_field = result.field_confidences["api_number"]
        # 0.80 is between 0.70 and 0.95 for api_number -> review
        assert api_field.disposition == "review"

    def test_document_score_is_dataclass(self):
        """DocumentScore should be a proper dataclass with all expected fields."""
        scorer = ConfidenceScorer()
        fields = {"api_number": make_field("42501201300000", confidence=0.90)}
        result = scorer.score(0.85, 0.90, fields)
        assert isinstance(result, DocumentScore)
        assert hasattr(result, "ocr_confidence")
        assert hasattr(result, "field_confidences")
        assert hasattr(result, "weighted_field_confidence")
        assert hasattr(result, "classification_confidence")
        assert hasattr(result, "document_confidence")
        assert hasattr(result, "disposition")
        assert hasattr(result, "disposition_reasons")
        assert hasattr(result, "critical_field_override")

    def test_critical_fields_defined(self):
        """Verify critical fields include api_number and production fields."""
        assert "api_number" in CRITICAL_FIELDS
        assert "production_oil_bbl" in CRITICAL_FIELDS
        assert "production_gas_mcf" in CRITICAL_FIELDS

    def test_field_weights_defined(self):
        """Verify key field weights match specification."""
        assert FIELD_WEIGHTS["api_number"] == 3.0
        assert FIELD_WEIGHTS["operator_name"] == 2.5
        assert FIELD_WEIGHTS["production_oil_bbl"] == 2.0
        assert FIELD_WEIGHTS["days_produced"] == 1.0
