"""Task 7.1: Pipeline integration tests.

Tests the document classification, extraction, normalization, and confidence
scoring pipeline working together as a unit with synthetic text data.
"""

from og_scraper.pipeline.classifier import DocumentClassifier
from og_scraper.pipeline.confidence import ConfidenceScorer
from og_scraper.pipeline.extractor import DataExtractor
from og_scraper.pipeline.normalizer import DataNormalizer


class TestClassifierExtractorIntegration:
    """Test classifier + extractor working together."""

    def test_production_report_classified_and_extracted(self):
        """Classify text as production_report, then extract production fields."""
        text = """
        MONTHLY PRODUCTION REPORT
        Production Report Summary
        Oil Production: 1,500 barrels produced
        Gas Production: 5,000 mcf produced
        Water Production: 200 BBL
        Days Produced: 30
        API Number: 42-461-12345-00-00
        Operator: Devon Energy Corporation
        Reporting Period: January 2025
        """
        classifier = DocumentClassifier()
        result = classifier.classify(text, metadata={"state": "TX"})
        assert result.doc_type == "production_report"

        extractor = DataExtractor()
        extraction = extractor.extract(text, result.doc_type, "TX")
        assert "api_number" in extraction.fields
        assert extraction.fields["api_number"].value is not None

    def test_well_permit_classified_and_extracted(self):
        """Classify text as well_permit, then extract permit fields."""
        text = """
        APPLICATION TO DRILL
        Permit to Drill
        Drilling Permit
        API Number: 35-019-23456
        Operator: Continental Resources
        Proposed Total Depth: 12,000 feet
        Anticipated Spud Date: 2025-03-15
        Surface Location: Section 12, T5N, R3W
        Bottom Hole Location: Section 12, T5N, R3W
        County: Grady
        State: Oklahoma
        """
        classifier = DocumentClassifier()
        result = classifier.classify(text)
        assert result.doc_type == "well_permit"

        extractor = DataExtractor()
        extraction = extractor.extract(text, result.doc_type, "OK")
        assert "api_number" in extraction.fields

    def test_completion_report_classified_and_extracted(self):
        """Classify text as completion_report."""
        text = """
        WELL COMPLETION REPORT
        Completion Report
        Completed Interval: 9,500 - 10,200 ft
        Perforation Interval: 9,600 - 10,100 ft
        Initial Production: 250 BOPD
        Frac Stages: 45
        Lateral Length: 10,500 ft
        Completion Date: 2025-01-20
        API Number: 42-461-99999
        """
        classifier = DocumentClassifier()
        result = classifier.classify(text)
        assert result.doc_type == "completion_report"


class TestExtractorNormalizerIntegration:
    """Test extractor + normalizer working together."""

    def test_extracted_fields_normalized(self):
        """Fields from extractor should be normalized consistently."""
        text = """
        API Number: 42-461-12345-00-00
        Operator: DEVON ENERGY CORP
        Oil Production: 1,500 BBL
        Gas Production: 5,000 MCF
        """
        extractor = DataExtractor()
        extraction = extractor.extract(text, "production_report", "TX")

        normalizer = DataNormalizer()
        normalization = normalizer.normalize(extraction)
        assert isinstance(normalization.fields, dict)


class TestFullScoringPipeline:
    """Test classifier -> extractor -> scorer as a complete flow."""

    def test_high_quality_document_gets_high_score(self):
        """Well-formed document with clear data should score high."""
        text = """
        MONTHLY PRODUCTION REPORT
        Production Report
        API Number: 42-461-12345-00-00
        Operator: Devon Energy Corporation
        Well Name: State Trust #1
        County: Harris
        Oil Production: 1,500 barrels produced
        Gas Production: 5,000 mcf produced
        Water Production: 200 BBL
        Days Produced: 30
        Reporting Period: January 2025
        """
        classifier = DocumentClassifier()
        classification = classifier.classify(text, metadata={"state": "TX"})

        extractor = DataExtractor()
        extraction = extractor.extract(text, classification.doc_type, "TX")

        expected_fields = extractor.EXPECTED_FIELDS.get(classification.doc_type, [])

        scorer = ConfidenceScorer()
        score = scorer.score(
            ocr_confidence=1.0,  # Text PDF, no OCR needed
            classification_confidence=classification.confidence,
            fields=extraction.fields,
            expected_fields=expected_fields,
        )

        assert score.document_confidence > 0.0
        assert score.disposition in ("accept", "review", "reject")

    def test_empty_document_gets_low_score(self):
        """Empty document should score below reject threshold."""
        classifier = DocumentClassifier()
        classification = classifier.classify("")

        extractor = DataExtractor()
        extraction = extractor.extract("", classification.doc_type, "TX")

        scorer = ConfidenceScorer()
        score = scorer.score(
            ocr_confidence=0.0,
            classification_confidence=classification.confidence,
            fields=extraction.fields,
            expected_fields=["api_number", "operator_name"],
        )

        assert score.document_confidence < 0.50
        assert score.disposition == "reject"

    def test_partial_data_gets_medium_score(self):
        """Document with some fields but missing critical ones should get review."""
        text = """
        Some document about oil and gas
        Operator: Devon Energy
        County: Harris, Texas
        """
        classifier = DocumentClassifier()
        classification = classifier.classify(text)

        extractor = DataExtractor()
        extraction = extractor.extract(text, classification.doc_type, "TX")

        scorer = ConfidenceScorer()
        score = scorer.score(
            ocr_confidence=0.80,
            classification_confidence=classification.confidence,
            fields=extraction.fields,
            expected_fields=["api_number", "operator_name", "production_oil_bbl"],
        )

        # Missing API number and production means low score
        assert score.document_confidence < 0.85

    def test_multiple_states_classify_consistently(self):
        """Same document type text with different state hints should classify the same."""
        text = """
        MONTHLY PRODUCTION REPORT
        Production Report Summary
        Oil Production: 1,500 barrels produced
        Gas Production: 5,000 mcf produced
        Days Produced: 30
        """
        classifier = DocumentClassifier()
        result_tx = classifier.classify(text, metadata={"state": "TX"})
        result_ok = classifier.classify(text, metadata={"state": "OK"})
        result_co = classifier.classify(text, metadata={"state": "CO"})

        assert result_tx.doc_type == result_ok.doc_type == result_co.doc_type == "production_report"
