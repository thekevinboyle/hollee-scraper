"""Well model -- one row per physical well with PostGIS location."""

import uuid
from datetime import date

from geoalchemy2 import Geometry
from sqlalchemy import text, DATE, DOUBLE_PRECISION, INTEGER, VARCHAR, Computed, ForeignKey, Index, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from .enums import WellStatus


class Well(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "wells"

    api_number: Mapped[str] = mapped_column(VARCHAR(14), nullable=False)
    api_10: Mapped[str] = mapped_column(VARCHAR(10), Computed("LEFT(api_number, 10)"), nullable=True)
    well_name: Mapped[str | None] = mapped_column(VARCHAR(500), nullable=True)
    well_number: Mapped[str | None] = mapped_column(VARCHAR(100), nullable=True)
    operator_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("operators.id", ondelete="SET NULL"), nullable=True
    )
    state_code: Mapped[str] = mapped_column(VARCHAR(2), ForeignKey("states.code"), nullable=False)
    county: Mapped[str | None] = mapped_column(VARCHAR(255), nullable=True)
    basin: Mapped[str | None] = mapped_column(VARCHAR(255), nullable=True)
    field_name: Mapped[str | None] = mapped_column(VARCHAR(255), nullable=True)
    lease_name: Mapped[str | None] = mapped_column(VARCHAR(500), nullable=True)
    # Location
    latitude: Mapped[float | None] = mapped_column(DOUBLE_PRECISION, nullable=True)
    longitude: Mapped[float | None] = mapped_column(DOUBLE_PRECISION, nullable=True)
    location: Mapped[str | None] = mapped_column(Geometry("POINT", srid=4326), nullable=True)
    # Well details
    well_status: Mapped[WellStatus] = mapped_column(default=WellStatus.UNKNOWN, server_default="unknown")
    well_type: Mapped[str | None] = mapped_column(VARCHAR(50), nullable=True)
    spud_date: Mapped[date | None] = mapped_column(DATE, nullable=True)
    completion_date: Mapped[date | None] = mapped_column(DATE, nullable=True)
    total_depth: Mapped[int | None] = mapped_column(INTEGER, nullable=True)
    true_vertical_depth: Mapped[int | None] = mapped_column(INTEGER, nullable=True)
    lateral_length: Mapped[int | None] = mapped_column(INTEGER, nullable=True)
    # Flexible data
    metadata_: Mapped[dict] = mapped_column("metadata", JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    alternate_ids: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    # Search
    search_vector: Mapped[str | None] = mapped_column(TSVECTOR, nullable=True)

    # Relationships
    operator = relationship("Operator", back_populates="wells", lazy="selectin")
    documents = relationship("Document", back_populates="well", lazy="selectin")

    __table_args__ = (
        UniqueConstraint("api_number", "state_code", name="uq_wells_api_state"),
        Index("idx_wells_api_number", "api_number"),
        Index("idx_wells_api_10", "api_10"),
        Index(
            "idx_wells_api_trgm", "api_number", postgresql_using="gin", postgresql_ops={"api_number": "gin_trgm_ops"}
        ),
        Index("idx_wells_operator", "operator_id"),
        Index("idx_wells_state_county", "state_code", "county"),
        Index("idx_wells_status", "well_status"),
        Index(
            "idx_wells_lease_trgm", "lease_name", postgresql_using="gin", postgresql_ops={"lease_name": "gin_trgm_ops"}
        ),
        Index("idx_wells_location_gist", "location", postgresql_using="gist"),
        Index("idx_wells_search", "search_vector", postgresql_using="gin"),
        Index("idx_wells_metadata_gin", "metadata", postgresql_using="gin"),
        Index("idx_wells_alt_ids_gin", "alternate_ids", postgresql_using="gin"),
    )
