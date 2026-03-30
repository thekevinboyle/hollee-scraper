"""DataCorrection model -- audit trail for manual corrections."""

import uuid
from datetime import datetime

from sqlalchemy import TIMESTAMP, VARCHAR, ForeignKey, Index
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, UUIDPrimaryKeyMixin


class DataCorrection(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "data_corrections"

    extracted_data_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("extracted_data.id", ondelete="CASCADE"), nullable=False
    )
    review_queue_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("review_queue.id", ondelete="SET NULL"), nullable=True
    )
    field_path: Mapped[str] = mapped_column(VARCHAR(255), nullable=False)
    old_value: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    new_value: Mapped[dict] = mapped_column(JSONB, nullable=False)
    corrected_by: Mapped[str | None] = mapped_column(VARCHAR(100), nullable=True)
    corrected_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default="now()", nullable=False)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default="now()", nullable=False)

    # Relationships
    extracted_data = relationship("ExtractedData", back_populates="corrections")

    __table_args__ = (
        Index("idx_corrections_extracted_data", "extracted_data_id"),
        Index("idx_corrections_review_queue", "review_queue_id"),
    )
