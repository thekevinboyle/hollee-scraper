"""Operator model -- normalized oil & gas operator entities."""

from sqlalchemy import text, VARCHAR, Index
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Operator(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "operators"

    name: Mapped[str] = mapped_column(VARCHAR(500), nullable=False)
    normalized_name: Mapped[str] = mapped_column(VARCHAR(500), nullable=False)
    aliases: Mapped[list] = mapped_column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    state_operator_ids: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    metadata_: Mapped[dict] = mapped_column("metadata", JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    search_vector: Mapped[str | None] = mapped_column(TSVECTOR, nullable=True)

    # Relationships
    wells = relationship("Well", back_populates="operator", lazy="selectin")

    __table_args__ = (
        Index("idx_operators_normalized_name", "normalized_name"),
        Index("idx_operators_name_trgm", "name", postgresql_using="gin", postgresql_ops={"name": "gin_trgm_ops"}),
        Index("idx_operators_search", "search_vector", postgresql_using="gin"),
    )
