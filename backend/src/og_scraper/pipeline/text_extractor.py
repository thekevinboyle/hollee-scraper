"""Hybrid PDF text extraction: PyMuPDF4LLM for text, PaddleOCR for scans.

This is the primary public interface for the text extraction pipeline. It
orchestrates page classification, routing to the appropriate extraction engine,
and result aggregation with confidence metadata.

Usage:
    extractor = TextExtractor()
    result = extractor.extract("document.pdf")
    print(result.text)
    print(f"Confidence: {result.ocr_confidence}")
    print(f"Method: {result.method}")
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

import fitz  # PyMuPDF

from og_scraper.pipeline.ocr import ocr_pdf_page
from og_scraper.pipeline.page_classifier import classify_pdf_pages

logger = logging.getLogger(__name__)


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


class TextExtractor:
    """Hybrid text extractor for PDF documents.

    Routes text-based pages to PyMuPDF (fast, confidence=1.0) and scanned
    pages to PaddleOCR (slower, variable confidence). Mixed pages try both
    and use whichever produces more text.
    """

    # Minimum characters per page from PyMuPDF to consider it a text page.
    # Below this, fall back to OCR even if page was classified as text.
    TEXT_CHAR_THRESHOLD = 50

    def extract(self, file_path: Path | str) -> ExtractionResult:
        """Extract text from a PDF file, auto-detecting text vs scanned pages.

        Args:
            file_path: Path to the PDF file.

        Returns:
            ExtractionResult with text, per-page results, and confidence metadata.

        Raises:
            FileNotFoundError: If the PDF file does not exist.
            ValueError: If the file is not a PDF.
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
            {
                c: sum(1 for p in page_classifications if p["classification"] == c)
                for c in ("text", "scanned", "mixed", "empty")
            },
        )

        # Step 2: Extract text from each page using appropriate method
        page_results: list[PageResult] = []

        for page_info in page_classifications:
            page_num = page_info["page_num"]
            classification = page_info["classification"]

            if classification == "empty":
                page_results.append(
                    PageResult(
                        page_num=page_num,
                        text="",
                        confidence=1.0,
                        method="skip",
                        classification="empty",
                    )
                )
                continue

            if classification == "text":
                result = self._extract_text_page(file_path, page_num)
            elif classification == "scanned":
                result = self._extract_scanned_page(file_path, page_num)
            else:  # mixed
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
                page_num,
                len(text.strip()),
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
        """Extract text from a mixed page -- try both methods, use the better one."""
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

    def _aggregate_results(self, page_results: list[PageResult], total_pages: int) -> ExtractionResult:
        """Combine per-page results into a document-level ExtractionResult."""
        all_text = "\n\n".join(pr.text for pr in page_results if pr.text)

        # Determine dominant method
        pymupdf_count = sum(1 for pr in page_results if pr.method == "pymupdf")
        ocr_count = sum(1 for pr in page_results if pr.method == "paddleocr")
        if pymupdf_count > 0 and ocr_count > 0:
            dominant_method: Literal["pymupdf", "paddleocr", "mixed"] = "mixed"
        elif ocr_count > 0:
            dominant_method = "paddleocr"
        else:
            dominant_method = "pymupdf"

        # Document-level OCR confidence = minimum page confidence (weakest-link)
        active_pages = [pr for pr in page_results if pr.method != "skip"]
        ocr_confidence = min(pr.confidence for pr in active_pages) if active_pages else 0.0

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

        scanned_count = sum(1 for pr in page_results if pr.classification in ("scanned", "mixed"))
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
