"""Tests for SQLAlchemy models and database schema."""

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from og_scraper.models import (
    DataCorrection,
    DocType,
    Document,
    DocumentStatus,
    ExtractedData,
    Operator,
    ReviewQueue,
    ReviewStatus,
    ScrapeJob,
    ScrapeJobStatus,
    State,
    Well,
    WellStatus,
)


@pytest.mark.asyncio
async def test_all_tables_created(db_session):
    """Verify all 8 tables exist in the database."""
    result = await db_session.execute(
        text("SELECT table_name FROM information_schema.tables WHERE table_schema='public' ORDER BY table_name")
    )
    tables = {row[0] for row in result.fetchall()}
    expected = {
        "states",
        "operators",
        "wells",
        "documents",
        "extracted_data",
        "review_queue",
        "scrape_jobs",
        "data_corrections",
    }
    assert expected.issubset(tables), f"Missing tables: {expected - tables}"


@pytest.mark.asyncio
async def test_insert_state(db_session):
    """Insert a state and verify it persists."""
    state = State(code="TX", name="Texas", api_state_code="42", tier=1)
    db_session.add(state)
    await db_session.flush()
    assert state.code == "TX"
    assert state.name == "Texas"
    assert state.api_state_code == "42"
    assert state.tier == 1


@pytest.mark.asyncio
async def test_insert_operator_with_search_vector(db_session):
    """Insert an operator and verify search_vector trigger populates it."""
    operator = Operator(
        name="Devon Energy Corporation",
        normalized_name="devon energy corporation",
    )
    db_session.add(operator)
    await db_session.flush()

    # Refresh from DB to get trigger-computed search_vector
    result = await db_session.execute(
        text("SELECT search_vector FROM operators WHERE id = :id"),
        {"id": operator.id},
    )
    row = result.fetchone()
    assert row is not None
    assert row[0] is not None  # search_vector should be populated by trigger


@pytest.mark.asyncio
async def test_insert_well_with_location(db_session):
    """Insert a well with lat/long and verify the PostGIS geometry column is populated via trigger."""
    state = State(code="OK", name="Oklahoma", api_state_code="35", tier=1)
    db_session.add(state)
    await db_session.flush()

    well = Well(
        api_number="35019213370000",
        state_code="OK",
        well_name="Test Well #1",
        latitude=35.4676,
        longitude=-97.5164,
    )
    db_session.add(well)
    await db_session.flush()

    assert well.id is not None
    assert well.api_number == "35019213370000"

    # Verify the location trigger populated the geometry column
    result = await db_session.execute(
        text("SELECT ST_AsText(location) FROM wells WHERE id = :id"),
        {"id": well.id},
    )
    row = result.fetchone()
    assert row is not None
    assert row[0] is not None
    assert "POINT" in row[0]


@pytest.mark.asyncio
async def test_well_search_vector_populated(db_session):
    """Insert a well with well_name and verify search_vector is populated."""
    state = State(code="NM", name="New Mexico", api_state_code="30", tier=1)
    db_session.add(state)
    await db_session.flush()

    well = Well(
        api_number="30015000010000",
        state_code="NM",
        well_name="Permian Basin #1",
        county="Lea",
        basin="Permian",
    )
    db_session.add(well)
    await db_session.flush()

    result = await db_session.execute(
        text("SELECT search_vector FROM wells WHERE id = :id"),
        {"id": well.id},
    )
    row = result.fetchone()
    assert row is not None
    assert row[0] is not None  # search_vector should be populated by trigger


@pytest.mark.asyncio
async def test_well_api_10_generated(db_session):
    """Verify api_10 computed column returns first 10 chars of api_number."""
    state = State(code="CO", name="Colorado", api_state_code="05", tier=1)
    db_session.add(state)
    await db_session.flush()

    well = Well(
        api_number="05123456780000",
        state_code="CO",
        well_name="API 10 Test",
    )
    db_session.add(well)
    await db_session.flush()

    result = await db_session.execute(
        text("SELECT api_10 FROM wells WHERE id = :id"),
        {"id": well.id},
    )
    row = result.fetchone()
    assert row is not None
    assert row[0] == "0512345678"


@pytest.mark.asyncio
async def test_enum_values_match_discovery():
    """Verify enum values match DISCOVERY.md document types."""
    doc_types = {e.value for e in DocType}
    expected_doc_types = {
        "well_permit",
        "completion_report",
        "production_report",
        "spacing_order",
        "pooling_order",
        "plugging_report",
        "inspection_record",
        "incident_report",
        "unknown",
        "other",
    }
    assert doc_types == expected_doc_types

    well_statuses = {e.value for e in WellStatus}
    expected_well_statuses = {
        "active",
        "inactive",
        "plugged",
        "permitted",
        "drilling",
        "completed",
        "shut_in",
        "temporarily_abandoned",
        "unknown",
    }
    assert well_statuses == expected_well_statuses

    document_statuses = {e.value for e in DocumentStatus}
    expected_document_statuses = {
        "discovered",
        "downloading",
        "downloaded",
        "classifying",
        "classified",
        "extracting",
        "extracted",
        "normalized",
        "stored",
        "flagged_for_review",
        "download_failed",
        "classification_failed",
        "extraction_failed",
    }
    assert document_statuses == expected_document_statuses

    scrape_statuses = {e.value for e in ScrapeJobStatus}
    expected_scrape_statuses = {"pending", "running", "completed", "failed", "cancelled"}
    assert scrape_statuses == expected_scrape_statuses

    review_statuses = {e.value for e in ReviewStatus}
    expected_review_statuses = {"pending", "approved", "rejected", "corrected"}
    assert review_statuses == expected_review_statuses


@pytest.mark.asyncio
async def test_document_file_hash_unique_constraint(db_session):
    """Insert a document with file_hash, then verify UNIQUE constraint prevents duplicates."""
    state = State(code="ND", name="North Dakota", api_state_code="33", tier=1)
    db_session.add(state)
    await db_session.flush()

    doc1 = Document(
        state_code="ND",
        source_url="https://example.com/doc1.pdf",
        file_hash="abc123def456abc123def456abc123def456abc123def456abc123def456abcd",
    )
    db_session.add(doc1)
    await db_session.flush()

    doc2 = Document(
        state_code="ND",
        source_url="https://example.com/doc2.pdf",
        file_hash="abc123def456abc123def456abc123def456abc123def456abc123def456abcd",  # Same hash
    )
    db_session.add(doc2)
    with pytest.raises(IntegrityError):
        await db_session.flush()


@pytest.mark.asyncio
async def test_cascade_delete_extracted_data(db_session):
    """Insert extracted_data linked to a document, then delete the document and verify cascade."""
    state = State(code="WY", name="Wyoming", api_state_code="49", tier=2)
    db_session.add(state)
    await db_session.flush()

    doc = Document(
        state_code="WY",
        source_url="https://example.com/doc.pdf",
    )
    db_session.add(doc)
    await db_session.flush()

    extracted = ExtractedData(
        document_id=doc.id,
        data_type="production",
        data={"oil_bbl": 1250, "gas_mcf": 3400},
        field_confidence={"oil_bbl": 0.97, "gas_mcf": 0.92},
        confidence_score=0.945,
    )
    db_session.add(extracted)
    await db_session.flush()
    extracted_id = extracted.id

    # Delete the document -- extracted_data should cascade
    await db_session.delete(doc)
    await db_session.flush()

    result = await db_session.execute(
        text("SELECT count(*) FROM extracted_data WHERE id = :id"),
        {"id": extracted_id},
    )
    count = result.scalar()
    assert count == 0


@pytest.mark.asyncio
async def test_scrape_job_crud(db_session):
    """Insert a scrape job and verify progress counter defaults."""
    state = State(code="LA", name="Louisiana", api_state_code="17", tier=2)
    db_session.add(state)
    await db_session.flush()

    job = ScrapeJob(
        state_code="LA",
        job_type="incremental",
    )
    db_session.add(job)
    await db_session.flush()

    assert job.id is not None
    assert job.status == ScrapeJobStatus.PENDING
    assert job.documents_found == 0
    assert job.documents_processed == 0


@pytest.mark.asyncio
async def test_review_queue_and_data_correction(db_session):
    """Insert a review queue item and a data correction linked to it."""
    state = State(code="PA", name="Pennsylvania", api_state_code="37", tier=2)
    db_session.add(state)
    await db_session.flush()

    doc = Document(
        state_code="PA",
        source_url="https://example.com/pa-doc.pdf",
    )
    db_session.add(doc)
    await db_session.flush()

    extracted = ExtractedData(
        document_id=doc.id,
        data_type="permit",
        data={"permit_number": "PA-2025-001"},
    )
    db_session.add(extracted)
    await db_session.flush()

    review = ReviewQueue(
        document_id=doc.id,
        extracted_data_id=extracted.id,
        reason="low_confidence",
        document_confidence=0.65,
    )
    db_session.add(review)
    await db_session.flush()

    assert review.id is not None
    assert review.status == ReviewStatus.PENDING

    correction = DataCorrection(
        extracted_data_id=extracted.id,
        review_queue_id=review.id,
        field_path="data.permit_number",
        old_value={"value": "PA-2025-001"},
        new_value={"value": "PA-2025-002"},
        corrected_by="admin",
    )
    db_session.add(correction)
    await db_session.flush()
    assert correction.id is not None


@pytest.mark.asyncio
async def test_postgis_extension_enabled(db_session):
    """Verify PostGIS extension is functional."""
    result = await db_session.execute(text("SELECT PostGIS_Version()"))
    version = result.scalar()
    assert version is not None


@pytest.mark.asyncio
async def test_uuid_extension_enabled(db_session):
    """Verify uuid-ossp extension is functional."""
    result = await db_session.execute(text("SELECT uuid_generate_v4()"))
    uid = result.scalar()
    assert uid is not None
    assert isinstance(uid, uuid.UUID)


@pytest.mark.asyncio
async def test_pg_trgm_extension_enabled(db_session):
    """Verify pg_trgm extension is functional."""
    result = await db_session.execute(text("SELECT similarity('test', 'tset')"))
    sim = result.scalar()
    assert sim is not None
    assert sim > 0
