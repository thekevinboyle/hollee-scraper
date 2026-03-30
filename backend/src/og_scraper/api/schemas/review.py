"""Pydantic schemas for review queue API endpoints."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from .document import DocumentDetail, ExtractedDataSummary
from .enums import DocType, ReviewStatus


class ReviewQueueItem(BaseModel):
    """List view of a review queue item."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    document_id: uuid.UUID
    extracted_data_id: uuid.UUID | None = None
    status: ReviewStatus
    reason: str
    document_confidence: float | None = None
    # Joined fields for display
    well_api_number: str | None = None
    state_code: str | None = None
    doc_type: DocType | None = None
    well_name: str | None = None
    operator_name: str | None = None
    created_at: datetime


class ReviewItemDetail(ReviewQueueItem):
    """Full detail view including document, extracted data, and file URL."""

    flag_details: dict = {}
    field_confidences: dict = {}
    corrections: dict = {}
    notes: str | None = None
    reviewed_by: str | None = None
    reviewed_at: datetime | None = None
    # Nested objects
    document: DocumentDetail | None = None
    extracted_data: ExtractedDataSummary | None = None
    # Computed field for frontend to display original file
    file_url: str | None = None


class ReviewAction(BaseModel):
    """Request body for PATCH /review/{id}."""

    status: ReviewStatus = Field(
        ...,
        description="New status: 'approved', 'rejected', or 'corrected'",
    )
    corrections: dict | None = Field(
        None,
        description='Field corrections: {"field_name": {"old": "...", "new": "..."}}',
    )
    notes: str | None = Field(
        None,
        description="Optional reviewer notes",
    )
    reviewed_by: str | None = Field(
        None,
        description="Name of the reviewer (no auth, just a freeform name)",
    )


class ReviewStats(BaseModel):
    """Summary stats for the review queue."""

    pending_count: int
    approved_count: int
    rejected_count: int
    corrected_count: int
    avg_confidence: float | None = None
