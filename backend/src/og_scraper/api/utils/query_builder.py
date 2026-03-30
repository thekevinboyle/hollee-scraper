"""Reusable query builders for wells and documents.

Supports filtering, sorting, and full-text search using SQLAlchemy 2.0 patterns.
"""

from datetime import date

from sqlalchemy import asc, desc, func, or_, select

from og_scraper.models.document import Document
from og_scraper.models.operator import Operator
from og_scraper.models.well import Well


def build_wells_query(
    q: str | None = None,
    api_number: str | None = None,
    state: str | None = None,
    county: str | None = None,
    operator: str | None = None,
    lease_name: str | None = None,
    well_status: str | None = None,
    well_type: str | None = None,
    sort_by: str = "api_number",
    sort_dir: str = "asc",
):
    """Build a wells query with filters, search, and sorting.

    Returns a select() statement that yields rows with:
    (Well columns..., operator_name, document_count)
    """
    # Subquery for document count per well
    doc_count_subq = (
        select(
            Document.well_id,
            func.count(Document.id).label("document_count"),
        )
        .group_by(Document.well_id)
        .subquery()
    )

    query = (
        select(
            Well.id,
            Well.api_number,
            Well.well_name,
            Operator.name.label("operator_name"),
            Well.state_code,
            Well.county,
            Well.well_status,
            Well.well_type,
            Well.latitude,
            Well.longitude,
            func.coalesce(doc_count_subq.c.document_count, 0).label("document_count"),
        )
        .outerjoin(Operator, Well.operator_id == Operator.id)
        .outerjoin(doc_count_subq, Well.id == doc_count_subq.c.well_id)
    )

    # Full-text search
    if q:
        ts_query = func.plainto_tsquery("english", q)
        query = query.where(Well.search_vector.op("@@")(ts_query))
        # Order by relevance when searching
        query = query.order_by(func.ts_rank(Well.search_vector, ts_query).desc())

    # API number filter: exact or prefix match
    if api_number:
        import re

        normalized = re.sub(r"[^0-9]", "", api_number)
        if len(normalized) >= 10:
            query = query.where(
                or_(
                    Well.api_number == normalized,
                    Well.api_10 == normalized[:10],
                )
            )
        else:
            query = query.where(Well.api_number.startswith(normalized))

    # Simple filters
    if state:
        query = query.where(Well.state_code == state.upper())
    if county:
        query = query.where(Well.county.ilike(f"%{county}%"))
    if operator:
        query = query.where(Operator.name.ilike(f"%{operator}%"))
    if lease_name:
        query = query.where(Well.lease_name.ilike(f"%{lease_name}%"))
    if well_status:
        query = query.where(Well.well_status == well_status)
    if well_type:
        query = query.where(Well.well_type == well_type)

    # Sorting (only if not using full-text relevance sorting)
    if not q:
        # Map sort_by to actual column
        sort_columns = {
            "api_number": Well.api_number,
            "well_name": Well.well_name,
            "state_code": Well.state_code,
            "county": Well.county,
            "well_status": Well.well_status,
            "well_type": Well.well_type,
        }
        sort_column = sort_columns.get(sort_by, Well.api_number)
        order_func = desc if sort_dir == "desc" else asc
        query = query.order_by(order_func(sort_column))

    return query


def build_documents_query(
    q: str | None = None,
    well_id: str | None = None,
    state: str | None = None,
    doc_type: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    min_confidence: float | None = None,
    status: str | None = None,
    sort_by: str = "scraped_at",
    sort_dir: str = "desc",
):
    """Build a documents query with filters, search, and sorting.

    Returns a select() statement that yields DocumentSummary-compatible rows.
    """
    query = select(
        Document.id,
        Document.well_id,
        Document.state_code,
        Document.doc_type,
        Document.document_date,
        Document.confidence_score,
        Document.file_format,
        Document.source_url,
        Document.scraped_at,
    )

    # Full-text search
    if q:
        ts_query = func.plainto_tsquery("english", q)
        query = query.where(Document.search_vector.op("@@")(ts_query))
        query = query.order_by(func.ts_rank(Document.search_vector, ts_query).desc())

    # Filters
    if well_id:
        query = query.where(Document.well_id == well_id)
    if state:
        query = query.where(Document.state_code == state.upper())
    if doc_type:
        query = query.where(Document.doc_type == doc_type)
    if date_from:
        query = query.where(Document.document_date >= date_from)
    if date_to:
        query = query.where(Document.document_date <= date_to)
    if min_confidence is not None:
        query = query.where(Document.confidence_score >= min_confidence)
    if status:
        query = query.where(Document.status == status)

    # Sorting (only if not using full-text relevance sorting)
    if not q:
        sort_columns = {
            "scraped_at": Document.scraped_at,
            "document_date": Document.document_date,
            "doc_type": Document.doc_type,
            "confidence_score": Document.confidence_score,
            "state_code": Document.state_code,
        }
        sort_column = sort_columns.get(sort_by, Document.scraped_at)
        order_func = desc if sort_dir == "desc" else asc
        query = query.order_by(order_func(sort_column))

    return query
