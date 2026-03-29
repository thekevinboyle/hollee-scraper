# Task 2.1: PDF Text Extraction & OCR

## Objective

Implement a hybrid text extraction system that automatically detects whether a PDF is text-based or scanned and routes to the appropriate extraction engine. Text-based PDFs use PyMuPDF4LLM (fast, high confidence), scanned PDFs use PaddleOCR v3 (slower, variable confidence), and mixed PDFs are handled page-by-page. This is the foundational text extraction layer that all downstream pipeline stages depend on.

## Context

This is the first task in Phase 2 (Document Pipeline). It sits between the Phase 1 foundation (project scaffolding, database, scraper framework) and the rest of the pipeline (classification, extraction, validation). Every document entering the pipeline must first have its text extracted before it can be classified, parsed, or scored. The quality and confidence metadata produced here flows through all subsequent stages.

## Dependencies

- Task 1.1 - Project structure exists (monorepo layout, Python packages installed)

## Blocked By

- Task 1.1

## Research Findings

Key findings from research files relevant to this task:

- From `document-processing.md`: PyMuPDF4LLM is the fastest text PDF extractor (0.12s benchmark, 50-100 pages/second on CPU). pdfplumber is secondary for precise table extraction.
- From `document-pipeline-implementation.md`: PaddleOCR 3.x has breaking API changes from 2.x — use `PaddleOCR` class with `.predict()` method. Set `text_rec_score_thresh=0.0` to keep all results and filter downstream.
- From `document-pipeline-implementation.md`: Per-page classification is critical — some PDFs have text pages mixed with scanned pages within the same document. Classify each page independently, not the whole document.
- From `document-pipeline-implementation.md`: Memory leak in PaddleOCR 3.x CPU mode — must set `CPU_RUNTIME_CACHE_CAPACITY=20` before importing PaddleOCR. Server models require ~1-1.5GB baseline RAM.
- From `document-processing.md`: PaddleOCR PP-OCRv5 server models are the best accuracy option (~90%+ on government documents). CPU throughput: 0.3-1.0 pages/second for OCR, 50-100 pages/second for text extraction.

## Implementation Plan

### Step 1: Create Pipeline Package Structure

Create the `pipeline` package under the backend source directory.

**Create these files:**
- `backend/src/og_scraper/pipeline/__init__.py` — Package init, export key classes
- `backend/src/og_scraper/pipeline/text_extractor.py` — Main TextExtractor class
- `backend/src/og_scraper/pipeline/ocr.py` — PaddleOCR wrapper
- `backend/src/og_scraper/pipeline/page_classifier.py` — PDF page classification (text vs scanned)

**Package init exports:**
```python
from og_scraper.pipeline.text_extractor import TextExtractor, ExtractionResult, PageResult
```

### Step 2: Implement Data Models

Define Pydantic models (or dataclasses) for extraction results. These are the contracts downstream tasks consume.

**In `text_extractor.py` (top of file):**

```python
from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal


@dataclass
class PageResult:
    """Result of extracting text from a single PDF page."""
    page_num: int
    text: str
    confidence: float  # 0.0-1.0; 1.0 for text extraction, OCR score for scanned
    method: Literal["pymupdf", "paddleocr", "skip"]
    classification: Literal["text", "scanned", "mixed", "empty"]
    lines: list[dict] = field(default_factory=list)  # OCR line-level details (text, confidence, bbox)


@dataclass
class ExtractionResult:
    """Result of extracting text from an entire PDF document."""
    text: str  # Full concatenated text from all pages
    pages: list[PageResult]
    method: Literal["pymupdf", "paddleocr", "mixed"]  # Dominant method used
    ocr_confidence: float  # Document-level OCR confidence (min page confidence)
    page_confidences: list[dict]  # Per-page confidence metadata for JSONB storage
    total_pages: int
    scanned_page_count: int
    text_page_count: int
```

### Step 3: Implement Page Classifier

**In `page_classifier.py`:**

This module classifies each page of a PDF as `text`, `scanned`, `mixed`, or `empty` using PyMuPDF. The heuristic is: if a page has >100 characters of extractable text and <50% image coverage, it's text. If it has >85% image coverage and <100 chars, it's scanned. Otherwise it's mixed or empty.

```python
import fitz  # PyMuPDF


def classify_pdf_pages(pdf_path: str | Path) -> list[dict]:
    """
    Classify each page of a PDF as text-based, scanned, mixed, or empty.

    Heuristics:
    - text: >100 chars extractable text AND image coverage <= 50%
    - scanned: >85% image coverage AND <100 chars extractable text
    - mixed: substantial text AND substantial images
    - empty: <20 chars AND no images

    Returns list of dicts:
    [
        {
            "page_num": 0,
            "classification": "text"|"scanned"|"mixed"|"empty",
            "text_length": int,
            "image_count": int,
            "image_coverage": float (0.0-1.0),
        },
        ...
    ]
    """
    doc = fitz.open(str(pdf_path))
    page_classifications = []

    for page_num, page in enumerate(doc):
        text = page.get_text("text").strip()
        text_length = len(text)
        images = page.get_images(full=True)
        page_rect = page.rect
        page_area = page_rect.width * page_rect.height

        # Calculate image coverage as fraction of page area
        image_coverage = 0.0
        for img in images:
            xref = img[0]
            try:
                img_rects = page.get_image_rects(xref)
                if img_rects:
                    for rect in img_rects:
                        image_coverage += (rect.width * rect.height) / page_area
            except Exception:
                image_coverage += 0.5 if images else 0.0

        image_coverage = min(image_coverage, 1.0)

        has_substantial_text = text_length > 100
        is_mostly_image = image_coverage > 0.85

        if is_mostly_image and not has_substantial_text:
            classification = "scanned"
        elif has_substantial_text and image_coverage <= 0.5:
            classification = "text"
        elif text_length < 20 and not images:
            classification = "empty"
        else:
            classification = "mixed"

        page_classifications.append({
            "page_num": page_num,
            "classification": classification,
            "text_length": text_length,
            "image_count": len(images),
            "image_coverage": image_coverage,
        })

    doc.close()
    return page_classifications
```

**Key thresholds (tuned for government O&G documents):**
- `100` chars: minimum for "substantial text" — government forms typically have hundreds of chars even on sparse pages
- `0.85` image coverage: threshold for "scanned" — full-page scans have 90%+ coverage
- `0.50` image coverage: threshold for "mixed" — half-page image with text below
- `20` chars: below this and no images = effectively empty page

### Step 4: Implement PaddleOCR Wrapper

**In `ocr.py`:**

This wraps PaddleOCR with memory management, confidence tracking, and image preprocessing for poor-quality scans.

**Critical: Set environment variables BEFORE importing PaddleOCR:**

```python
from __future__ import annotations

import gc
import os
import tempfile
from pathlib import Path

# MUST be set before importing paddleocr — prevents memory leak
os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"  # Required on macOS Apple Silicon
os.environ["CPU_RUNTIME_CACHE_CAPACITY"] = "20"  # Limit runtime cache to prevent memory growth

import fitz  # PyMuPDF — for converting PDF pages to images
import numpy as np

# Lazy-load PaddleOCR to avoid import overhead when only processing text PDFs
_ocr_engine = None


def _get_ocr_engine():
    """Lazily initialize PaddleOCR engine (loads ~1-1.5GB of models)."""
    global _ocr_engine
    if _ocr_engine is None:
        from paddleocr import PaddleOCR
        _ocr_engine = PaddleOCR(
            text_detection_model_name="PP-OCRv5_server_det",
            text_recognition_model_name="PP-OCRv5_server_rec",
            use_doc_orientation_classify=True,   # Auto-detect rotation
            use_doc_unwarping=False,             # Not needed for scans (only for photos)
            text_det_thresh=0.3,                 # Lower catches faint text on government forms
            text_det_box_thresh=0.5,             # Lower for faded scans (default 0.6)
            text_rec_score_thresh=0.0,           # Keep ALL results — filter ourselves
            device="cpu",
            cpu_threads=4,
            enable_mkldnn=True,                  # MKL-DNN acceleration on CPU
        )
    return _ocr_engine


def ocr_pdf_page(pdf_path: str | Path, page_num: int, dpi: int = 300) -> dict:
    """
    Extract text from a single scanned PDF page using PaddleOCR.

    Args:
        pdf_path: Path to the PDF file
        page_num: Zero-indexed page number
        dpi: Resolution for page-to-image conversion (300 for text, 600 for fine print)

    Returns:
        {
            "page_num": int,
            "full_text": str,              # All recognized text joined with newlines
            "lines": [                     # Per-line details
                {
                    "text": str,
                    "confidence": float,   # rec_score 0.0-1.0
                    "bbox": list,          # [[x1,y1],[x2,y2],[x3,y3],[x4,y4]]
                    "bbox_area": float,    # Area of bounding box (for weighted averaging)
                },
            ],
            "weighted_confidence": float,  # Confidence weighted by text region size
            "avg_confidence": float,       # Simple average of all line confidences
            "min_confidence": float,       # Lowest line confidence
            "num_lines": int,
            "method": "paddleocr",
        }
    """
    ocr = _get_ocr_engine()

    # Convert PDF page to PNG image
    doc = fitz.open(str(pdf_path))
    page = doc[page_num]
    mat = fitz.Matrix(dpi / 72, dpi / 72)
    pix = page.get_pixmap(matrix=mat)

    # Write to temp file (PaddleOCR accepts file paths)
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
        pix.save(tmp.name)
        temp_path = tmp.name
    doc.close()

    try:
        results = list(ocr.predict(temp_path))

        lines = []
        confidences = []
        weighted_sum = 0.0
        total_area = 0.0

        for res in results:
            for item in res.res:
                text = item["rec_text"]
                score = item["rec_score"]
                bbox = item["dt_polys"]

                # Calculate bounding box area for weighted confidence
                if len(bbox) >= 4:
                    xs = [p[0] for p in bbox]
                    ys = [p[1] for p in bbox]
                    bbox_area = (max(xs) - min(xs)) * (max(ys) - min(ys))
                else:
                    bbox_area = 1.0

                lines.append({
                    "text": text,
                    "confidence": score,
                    "bbox": bbox,
                    "bbox_area": bbox_area,
                })
                confidences.append(score)
                weighted_sum += score * bbox_area
                total_area += bbox_area

        avg_confidence = sum(confidences) / len(confidences) if confidences else 0.0
        min_confidence = min(confidences) if confidences else 0.0
        weighted_confidence = weighted_sum / total_area if total_area > 0 else 0.0

        return {
            "page_num": page_num,
            "full_text": "\n".join(line["text"] for line in lines),
            "lines": lines,
            "weighted_confidence": weighted_confidence,
            "avg_confidence": avg_confidence,
            "min_confidence": min_confidence,
            "num_lines": len(lines),
            "method": "paddleocr",
        }
    finally:
        os.unlink(temp_path)


def preprocess_poor_scan(image_path: str) -> str:
    """
    Preprocess a poor-quality scanned image for better OCR accuracy.
    Applies grayscale conversion, denoising, adaptive thresholding, and deskew.
    Returns path to preprocessed image (caller must clean up).

    Use only when initial OCR confidence is below 0.60.
    """
    import cv2

    img = cv2.imread(image_path)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    denoised = cv2.fastNlMeansDenoising(gray, h=10)
    binary = cv2.adaptiveThreshold(
        denoised, 255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY, 31, 10
    )

    # Deskew
    coords = np.column_stack(np.where(binary > 0))
    if len(coords) > 100:
        angle = cv2.minAreaRect(coords)[-1]
        if angle < -45:
            angle = -(90 + angle)
        else:
            angle = -angle
        if abs(angle) > 0.5:
            (h, w) = binary.shape[:2]
            M = cv2.getRotationMatrix2D((w // 2, h // 2), angle, 1.0)
            binary = cv2.warpAffine(
                binary, M, (w, h),
                flags=cv2.INTER_CUBIC,
                borderMode=cv2.BORDER_REPLICATE,
            )

    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
        cv2.imwrite(tmp.name, binary)
        return tmp.name
```

### Step 5: Implement the Main TextExtractor

**In `text_extractor.py`:**

This is the primary public interface. It orchestrates page classification, routing, and result aggregation.

```python
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

import fitz  # PyMuPDF
import pymupdf4llm

from og_scraper.pipeline.page_classifier import classify_pdf_pages
from og_scraper.pipeline.ocr import ocr_pdf_page

logger = logging.getLogger(__name__)


# --- Data models (as defined in Step 2) ---
# PageResult, ExtractionResult defined here


class TextExtractor:
    """
    Hybrid text extractor for PDF documents.

    Routes text-based pages to PyMuPDF4LLM (fast, confidence=1.0)
    and scanned pages to PaddleOCR (slower, variable confidence).
    Mixed pages try both and use whichever produces more text.
    """

    # Minimum characters per page from PyMuPDF to consider it a text page.
    # Below this, fall back to OCR even if page was classified as text.
    TEXT_CHAR_THRESHOLD = 50

    def extract(self, file_path: Path | str) -> ExtractionResult:
        """
        Extract text from a PDF file, auto-detecting text vs scanned pages.

        Args:
            file_path: Path to the PDF file

        Returns:
            ExtractionResult with text, per-page results, and confidence metadata
        """
        file_path = Path(file_path)
        if not file_path.exists():
            raise FileNotFoundError(f"PDF not found: {file_path}")

        if file_path.suffix.lower() != ".pdf":
            raise ValueError(f"Unsupported file type: {file_path.suffix}. Only PDF is supported.")

        # Step 1: Classify each page
        page_classifications = classify_pdf_pages(file_path)
        total_pages = len(page_classifications)

        logger.info(
            "Classified %d pages: %s",
            total_pages,
            {c: sum(1 for p in page_classifications if p["classification"] == c)
             for c in ("text", "scanned", "mixed", "empty")},
        )

        # Step 2: Extract text from each page using appropriate method
        page_results: list[PageResult] = []

        for page_info in page_classifications:
            page_num = page_info["page_num"]
            classification = page_info["classification"]

            if classification == "empty":
                page_results.append(PageResult(
                    page_num=page_num,
                    text="",
                    confidence=1.0,
                    method="skip",
                    classification="empty",
                ))
                continue

            if classification == "text":
                result = self._extract_text_page(file_path, page_num)
                page_results.append(result)

            elif classification == "scanned":
                result = self._extract_scanned_page(file_path, page_num)
                page_results.append(result)

            elif classification == "mixed":
                result = self._extract_mixed_page(file_path, page_num)
                page_results.append(result)

        # Step 3: Aggregate results
        return self._aggregate_results(page_results, total_pages)

    def _extract_text_page(self, file_path: Path, page_num: int) -> PageResult:
        """Extract text from a text-based PDF page using PyMuPDF."""
        doc = fitz.open(str(file_path))
        page = doc[page_num]
        text = page.get_text("text")
        doc.close()

        # Safety check: if PyMuPDF returned very little text, fall back to OCR
        if len(text.strip()) < self.TEXT_CHAR_THRESHOLD:
            logger.warning(
                "Page %d classified as text but PyMuPDF returned only %d chars, falling back to OCR",
                page_num, len(text.strip()),
            )
            return self._extract_scanned_page(file_path, page_num)

        return PageResult(
            page_num=page_num,
            text=text,
            confidence=1.0,  # Text extraction is deterministic
            method="pymupdf",
            classification="text",
        )

    def _extract_scanned_page(self, file_path: Path, page_num: int) -> PageResult:
        """Extract text from a scanned PDF page using PaddleOCR."""
        ocr_result = ocr_pdf_page(file_path, page_num, dpi=300)

        return PageResult(
            page_num=page_num,
            text=ocr_result["full_text"],
            confidence=ocr_result["weighted_confidence"],
            method="paddleocr",
            classification="scanned",
            lines=ocr_result["lines"],
        )

    def _extract_mixed_page(self, file_path: Path, page_num: int) -> PageResult:
        """
        Extract text from a mixed page — try both methods, use the better one.
        """
        # Try text extraction first (fast)
        doc = fitz.open(str(file_path))
        page = doc[page_num]
        text_result = page.get_text("text")
        doc.close()

        # Also try OCR
        ocr_result = ocr_pdf_page(file_path, page_num, dpi=300)

        # Use whichever produced more text
        if len(text_result.strip()) >= len(ocr_result["full_text"].strip()):
            return PageResult(
                page_num=page_num,
                text=text_result,
                confidence=0.95,  # Slightly lower than pure text because page was ambiguous
                method="pymupdf",
                classification="mixed",
            )
        else:
            return PageResult(
                page_num=page_num,
                text=ocr_result["full_text"],
                confidence=ocr_result["weighted_confidence"],
                method="paddleocr",
                classification="mixed",
                lines=ocr_result["lines"],
            )

    def _aggregate_results(
        self, page_results: list[PageResult], total_pages: int
    ) -> ExtractionResult:
        """Combine per-page results into a document-level ExtractionResult."""
        all_text = "\n\n".join(pr.text for pr in page_results if pr.text)

        # Determine dominant method
        pymupdf_count = sum(1 for pr in page_results if pr.method == "pymupdf")
        ocr_count = sum(1 for pr in page_results if pr.method == "paddleocr")
        if pymupdf_count > 0 and ocr_count > 0:
            dominant_method = "mixed"
        elif ocr_count > 0:
            dominant_method = "paddleocr"
        else:
            dominant_method = "pymupdf"

        # Document-level OCR confidence = minimum page confidence (weakest-link)
        # Per confidence-scoring skill: use minimum, not average
        active_pages = [pr for pr in page_results if pr.method != "skip"]
        if active_pages:
            ocr_confidence = min(pr.confidence for pr in active_pages)
        else:
            ocr_confidence = 0.0

        # Per-page confidence metadata for JSONB storage
        page_confidences = [
            {
                "page": pr.page_num,
                "method": pr.method,
                "confidence": pr.confidence,
                "classification": pr.classification,
            }
            for pr in page_results
        ]

        scanned_count = sum(
            1 for pr in page_results if pr.classification in ("scanned", "mixed")
        )
        text_count = sum(1 for pr in page_results if pr.classification == "text")

        return ExtractionResult(
            text=all_text,
            pages=page_results,
            method=dominant_method,
            ocr_confidence=ocr_confidence,
            page_confidences=page_confidences,
            total_pages=total_pages,
            scanned_page_count=scanned_count,
            text_page_count=text_count,
        )
```

### Step 6: Create Test Fixtures

Create minimal test PDF files for automated testing.

**`backend/tests/fixtures/sample_text.pdf`** — Generate programmatically in the test setup:

```python
# In conftest.py or test setup
import fitz

def create_sample_text_pdf(path: Path):
    """Create a simple text-based PDF for testing."""
    doc = fitz.open()
    page = doc.new_page()
    text = """RAILROAD COMMISSION OF TEXAS
    OIL AND GAS DIVISION

    PRODUCTION REPORT

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
    """
    page.insert_text((72, 72), text, fontsize=11)
    doc.save(str(path))
    doc.close()
```

**`backend/tests/fixtures/sample_scan.pdf`** — A PDF containing a rasterized image page (create by rendering text to an image, then embedding the image in a PDF):

```python
def create_sample_scanned_pdf(path: Path):
    """Create a scanned-style PDF (text rendered as image) for testing."""
    doc = fitz.open()
    page = doc.new_page()

    # Create a temporary text PDF, render it as an image, then insert that image
    tmp_doc = fitz.open()
    tmp_page = tmp_doc.new_page()
    tmp_page.insert_text((72, 72), "WELL PERMIT APPLICATION\nAPI No: 42-501-20130", fontsize=14)
    pix = tmp_page.get_pixmap(dpi=300)
    img_data = pix.tobytes("png")
    tmp_doc.close()

    # Insert image into the real page (makes it a "scanned" document)
    page.insert_image(page.rect, stream=img_data)
    doc.save(str(path))
    doc.close()
```

### Step 7: Write Unit Tests

**In `backend/tests/pipeline/test_text_extractor.py`:**

```python
import pytest
from pathlib import Path
from og_scraper.pipeline.text_extractor import TextExtractor, ExtractionResult, PageResult
from og_scraper.pipeline.page_classifier import classify_pdf_pages


class TestPageClassifier:
    """Test PDF page classification (text vs scanned vs mixed vs empty)."""

    def test_text_page_classified_as_text(self, sample_text_pdf: Path):
        pages = classify_pdf_pages(sample_text_pdf)
        assert len(pages) >= 1
        assert pages[0]["classification"] == "text"
        assert pages[0]["text_length"] > 100

    def test_scanned_page_classified_as_scanned(self, sample_scan_pdf: Path):
        pages = classify_pdf_pages(sample_scan_pdf)
        assert len(pages) >= 1
        assert pages[0]["classification"] in ("scanned", "mixed")
        assert pages[0]["image_coverage"] > 0.5

    def test_empty_page_classified_as_empty(self, empty_pdf: Path):
        pages = classify_pdf_pages(empty_pdf)
        assert pages[0]["classification"] == "empty"
        assert pages[0]["text_length"] < 20


class TestTextExtractor:
    """Test the hybrid text extraction system."""

    def test_text_pdf_uses_pymupdf(self, sample_text_pdf: Path):
        extractor = TextExtractor()
        result = extractor.extract(sample_text_pdf)
        assert isinstance(result, ExtractionResult)
        assert result.method == "pymupdf"
        assert result.ocr_confidence == 1.0
        assert "PRODUCTION REPORT" in result.text or "production report" in result.text.lower()
        assert result.text_page_count >= 1
        assert result.scanned_page_count == 0

    def test_scanned_pdf_uses_paddleocr(self, sample_scan_pdf: Path):
        extractor = TextExtractor()
        result = extractor.extract(sample_scan_pdf)
        assert isinstance(result, ExtractionResult)
        assert result.method == "paddleocr"
        assert 0.0 < result.ocr_confidence <= 1.0
        assert len(result.text) > 0
        assert result.scanned_page_count >= 1

    def test_multi_page_pdf_returns_per_page_results(self, multi_page_pdf: Path):
        extractor = TextExtractor()
        result = extractor.extract(multi_page_pdf)
        assert result.total_pages >= 2
        assert len(result.pages) >= 2
        for page in result.pages:
            assert isinstance(page, PageResult)
            assert page.page_num >= 0

    def test_page_confidences_metadata_format(self, sample_text_pdf: Path):
        extractor = TextExtractor()
        result = extractor.extract(sample_text_pdf)
        for pc in result.page_confidences:
            assert "page" in pc
            assert "method" in pc
            assert "confidence" in pc
            assert "classification" in pc
            assert 0.0 <= pc["confidence"] <= 1.0

    def test_text_pdf_confidence_is_1(self, sample_text_pdf: Path):
        extractor = TextExtractor()
        result = extractor.extract(sample_text_pdf)
        assert result.ocr_confidence == 1.0

    def test_nonexistent_file_raises_error(self):
        extractor = TextExtractor()
        with pytest.raises(FileNotFoundError):
            extractor.extract(Path("/nonexistent/file.pdf"))

    def test_non_pdf_raises_error(self, tmp_path: Path):
        txt_file = tmp_path / "test.txt"
        txt_file.write_text("not a pdf")
        extractor = TextExtractor()
        with pytest.raises(ValueError, match="Unsupported file type"):
            extractor.extract(txt_file)


class TestOCRWrapper:
    """Test PaddleOCR wrapper directly."""

    def test_ocr_returns_confidence_per_line(self, sample_scan_pdf: Path):
        from og_scraper.pipeline.ocr import ocr_pdf_page
        result = ocr_pdf_page(sample_scan_pdf, page_num=0)
        assert result["method"] == "paddleocr"
        assert result["num_lines"] > 0
        for line in result["lines"]:
            assert "text" in line
            assert "confidence" in line
            assert 0.0 <= line["confidence"] <= 1.0
            assert "bbox" in line

    def test_ocr_weighted_confidence(self, sample_scan_pdf: Path):
        from og_scraper.pipeline.ocr import ocr_pdf_page
        result = ocr_pdf_page(sample_scan_pdf, page_num=0)
        assert 0.0 <= result["weighted_confidence"] <= 1.0
        assert 0.0 <= result["avg_confidence"] <= 1.0
        assert result["min_confidence"] <= result["avg_confidence"]
```

**Test fixtures (conftest.py):**
Create `backend/tests/pipeline/conftest.py` with pytest fixtures that generate the test PDFs:
- `sample_text_pdf` — text-based PDF with O&G content
- `sample_scan_pdf` — scanned-style PDF (text rendered as image)
- `multi_page_pdf` — 3-page PDF with mixed content
- `empty_pdf` — PDF with a blank page

## Files to Create

- `backend/src/og_scraper/pipeline/__init__.py` - Package init with exports
- `backend/src/og_scraper/pipeline/text_extractor.py` - TextExtractor class and data models
- `backend/src/og_scraper/pipeline/ocr.py` - PaddleOCR wrapper with confidence tracking and memory management
- `backend/src/og_scraper/pipeline/page_classifier.py` - PDF page classification (text/scanned/mixed/empty)
- `backend/tests/pipeline/__init__.py` - Test package init
- `backend/tests/pipeline/conftest.py` - Test fixtures (PDF generators)
- `backend/tests/pipeline/test_text_extractor.py` - Unit tests

## Files to Modify

- `backend/pyproject.toml` - Ensure `pymupdf`, `pymupdf4llm`, `paddlepaddle`, `paddleocr`, `opencv-python-headless`, `numpy` are in dependencies (should already be from Task 1.1; verify and add if missing)

## Contracts

### Provides (for downstream tasks)

- **Class**: `TextExtractor` with `extract(file_path: Path) -> ExtractionResult`
- **Data Model**: `ExtractionResult` — `{text: str, pages: list[PageResult], method: str, ocr_confidence: float, page_confidences: list[dict], total_pages: int, scanned_page_count: int, text_page_count: int}`
- **Data Model**: `PageResult` — `{page_num: int, text: str, confidence: float, method: str, classification: str, lines: list[dict]}`
- **Function**: `ocr_pdf_page(pdf_path, page_num, dpi) -> dict` — Low-level OCR access
- **Function**: `classify_pdf_pages(pdf_path) -> list[dict]` — Page-level classification

### Consumes (from upstream tasks)

- Task 1.1: Project structure, Python package layout, installed dependencies

## Acceptance Criteria

- [ ] Text-based PDFs extracted via PyMuPDF with confidence = 1.0
- [ ] Scanned PDFs extracted via PaddleOCR with confidence scores between 0.0 and 1.0
- [ ] Auto-detection correctly routes text pages to PyMuPDF and scanned pages to PaddleOCR
- [ ] OCR confidence tracked per page (weighted by text region size) and rolled up to document level (minimum page confidence)
- [ ] Multi-page PDFs handled with per-page results
- [ ] Mixed PDFs (some text pages, some scanned) processed correctly with page-level routing
- [ ] Memory management: `CPU_RUNTIME_CACHE_CAPACITY` set, lazy model loading
- [ ] All tests pass
- [ ] Build succeeds (`uv run python -c "from og_scraper.pipeline import TextExtractor"`)

## Testing Protocol

### Unit/Integration Tests

- Test file: `backend/tests/pipeline/test_text_extractor.py`
- Test cases:
  - [ ] Text PDF returns text with PyMuPDF method and confidence 1.0
  - [ ] Scanned PDF returns text with PaddleOCR method and confidence 0.0-1.0
  - [ ] Page classifier correctly identifies text, scanned, mixed, and empty pages
  - [ ] Multi-page PDF returns per-page results with correct page numbers
  - [ ] Page confidences metadata has correct JSONB-compatible format
  - [ ] OCR wrapper returns per-line confidence and bounding boxes
  - [ ] Weighted confidence accounts for text region size
  - [ ] FileNotFoundError raised for missing files
  - [ ] ValueError raised for non-PDF files
  - [ ] Auto-fallback: text page with <50 chars falls back to OCR

### Build/Lint/Type Checks

- [ ] `uv run ruff check backend/src/og_scraper/pipeline/` passes
- [ ] `uv run ruff format --check backend/src/og_scraper/pipeline/` passes
- [ ] `uv run pytest backend/tests/pipeline/test_text_extractor.py -v` — all tests pass

## Skills to Read

- `document-processing-pipeline` - PaddleOCR configuration, PyMuPDF4LLM usage, page classification heuristics, confidence tracking patterns
- `confidence-scoring` - How OCR confidence feeds into Tier 1 scoring (per-page weighted average, document-level minimum)

## Research Files to Read

- `.claude/orchestration-og-doc-scraper/research/document-pipeline-implementation.md` - Sections 1 (PaddleOCR setup), 3 (PDF processing pipeline), 1.6 (confidence thresholds), 1.8 (memory management)
- `.claude/orchestration-og-doc-scraper/research/document-processing.md` - Section 1 (PDF text extraction libraries), Section 2 (OCR solutions)

## Git

- Branch: `feat/task-2.1-text-extraction`
- Commit message prefix: `Task 2.1:`
