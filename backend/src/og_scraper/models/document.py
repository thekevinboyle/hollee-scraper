"""Document model -- every scraped document with provenance tracking."""

import uuid
from datetime import date, datetime

from sqlalchemy import text, BIGINT, DATE, NUMERIC, TEXT, TIMESTAMP, VARCHAR, ForeignKey, Index
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from .enums import DocType, DocumentStatus


class Document(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "documents"

    well_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("wells.id", ondelete="SET NULL"), nullable=True
    )
    state_code: Mapped[str] = mapped_column(VARCHAR(2), ForeignKey("states.code"), nullable=False)
    scrape_job_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("scrape_jobs.id", ondelete="SET NULL"), nullable=True
    )
    doc_type: Mapped[DocType] = mapped_column(default=DocType.OTHER, server_default="other")
    status: Mapped[DocumentStatus] = mapped_column(default=DocumentStatus.DISCOVERED, server_default="discovered")
    # Provenance
    source_url: Mapped[str] = mapped_column(TEXT, nullable=False)
    file_path: Mapped[str | None] = mapped_column(TEXT, nullable=True)
    file_hash: Mapped[str | None] = mapped_column(VARCHAR(64), unique=True, nullable=True)
    file_format: Mapped[str | None] = mapped_column(VARCHAR(20), nullable=True)
    file_size_bytes: Mapped[int | None] = mapped_column(BIGINT, nullable=True)
    # Confidence
    confidence_score: Mapped[float | None] = mapped_column(NUMERIC(5, 4), nullable=True)
    ocr_confidence: Mapped[float | None] = mapped_column(NUMERIC(5, 4), nullable=True)
    # Classification
    classification_method: Mapped[str | None] = mapped_column(VARCHAR(50), nullable=True)
    # Dates
    document_date: Mapped[date | None] = mapped_column(DATE, nullable=True)
    scraped_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default="now()", nullable=False)
    processed_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    # Flexible metadata
    raw_metadata: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    # Search
    search_vector: Mapped[str | None] = mapped_column(TSVECTOR, nullable=True)

    # Relationships
    well = relationship("Well", back_populates="documents", lazy="selectin")
    extracted_data = relationship(
        "ExtractedData", back_populates="document", lazy="selectin", cascade="all, delete-orphan"
    )
    review_items = relationship(
        "ReviewQueue", back_populates="document", lazy="selectin", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("idx_documents_state_type", "state_code", "doc_type"),
        Index("idx_documents_well", "well_id"),
        Index("idx_documents_scrape_job", "scrape_job_id"),
        Index("idx_documents_date", "document_date"),
        Index("idx_documents_status", "status"),
        Index("idx_documents_source_url", "source_url", postgresql_using="hash"),
        Index("idx_documents_search", "search_vector", postgresql_using="gin"),
        Index("idx_documents_metadata_gin", "raw_metadata", postgresql_using="gin"),
    )
