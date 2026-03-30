"""State model -- 10 supported US states."""

from datetime import datetime

from sqlalchemy import SMALLINT, TIMESTAMP, VARCHAR, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin


class State(Base, TimestampMixin):
    __tablename__ = "states"

    code: Mapped[str] = mapped_column(VARCHAR(2), primary_key=True)
    name: Mapped[str] = mapped_column(VARCHAR(100), nullable=False)
    api_state_code: Mapped[str] = mapped_column(VARCHAR(2), unique=True, nullable=False)
    tier: Mapped[int] = mapped_column(SMALLINT, nullable=False, default=1)
    last_scraped_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    config: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
