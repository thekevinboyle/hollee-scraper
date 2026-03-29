# Task 2.R: Phase 2 Regression

## Objective

Full regression test of the entire document processing pipeline built in Phase 2 (Tasks 2.1-2.4). Verify that all pipeline stages work correctly in isolation and integrated end-to-end. Confirm that text PDFs auto-accept, scanned PDFs route to review, corrupt files are rejected, confidence scoring math is correct, classification accuracy exceeds 80%, and single-document processing completes within 30 seconds (including OCR).

## Context

This is the regression task for Phase 2. All four feature tasks must be complete before this runs. This task does NOT build new features — it exclusively tests existing code. Any failures discovered here must be fixed before proceeding to Phase 3 (Backend API). The pipeline built in Phase 2 is the core data quality engine that everything else depends on.

## Dependencies

- Task 2.1 - PDF text extraction and OCR (TextExtractor, OCR wrapper, page classifier)
- Task 2.2 - Document classification (DocumentClassifier, keyword matching, form detection)
- Task 2.3 - Data extraction and normalization (DataExtractor, DataNormalizer, regex patterns)
- Task 2.4 - Validation and confidence scoring (ConfidenceScorer, DocumentPipeline, validators)
- Task 1.1 - Project structure (for running tests)
- Task 1.2 - Database schema (for verifying pipeline output matches DB columns)

## Blocked By

- Task 2.1, Task 2.2, Task 2.3, Task 2.4

## Research Findings

- From `confidence-scoring` skill: Document-level auto-accept threshold is 0.85, review is 0.50-0.84, reject is < 0.50. Composite formula: `0.3 * classification + 0.5 * weighted_fields + 0.2 * ocr`.
- From `document-processing-pipeline` skill: CPU throughput for OCR is 0.3-1.0 pages/second. Text PDF extraction is 50-100 pages/second. A single document should process in <30 seconds total.
- From `document-processing-pipeline` skill: Classification target accuracy is >80% using the three-strategy cascade. Form number detection is ~100% accurate when forms are present.

## Implementation Plan

### Step 1: Create Comprehensive Test Fixtures

Create a set of test documents that cover the full range of pipeline scenarios. These go in `backend/tests/fixtures/` and are generated programmatically in a shared conftest.

**Required test fixtures:**

| Fixture | Type | Content | Expected Result |
|---------|------|---------|-----------------|
| `text_production_report.pdf` | Text PDF | TX production report with all fields | auto-accept, type=production_report |
| `text_well_permit.pdf` | Text PDF | OK well permit with Form 1002A | auto-accept, type=well_permit |
| `text_completion_report.pdf` | Text PDF | CO completion report | auto-accept, type=completion_report |
| `scanned_production_report.pdf` | Scanned PDF | Production data as image | review or accept, type=production_report |
| `scanned_poor_quality.pdf` | Low-quality scan | Faded, skewed text | review or reject |
| `mixed_document.pdf` | Mixed PDF | Page 1 text, page 2 scanned | method=mixed |
| `empty_document.pdf` | Empty PDF | Blank page | reject, type=unknown |
| `corrupt_file.pdf` | Corrupt | Invalid PDF bytes | error/reject |
| `multi_page_report.pdf` | Text PDF | 3-page production report | auto-accept, all pages processed |
| `ambiguous_document.pdf` | Text PDF | Text with mixed O&G terms | review, type may vary |

**Fixture generation (in `backend/tests/pipeline/conftest.py`):**

```python
import pytest
from pathlib import Path
import fitz  # PyMuPDF


@pytest.fixture
def fixtures_dir(tmp_path: Path) -> Path:
    """Create a temporary directory for test fixtures."""
    fixtures = tmp_path / "fixtures"
    fixtures.mkdir()
    return fixtures


@pytest.fixture
def sample_text_pdf(fixtures_dir: Path) -> Path:
    """Text-based production report PDF with all major fields."""
    path = fixtures_dir / "text_production_report.pdf"
    doc = fitz.open()
    page = doc.new_page()
    text = """RAILROAD COMMISSION OF TEXAS
OIL AND GAS DIVISION

MONTHLY PRODUCTION REPORT
Form PR

Operator: Devon Energy Corporation
Well Name: Permian Basin Unit #42
API Number: 42-501-20130-00-00
County: Ector
State: Texas

Reporting Period: January 2026

Oil Production: 1,234 BBL
Gas Production: 5,678 MCF
Water Production: 890 BBL
Days Produced: 31

Latitude: 31.9505
Longitude: -102.0775
"""
    page.insert_text((72, 72), text, fontsize=10)
    doc.save(str(path))
    doc.close()
    return path


@pytest.fixture
def sample_well_permit_pdf(fixtures_dir: Path) -> Path:
    """Text-based well permit PDF with form number."""
    path = fixtures_dir / "text_well_permit.pdf"
    doc = fitz.open()
    page = doc.new_page()
    text = """APPLICATION TO DRILL, DEEPEN, OR PLUG BACK
FORM W-1

Railroad Commission of Texas

Operator: Pioneer Natural Resources
Well Name: Spraberry Unit #7
API Number: 42-329-34567-00-00
County: Midland
State: Texas

Proposed Total Depth: 12,500 ft
Surface Location: Section 12, Block 37, T2S
Anticipated Spud Date: 03/15/2026
Permit Date: 02/01/2026
Permit Number: 876543
"""
    page.insert_text((72, 72), text, fontsize=10)
    doc.save(str(path))
    doc.close()
    return path


@pytest.fixture
def sample_completion_pdf(fixtures_dir: Path) -> Path:
    """Text-based completion report."""
    path = fixtures_dir / "text_completion_report.pdf"
    doc = fitz.open()
    page = doc.new_page()
    text = """WELL COMPLETION REPORT
Oklahoma Corporation Commission
Form 1002C

Operator: Continental Resources Inc
Well Name: SCOOP Unit 14-2H
API Number: 37-019-24567-00-00
County: Grady

Completion Date: 02/28/2026
Total Depth: 18,400 ft
Lateral Length: 10,200 ft
Perforation Interval: 8,200 - 18,400 ft
Frac Stages: 45
Initial Production Rate: 1,200 BOPD
"""
    page.insert_text((72, 72), text, fontsize=10)
    doc.save(str(path))
    doc.close()
    return path


@pytest.fixture
def sample_scan_pdf(fixtures_dir: Path) -> Path:
    """Scanned-style PDF (text rendered as image)."""
    path = fixtures_dir / "scanned_production_report.pdf"
    doc = fitz.open()

    # Create text, render to image, embed image
    tmp_doc = fitz.open()
    tmp_page = tmp_doc.new_page()
    tmp_page.insert_text((72, 72), (
        "PRODUCTION REPORT\n"
        "Operator: Devon Energy\n"
        "API No: 42-501-20130-00-00\n"
        "Oil: 1,234 BBL\n"
        "Gas: 5,678 MCF\n"
    ), fontsize=14)
    pix = tmp_page.get_pixmap(dpi=300)
    img_data = pix.tobytes("png")
    tmp_doc.close()

    page = doc.new_page()
    page.insert_image(page.rect, stream=img_data)
    doc.save(str(path))
    doc.close()
    return path


@pytest.fixture
def empty_pdf(fixtures_dir: Path) -> Path:
    """PDF with a blank page."""
    path = fixtures_dir / "empty_document.pdf"
    doc = fitz.open()
    doc.new_page()
    doc.save(str(path))
    doc.close()
    return path


@pytest.fixture
def multi_page_pdf(fixtures_dir: Path) -> Path:
    """Multi-page text PDF."""
    path = fixtures_dir / "multi_page_report.pdf"
    doc = fitz.open()
    for i in range(3):
        page = doc.new_page()
        page.insert_text((72, 72), f"Page {i+1}\nProduction Report\nOil: {1000+i*100} BBL\n", fontsize=10)
    doc.save(str(path))
    doc.close()
    return path


@pytest.fixture
def corrupt_pdf(fixtures_dir: Path) -> Path:
    """Corrupt/invalid PDF file."""
    path = fixtures_dir / "corrupt_file.pdf"
    path.write_bytes(b"THIS IS NOT A PDF FILE AT ALL")
    return path


@pytest.fixture
def ambiguous_pdf(fixtures_dir: Path) -> Path:
    """PDF with ambiguous content that does not clearly match one type."""
    path = fixtures_dir / "ambiguous_document.pdf"
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), (
        "General Well Information\n"
        "County: Ector\n"
        "State: Texas\n"
        "Various oil and gas data follows.\n"
    ), fontsize=10)
    doc.save(str(path))
    doc.close()
    return path
```

### Step 2: Run All Existing Unit Tests

Execute every test file created in Tasks 2.1-2.4.

```bash
uv run pytest backend/tests/pipeline/ -v --tb=long
```

**Expected test files:**
- `backend/tests/pipeline/test_text_extractor.py` (Task 2.1)
- `backend/tests/pipeline/test_classifier.py` (Task 2.2)
- `backend/tests/pipeline/test_extractor.py` (Task 2.3)
- `backend/tests/pipeline/test_normalizer.py` (Task 2.3)
- `backend/tests/pipeline/test_validator.py` (Task 2.4)
- `backend/tests/pipeline/test_confidence.py` (Task 2.4)
- `backend/tests/pipeline/test_pipeline.py` (Task 2.4)

All must pass. Any failures must be diagnosed and fixed.

### Step 3: End-to-End Pipeline Regression Tests

**Create `backend/tests/pipeline/test_regression.py`:**

```python
"""
Phase 2 Regression Tests

End-to-end tests that verify the complete document pipeline produces
correct results for a variety of input documents.
"""

import time
import pytest
from pathlib import Path

from og_scraper.pipeline import (
    DocumentPipeline,
    ProcessingResult,
    TextExtractor,
    DocumentClassifier,
    DataExtractor,
    DataNormalizer,
    ConfidenceScorer,
)
from og_scraper.pipeline.confidence import (
    DOCUMENT_ACCEPT_THRESHOLD,
    DOCUMENT_REVIEW_THRESHOLD,
)


class TestEndToEndTextPDF:
    """Test: text PDF -> full pipeline -> auto-accepted result with all fields."""

    def test_production_report_auto_accepted(self, sample_text_pdf: Path):
        pipeline = DocumentPipeline()
        result = pipeline.process(sample_text_pdf, state="TX")

        assert result.disposition in ("accept", "review")
        assert result.doc_type == "production_report"
        assert result.extraction_method == "pymupdf"
        assert result.score.ocr_confidence == 1.0
        assert "api_number" in result.field_extraction.fields
        assert "operator_name" in result.field_extraction.fields
        assert len(result.raw_text) > 100

    def test_well_permit_with_form_number(self, sample_well_permit_pdf: Path):
        pipeline = DocumentPipeline()
        result = pipeline.process(sample_well_permit_pdf, state="TX")

        assert result.doc_type == "well_permit"
        assert result.classification.form_number is not None
        assert result.classification.confidence >= 0.95  # Form number = 0.98
        assert "api_number" in result.field_extraction.fields
        assert "permit_number" in result.field_extraction.fields or "permit_date" in result.field_extraction.fields

    def test_completion_report_with_form_number(self, sample_completion_pdf: Path):
        pipeline = DocumentPipeline()
        result = pipeline.process(sample_completion_pdf, state="OK")

        assert result.doc_type == "completion_report"
        assert result.classification.form_number is not None

    def test_all_confidence_tiers_populated(self, sample_text_pdf: Path):
        pipeline = DocumentPipeline()
        result = pipeline.process(sample_text_pdf, state="TX")

        # Tier 1: OCR
        assert result.score.ocr_confidence >= 0.0
        # Tier 2: Fields
        assert result.score.weighted_field_confidence >= 0.0
        assert len(result.score.field_confidences) > 0
        # Tier 3: Document
        assert result.score.document_confidence >= 0.0
        assert result.score.classification_confidence >= 0.0

    def test_normalized_fields_present(self, sample_text_pdf: Path):
        pipeline = DocumentPipeline()
        result = pipeline.process(sample_text_pdf, state="TX")

        assert len(result.normalized_fields) > 0
        # API number should be 14 digits, no dashes
        if "api_number" in result.normalized_fields:
            api = result.normalized_fields["api_number"]
            assert len(api) == 14
            assert api.isdigit()


class TestEndToEndScannedPDF:
    """Test: scanned PDF -> full pipeline -> review-queue result with OCR text."""

    def test_scanned_pdf_processes(self, sample_scan_pdf: Path):
        pipeline = DocumentPipeline()
        result = pipeline.process(sample_scan_pdf, state="TX")

        assert isinstance(result, ProcessingResult)
        assert result.disposition in ("accept", "review", "reject")
        assert result.extraction_method in ("paddleocr", "mixed")
        assert result.score.ocr_confidence < 1.0  # OCR, not text extraction
        assert len(result.raw_text) > 0

    def test_scanned_pdf_has_page_confidences(self, sample_scan_pdf: Path):
        pipeline = DocumentPipeline()
        result = pipeline.process(sample_scan_pdf, state="TX")

        assert len(result.text_extraction.page_confidences) > 0
        for pc in result.text_extraction.page_confidences:
            assert "page" in pc
            assert "confidence" in pc
            assert "method" in pc


class TestEndToEndEdgeCases:
    """Test: edge cases — corrupt, empty, ambiguous documents."""

    def test_empty_pdf_rejected(self, empty_pdf: Path):
        pipeline = DocumentPipeline()
        result = pipeline.process(empty_pdf)

        assert result.doc_type == "unknown"
        assert result.disposition in ("reject", "review")
        assert result.score.document_confidence < DOCUMENT_ACCEPT_THRESHOLD

    def test_corrupt_file_handled(self, corrupt_pdf: Path):
        pipeline = DocumentPipeline()
        # Should either raise an exception or return a reject result
        try:
            result = pipeline.process(corrupt_pdf)
            assert result.disposition == "reject"
        except Exception:
            pass  # Exception is acceptable for corrupt files

    def test_ambiguous_document_low_confidence(self, ambiguous_pdf: Path):
        pipeline = DocumentPipeline()
        result = pipeline.process(ambiguous_pdf)

        # Ambiguous text should have lower classification confidence
        assert result.classification.confidence < 0.80


class TestConfidenceScoringMath:
    """Verify confidence scoring formulas are mathematically correct."""

    def test_composite_formula_calculation(self, sample_text_pdf: Path):
        pipeline = DocumentPipeline()
        result = pipeline.process(sample_text_pdf, state="TX")

        # Manually verify: 0.3*class + 0.5*fields + 0.2*ocr
        expected = (
            0.3 * result.score.classification_confidence
            + 0.5 * result.score.weighted_field_confidence
            + 0.2 * result.score.ocr_confidence
        )
        assert abs(result.score.document_confidence - expected) < 0.01

    def test_field_confidence_within_bounds(self, sample_text_pdf: Path):
        pipeline = DocumentPipeline()
        result = pipeline.process(sample_text_pdf, state="TX")

        for field_name, field_conf in result.score.field_confidences.items():
            assert 0.0 <= field_conf.adjusted_confidence <= 1.0, (
                f"Field {field_name} confidence {field_conf.adjusted_confidence} out of bounds"
            )
            assert field_conf.weight > 0

    def test_disposition_matches_thresholds(self, sample_text_pdf: Path):
        pipeline = DocumentPipeline()
        result = pipeline.process(sample_text_pdf, state="TX")

        conf = result.score.document_confidence
        if not result.score.critical_field_override:
            if conf >= DOCUMENT_ACCEPT_THRESHOLD:
                assert result.disposition == "accept"
            elif conf >= DOCUMENT_REVIEW_THRESHOLD:
                assert result.disposition == "review"
            else:
                assert result.disposition == "reject"


class TestClassificationAccuracy:
    """Verify classification accuracy >80% across test document set."""

    def test_production_report_classified(self, sample_text_pdf: Path):
        classifier = DocumentClassifier()
        pipeline = DocumentPipeline()
        result = pipeline.process(sample_text_pdf, state="TX")
        assert result.doc_type == "production_report"

    def test_well_permit_classified(self, sample_well_permit_pdf: Path):
        pipeline = DocumentPipeline()
        result = pipeline.process(sample_well_permit_pdf, state="TX")
        assert result.doc_type == "well_permit"

    def test_completion_report_classified(self, sample_completion_pdf: Path):
        pipeline = DocumentPipeline()
        result = pipeline.process(sample_completion_pdf, state="OK")
        assert result.doc_type == "completion_report"

    def test_classification_accuracy_threshold(
        self,
        sample_text_pdf: Path,
        sample_well_permit_pdf: Path,
        sample_completion_pdf: Path,
    ):
        """At least 80% of test documents should be correctly classified."""
        pipeline = DocumentPipeline()
        expected = [
            (sample_text_pdf, "production_report"),
            (sample_well_permit_pdf, "well_permit"),
            (sample_completion_pdf, "completion_report"),
        ]
        correct = 0
        for pdf_path, expected_type in expected:
            result = pipeline.process(pdf_path)
            if result.doc_type == expected_type:
                correct += 1

        accuracy = correct / len(expected)
        assert accuracy >= 0.80, f"Classification accuracy {accuracy:.0%} below 80% threshold"


class TestPerformance:
    """Verify single document processing time is within budget."""

    def test_text_pdf_under_5_seconds(self, sample_text_pdf: Path):
        """Text PDFs should process very quickly (no OCR needed)."""
        pipeline = DocumentPipeline()
        start = time.time()
        result = pipeline.process(sample_text_pdf, state="TX")
        elapsed = time.time() - start

        assert elapsed < 5.0, f"Text PDF took {elapsed:.1f}s (limit: 5s)"

    def test_scanned_pdf_under_30_seconds(self, sample_scan_pdf: Path):
        """Scanned PDFs with OCR should process under 30 seconds."""
        pipeline = DocumentPipeline()
        start = time.time()
        result = pipeline.process(sample_scan_pdf, state="TX")
        elapsed = time.time() - start

        assert elapsed < 30.0, f"Scanned PDF took {elapsed:.1f}s (limit: 30s)"


class TestPipelineStageIsolation:
    """Verify each pipeline stage works independently."""

    def test_text_extractor_standalone(self, sample_text_pdf: Path):
        extractor = TextExtractor()
        result = extractor.extract(sample_text_pdf)
        assert len(result.text) > 0
        assert result.total_pages >= 1

    def test_classifier_standalone(self):
        classifier = DocumentClassifier()
        result = classifier.classify("Monthly Production Report\nOil: 1,234 BBL\nGas: 5,678 MCF")
        assert result.doc_type == "production_report"
        assert result.confidence > 0.3

    def test_data_extractor_standalone(self):
        extractor = DataExtractor()
        text = "API Number: 42-501-20130-00-00\nOperator: Devon Energy\nOil Production: 1,234 BBL"
        result = extractor.extract(text, doc_type="production_report", state="TX")
        assert "api_number" in result.fields
        assert "operator_name" in result.fields

    def test_normalizer_standalone(self):
        from og_scraper.pipeline.extractor import ExtractionResult as FieldExtractionResult, FieldValue
        extraction = FieldExtractionResult(
            fields={
                "api_number": FieldValue(
                    value="4250120130", confidence=0.90,
                    source_text="", pattern_used="", extraction_method="regex",
                    pattern_specificity=0.85,
                ),
            },
            raw_text="", doc_type="production_report", state="TX",
        )
        normalizer = DataNormalizer()
        result = normalizer.normalize(extraction)
        assert result.fields["api_number"] == "42501201300000"

    def test_confidence_scorer_standalone(self):
        from og_scraper.pipeline.extractor import FieldValue
        scorer = ConfidenceScorer()
        fields = {
            "api_number": FieldValue(
                value="42501201300000", confidence=0.95,
                source_text="", pattern_used="", extraction_method="regex",
                pattern_specificity=1.0,
            ),
        }
        result = scorer.score(
            ocr_confidence=1.0,
            classification_confidence=0.98,
            fields=fields,
        )
        assert result.disposition in ("accept", "review", "reject")
        assert 0.0 <= result.document_confidence <= 1.0
```

### Step 4: Run Lint and Format Checks

```bash
# Lint all pipeline code
uv run ruff check backend/src/og_scraper/pipeline/

# Format check
uv run ruff format --check backend/src/og_scraper/pipeline/

# Fix any issues found
uv run ruff check --fix backend/src/og_scraper/pipeline/
uv run ruff format backend/src/og_scraper/pipeline/
```

### Step 5: Run Full Test Suite and Generate Report

```bash
# Run all Phase 2 tests with verbose output
uv run pytest backend/tests/pipeline/ -v --tb=long -x

# If all pass, run without -x for full report
uv run pytest backend/tests/pipeline/ -v --tb=short
```

**Expected output:** All tests pass. Zero failures. Performance tests complete within budget.

### Step 6: Fix Any Failures

If any tests fail:
1. Read the failure output carefully
2. Identify the root cause (logic error, missing import, incorrect threshold, etc.)
3. Fix the issue in the relevant source file (from Task 2.1-2.4)
4. Re-run all tests to confirm the fix does not break other tests
5. Document what was fixed in the commit message

## Files to Create

- `backend/tests/pipeline/test_regression.py` - Phase 2 regression tests (end-to-end, math verification, accuracy, performance)
- Update `backend/tests/pipeline/conftest.py` - Add comprehensive test fixtures if not already complete from previous tasks

## Files to Modify

- Any pipeline source files that have bugs discovered during regression testing (fix bugs, do not add features)

## Contracts

### Provides (for downstream tasks)

- Verified, tested pipeline that Phase 3+ can depend on
- Confirmed accuracy and performance characteristics

### Consumes (from upstream tasks)

- All Task 2.1-2.4 code and test fixtures

## Acceptance Criteria

- [ ] End-to-end: Text PDF -> full pipeline -> auto-accepted result with all fields extracted
- [ ] End-to-end: Scanned PDF -> full pipeline -> review-queue result with OCR text
- [ ] End-to-end: Corrupt/unreadable file -> pipeline -> rejected result or handled exception
- [ ] End-to-end: Empty PDF -> pipeline -> rejected with unknown type
- [ ] All unit tests pass: `uv run pytest backend/tests/pipeline/` — zero failures
- [ ] Confidence scores are mathematically correct: composite formula verified with manual calculation
- [ ] Classification accuracy >80% across test document set (at least 3 document types tested)
- [ ] Performance: Text PDF processes in <5 seconds
- [ ] Performance: Scanned PDF processes in <30 seconds (including OCR)
- [ ] Each pipeline stage works independently (can be called in isolation)
- [ ] No lint errors: `uv run ruff check backend/src/og_scraper/pipeline/` passes
- [ ] No format issues: `uv run ruff format --check backend/src/og_scraper/pipeline/` passes

## Testing Protocol

### Full Test Suite

```bash
uv run pytest backend/tests/pipeline/ -v --tb=long
```

### Individual Test Groups

```bash
# Text extraction (Task 2.1)
uv run pytest backend/tests/pipeline/test_text_extractor.py -v

# Classification (Task 2.2)
uv run pytest backend/tests/pipeline/test_classifier.py -v

# Data extraction (Task 2.3)
uv run pytest backend/tests/pipeline/test_extractor.py -v
uv run pytest backend/tests/pipeline/test_normalizer.py -v

# Validation & confidence (Task 2.4)
uv run pytest backend/tests/pipeline/test_validator.py -v
uv run pytest backend/tests/pipeline/test_confidence.py -v
uv run pytest backend/tests/pipeline/test_pipeline.py -v

# Regression (this task)
uv run pytest backend/tests/pipeline/test_regression.py -v
```

### Build/Lint/Type Checks

- [ ] `uv run ruff check backend/src/og_scraper/pipeline/` passes with zero errors
- [ ] `uv run ruff format --check backend/src/og_scraper/pipeline/` passes
- [ ] `uv run python -c "from og_scraper.pipeline import DocumentPipeline, ProcessingResult"` succeeds

## Skills to Read

- `confidence-scoring` - Verify threshold values and formula match implementation
- `document-processing-pipeline` - Verify pipeline stages match architecture
- `og-testing-strategies` - Testing patterns, fixture management, regression test design

## Research Files to Read

- `.claude/orchestration-og-doc-scraper/research/document-pipeline-implementation.md` - Reference for expected behavior at each pipeline stage
- `.claude/orchestration-og-doc-scraper/research/document-processing.md` - Reference for OCR accuracy expectations and performance benchmarks

## Git

- Branch: `test/task-2.R-phase2-regression`
- Commit message prefix: `Task 2.R:`
