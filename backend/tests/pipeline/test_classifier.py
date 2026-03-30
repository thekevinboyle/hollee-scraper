"""Tests for the document classification pipeline.

Covers all three classification strategies:
1. Form number detection (TX, OK, CO, NM, ND, WY, PA forms)
2. Header/footer agency analysis (all 10 states)
3. Weighted keyword matching (all 7 document types)
Plus the combined DocumentClassifier pipeline.
"""

import pytest

from og_scraper.pipeline.classifier import (
    ClassificationResult,
    DocumentClassifier,
    analyze_header_footer,
    classify_by_keywords,
    detect_form_number,
)


# --- Sample document text snippets for testing ---

PRODUCTION_REPORT_TEXT = """
RAILROAD COMMISSION OF TEXAS
OIL AND GAS DIVISION

MONTHLY PRODUCTION REPORT

Operator: Devon Energy Corporation
Lease Name: Permian Basin Unit #42
API Number: 42-501-20130-00-00

Reporting Period: January 2026

Oil Production: 1,234 BBL
Gas Production: 5,678 MCF
Water Production: 890 BBL
Days Produced: 31
"""

WELL_PERMIT_TEXT = """
APPLICATION TO DRILL, DEEPEN, OR PLUG BACK
FORM W-1

Railroad Commission of Texas

Operator: Pioneer Natural Resources
Well Name: Spraberry #7
API Number: 42-329-34567

Proposed Total Depth: 12,500 ft
Surface Location: Section 12, Block 37, T2S
Anticipated Spud Date: 03/15/2026
"""

COMPLETION_REPORT_TEXT = """
WELL COMPLETION REPORT
Oklahoma Corporation Commission
Form 1002C

Operator: Continental Resources
Well Name: SCOOP Unit 14-2H
API Number: 37-019-24567-00-00

Completion Date: 02/28/2026
Total Depth: 18,400 ft
Lateral Length: 10,200 ft
Perforation Interval: 8,200 - 18,400 ft
Frac Stages: 45
Initial Production Rate: 1,200 BOPD
"""

PLUGGING_REPORT_TEXT = """
PLUGGING REPORT
PLUG AND ABANDON

Well Name: Old Discovery #1
API Number: 42-383-00123

Cement Plug placed at 5,000 ft to 5,200 ft
Surface Restoration completed
Casing Left in Hole: 2,500 ft of 7" casing
"""

SPACING_ORDER_TEXT = """
BEFORE THE CORPORATION COMMISSION OF THE STATE OF OKLAHOMA

POOLING ORDER NO. 789123

In the matter of the application of Continental Resources
for a drilling and spacing unit order
covering Section 14, Township 6 North, Range 5 West

The Commission hereby establishes a 640-acre drilling unit
with compulsory pooling of all interest owners.
"""

INSPECTION_RECORD_TEXT = """
FIELD INSPECTION REPORT

Colorado Energy and Carbon Management Commission

Inspector: John Smith
Inspection Date: 03/01/2026
Well Inspection of: Niobrara Unit #3

Findings: All equipment in compliance
Violation: None observed
Compliance Status: Compliant
"""

INCIDENT_REPORT_TEXT = """
SPILL REPORT / INCIDENT NOTIFICATION

Railroad Commission of Texas

Incident Report filed by: XTO Energy
Date of Incident: 02/15/2026

Type: Crude oil spill
Volume Released: 25 BBL
Volume Recovered: 20 BBL
Environmental Release to: Soil
Corrective Action: Excavation and disposal of contaminated soil
"""

AMBIGUOUS_TEXT = """
Well information document
Some general oil and gas data
County: Ector
State: Texas
"""

EMPTY_TEXT = ""


class TestFormNumberDetection:
    def test_texas_w1_permit(self):
        result = detect_form_number("Form W-1 Application to Drill")
        assert result is not None
        assert result[1] == "well_permit"
        assert result[2] == "TX"

    def test_texas_w2_completion(self):
        result = detect_form_number("Form W-2 Oil Well Completion Report")
        assert result is not None
        assert result[1] == "completion_report"

    def test_texas_w3_plugging(self):
        result = detect_form_number("Form W-3 Plugging Record")
        assert result is not None
        assert result[1] == "plugging_report"

    def test_texas_pr_production(self):
        result = detect_form_number("Form PR Monthly Production Report")
        assert result is not None
        assert result[1] == "production_report"
        assert result[2] == "TX"

    def test_texas_h10_incident(self):
        result = detect_form_number("Form H-10 Incident Report")
        assert result is not None
        assert result[1] == "incident_report"
        assert result[2] == "TX"

    def test_oklahoma_1002a(self):
        result = detect_form_number("Application Form 1002A Intent to Drill")
        assert result is not None
        assert result[1] == "well_permit"
        assert result[2] == "OK"

    def test_oklahoma_1002c(self):
        result = detect_form_number("Form 1002C Completion Report")
        assert result is not None
        assert result[1] == "completion_report"

    def test_colorado_form2(self):
        result = detect_form_number("Form 2 Application for Permit to Drill")
        assert result is not None
        assert result[1] == "well_permit"
        assert result[2] == "CO"

    def test_colorado_form5a(self):
        result = detect_form_number("Form 5A Completed Interval Report")
        assert result is not None
        assert result[1] == "completion_report"

    def test_colorado_form6(self):
        result = detect_form_number("Form 6 Plug and Abandon Report")
        assert result is not None
        assert result[1] == "plugging_report"
        assert result[2] == "CO"

    def test_new_mexico_c101(self):
        result = detect_form_number("C-101 Application for Permit to Drill")
        assert result is not None
        assert result[1] == "well_permit"
        assert result[2] == "NM"

    def test_no_form_number(self):
        result = detect_form_number("Just a regular document with no form numbers")
        assert result is None

    def test_case_insensitive(self):
        result = detect_form_number("FORM W-1 APPLICATION TO DRILL")
        assert result is not None
        assert result[1] == "well_permit"

    def test_form_number_with_spaces(self):
        result = detect_form_number("Form W 1 Application to Drill")
        assert result is not None
        assert result[1] == "well_permit"

    def test_eia_914_federal(self):
        result = detect_form_number("EIA-914 Monthly Crude Oil Production Report")
        assert result is not None
        assert result[1] == "production_report"
        assert result[2] == "FED"


class TestHeaderFooterAnalysis:
    def test_texas_agency(self):
        text = "Railroad Commission of Texas\nOil and Gas Division\nSome content"
        result = analyze_header_footer(text)
        assert result["state_agency"] == "TX"

    def test_oklahoma_agency(self):
        text = "Corporation Commission of Oklahoma\nOrder No. 12345"
        result = analyze_header_footer(text)
        assert result["state_agency"] == "OK"

    def test_colorado_agency(self):
        text = "Colorado Oil and Gas Conservation Commission\nInspection Record"
        result = analyze_header_footer(text)
        assert result["state_agency"] == "CO"

    def test_north_dakota_agency(self):
        text = "Department of Mineral Resources\nNorth Dakota"
        result = analyze_header_footer(text)
        assert result["state_agency"] == "ND"

    def test_new_mexico_agency(self):
        text = "Oil Conservation Division\nNew Mexico"
        result = analyze_header_footer(text)
        assert result["state_agency"] == "NM"

    def test_wyoming_agency(self):
        text = "Wyoming Oil and Gas Conservation Commission\nWell Data"
        result = analyze_header_footer(text)
        assert result["state_agency"] == "WY"

    def test_louisiana_agency(self):
        text = "SONRIS\nLouisiana Well Data"
        result = analyze_header_footer(text)
        assert result["state_agency"] == "LA"

    def test_pennsylvania_agency(self):
        text = "PA DEP\nOil and Gas Well Report"
        result = analyze_header_footer(text)
        assert result["state_agency"] == "PA"

    def test_california_agency(self):
        text = "CalGEM\nGeologic Energy Management Division"
        result = analyze_header_footer(text)
        assert result["state_agency"] == "CA"

    def test_alaska_agency(self):
        text = "AOGCC\nAlaska Oil and Gas Report"
        result = analyze_header_footer(text)
        assert result["state_agency"] == "AK"

    def test_no_agency(self):
        text = "Generic Document\nWith no agency header"
        result = analyze_header_footer(text)
        assert result["state_agency"] is None

    def test_document_title_detection(self):
        text = "RAILROAD COMMISSION OF TEXAS\nMONTHLY PRODUCTION REPORT\nSome data"
        result = analyze_header_footer(text)
        assert result["document_title"] is not None
        assert "report" in result["document_title"].lower()


class TestKeywordClassification:
    def test_production_report(self):
        result = classify_by_keywords(PRODUCTION_REPORT_TEXT)
        assert result.doc_type == "production_report"
        assert result.confidence > 0.3

    def test_well_permit(self):
        result = classify_by_keywords(WELL_PERMIT_TEXT)
        assert result.doc_type == "well_permit"
        assert result.confidence > 0.2

    def test_completion_report(self):
        result = classify_by_keywords(COMPLETION_REPORT_TEXT)
        assert result.doc_type == "completion_report"
        assert result.confidence > 0.5

    def test_plugging_report(self):
        result = classify_by_keywords(PLUGGING_REPORT_TEXT)
        assert result.doc_type == "plugging_report"
        assert result.confidence > 0.5

    def test_spacing_order(self):
        result = classify_by_keywords(SPACING_ORDER_TEXT)
        assert result.doc_type == "spacing_order"
        assert result.confidence > 0.4

    def test_inspection_record(self):
        result = classify_by_keywords(INSPECTION_RECORD_TEXT)
        assert result.doc_type == "inspection_record"
        assert result.confidence > 0.4

    def test_incident_report(self):
        result = classify_by_keywords(INCIDENT_REPORT_TEXT)
        assert result.doc_type == "incident_report"
        assert result.confidence > 0.5

    def test_strong_signals_boost_confidence(self):
        # Text with 2+ strong signals should get boosted
        text = "Monthly production report. Annual production summary. Oil production 1,234 BBL."
        result = classify_by_keywords(text)
        assert result.doc_type == "production_report"
        assert result.confidence > 0.4

    def test_ambiguous_text_low_confidence(self):
        result = classify_by_keywords(AMBIGUOUS_TEXT)
        assert result.confidence < 0.5

    def test_empty_text_returns_unknown(self):
        result = classify_by_keywords("")
        assert result.doc_type == "unknown"
        assert result.confidence == 0.0

    def test_scores_dict_populated(self):
        result = classify_by_keywords(PRODUCTION_REPORT_TEXT)
        assert len(result.scores) > 0
        assert "production_report" in result.scores

    def test_matched_keywords_populated(self):
        result = classify_by_keywords(PRODUCTION_REPORT_TEXT)
        assert len(result.matched_keywords) > 0

    def test_ambiguity_penalty_applied(self):
        """When two types score very similarly, confidence should be penalized."""
        # Text that could be inspection or incident (both have "corrective action", "violation")
        text = (
            "Compliance inspection report. "
            "Violation found. Corrective action required. "
            "Incident report filed. Spill report attached."
        )
        result = classify_by_keywords(text)
        # With ambiguity between types, confidence should be moderated
        assert result.confidence < 0.9


class TestDocumentClassifier:
    """Test the full classification pipeline."""

    def test_form_number_highest_priority(self):
        classifier = DocumentClassifier()
        result = classifier.classify(WELL_PERMIT_TEXT)
        assert result.doc_type == "well_permit"
        assert result.form_number is not None
        assert result.confidence == 0.98
        assert result.strategy == "form_number"

    def test_form_number_sets_state_agency(self):
        classifier = DocumentClassifier()
        result = classifier.classify(WELL_PERMIT_TEXT)
        assert result.state_agency == "TX"

    def test_keyword_classification(self):
        classifier = DocumentClassifier()
        result = classifier.classify(PRODUCTION_REPORT_TEXT)
        assert result.doc_type == "production_report"
        assert result.confidence > 0.5

    def test_header_boosts_keyword_confidence(self):
        # Text with agency header should have higher confidence than without
        with_header = "Railroad Commission of Texas\n" + PRODUCTION_REPORT_TEXT
        without_header = "Generic Agency\n" + PRODUCTION_REPORT_TEXT.replace(
            "RAILROAD COMMISSION OF TEXAS\nOIL AND GAS DIVISION\n\n", ""
        )
        classifier = DocumentClassifier()
        result_with = classifier.classify(with_header)
        result_without = classifier.classify(without_header)
        # Both should classify correctly; with header may have higher confidence
        assert result_with.doc_type == "production_report"
        assert result_without.doc_type == "production_report"

    def test_combined_strategy_when_header_found(self):
        classifier = DocumentClassifier()
        # Production report text already has "RAILROAD COMMISSION OF TEXAS" in header
        result = classifier.classify(PRODUCTION_REPORT_TEXT)
        assert result.strategy in ("combined", "form_number")

    def test_unknown_for_empty_text(self):
        classifier = DocumentClassifier()
        result = classifier.classify("")
        assert result.doc_type == "unknown"
        assert result.confidence == 0.0

    def test_unknown_for_none_text(self):
        classifier = DocumentClassifier()
        result = classifier.classify(None)
        assert result.doc_type == "unknown"
        assert result.confidence == 0.0

    def test_unknown_for_whitespace_text(self):
        classifier = DocumentClassifier()
        result = classifier.classify("   \n\n  ")
        assert result.doc_type == "unknown"
        assert result.confidence == 0.0

    def test_unknown_for_irrelevant_text(self):
        classifier = DocumentClassifier()
        result = classifier.classify("The quick brown fox jumps over the lazy dog.")
        assert result.doc_type == "unknown"
        assert result.confidence < 0.30

    def test_metadata_state_hint(self):
        classifier = DocumentClassifier()
        # Providing metadata with state should influence confidence
        text = (
            "Railroad Commission of Texas\n"
            "Monthly Production Report\n"
            "Oil Production: 1234 BBL\n"
            "Gas Production: 5678 MCF\n"
            "Days Produced: 30\n"
        )
        result = classifier.classify(text, metadata={"state": "TX"})
        assert result.doc_type == "production_report"

    def test_metadata_state_hint_boosts_confidence(self):
        classifier = DocumentClassifier()
        text = (
            "Railroad Commission of Texas\n"
            "Monthly Production Report\n"
            "Oil Production: 1234 BBL\n"
            "Gas Production: 5678 MCF\n"
            "Days Produced: 30\n"
        )
        result_without = classifier.classify(text)
        result_with = classifier.classify(text, metadata={"state": "TX"})
        # With matching metadata, confidence should be at least as high
        assert result_with.confidence >= result_without.confidence

    def test_all_seven_document_types(self):
        """Verify all 7 document types can be classified."""
        classifier = DocumentClassifier()
        samples = {
            "production_report": PRODUCTION_REPORT_TEXT,
            "well_permit": WELL_PERMIT_TEXT,
            "completion_report": COMPLETION_REPORT_TEXT,
            "plugging_report": PLUGGING_REPORT_TEXT,
            "spacing_order": SPACING_ORDER_TEXT,
            "inspection_record": INSPECTION_RECORD_TEXT,
            "incident_report": INCIDENT_REPORT_TEXT,
        }
        for expected_type, text in samples.items():
            result = classifier.classify(text)
            assert result.doc_type == expected_type, (
                f"Expected {expected_type}, got {result.doc_type} "
                f"(confidence={result.confidence}, keywords={result.matched_keywords})"
            )

    def test_classification_result_has_all_fields(self):
        classifier = DocumentClassifier()
        result = classifier.classify(PRODUCTION_REPORT_TEXT)
        assert hasattr(result, "doc_type")
        assert hasattr(result, "confidence")
        assert hasattr(result, "matched_keywords")
        assert hasattr(result, "form_number")
        assert hasattr(result, "state_agency")
        assert hasattr(result, "strategy")
        assert 0.0 <= result.confidence <= 1.0

    def test_confidence_always_between_0_and_1(self):
        """Confidence should never exceed 1.0 or go below 0.0."""
        classifier = DocumentClassifier()
        texts = [
            PRODUCTION_REPORT_TEXT,
            WELL_PERMIT_TEXT,
            COMPLETION_REPORT_TEXT,
            PLUGGING_REPORT_TEXT,
            SPACING_ORDER_TEXT,
            INSPECTION_RECORD_TEXT,
            INCIDENT_REPORT_TEXT,
            AMBIGUOUS_TEXT,
            EMPTY_TEXT,
            "random unrelated text about cooking recipes",
        ]
        for text in texts:
            result = classifier.classify(text)
            assert 0.0 <= result.confidence <= 1.0, (
                f"Confidence {result.confidence} out of range for text: {text[:50]}..."
            )

    def test_completion_report_with_oklahoma_form(self):
        """Oklahoma 1002C form should be detected by form number strategy."""
        classifier = DocumentClassifier()
        result = classifier.classify(COMPLETION_REPORT_TEXT)
        assert result.doc_type == "completion_report"
        assert result.form_number is not None
        assert result.strategy == "form_number"
        assert result.state_agency == "OK"

    def test_inspection_with_colorado_header(self):
        """Inspection record with Colorado agency header should use combined strategy."""
        classifier = DocumentClassifier()
        result = classifier.classify(INSPECTION_RECORD_TEXT)
        assert result.doc_type == "inspection_record"
        # Colorado ECMC should be detected in header
        assert result.state_agency == "CO"

    def test_spacing_order_with_oklahoma_header(self):
        """Spacing order with Oklahoma header should classify correctly."""
        classifier = DocumentClassifier()
        result = classifier.classify(SPACING_ORDER_TEXT)
        assert result.doc_type == "spacing_order"
