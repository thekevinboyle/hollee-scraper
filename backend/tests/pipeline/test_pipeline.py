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

    def test_processing_result_has_all_stages(self, sample_text_pdf: Path):
        """Verify all pipeline stages are represented in the result."""
        pipeline = DocumentPipeline()
        result = pipeline.process(sample_text_pdf, state="TX")

        # Stage 1: Text extraction
        assert result.text_extraction is not None
        assert result.raw_text is not None
        assert result.extraction_method is not None
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
        """overall_confidence property should match score.document_confidence."""
        pipeline = DocumentPipeline()
        result = pipeline.process(sample_text_pdf)
        assert 0.0 <= result.overall_confidence <= 1.0
        assert result.overall_confidence == result.score.document_confidence

    def test_state_hint_used(self, sample_text_pdf: Path):
        """Both with and without state hint should produce valid results."""
        pipeline = DocumentPipeline()
        result_with_state = pipeline.process(sample_text_pdf, state="TX")
        result_no_state = pipeline.process(sample_text_pdf, state="")
        # Both should classify and produce a valid doc_type
        assert result_with_state.doc_type is not None
        assert result_no_state.doc_type is not None

    def test_file_path_stored(self, sample_text_pdf: Path):
        """ProcessingResult should store the file path as a string."""
        pipeline = DocumentPipeline()
        result = pipeline.process(sample_text_pdf, state="TX")
        assert result.file_path == str(sample_text_pdf)
        assert result.state == "TX"

    def test_extraction_errors_collected(self, sample_text_pdf: Path):
        """Processing errors from field extraction should be collected."""
        pipeline = DocumentPipeline()
        result = pipeline.process(sample_text_pdf, state="TX")
        # processing_errors is a list (may have missing field warnings)
        assert isinstance(result.processing_errors, list)
        assert isinstance(result.processing_warnings, list)

    def test_fields_extracted_from_text_pdf(self, sample_text_pdf: Path):
        """Text PDF with O&G content should extract at least some fields."""
        pipeline = DocumentPipeline()
        result = pipeline.process(sample_text_pdf, state="TX")
        # The sample_text_pdf conftest has API number, operator, production data
        assert len(result.field_extraction.fields) > 0

    def test_text_pdf_high_ocr_confidence(self, sample_text_pdf: Path):
        """Text PDFs should have OCR confidence of 1.0."""
        pipeline = DocumentPipeline()
        result = pipeline.process(sample_text_pdf, state="TX")
        assert result.score.ocr_confidence == 1.0

    def test_empty_pdf_handles_gracefully(self, empty_pdf: Path):
        """Empty PDF should process without crashing."""
        pipeline = DocumentPipeline()
        result = pipeline.process(empty_pdf, state="TX")
        assert isinstance(result, ProcessingResult)
        # Empty PDF should have low confidence or unknown doc_type
        assert result.doc_type == "unknown" or result.disposition in ("review", "reject")

    def test_multi_page_pdf(self, multi_page_pdf: Path):
        """Multi-page PDF should process all pages."""
        pipeline = DocumentPipeline()
        result = pipeline.process(multi_page_pdf, state="TX")
        assert isinstance(result, ProcessingResult)
        assert result.text_extraction.total_pages == 3
        assert len(result.raw_text) > 0

    def test_normalized_fields_populated(self, sample_text_pdf: Path):
        """Normalized fields should be a dict with values."""
        pipeline = DocumentPipeline()
        result = pipeline.process(sample_text_pdf, state="TX")
        assert isinstance(result.normalized_fields, dict)
        # Should have at least as many normalized fields as extracted fields
        assert len(result.normalized_fields) > 0

    def test_score_has_field_confidences(self, sample_text_pdf: Path):
        """Score result should contain per-field confidence details."""
        pipeline = DocumentPipeline()
        result = pipeline.process(sample_text_pdf, state="TX")
        assert isinstance(result.score.field_confidences, dict)
        for field_name, fc in result.score.field_confidences.items():
            assert 0.0 <= fc.adjusted_confidence <= 1.0
            assert fc.disposition in ("accept", "review", "reject")
            assert fc.weight > 0
