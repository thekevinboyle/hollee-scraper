"""ReviewQueue model -- items flagged for human review."""

import uuid
from datetime import datetime

from sqlalchemy import text, NUMERIC, TEXT, TIMESTAMP, VARCHAR, ForeignKey, Index
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from .enums import ReviewStatus, ReviewStatusPG


class ReviewQueue(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "review_queue"

    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )
    extracted_data_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("extracted_data.id", ondelete="CASCADE"), nullable=True
    )
    status: Mapped[ReviewStatus] = mapped_column(ReviewStatusPG, default=ReviewStatus.PENDING, server_default="pending")
    reason: Mapped[str] = mapped_column(TEXT, nullable=False)
    flag_details: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    document_confidence: Mapped[float | None] = mapped_column(NUMERIC(5, 4), nullable=True)
    field_confidences: Mapped[dict | None] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    reviewed_by: Mapped[str | None] = mapped_column(VARCHAR(100), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    corrections: Mapped[dict | None] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    notes: Mapped[str | None] = mapped_column(TEXT, nullable=True)

    # Relationships
    document = relationship("Document", back_populates="review_items")

    __table_args__ = (
        Index("idx_review_status", "status"),
        Index("idx_review_document", "document_id"),
    )
