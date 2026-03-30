"""Pydantic schemas for well API endpoints."""

import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict

from .document import DocumentSummary
from .enums import WellStatus


class WellSummary(BaseModel):
    """Well summary for list views."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    api_number: str
    well_name: str | None = None
    operator_name: str | None = None
    state_code: str
    county: str | None = None
    well_status: WellStatus | None = None
    well_type: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    document_count: int = 0


class WellDetail(BaseModel):
    """Full well detail with nested documents."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    api_number: str
    api_10: str | None = None
    well_name: str | None = None
    well_number: str | None = None
    operator_id: uuid.UUID | None = None
    operator_name: str | None = None
    state_code: str
    county: str | None = None
    basin: str | None = None
    field_name: str | None = None
    lease_name: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    well_status: WellStatus | None = None
    well_type: str | None = None
    spud_date: date | None = None
    completion_date: date | None = None
    total_depth: int | None = None
    true_vertical_depth: int | None = None
    lateral_length: int | None = None
    metadata: dict = {}
    alternate_ids: dict = {}
    documents: list[DocumentSummary] = []
    created_at: datetime | None = None
    updated_at: datetime | None = None
