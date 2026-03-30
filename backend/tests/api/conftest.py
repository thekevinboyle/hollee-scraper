"""Shared test fixtures for API endpoint tests.

Uses httpx.AsyncClient with ASGI transport and overrides
the get_db dependency to use a mock async session, so no
real database is needed for basic endpoint testing.
"""

import uuid
from datetime import UTC, date, datetime
from unittest.mock import MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from og_scraper.api.app import create_app
from og_scraper.models.document import Document
from og_scraper.models.enums import DocType, DocumentStatus, WellStatus
from og_scraper.models.extracted_data import ExtractedData
from og_scraper.models.operator import Operator
from og_scraper.models.well import Well

# ---------------------------------------------------------------------------
# Deterministic UUIDs for test entities
# ---------------------------------------------------------------------------
STATE_TX = "TX"
STATE_NM = "NM"
STATE_ND = "ND"

OPERATOR_1_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")
OPERATOR_2_ID = uuid.UUID("00000000-0000-0000-0000-000000000002")

WELL_1_ID = uuid.UUID("10000000-0000-0000-0000-000000000001")
WELL_2_ID = uuid.UUID("10000000-0000-0000-0000-000000000002")
WELL_3_ID = uuid.UUID("10000000-0000-0000-0000-000000000003")
WELL_4_ID = uuid.UUID("10000000-0000-0000-0000-000000000004")
WELL_5_ID = uuid.UUID("10000000-0000-0000-0000-000000000005")

DOC_1_ID = uuid.UUID("20000000-0000-0000-0000-000000000001")
DOC_2_ID = uuid.UUID("20000000-0000-0000-0000-000000000002")
DOC_3_ID = uuid.UUID("20000000-0000-0000-0000-000000000003")
DOC_4_ID = uuid.UUID("20000000-0000-0000-0000-000000000004")
DOC_5_ID = uuid.UUID("20000000-0000-0000-0000-000000000005")

EXTRACTED_1_ID = uuid.UUID("30000000-0000-0000-0000-000000000001")
EXTRACTED_2_ID = uuid.UUID("30000000-0000-0000-0000-000000000002")

NOW = datetime(2025, 6, 15, 12, 0, 0, tzinfo=UTC)


# ---------------------------------------------------------------------------
# Sample data factories
# ---------------------------------------------------------------------------
def make_operator(op_id, name, normalized_name):
    op = MagicMock(spec=Operator)
    op.id = op_id
    op.name = name
    op.normalized_name = normalized_name
    op.aliases = []
    op.state_operator_ids = {}
    op.metadata_ = {}
    op.created_at = NOW
    op.updated_at = NOW
    return op


def make_well(well_id, api_number, state_code, operator=None, **kwargs):
    w = MagicMock(spec=Well)
    w.id = well_id
    w.api_number = api_number
    w.api_10 = api_number[:10] if len(api_number) >= 10 else api_number
    w.well_name = kwargs.get("well_name", f"Test Well {api_number}")
    w.well_number = kwargs.get("well_number", "1")
    w.operator_id = operator.id if operator else None
    w.operator = operator
    w.state_code = state_code
    w.county = kwargs.get("county", "Test County")
    w.basin = kwargs.get("basin", "Permian")
    w.field_name = kwargs.get("field_name")
    w.lease_name = kwargs.get("lease_name")
    w.latitude = kwargs.get("latitude", 32.0)
    w.longitude = kwargs.get("longitude", -101.0)
    w.well_status = kwargs.get("well_status", WellStatus.ACTIVE)
    w.well_type = kwargs.get("well_type", "oil")
    w.spud_date = kwargs.get("spud_date")
    w.completion_date = kwargs.get("completion_date")
    w.total_depth = kwargs.get("total_depth")
    w.true_vertical_depth = kwargs.get("true_vertical_depth")
    w.lateral_length = kwargs.get("lateral_length")
    w.metadata_ = kwargs.get("metadata_", {})
    w.alternate_ids = kwargs.get("alternate_ids", {})
    w.documents = kwargs.get("documents", [])
    w.created_at = NOW
    w.updated_at = NOW
    return w


def make_document(doc_id, well=None, state_code="TX", **kwargs):
    d = MagicMock(spec=Document)
    d.id = doc_id
    d.well_id = well.id if well else None
    d.well = well
    d.state_code = state_code
    d.doc_type = kwargs.get("doc_type", DocType.WELL_PERMIT)
    d.status = kwargs.get("status", DocumentStatus.STORED)
    d.source_url = kwargs.get("source_url", f"https://example.com/doc/{doc_id}")
    d.file_path = kwargs.get("file_path")
    d.file_hash = kwargs.get("file_hash")
    d.file_format = kwargs.get("file_format", "pdf")
    d.file_size_bytes = kwargs.get("file_size_bytes")
    d.confidence_score = kwargs.get("confidence_score", 0.95)
    d.ocr_confidence = kwargs.get("ocr_confidence", 0.92)
    d.classification_method = kwargs.get("classification_method", "rule_based")
    d.document_date = kwargs.get("document_date", date(2025, 1, 15))
    d.scraped_at = kwargs.get("scraped_at", NOW)
    d.processed_at = kwargs.get("processed_at", NOW)
    d.raw_metadata = kwargs.get("raw_metadata", {})
    d.extracted_data = kwargs.get("extracted_data", [])
    d.created_at = NOW
    d.updated_at = NOW
    return d


def make_extracted_data(ed_id, doc_id, **kwargs):
    ed = MagicMock(spec=ExtractedData)
    ed.id = ed_id
    ed.document_id = doc_id
    ed.data_type = kwargs.get("data_type", "production")
    ed.data = kwargs.get("data", {"oil_bbl": 1250, "gas_mcf": 3400})
    ed.field_confidence = kwargs.get("field_confidence", {"oil_bbl": 0.97, "gas_mcf": 0.92})
    ed.confidence_score = kwargs.get("confidence_score", 0.94)
    ed.extractor_used = kwargs.get("extractor_used", "paddleocr")
    ed.extraction_version = kwargs.get("extraction_version", "1.0")
    ed.reporting_period_start = kwargs.get("reporting_period_start", date(2025, 1, 1))
    ed.reporting_period_end = kwargs.get("reporting_period_end", date(2025, 1, 31))
    ed.extracted_at = kwargs.get("extracted_at", NOW)
    ed.created_at = NOW
    ed.updated_at = NOW
    return ed


# ---------------------------------------------------------------------------
# Build the standard seed data set
# ---------------------------------------------------------------------------
def build_seed_data():
    """Build a complete seed data set for tests."""
    # Operators
    op1 = make_operator(OPERATOR_1_ID, "Devon Energy Corporation", "devon energy corporation")
    op2 = make_operator(OPERATOR_2_ID, "Continental Resources", "continental resources")

    # Wells
    w1 = make_well(
        WELL_1_ID,
        "42501201300300",
        STATE_TX,
        operator=op1,
        county="Reeves",
        basin="Permian",
        well_status=WellStatus.ACTIVE,
    )
    w2 = make_well(
        WELL_2_ID,
        "42501201300400",
        STATE_TX,
        operator=op1,
        county="Loving",
        basin="Permian",
        well_status=WellStatus.ACTIVE,
    )
    w3 = make_well(
        WELL_3_ID,
        "30015123450000",
        STATE_NM,
        operator=op2,
        county="Lea",
        basin="Permian",
        well_status=WellStatus.DRILLING,
    )
    w4 = make_well(
        WELL_4_ID,
        "33105678900000",
        STATE_ND,
        operator=op2,
        county="McKenzie",
        basin="Williston",
        well_status=WellStatus.PLUGGED,
    )
    w5 = make_well(
        WELL_5_ID,
        "42501201300500",
        STATE_TX,
        operator=op1,
        county="Ward",
        basin="Permian",
        well_status=WellStatus.COMPLETED,
    )

    # Extracted data
    ed1 = make_extracted_data(EXTRACTED_1_ID, DOC_1_ID, data_type="production")
    ed2 = make_extracted_data(EXTRACTED_2_ID, DOC_2_ID, data_type="permit")

    # Documents
    d1 = make_document(
        DOC_1_ID,
        well=w1,
        state_code=STATE_TX,
        doc_type=DocType.PRODUCTION_REPORT,
        confidence_score=0.95,
        document_date=date(2025, 1, 15),
        extracted_data=[ed1],
    )
    d2 = make_document(
        DOC_2_ID,
        well=w1,
        state_code=STATE_TX,
        doc_type=DocType.WELL_PERMIT,
        confidence_score=0.88,
        document_date=date(2025, 3, 1),
        extracted_data=[ed2],
    )
    d3 = make_document(
        DOC_3_ID,
        well=w2,
        state_code=STATE_TX,
        doc_type=DocType.COMPLETION_REPORT,
        confidence_score=0.92,
        document_date=date(2025, 6, 15),
    )
    d4 = make_document(
        DOC_4_ID,
        well=w3,
        state_code=STATE_NM,
        doc_type=DocType.WELL_PERMIT,
        confidence_score=0.78,
        document_date=date(2024, 11, 1),
    )
    d5 = make_document(
        DOC_5_ID,
        well=w4,
        state_code=STATE_ND,
        doc_type=DocType.PLUGGING_REPORT,
        confidence_score=0.97,
        document_date=date(2025, 2, 20),
    )

    # Attach documents to wells
    w1.documents = [d1, d2]
    w2.documents = [d3]
    w3.documents = [d4]
    w4.documents = [d5]
    w5.documents = []

    return {
        "operators": [op1, op2],
        "wells": [w1, w2, w3, w4, w5],
        "documents": [d1, d2, d3, d4, d5],
        "extracted_data": [ed1, ed2],
        "states": [
            {"code": STATE_TX, "name": "Texas", "api_state_code": "42", "tier": 1},
            {"code": STATE_NM, "name": "New Mexico", "api_state_code": "30", "tier": 1},
            {"code": STATE_ND, "name": "North Dakota", "api_state_code": "33", "tier": 1},
        ],
    }


@pytest.fixture
def seed_data():
    return build_seed_data()


@pytest.fixture
def app():
    """Create a FastAPI test app."""
    return create_app()


@pytest.fixture
async def client(app):
    """AsyncClient that talks to the test app via ASGI transport."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
