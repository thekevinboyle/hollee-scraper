"""Pydantic schemas for scrape job endpoints."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from .enums import ScrapeJobStatus


class ScrapeJobCreate(BaseModel):
    """Request body for POST /api/v1/scrape."""

    state_code: str | None = Field(
        None,
        description="2-letter state code (e.g., TX). None = all states.",
        min_length=2,
        max_length=2,
    )
    job_type: str = Field(
        default="full",
        description="Job type: 'full', 'incremental', or 'targeted'",
    )
    parameters: dict = Field(
        default_factory=dict,
        description="Optional parameters: date_range, doc_types, operator, etc.",
    )


class ScrapeJobSummary(BaseModel):
    """Summary representation for list endpoints."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    state_code: str | None = None
    status: ScrapeJobStatus
    job_type: str
    documents_found: int = 0
    documents_downloaded: int = 0
    documents_processed: int = 0
    documents_failed: int = 0
    started_at: datetime | None = None
    finished_at: datetime | None = None
    created_at: datetime


class ScrapeJobDetail(ScrapeJobSummary):
    """Detailed representation with parameters and errors."""

    parameters: dict = Field(default_factory=dict)
    errors: list[dict] = Field(default_factory=list)
    total_documents: int = 0


class ScrapeProgressEvent(BaseModel):
    """Shape of each SSE progress event data payload."""

    status: str
    documents_found: int = 0
    documents_downloaded: int = 0
    documents_processed: int = 0
    documents_failed: int = 0
    current_stage: str | None = None
    message: str | None = None
