"""ScrapeJob model -- on-demand scrape job tracking."""

from datetime import datetime

from sqlalchemy import text, INTEGER, TIMESTAMP, VARCHAR, ForeignKey, Index
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from .enums import ScrapeJobStatus, ScrapeJobStatusPG


class ScrapeJob(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "scrape_jobs"

    state_code: Mapped[str | None] = mapped_column(VARCHAR(2), ForeignKey("states.code"), nullable=True)
    status: Mapped[ScrapeJobStatus] = mapped_column(ScrapeJobStatusPG, default=ScrapeJobStatus.PENDING, server_default="pending")
    job_type: Mapped[str] = mapped_column(VARCHAR(50), nullable=False, default="full", server_default="full")
    parameters: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    # Progress
    total_documents: Mapped[int] = mapped_column(INTEGER, default=0, server_default="0")
    documents_found: Mapped[int] = mapped_column(INTEGER, default=0, server_default="0")
    documents_downloaded: Mapped[int] = mapped_column(INTEGER, default=0, server_default="0")
    documents_processed: Mapped[int] = mapped_column(INTEGER, default=0, server_default="0")
    documents_failed: Mapped[int] = mapped_column(INTEGER, default=0, server_default="0")
    # Timing
    started_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    # Errors
    errors: Mapped[list] = mapped_column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))

    __table_args__ = (
        Index("idx_scrape_jobs_status", "status"),
        Index("idx_scrape_jobs_state", "state_code"),
    )
