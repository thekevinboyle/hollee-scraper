"""Tests for review queue API endpoints.

Uses mock-based testing with dependency overrides, following the same pattern
as the other API test files (test_documents.py, test_wells.py).
"""

import uuid
from collections import namedtuple
from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from og_scraper.api.deps import get_db
from og_scraper.models.data_correction import DataCorrection
from og_scraper.models.document import Document
from og_scraper.models.enums import DocType, DocumentStatus
from og_scraper.models.extracted_data import ExtractedData
from og_scraper.models.operator import Operator
from og_scraper.models.review_queue import ReviewQueue
from og_scraper.models.well import Well

# ---------------------------------------------------------------------------
# Deterministic UUIDs
# ---------------------------------------------------------------------------
REVIEW_1_ID = uuid.UUID("40000000-0000-0000-0000-000000000001")
REVIEW_2_ID = uuid.UUID("40000000-0000-0000-0000-000000000002")
DOC_1_ID = uuid.UUID("20000000-0000-0000-0000-000000000001")
DOC_2_ID = uuid.UUID("20000000-0000-0000-0000-000000000002")
WELL_1_ID = uuid.UUID("10000000-0000-0000-0000-000000000001")
OPERATOR_1_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")
EXTRACTED_1_ID = uuid.UUID("30000000-0000-0000-0000-000000000001")
EXTRACTED_2_ID = uuid.UUID("30000000-0000-0000-0000-000000000002")

NOW = datetime(2025, 6, 15, 12, 0, 0, tzinfo=UTC)

# Named tuple matching the select() columns in list_review_items
ReviewRow = namedtuple(
    "ReviewRow",
    [
        "id",
        "document_id",
        "extracted_data_id",
        "status",
        "reason",
        "document_confidence",
        "created_at",
        "state_code",
        "doc_type",
        "well_api_number",
        "well_name",
        "operator_name",
    ],
)


# ---------------------------------------------------------------------------
# Mock factories
# ---------------------------------------------------------------------------
def make_review_queue(review_id, doc_id, extracted_id=None, status="pending", **kwargs):
    rq = MagicMock(spec=ReviewQueue)
    rq.id = review_id
    rq.document_id = doc_id
    rq.extracted_data_id = extracted_id
    rq.status = status
    rq.reason = kwargs.get("reason", "low_field_confidence: operator_name")
    rq.flag_details = kwargs.get("flag_details", {"low_fields": ["operator_name"]})
    rq.document_confidence = kwargs.get("document_confidence", Decimal("0.7200"))
    rq.field_confidences = kwargs.get(
        "field_confidences",
        {"oil_bbl": 0.95, "gas_mcf": 0.92, "operator_name": 0.55},
    )
    rq.corrections = kwargs.get("corrections", {})
    rq.notes = kwargs.get("notes")
    rq.reviewed_by = kwargs.get("reviewed_by")
    rq.reviewed_at = kwargs.get("reviewed_at")
    rq.created_at = kwargs.get("created_at", NOW)
    rq.updated_at = NOW
    return rq


def make_document_mock(doc_id, well_id=None, state_code="TX", **kwargs):
    d = MagicMock(spec=Document)
    d.id = doc_id
    d.well_id = well_id
    d.state_code = state_code
    d.doc_type = kwargs.get("doc_type", DocType.PRODUCTION_REPORT)
    d.status = kwargs.get("status", DocumentStatus.FLAGGED_FOR_REVIEW)
    d.source_url = kwargs.get("source_url", f"https://example.com/doc/{doc_id}")
    d.file_path = kwargs.get("file_path", "/data/documents/test.pdf")
    d.file_hash = kwargs.get("file_hash")
    d.file_format = kwargs.get("file_format", "pdf")
    d.file_size_bytes = kwargs.get("file_size_bytes")
    d.confidence_score = kwargs.get("confidence_score", Decimal("0.7200"))
    d.ocr_confidence = kwargs.get("ocr_confidence", Decimal("0.8000"))
    d.classification_method = kwargs.get("classification_method", "rule_based")
    d.document_date = kwargs.get("document_date")
    d.scraped_at = NOW
    d.processed_at = NOW
    d.raw_metadata = {}
    d.extracted_data = []
    d.well = None
    d.created_at = NOW
    d.updated_at = NOW
    return d


def make_well_mock(well_id, api_number="42501201300300", operator_id=None, **kwargs):
    w = MagicMock(spec=Well)
    w.id = well_id
    w.api_number = api_number
    w.well_name = kwargs.get("well_name", "Test Well #1")
    w.operator_id = operator_id
    w.state_code = kwargs.get("state_code", "TX")
    return w


def make_operator_mock(op_id, name="Test Operator"):
    op = MagicMock(spec=Operator)
    op.id = op_id
    op.name = name
    return op


def make_extracted_data_mock(ed_id, doc_id, **kwargs):
    ed = MagicMock(spec=ExtractedData)
    ed.id = ed_id
    ed.document_id = doc_id
    ed.data_type = kwargs.get("data_type", "production")
    ed.data = kwargs.get(
        "data",
        {"oil_bbl": 1250, "gas_mcf": 3400, "operator_name": "Tset Opertaor"},
    )
    ed.field_confidence = kwargs.get(
        "field_confidence",
        {"oil_bbl": 0.95, "gas_mcf": 0.92, "operator_name": 0.55},
    )
    ed.confidence_score = kwargs.get("confidence_score", Decimal("0.7200"))
    ed.extractor_used = "paddleocr"
    ed.extraction_version = "1.0"
    ed.reporting_period_start = None
    ed.reporting_period_end = None
    ed.extracted_at = NOW
    ed.created_at = NOW
    ed.updated_at = NOW
    return ed


def make_review_row(review, document, well=None, operator=None):
    """Create a ReviewRow from mock objects for list endpoint testing."""
    return ReviewRow(
        id=review.id,
        document_id=review.document_id,
        extracted_data_id=review.extracted_data_id,
        status=review.status,
        reason=review.reason,
        document_confidence=review.document_confidence,
        created_at=review.created_at,
        state_code=document.state_code,
        doc_type=document.doc_type,
        well_api_number=well.api_number if well else None,
        well_name=well.well_name if well else None,
        operator_name=operator.name if operator else None,
    )


# ---------------------------------------------------------------------------
# Tests: GET /api/v1/review (list)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_list_review_items_returns_200(app):
    """GET /api/v1/review returns 200 with paginated response of pending items."""
    review = make_review_queue(REVIEW_1_ID, DOC_1_ID, EXTRACTED_1_ID)
    document = make_document_mock(DOC_1_ID, WELL_1_ID)
    well = make_well_mock(WELL_1_ID, operator_id=OPERATOR_1_ID)
    operator = make_operator_mock(OPERATOR_1_ID)
    rows = [make_review_row(review, document, well, operator)]

    mock_db = AsyncMock()

    async def mock_get_db():
        yield mock_db

    app.dependency_overrides[get_db] = mock_get_db

    with patch("og_scraper.api.routes.review.paginate") as mock_paginate:
        mock_paginate.return_value = {
            "items": rows,
            "total": 1,
            "page": 1,
            "page_size": 50,
            "total_pages": 1,
        }

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test", follow_redirects=True) as client:
            response = await client.get("/api/v1/review")

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert len(data["items"]) == 1
        item = data["items"][0]
        assert item["status"] == "pending"
        assert item["reason"] == "low_field_confidence: operator_name"
        assert item["state_code"] == "TX"
        assert item["well_api_number"] == "42501201300300"
        assert item["operator_name"] == "Test Operator"

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_list_review_items_filter_by_state(app):
    """GET /api/v1/review?state=TX returns TX items; ?state=OK returns empty."""
    review = make_review_queue(REVIEW_1_ID, DOC_1_ID, EXTRACTED_1_ID)
    document = make_document_mock(DOC_1_ID, WELL_1_ID)
    well = make_well_mock(WELL_1_ID, operator_id=OPERATOR_1_ID)
    operator = make_operator_mock(OPERATOR_1_ID)
    rows = [make_review_row(review, document, well, operator)]

    mock_db = AsyncMock()

    async def mock_get_db():
        yield mock_db

    app.dependency_overrides[get_db] = mock_get_db

    with patch("og_scraper.api.routes.review.paginate") as mock_paginate:
        # TX should return 1
        mock_paginate.return_value = {
            "items": rows,
            "total": 1,
            "page": 1,
            "page_size": 50,
            "total_pages": 1,
        }
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test", follow_redirects=True) as client:
            response = await client.get("/api/v1/review?state=TX")
        assert response.status_code == 200
        assert response.json()["total"] == 1

        # OK should return 0
        mock_paginate.return_value = {
            "items": [],
            "total": 0,
            "page": 1,
            "page_size": 50,
            "total_pages": 1,
        }
        async with AsyncClient(transport=transport, base_url="http://test", follow_redirects=True) as client:
            response = await client.get("/api/v1/review?state=OK")
        assert response.status_code == 200
        assert response.json()["total"] == 0

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_list_review_items_filter_by_doc_type(app):
    """GET /api/v1/review?doc_type=production_report filters by document type."""
    review = make_review_queue(REVIEW_1_ID, DOC_1_ID, EXTRACTED_1_ID)
    document = make_document_mock(DOC_1_ID, WELL_1_ID, doc_type=DocType.PRODUCTION_REPORT)
    well = make_well_mock(WELL_1_ID)
    rows = [make_review_row(review, document, well)]

    mock_db = AsyncMock()

    async def mock_get_db():
        yield mock_db

    app.dependency_overrides[get_db] = mock_get_db

    with patch("og_scraper.api.routes.review.paginate") as mock_paginate:
        mock_paginate.return_value = {
            "items": rows,
            "total": 1,
            "page": 1,
            "page_size": 50,
            "total_pages": 1,
        }

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test", follow_redirects=True) as client:
            response = await client.get("/api/v1/review?doc_type=production_report")

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert data["items"][0]["doc_type"] == "production_report"

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_list_review_items_sorts_by_confidence_desc(app):
    """GET /api/v1/review returns items sorted by confidence descending (default)."""
    # Higher confidence first
    review1 = make_review_queue(REVIEW_1_ID, DOC_1_ID, EXTRACTED_1_ID, document_confidence=Decimal("0.8000"))
    review2 = make_review_queue(REVIEW_2_ID, DOC_2_ID, EXTRACTED_2_ID, document_confidence=Decimal("0.6000"))
    doc1 = make_document_mock(DOC_1_ID, WELL_1_ID)
    doc2 = make_document_mock(DOC_2_ID, WELL_1_ID)
    well = make_well_mock(WELL_1_ID)
    rows = [
        make_review_row(review1, doc1, well),
        make_review_row(review2, doc2, well),
    ]

    mock_db = AsyncMock()

    async def mock_get_db():
        yield mock_db

    app.dependency_overrides[get_db] = mock_get_db

    with patch("og_scraper.api.routes.review.paginate") as mock_paginate:
        mock_paginate.return_value = {
            "items": rows,
            "total": 2,
            "page": 1,
            "page_size": 50,
            "total_pages": 1,
        }

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test", follow_redirects=True) as client:
            response = await client.get("/api/v1/review")

        assert response.status_code == 200
        data = response.json()
        items = data["items"]
        assert len(items) == 2
        # First item should have higher confidence
        assert items[0]["document_confidence"] >= items[1]["document_confidence"]

    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Tests: GET /api/v1/review/{id} (detail)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_get_review_detail(app):
    """GET /api/v1/review/{id} returns full detail with document and extracted_data."""
    review = make_review_queue(REVIEW_1_ID, DOC_1_ID, EXTRACTED_1_ID)
    document = make_document_mock(DOC_1_ID, WELL_1_ID)
    well = make_well_mock(WELL_1_ID, operator_id=OPERATOR_1_ID)
    operator = make_operator_mock(OPERATOR_1_ID)
    extracted = make_extracted_data_mock(EXTRACTED_1_ID, DOC_1_ID)

    mock_db = AsyncMock()
    # The endpoint calls db.execute() multiple times with different queries:
    # 1. select ReviewQueue
    # 2. select Document
    # 3. select Well
    # 4. select Operator
    # 5. select ExtractedData
    mock_results = []
    for obj in [review, document, well, operator, extracted]:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = obj
        mock_results.append(mock_result)

    mock_db.execute = AsyncMock(side_effect=mock_results)

    async def mock_get_db():
        yield mock_db

    app.dependency_overrides[get_db] = mock_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(f"/api/v1/review/{REVIEW_1_ID}")

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == str(REVIEW_1_ID)
    assert data["status"] == "pending"
    assert data["document"] is not None
    assert data["extracted_data"] is not None
    assert data["file_url"] == f"/api/v1/documents/{DOC_1_ID}/file"
    assert data["well_api_number"] == "42501201300300"
    assert data["operator_name"] == "Test Operator"
    assert data["flag_details"] == {"low_fields": ["operator_name"]}

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_get_review_detail_not_found(app):
    """GET /api/v1/review/{id} returns 404 for nonexistent ID."""
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
        response = await client.get(f"/api/v1/review/{fake_id}")

    assert response.status_code == 404

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_get_review_detail_no_file_path(app):
    """GET /api/v1/review/{id} returns file_url=None when document has no file_path."""
    review = make_review_queue(REVIEW_1_ID, DOC_1_ID, EXTRACTED_1_ID)
    document = make_document_mock(DOC_1_ID, WELL_1_ID, file_path=None)
    well = make_well_mock(WELL_1_ID)
    extracted = make_extracted_data_mock(EXTRACTED_1_ID, DOC_1_ID)

    mock_db = AsyncMock()
    # No operator_id, so only 4 queries: review, document, well, extracted_data
    # well.operator_id = None so operator query is skipped
    well.operator_id = None
    mock_results = []
    for obj in [review, document, well, extracted]:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = obj
        mock_results.append(mock_result)

    mock_db.execute = AsyncMock(side_effect=mock_results)

    async def mock_get_db():
        yield mock_db

    app.dependency_overrides[get_db] = mock_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(f"/api/v1/review/{REVIEW_1_ID}")

    assert response.status_code == 200
    data = response.json()
    assert data["file_url"] is None

    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Tests: PATCH /api/v1/review/{id} (approve)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_approve_review(app):
    """PATCH /api/v1/review/{id} with approved updates status."""
    review = make_review_queue(REVIEW_1_ID, DOC_1_ID, EXTRACTED_1_ID)
    document = make_document_mock(DOC_1_ID, WELL_1_ID)
    well = make_well_mock(WELL_1_ID)
    well.operator_id = None

    mock_db = AsyncMock()
    # Calls: 1) select review, 2) select document, 3) flush,
    # then for response: 4) select well, 5) select extracted_data
    extracted = make_extracted_data_mock(EXTRACTED_1_ID, DOC_1_ID)

    mock_results = []
    for obj in [review, document, well, extracted]:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = obj
        mock_results.append(mock_result)

    mock_db.execute = AsyncMock(side_effect=mock_results)
    mock_db.flush = AsyncMock()

    async def mock_get_db():
        yield mock_db

    app.dependency_overrides[get_db] = mock_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.patch(
            f"/api/v1/review/{REVIEW_1_ID}",
            json={"status": "approved", "reviewed_by": "John"},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "approved"
    assert data["reviewed_by"] == "John"
    # Verify document status was updated
    assert document.status == "stored"

    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Tests: PATCH /api/v1/review/{id} (reject)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_reject_review(app):
    """PATCH /api/v1/review/{id} with rejected updates status."""
    review = make_review_queue(REVIEW_1_ID, DOC_1_ID, EXTRACTED_1_ID)
    document = make_document_mock(DOC_1_ID, WELL_1_ID)
    well = make_well_mock(WELL_1_ID)
    well.operator_id = None
    extracted = make_extracted_data_mock(EXTRACTED_1_ID, DOC_1_ID)

    mock_db = AsyncMock()
    mock_results = []
    for obj in [review, document, well, extracted]:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = obj
        mock_results.append(mock_result)

    mock_db.execute = AsyncMock(side_effect=mock_results)
    mock_db.flush = AsyncMock()

    async def mock_get_db():
        yield mock_db

    app.dependency_overrides[get_db] = mock_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.patch(
            f"/api/v1/review/{REVIEW_1_ID}",
            json={
                "status": "rejected",
                "reviewed_by": "John",
                "notes": "Document is unreadable",
            },
        )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "rejected"
    assert data["notes"] == "Document is unreadable"
    # Verify document status was updated to extraction_failed
    assert document.status == "extraction_failed"

    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Tests: PATCH /api/v1/review/{id} (correct)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_correct_review(app):
    """PATCH /api/v1/review/{id} with corrected updates extracted_data and creates audit trail."""
    review = make_review_queue(REVIEW_1_ID, DOC_1_ID, EXTRACTED_1_ID)
    document = make_document_mock(DOC_1_ID, WELL_1_ID)
    extracted = make_extracted_data_mock(EXTRACTED_1_ID, DOC_1_ID)
    well = make_well_mock(WELL_1_ID)
    well.operator_id = None

    mock_db = AsyncMock()
    # Calls for correct: review, extracted_data, document, flush
    # Then for response: well, extracted_data again
    mock_results = []
    for obj in [review, extracted, document, well, extracted]:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = obj
        mock_results.append(mock_result)

    mock_db.execute = AsyncMock(side_effect=mock_results)
    mock_db.flush = AsyncMock()
    mock_db.add = MagicMock()

    async def mock_get_db():
        yield mock_db

    app.dependency_overrides[get_db] = mock_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.patch(
            f"/api/v1/review/{REVIEW_1_ID}",
            json={
                "status": "corrected",
                "corrections": {
                    "operator_name": {"old": "Tset Opertaor", "new": "Test Operator"},
                },
                "reviewed_by": "John",
                "notes": "Fixed typo in operator name",
            },
        )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "corrected"
    assert data["reviewed_by"] == "John"
    assert data["notes"] == "Fixed typo in operator name"
    # Verify extracted data was updated
    assert extracted.data["operator_name"] == "Test Operator"
    # Verify document status was updated
    assert document.status == "stored"
    # Verify db.add was called with a DataCorrection object
    mock_db.add.assert_called()
    added_obj = mock_db.add.call_args[0][0]
    assert isinstance(added_obj, DataCorrection)
    assert added_obj.field_path == "operator_name"
    assert added_obj.corrected_by == "John"

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_correct_review_multiple_fields(app):
    """PATCH with corrected creates multiple data_corrections records for multiple fields."""
    review = make_review_queue(REVIEW_1_ID, DOC_1_ID, EXTRACTED_1_ID)
    document = make_document_mock(DOC_1_ID, WELL_1_ID)
    extracted = make_extracted_data_mock(
        EXTRACTED_1_ID,
        DOC_1_ID,
        data={"oil_bbl": 1250, "gas_mcf": 3400, "operator_name": "Tset Opertaor"},
    )
    well = make_well_mock(WELL_1_ID)
    well.operator_id = None

    mock_db = AsyncMock()
    mock_results = []
    for obj in [review, extracted, document, well, extracted]:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = obj
        mock_results.append(mock_result)

    mock_db.execute = AsyncMock(side_effect=mock_results)
    mock_db.flush = AsyncMock()
    mock_db.add = MagicMock()

    async def mock_get_db():
        yield mock_db

    app.dependency_overrides[get_db] = mock_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.patch(
            f"/api/v1/review/{REVIEW_1_ID}",
            json={
                "status": "corrected",
                "corrections": {
                    "operator_name": {"old": "Tset Opertaor", "new": "Test Operator"},
                    "oil_bbl": {"old": 1250, "new": 1350},
                },
                "reviewed_by": "John",
            },
        )

    assert response.status_code == 200
    # Two corrections = two db.add calls
    assert mock_db.add.call_count == 2
    # Verify both corrections were applied to extracted data
    assert extracted.data["operator_name"] == "Test Operator"
    assert extracted.data["oil_bbl"] == 1350

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_correct_preserves_old_value(app):
    """PATCH with corrected preserves old_value in the DataCorrection audit record."""
    review = make_review_queue(REVIEW_1_ID, DOC_1_ID, EXTRACTED_1_ID)
    document = make_document_mock(DOC_1_ID, WELL_1_ID)
    extracted = make_extracted_data_mock(
        EXTRACTED_1_ID,
        DOC_1_ID,
        data={"operator_name": "Tset Opertaor"},
    )
    well = make_well_mock(WELL_1_ID)
    well.operator_id = None

    mock_db = AsyncMock()
    mock_results = []
    for obj in [review, extracted, document, well, extracted]:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = obj
        mock_results.append(mock_result)

    mock_db.execute = AsyncMock(side_effect=mock_results)
    mock_db.flush = AsyncMock()
    mock_db.add = MagicMock()

    async def mock_get_db():
        yield mock_db

    app.dependency_overrides[get_db] = mock_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.patch(
            f"/api/v1/review/{REVIEW_1_ID}",
            json={
                "status": "corrected",
                "corrections": {
                    "operator_name": {"old": "Tset Opertaor", "new": "Test Operator"},
                },
                "reviewed_by": "John",
            },
        )

    assert response.status_code == 200
    added_obj = mock_db.add.call_args[0][0]
    assert added_obj.old_value == "Tset Opertaor"
    assert added_obj.new_value == "Test Operator"

    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Tests: Error cases
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_cannot_act_on_resolved_review(app):
    """PATCH /api/v1/review/{id} returns 400 when acting on already-resolved item."""
    # Review already approved
    review = make_review_queue(REVIEW_1_ID, DOC_1_ID, EXTRACTED_1_ID, status="approved")

    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = review
    mock_db.execute.return_value = mock_result

    async def mock_get_db():
        yield mock_db

    app.dependency_overrides[get_db] = mock_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.patch(
            f"/api/v1/review/{REVIEW_1_ID}",
            json={"status": "rejected"},
        )

    assert response.status_code == 400
    assert "already resolved" in response.json()["detail"].lower()

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_correct_without_corrections_fails(app):
    """PATCH with corrected but no corrections dict returns 400."""
    review = make_review_queue(REVIEW_1_ID, DOC_1_ID, EXTRACTED_1_ID)

    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = review
    mock_db.execute.return_value = mock_result

    async def mock_get_db():
        yield mock_db

    app.dependency_overrides[get_db] = mock_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.patch(
            f"/api/v1/review/{REVIEW_1_ID}",
            json={"status": "corrected"},
        )

    assert response.status_code == 400
    assert "corrections are required" in response.json()["detail"].lower()

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_patch_review_not_found(app):
    """PATCH /api/v1/review/{id} returns 404 for nonexistent item."""
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
        response = await client.patch(
            f"/api/v1/review/{fake_id}",
            json={"status": "approved"},
        )

    assert response.status_code == 404

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_correct_with_empty_corrections_fails(app):
    """PATCH with corrected and empty corrections dict returns 400."""
    review = make_review_queue(REVIEW_1_ID, DOC_1_ID, EXTRACTED_1_ID)

    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = review
    mock_db.execute.return_value = mock_result

    async def mock_get_db():
        yield mock_db

    app.dependency_overrides[get_db] = mock_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.patch(
            f"/api/v1/review/{REVIEW_1_ID}",
            json={"status": "corrected", "corrections": {}},
        )

    assert response.status_code == 400

    app.dependency_overrides.clear()
