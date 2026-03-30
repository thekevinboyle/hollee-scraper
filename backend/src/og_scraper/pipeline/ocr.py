"""PaddleOCR wrapper with lazy loading, confidence tracking, and memory management.

Wraps PaddleOCR v3 for extracting text from scanned PDF pages. The OCR engine
is lazily initialized on first use to avoid the ~1-1.5GB memory overhead when
only processing text-based PDFs.

CRITICAL: Environment variables are set at module level, BEFORE any PaddleOCR
import, to prevent memory leaks and macOS Apple Silicon crashes.
"""

from __future__ import annotations

import gc
import logging
import os
import tempfile
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

# MUST be set before importing paddleocr -- prevents memory leak and macOS crash
os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"  # Required on macOS Apple Silicon
os.environ["CPU_RUNTIME_CACHE_CAPACITY"] = "20"  # Limit runtime cache to prevent memory growth

import fitz  # PyMuPDF -- for converting PDF pages to images

logger = logging.getLogger(__name__)

# Lazy-load PaddleOCR to avoid import overhead when only processing text PDFs
_ocr_engine = None


def _get_ocr_engine():
    """Lazily initialize PaddleOCR engine (loads ~1-1.5GB of models).

    Returns the singleton OCR engine instance, creating it on first call.
    """
    global _ocr_engine  # noqa: PLW0603
    if _ocr_engine is None:
        logger.info("Initializing PaddleOCR engine (this may take a moment)...")
        from paddleocr import PaddleOCR

        _ocr_engine = PaddleOCR(
            text_detection_model_name="PP-OCRv5_server_det",
            text_recognition_model_name="PP-OCRv5_server_rec",
            use_doc_orientation_classify=True,  # Auto-detect rotation
            use_doc_unwarping=False,  # Not needed for scans (only for photos)
            text_det_thresh=0.3,  # Lower catches faint text on government forms
            text_det_box_thresh=0.5,  # Lower for faded scans (default 0.6)
            text_rec_score_thresh=0.0,  # Keep ALL results -- filter ourselves
            device="cpu",
            cpu_threads=4,
            enable_mkldnn=True,  # MKL-DNN acceleration on CPU
        )
        logger.info("PaddleOCR engine initialized.")
    return _ocr_engine


def reset_ocr_engine() -> None:
    """Release the OCR engine to free memory. Useful for batch processing."""
    global _ocr_engine  # noqa: PLW0603
    _ocr_engine = None
    gc.collect()


def ocr_pdf_page(pdf_path: str | Path, page_num: int, dpi: int = 300) -> dict:
    """Extract text from a single scanned PDF page using PaddleOCR.

    Converts the PDF page to a PNG image at the specified DPI, then runs
    PaddleOCR text detection + recognition. Returns per-line confidence
    scores and bounding boxes.

    Args:
        pdf_path: Path to the PDF file.
        page_num: Zero-indexed page number.
        dpi: Resolution for page-to-image conversion (300 for text, 600 for fine print).

    Returns:
        Dict with keys:
        - page_num: int
        - full_text: str (all recognized text joined with newlines)
        - lines: list[dict] (per-line: text, confidence, bbox, bbox_area)
        - weighted_confidence: float (confidence weighted by text region size)
        - avg_confidence: float (simple average of all line confidences)
        - min_confidence: float (lowest line confidence)
        - num_lines: int
        - method: "paddleocr"
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
            if not hasattr(res, "res") or res.res is None:
                continue
            for item in res.res:
                text = item.get("rec_text", "")
                score = item.get("rec_score", 0.0)
                bbox = item.get("dt_polys", [])

                # Calculate bounding box area for weighted confidence
                if len(bbox) >= 4:
                    xs = [p[0] for p in bbox]
                    ys = [p[1] for p in bbox]
                    bbox_area = (max(xs) - min(xs)) * (max(ys) - min(ys))
                else:
                    bbox_area = 1.0

                lines.append(
                    {
                        "text": text,
                        "confidence": float(score),
                        "bbox": bbox,
                        "bbox_area": float(bbox_area),
                    }
                )
                confidences.append(float(score))
                weighted_sum += float(score) * float(bbox_area)
                total_area += float(bbox_area)

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
