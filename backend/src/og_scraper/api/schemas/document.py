"""Pydantic schemas for document API endpoints."""

import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict

from .enums import DocType, DocumentStatus


class ExtractedDataSummary(BaseModel):
    """Extracted data summary for document detail views."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    document_id: uuid.UUID
    data_type: str
    data: dict = {}
    field_confidence: dict = {}
    confidence_score: float | None = None
    extractor_used: str | None = None
    reporting_period_start: date | None = None
    reporting_period_end: date | None = None
    extracted_at: datetime | None = None


class DocumentSummary(BaseModel):
    """Document summary for list views."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    well_id: uuid.UUID | None = None
    state_code: str
    doc_type: DocType | None = None
    document_date: date | None = None
    confidence_score: float | None = None
    file_format: str | None = None
    source_url: str
    scraped_at: datetime | None = None


class DocumentDetail(BaseModel):
    """Full document detail with extracted data."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    well_id: uuid.UUID | None = None
    well_api_number: str | None = None
    state_code: str
    doc_type: DocType | None = None
    status: DocumentStatus | None = None
    source_url: str
    file_path: str | None = None
    file_format: str | None = None
    file_size_bytes: int | None = None
    file_hash: str | None = None
    confidence_score: float | None = None
    ocr_confidence: float | None = None
    classification_method: str | None = None
    document_date: date | None = None
    scraped_at: datetime | None = None
    processed_at: datetime | None = None
    raw_metadata: dict = {}
    extracted_data: list[ExtractedDataSummary] = []
    created_at: datetime | None = None
    updated_at: datetime | None = None
