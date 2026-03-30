"""Review Queue API endpoints.

GET  /api/v1/review        -- List review queue items sorted by confidence
GET  /api/v1/review/{id}   -- Review item detail with document + extracted data + file_url
PATCH /api/v1/review/{id}  -- Approve / correct / reject with action in body
"""

import json
import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import asc, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from og_scraper.api.deps import get_db
from og_scraper.api.schemas.enums import DocType, ReviewStatus, SortDirection
from og_scraper.api.schemas.pagination import PaginatedResponse
from og_scraper.api.schemas.review import ReviewAction, ReviewItemDetail, ReviewQueueItem
from og_scraper.api.utils.pagination import paginate
from og_scraper.models.data_correction import DataCorrection
from og_scraper.models.document import Document
from og_scraper.models.extracted_data import ExtractedData
from og_scraper.models.operator import Operator
from og_scraper.models.review_queue import ReviewQueue
from og_scraper.models.well import Well

router = APIRouter()

DbSession = Annotated[AsyncSession, Depends(get_db)]


@router.get("/", response_model=PaginatedResponse[ReviewQueueItem])
async def list_review_items(
    db: DbSession,
    status: ReviewStatus = ReviewStatus.PENDING,
    state: str | None = None,
    doc_type: DocType | None = None,
    min_confidence: float | None = None,
    max_confidence: float | None = None,
    sort_by: str = "document_confidence",
    sort_dir: SortDirection = SortDirection.DESC,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
):
    """List review queue items with filtering, sorting, and pagination.

    Default: pending items sorted by confidence descending (highest first = easiest to review).
    """
    query = (
        select(
            ReviewQueue.id,
            ReviewQueue.document_id,
            ReviewQueue.extracted_data_id,
            ReviewQueue.status,
            ReviewQueue.reason,
            ReviewQueue.document_confidence,
            ReviewQueue.created_at,
            Document.state_code.label("state_code"),
            Document.doc_type.label("doc_type"),
            Well.api_number.label("well_api_number"),
            Well.well_name.label("well_name"),
            Operator.name.label("operator_name"),
        )
        .join(Document, ReviewQueue.document_id == Document.id)
        .outerjoin(Well, Document.well_id == Well.id)
        .outerjoin(Operator, Well.operator_id == Operator.id)
    )

    # Filters
    query = query.where(ReviewQueue.status == status.value)
    if state:
        query = query.where(Document.state_code == state.upper())
    if doc_type:
        query = query.where(Document.doc_type == doc_type.value)
    if min_confidence is not None:
        query = query.where(ReviewQueue.document_confidence >= min_confidence)
    if max_confidence is not None:
        query = query.where(ReviewQueue.document_confidence <= max_confidence)

    # Sort -- default: highest confidence first (easiest to review)
    sort_col = ReviewQueue.created_at if sort_by == "created_at" else ReviewQueue.document_confidence

    order = desc(sort_col) if sort_dir == SortDirection.DESC else asc(sort_col)
    query = query.order_by(order)

    result = await paginate(db, query, page, page_size)

    # Convert Row objects to ReviewQueueItem dicts
    result["items"] = [
        ReviewQueueItem(
            id=row.id,
            document_id=row.document_id,
            extracted_data_id=row.extracted_data_id,
            status=row.status,
            reason=row.reason,
            document_confidence=float(row.document_confidence) if row.document_confidence is not None else None,
            well_api_number=row.well_api_number,
            state_code=row.state_code,
            doc_type=row.doc_type,
            well_name=row.well_name,
            operator_name=row.operator_name,
            created_at=row.created_at,
        )
        for row in result["items"]
    ]

    return result


@router.get("/{review_id}", response_model=ReviewItemDetail)
async def get_review_item(
    review_id: uuid.UUID,
    db: DbSession,
):
    """Get full detail for a review queue item.

    Includes the review record, nested document, extracted data, and a computed file_url.
    """
    query = select(ReviewQueue).where(ReviewQueue.id == review_id)
    result = await db.execute(query)
    review = result.scalar_one_or_none()
    if not review:
        raise HTTPException(status_code=404, detail="Review item not found")

    # Load document
    doc_query = select(Document).where(Document.id == review.document_id)
    doc_result = await db.execute(doc_query)
    document = doc_result.scalar_one_or_none()

    # Load well info for joined fields
    well = None
    operator_name = None
    if document and document.well_id:
        well_query = select(Well).where(Well.id == document.well_id)
        well_result = await db.execute(well_query)
        well = well_result.scalar_one_or_none()
        if well and well.operator_id:
            op_query = select(Operator).where(Operator.id == well.operator_id)
            op_result = await db.execute(op_query)
            op = op_result.scalar_one_or_none()
            if op:
                operator_name = op.name

    # Load extracted data if present
    extracted = None
    if review.extracted_data_id:
        ed_query = select(ExtractedData).where(ExtractedData.id == review.extracted_data_id)
        ed_result = await db.execute(ed_query)
        extracted = ed_result.scalar_one_or_none()

    # Build file URL
    file_url = f"/api/v1/documents/{review.document_id}/file" if document and document.file_path else None

    return ReviewItemDetail(
        id=review.id,
        document_id=review.document_id,
        extracted_data_id=review.extracted_data_id,
        status=review.status,
        reason=review.reason,
        document_confidence=float(review.document_confidence) if review.document_confidence is not None else None,
        flag_details=review.flag_details or {},
        field_confidences=review.field_confidences or {},
        corrections=review.corrections or {},
        notes=review.notes,
        reviewed_by=review.reviewed_by,
        reviewed_at=review.reviewed_at,
        created_at=review.created_at,
        # Joined fields
        state_code=document.state_code if document else None,
        doc_type=document.doc_type if document else None,
        well_api_number=well.api_number if well else None,
        well_name=well.well_name if well else None,
        operator_name=operator_name,
        # Nested objects
        document=document,
        extracted_data=extracted,
        file_url=file_url,
    )


@router.patch("/{review_id}", response_model=ReviewItemDetail)
async def update_review_item(
    review_id: uuid.UUID,
    action: ReviewAction,
    db: DbSession,
):
    """Take action on a review queue item: approve, correct, or reject.

    - Approve: marks document as accepted, updates document status to 'stored'.
    - Correct: updates extracted_data fields, logs corrections in data_corrections audit trail.
    - Reject: marks document as rejected, updates document status to 'extraction_failed'.

    Returns 400 if the item has already been resolved (not pending).
    """
    query = select(ReviewQueue).where(ReviewQueue.id == review_id)
    result = await db.execute(query)
    review = result.scalar_one_or_none()
    if not review:
        raise HTTPException(status_code=404, detail="Review item not found")
    if review.status != "pending":
        raise HTTPException(
            status_code=400,
            detail=f"Review item already resolved with status: {review.status}",
        )

    now = datetime.now(UTC)

    # Update review record
    review.status = action.status.value
    review.reviewed_by = action.reviewed_by
    review.reviewed_at = now
    review.notes = action.notes

    if action.status == ReviewStatus.CORRECTED:
        if not action.corrections:
            raise HTTPException(
                status_code=400,
                detail="Corrections are required when status is 'corrected'",
            )

        # Load extracted data
        if not review.extracted_data_id:
            raise HTTPException(status_code=400, detail="No extracted data to correct")

        ed_query = select(ExtractedData).where(ExtractedData.id == review.extracted_data_id)
        ed_result = await db.execute(ed_query)
        extracted = ed_result.scalar_one_or_none()
        if not extracted:
            raise HTTPException(status_code=404, detail="Extracted data not found")

        # Apply each correction
        updated_data = dict(extracted.data)  # Copy JSONB dict
        for field_path, correction in action.corrections.items():
            old_value = updated_data.get(field_path)
            new_value = correction.get("new") if isinstance(correction, dict) else correction

            # Update the extracted data
            updated_data[field_path] = new_value

            # Create audit trail record
            data_correction = DataCorrection(
                extracted_data_id=extracted.id,
                review_queue_id=review.id,
                field_path=field_path,
                old_value=json.loads(json.dumps(old_value)) if old_value is not None else None,
                new_value=json.loads(json.dumps(new_value)),
                corrected_by=action.reviewed_by,
                corrected_at=now,
            )
            db.add(data_correction)

        # Save updated data back to extracted_data
        extracted.data = updated_data
        review.corrections = action.corrections

    # Update document status
    doc_query = select(Document).where(Document.id == review.document_id)
    doc_result = await db.execute(doc_query)
    document = doc_result.scalar_one_or_none()
    if document:
        if action.status in (ReviewStatus.APPROVED, ReviewStatus.CORRECTED):
            document.status = "stored"
        elif action.status == ReviewStatus.REJECTED:
            document.status = "extraction_failed"

    # Flush changes (the auto-commit in get_db will finalize)
    await db.flush()

    # Re-read review for response building (re-fetch to get joined data)
    # Load well info
    well = None
    operator_name = None
    if document and document.well_id:
        well_query = select(Well).where(Well.id == document.well_id)
        well_result = await db.execute(well_query)
        well = well_result.scalar_one_or_none()
        if well and well.operator_id:
            op_query = select(Operator).where(Operator.id == well.operator_id)
            op_result = await db.execute(op_query)
            op = op_result.scalar_one_or_none()
            if op:
                operator_name = op.name

    # Load extracted data for response
    extracted_for_response = None
    if review.extracted_data_id:
        ed_query2 = select(ExtractedData).where(ExtractedData.id == review.extracted_data_id)
        ed_result2 = await db.execute(ed_query2)
        extracted_for_response = ed_result2.scalar_one_or_none()

    file_url = f"/api/v1/documents/{review.document_id}/file" if document and document.file_path else None

    return ReviewItemDetail(
        id=review.id,
        document_id=review.document_id,
        extracted_data_id=review.extracted_data_id,
        status=review.status,
        reason=review.reason,
        document_confidence=float(review.document_confidence) if review.document_confidence is not None else None,
        flag_details=review.flag_details or {},
        field_confidences=review.field_confidences or {},
        corrections=review.corrections or {},
        notes=review.notes,
        reviewed_by=review.reviewed_by,
        reviewed_at=review.reviewed_at,
        created_at=review.created_at,
        state_code=document.state_code if document else None,
        doc_type=document.doc_type if document else None,
        well_api_number=well.api_number if well else None,
        well_name=well.well_name if well else None,
        operator_name=operator_name,
        document=document,
        extracted_data=extracted_for_response,
        file_url=file_url,
    )


@router.get("/stats", response_model=dict)
async def get_review_stats(
    db: DbSession,
):
    """Get summary statistics for the review queue."""
    stats_query = select(
        func.count().filter(ReviewQueue.status == "pending").label("pending_count"),
        func.count().filter(ReviewQueue.status == "approved").label("approved_count"),
        func.count().filter(ReviewQueue.status == "rejected").label("rejected_count"),
        func.count().filter(ReviewQueue.status == "corrected").label("corrected_count"),
        func.avg(ReviewQueue.document_confidence).filter(ReviewQueue.status == "pending").label("avg_confidence"),
    )
    result = await db.execute(stats_query)
    row = result.one()

    return {
        "pending_count": row.pending_count or 0,
        "approved_count": row.approved_count or 0,
        "rejected_count": row.rejected_count or 0,
        "corrected_count": row.corrected_count or 0,
        "avg_confidence": float(row.avg_confidence) if row.avg_confidence is not None else None,
    }
