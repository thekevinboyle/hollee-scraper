"""Shared fixtures for scraper tests."""

import io
from unittest.mock import MagicMock

import pytest

try:
    import openpyxl
except ImportError:
    openpyxl = None

from scrapy.http import TextResponse


def make_fake_text_response(url: str, body: str, meta: dict | None = None) -> TextResponse:
    """Build a fake Scrapy TextResponse for testing parse methods."""
    request = MagicMock()
    request.url = url
    request.meta = meta or {}
    return TextResponse(
        url=url,
        body=body.encode("utf-8"),
        encoding="utf-8",
        request=request,
    )


def make_fake_binary_response(url: str, body: bytes, meta: dict | None = None):
    """Build a fake Scrapy Response for binary content (e.g. XLSX)."""
    from scrapy.http import Response

    request = MagicMock()
    request.url = url
    request.meta = meta or {}
    return Response(
        url=url,
        body=body,
        request=request,
    )


def build_xlsx_bytes(headers: list[str], rows: list[list], title_rows: int = 0) -> bytes:
    """Create an in-memory XLSX file and return its bytes.

    Args:
        headers: Column header strings
        rows: List of row data lists
        title_rows: Number of blank/title rows before the header row
    """
    if openpyxl is None:
        pytest.skip("openpyxl not installed")

    wb = openpyxl.Workbook()
    ws = wb.active

    # Add optional title rows
    for i in range(title_rows):
        ws.append([f"Title Row {i + 1}"] + [""] * (len(headers) - 1))

    # Add header row
    ws.append(headers)

    # Add data rows
    for row in rows:
        ws.append(row)

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf.read()
