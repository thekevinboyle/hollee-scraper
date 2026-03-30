"""Pydantic schemas for state API endpoints."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class StateSummary(BaseModel):
    """State summary with computed counts."""

    model_config = ConfigDict(from_attributes=True)

    code: str
    name: str
    api_state_code: str
    tier: int
    last_scraped_at: datetime | None = None
    well_count: int = 0
    document_count: int = 0
