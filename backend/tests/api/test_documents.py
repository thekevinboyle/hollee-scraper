"""Tests for document API endpoints."""

import uuid
from collections import namedtuple
from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from og_scraper.api.deps import get_db
from og_scraper.models.enums import DocType

DocRow = namedtuple(
    "DocRow",
    [
        "id",
        "well_id",
        "state_code",
        "doc_type",
        "document_date",
        "confidence_score",
        "file_format",
        "source_url",
        "scraped_at",
    ],
)


def make_doc_row(doc):
    """Create a DocRow from a mock document object."""
    return DocRow(
        id=doc.id,
        well_id=doc.well_id,
        state_code=doc.state_code,
        doc_type=doc.doc_type,
        document_date=doc.document_date,
        confidence_score=doc.confidence_score,
        file_format=doc.file_format,
        source_url=doc.source_url,
        scraped_at=doc.scraped_at,
    )


@pytest.mark.asyncio
async def test_list_documents_returns_200(app, seed_data):
    """GET /api/v1/documents returns 200 with paginated response."""
    docs = seed_data["documents"]
    doc_rows = [make_doc_row(d) for d in docs]

    mock_db = AsyncMock()

    async def mock_get_db():
        yield mock_db

    app.dependency_overrides[get_db] = mock_get_db

    with patch("og_scraper.api.routes.documents.paginate") as mock_paginate:
        mock_paginate.return_value = {
            "items": doc_rows,
            "total": len(doc_rows),
            "page": 1,
            "page_size": 50,
            "total_pages": 1,
        }

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test", follow_redirects=True) as client:
            response = await client.get("/api/v1/documents")

        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert "total" in data
        assert "page" in data
        assert "page_size" in data
        assert "total_pages" in data
        assert data["total"] == len(docs)

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_list_documents_filter_by_state_and_type(app, seed_data):
    """GET /api/v1/documents?state=TX&doc_type=production_report filters correctly."""
    docs = seed_data["documents"]
    matching = [d for d in docs if d.state_code == "TX" and d.doc_type == DocType.PRODUCTION_REPORT]
    doc_rows = [make_doc_row(d) for d in matching]

    mock_db = AsyncMock()

    async def mock_get_db():
        yield mock_db

    app.dependency_overrides[get_db] = mock_get_db

    with patch("og_scraper.api.routes.documents.paginate") as mock_paginate:
        mock_paginate.return_value = {
            "items": doc_rows,
            "total": len(doc_rows),
            "page": 1,
            "page_size": 50,
            "total_pages": 1,
        }

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test", follow_redirects=True) as client:
            response = await client.get("/api/v1/documents?state=TX&doc_type=production_report")

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == len(matching)
        for item in data["items"]:
            assert item["state_code"] == "TX"
            assert item["doc_type"] == "production_report"

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_list_documents_filter_by_confidence(app, seed_data):
    """GET /api/v1/documents?min_confidence=0.9 returns only high-confidence docs."""
    docs = seed_data["documents"]
    matching = [d for d in docs if d.confidence_score and d.confidence_score >= 0.9]
    doc_rows = [make_doc_row(d) for d in matching]

    mock_db = AsyncMock()

    async def mock_get_db():
        yield mock_db

    app.dependency_overrides[get_db] = mock_get_db

    with patch("og_scraper.api.routes.documents.paginate") as mock_paginate:
        mock_paginate.return_value = {
            "items": doc_rows,
            "total": len(doc_rows),
            "page": 1,
            "page_size": 50,
            "total_pages": 1,
        }

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test", follow_redirects=True) as client:
            response = await client.get("/api/v1/documents?min_confidence=0.9")

        assert response.status_code == 200
        data = response.json()
        for item in data["items"]:
            assert item["confidence_score"] is not None
            assert item["confidence_score"] >= 0.9

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_list_documents_filter_by_date_range(app, seed_data):
    """GET /api/v1/documents?date_from=2025-01-01&date_to=2025-12-31 filters by date."""
    docs = seed_data["documents"]
    matching = [d for d in docs if d.document_date and date(2025, 1, 1) <= d.document_date <= date(2025, 12, 31)]
    doc_rows = [make_doc_row(d) for d in matching]

    mock_db = AsyncMock()

    async def mock_get_db():
        yield mock_db

    app.dependency_overrides[get_db] = mock_get_db

    with patch("og_scraper.api.routes.documents.paginate") as mock_paginate:
        mock_paginate.return_value = {
            "items": doc_rows,
            "total": len(doc_rows),
            "page": 1,
            "page_size": 50,
            "total_pages": 1,
        }

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test", follow_redirects=True) as client:
            response = await client.get("/api/v1/documents?date_from=2025-01-01&date_to=2025-12-31")

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == len(matching)

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_get_document_detail(app, seed_data):
    """GET /api/v1/documents/{id} returns detail with extracted_data list."""
    doc = seed_data["documents"][0]

    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = doc
    mock_db.execute.return_value = mock_result

    async def mock_get_db():
        yield mock_db

    app.dependency_overrides[get_db] = mock_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(f"/api/v1/documents/{doc.id}")

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == str(doc.id)
    assert data["state_code"] == "TX"
    assert "extracted_data" in data
    assert len(data["extracted_data"]) == 1

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_get_document_not_found(app):
    """GET /api/v1/documents/{id} returns 404 for non-existent UUID."""
    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_db.execute.return_value = mock_result

    async def mock_get_db():
        yield mock_db

    app.dependency_overrides[get_db] = mock_get_db

    fake_id = uuid.uuid4()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(f"/api/v1/documents/{fake_id}")

    assert response.status_code == 404

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_get_document_file_serves_pdf(app, seed_data, tmp_path):
    """GET /api/v1/documents/{id}/file returns FileResponse for existing PDF."""
    # Create a temporary PDF file
    pdf_file = tmp_path / "test.pdf"
    pdf_file.write_bytes(b"%PDF-1.4 fake pdf content")

    doc = seed_data["documents"][0]
    doc.file_path = str(pdf_file)
    doc.file_format = "pdf"

    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = doc
    mock_db.execute.return_value = mock_result

    async def mock_get_db():
        yield mock_db

    app.dependency_overrides[get_db] = mock_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(f"/api/v1/documents/{doc.id}/file")

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert "inline" in response.headers.get("content-disposition", "")

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_get_document_file_serves_xlsx_as_attachment(app, seed_data, tmp_path):
    """GET /api/v1/documents/{id}/file serves non-PDF files as attachment."""
    xlsx_file = tmp_path / "test.xlsx"
    xlsx_file.write_bytes(b"PK fake xlsx content")

    doc = seed_data["documents"][0]
    doc.file_path = str(xlsx_file)
    doc.file_format = "xlsx"

    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = doc
    mock_db.execute.return_value = mock_result

    async def mock_get_db():
        yield mock_db

    app.dependency_overrides[get_db] = mock_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(f"/api/v1/documents/{doc.id}/file")

    assert response.status_code == 200
    assert "attachment" in response.headers.get("content-disposition", "")

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_get_document_file_missing_returns_404(app, seed_data):
    """GET /api/v1/documents/{id}/file returns 404 when file missing on disk."""
    doc = seed_data["documents"][0]
    doc.file_path = "/nonexistent/path/file.pdf"

    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = doc
    mock_db.execute.return_value = mock_result

    async def mock_get_db():
        yield mock_db

    app.dependency_overrides[get_db] = mock_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(f"/api/v1/documents/{doc.id}/file")

    assert response.status_code == 404

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_get_document_file_no_path_returns_404(app, seed_data):
    """GET /api/v1/documents/{id}/file returns 404 when file_path not set."""
    doc = seed_data["documents"][0]
    doc.file_path = None

    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = doc
    mock_db.execute.return_value = mock_result

    async def mock_get_db():
        yield mock_db

    app.dependency_overrides[get_db] = mock_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(f"/api/v1/documents/{doc.id}/file")

    assert response.status_code == 404

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_get_document_file_not_found_document(app):
    """GET /api/v1/documents/{id}/file returns 404 for non-existent document."""
    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_db.execute.return_value = mock_result

    async def mock_get_db():
        yield mock_db

    app.dependency_overrides[get_db] = mock_get_db

    fake_id = uuid.uuid4()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(f"/api/v1/documents/{fake_id}/file")

    assert response.status_code == 404

    app.dependency_overrides.clear()
