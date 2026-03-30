"""Test fixtures for pipeline tests: programmatically generated PDFs.

All test PDFs are generated using PyMuPDF, not stored as static fixtures.
This ensures tests are self-contained and reproducible.
"""

from pathlib import Path

import fitz  # PyMuPDF
import pytest


@pytest.fixture
def sample_text_pdf(tmp_path: Path) -> Path:
    """Create a text-based PDF with O&G content for testing.

    This PDF has extractable text (not images), so PyMuPDF should be able
    to extract all content with confidence 1.0.
    """
    pdf_path = tmp_path / "sample_text.pdf"
    doc = fitz.open()
    page = doc.new_page()
    text = (
        "RAILROAD COMMISSION OF TEXAS\n"
        "OIL AND GAS DIVISION\n"
        "\n"
        "PRODUCTION REPORT\n"
        "\n"
        "Operator: Devon Energy Corporation\n"
        "Well Name: Permian Basin Unit #42\n"
        "API Number: 42-501-20130-00-00\n"
        "County: Ector\n"
        "State: Texas\n"
        "\n"
        "Reporting Period: January 2026\n"
        "\n"
        "Oil Production: 1,234 BBL\n"
        "Gas Production: 5,678 MCF\n"
        "Water Production: 890 BBL\n"
        "Days Produced: 31\n"
    )
    page.insert_text((72, 72), text, fontsize=11)
    doc.save(str(pdf_path))
    doc.close()
    return pdf_path


@pytest.fixture
def sample_scan_pdf(tmp_path: Path) -> Path:
    """Create a scanned-style PDF (text rendered as image) for testing.

    This simulates a scanned document by rendering text to a pixmap image
    and then embedding that image into a PDF page. The page should be
    classified as 'scanned' because it has high image coverage and no
    extractable text.
    """
    pdf_path = tmp_path / "sample_scan.pdf"
    doc = fitz.open()
    page = doc.new_page()

    # Create a temporary text PDF, render it as an image, then embed it
    tmp_doc = fitz.open()
    tmp_page = tmp_doc.new_page()
    tmp_page.insert_text(
        (72, 72),
        (
            "WELL PERMIT APPLICATION\n"
            "API No: 42-501-20130\n"
            "Operator: Devon Energy Corporation\n"
            "Well Name: Permian Basin Unit #42\n"
            "County: Ector, State: Texas\n"
            "Proposed Total Depth: 10,500 ft\n"
        ),
        fontsize=14,
    )
    pix = tmp_page.get_pixmap(dpi=300)
    img_data = pix.tobytes("png")
    tmp_doc.close()

    # Insert image into the real page (makes it a "scanned" document)
    page.insert_image(page.rect, stream=img_data)
    doc.save(str(pdf_path))
    doc.close()
    return pdf_path


@pytest.fixture
def empty_pdf(tmp_path: Path) -> Path:
    """Create a PDF with a blank page (no text, no images)."""
    pdf_path = tmp_path / "empty.pdf"
    doc = fitz.open()
    doc.new_page()
    doc.save(str(pdf_path))
    doc.close()
    return pdf_path


@pytest.fixture
def multi_page_pdf(tmp_path: Path) -> Path:
    """Create a 3-page PDF with mixed content.

    Page 0: Text page (production data)
    Page 1: Text page (well info)
    Page 2: Empty page
    """
    pdf_path = tmp_path / "multi_page.pdf"
    doc = fitz.open()

    # Page 0: text page with production data
    page0 = doc.new_page()
    page0.insert_text(
        (72, 72),
        (
            "MONTHLY PRODUCTION REPORT\n"
            "Operator: Devon Energy Corporation\n"
            "API Number: 42-501-20130-00-00\n"
            "Oil Production: 1,234 BBL\n"
            "Gas Production: 5,678 MCF\n"
        ),
        fontsize=11,
    )

    # Page 1: text page with well info
    page1 = doc.new_page()
    page1.insert_text(
        (72, 72),
        (
            "WELL INFORMATION\n"
            "Well Name: Permian Basin Unit #42\n"
            "County: Ector\n"
            "State: Texas\n"
            "Total Depth: 10,500 ft\n"
            "Completion Date: 01/15/2026\n"
        ),
        fontsize=11,
    )

    # Page 2: empty page
    doc.new_page()

    doc.save(str(pdf_path))
    doc.close()
    return pdf_path


@pytest.fixture
def sparse_text_pdf(tmp_path: Path) -> Path:
    """Create a PDF with very little text (<50 chars) to test OCR fallback."""
    pdf_path = tmp_path / "sparse_text.pdf"
    doc = fitz.open()
    page = doc.new_page()
    # Insert less than 50 chars of text
    page.insert_text((72, 72), "Page 1", fontsize=11)
    doc.save(str(pdf_path))
    doc.close()
    return pdf_path
