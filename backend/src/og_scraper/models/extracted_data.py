"""ExtractedData model -- structured data from documents with per-field confidence."""

import uuid
from datetime import date, datetime

from sqlalchemy import text, DATE, NUMERIC, TIMESTAMP, VARCHAR, ForeignKey, Index
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class ExtractedData(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "extracted_data"

    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )
    well_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("wells.id", ondelete="SET NULL"), nullable=True
    )
    data_type: Mapped[str] = mapped_column(VARCHAR(50), nullable=False)
    data: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    field_confidence: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    confidence_score: Mapped[float | None] = mapped_column(NUMERIC(5, 4), nullable=True)
    extractor_used: Mapped[str | None] = mapped_column(VARCHAR(100), nullable=True)
    extraction_version: Mapped[str | None] = mapped_column(VARCHAR(20), nullable=True)
    reporting_period_start: Mapped[date | None] = mapped_column(DATE, nullable=True)
    reporting_period_end: Mapped[date | None] = mapped_column(DATE, nullable=True)
    extracted_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default="now()", nullable=False)

    # Relationships
    document = relationship("Document", back_populates="extracted_data")
    corrections = relationship(
        "DataCorrection", back_populates="extracted_data", lazy="selectin", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("idx_extracted_document", "document_id"),
        Index("idx_extracted_well", "well_id"),
        Index("idx_extracted_data_type", "data_type"),
        Index("idx_extracted_period", "reporting_period_start", "reporting_period_end"),
        Index("idx_extracted_data_gin", "data", postgresql_using="gin"),
        Index("idx_extracted_confidence_gin", "field_confidence", postgresql_using="gin"),
    )
