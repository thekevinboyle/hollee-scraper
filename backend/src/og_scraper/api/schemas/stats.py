"""Dashboard and per-state statistics Pydantic schemas."""

from pydantic import BaseModel


class DashboardStats(BaseModel):
    """Aggregate statistics for the dashboard overview page."""

    total_wells: int
    total_documents: int
    total_extracted: int
    documents_by_state: dict[str, int]
    documents_by_type: dict[str, int]
    wells_by_status: dict[str, int]
    wells_by_state: dict[str, int]
    review_queue_pending: int
    avg_confidence: float | None = None
    recent_scrape_jobs: list[dict]


class StateStats(BaseModel):
    """Per-state statistics."""

    state_code: str
    state_name: str
    total_wells: int
    total_documents: int
    documents_by_type: dict[str, int]
    wells_by_status: dict[str, int]
    avg_confidence: float | None = None
    last_scraped_at: str | None = None
    review_queue_pending: int
