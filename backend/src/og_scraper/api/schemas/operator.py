"""Pydantic schemas for operator API endpoints."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class OperatorSummary(BaseModel):
    """Operator summary for list views."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    normalized_name: str
    well_count: int = 0
    state_codes: list[str] = []


class OperatorDetail(BaseModel):
    """Full operator detail."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    normalized_name: str
    aliases: list = []
    state_operator_ids: dict = {}
    metadata: dict = {}
    well_count: int = 0
    state_codes: list[str] = []
    created_at: datetime | None = None
    updated_at: datetime | None = None
