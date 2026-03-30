"""PDF page classification: text-based, scanned, mixed, or empty.

Classifies each page independently using PyMuPDF heuristics based on
extractable text length and image coverage ratio. This drives the routing
decision in TextExtractor (PyMuPDF for text pages, PaddleOCR for scanned).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import fitz  # PyMuPDF

if TYPE_CHECKING:
    from pathlib import Path


# --- Thresholds tuned for government O&G documents ---
# Minimum characters for "substantial text" -- government forms have hundreds even on sparse pages
_TEXT_CHAR_THRESHOLD = 100
# Image coverage above this = "scanned" (full-page scans are 90%+)
_SCANNED_COVERAGE_THRESHOLD = 0.85
# Image coverage above this with substantial text = "mixed"
_MIXED_COVERAGE_THRESHOLD = 0.50
# Below this with no images = "empty"
_EMPTY_CHAR_THRESHOLD = 20


def classify_pdf_pages(pdf_path: str | Path) -> list[dict]:
    """Classify each page of a PDF as text-based, scanned, mixed, or empty.

    Heuristics:
    - text: >100 chars extractable text AND image coverage <= 50%
    - scanned: >85% image coverage AND <100 chars extractable text
    - mixed: substantial text AND substantial images
    - empty: <20 chars AND no images

    Args:
        pdf_path: Path to the PDF file.

    Returns:
        List of dicts, one per page, with keys:
        - page_num: zero-indexed page number
        - classification: "text" | "scanned" | "mixed" | "empty"
        - text_length: number of characters of extractable text
        - image_count: number of images on the page
        - image_coverage: fraction of page area covered by images (0.0-1.0)
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
        if page_area > 0:
            for img in images:
                xref = img[0]
                try:
                    img_rects = page.get_image_rects(xref)
                    if img_rects:
                        for rect in img_rects:
                            image_coverage += (rect.width * rect.height) / page_area
                except Exception:
                    # Fallback: assume moderate coverage if we can't compute
                    image_coverage += 0.5 if images else 0.0

        image_coverage = min(image_coverage, 1.0)

        has_substantial_text = text_length > _TEXT_CHAR_THRESHOLD
        is_mostly_image = image_coverage > _SCANNED_COVERAGE_THRESHOLD

        if is_mostly_image and not has_substantial_text:
            classification = "scanned"
        elif has_substantial_text and image_coverage <= _MIXED_COVERAGE_THRESHOLD:
            classification = "text"
        elif text_length < _EMPTY_CHAR_THRESHOLD and not images:
            classification = "empty"
        else:
            classification = "mixed"

        page_classifications.append(
            {
                "page_num": page_num,
                "classification": classification,
                "text_length": text_length,
                "image_count": len(images),
                "image_coverage": image_coverage,
            }
        )

    doc.close()
    return page_classifications
