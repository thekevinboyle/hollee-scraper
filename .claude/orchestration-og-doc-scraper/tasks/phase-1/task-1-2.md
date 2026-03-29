# Task 1.2: Database Schema & Migrations

## Objective

Create all 8 database tables as SQLAlchemy 2.0 async ORM models, configure Alembic for async migrations, generate the initial migration that creates the complete schema (extensions, enums, tables, indexes, triggers), and seed the 10 supported states. This establishes the complete data layer that all API endpoints, scrapers, and pipeline stages depend on.

## Context

Task 1.1 created the project scaffolding, Docker Compose with PostgreSQL+PostGIS, and the Python package structure. This task fills in the `backend/src/og_scraper/models/` directory with all 8 SQLAlchemy models and configures Alembic to generate and run migrations. The database schema is one of the most critical pieces of the project -- it defines the data contracts for wells, documents, extracted data, review workflows, and scrape jobs that every subsequent task depends on.

Key constraints from DISCOVERY.md:
- PostgreSQL 16 + PostGIS 3.4 (D19)
- UUID primary keys for all tables (except states which uses VARCHAR(2))
- JSONB for flexible/state-specific data (D19)
- Three-level confidence scoring: OCR, field, document (D23)
- Full-text search via tsvector + pg_trgm (D24)
- PostGIS GEOMETRY(Point, 4326) for well locations (D13)
- Strict data quality -- confidence below threshold goes to review queue (D10)

## Dependencies

- Task 1.1 - Project structure, Docker Compose with PostgreSQL, Python package layout

## Blocked By

- Task 1.1

## Research Findings

Key findings from research files relevant to this task:

- From `backend-schema-implementation.md`: Complete SQL DDL for all 8 tables with exact column types, constraints, and defaults. Extensions: uuid-ossp, postgis, pg_trgm. Five enum types. Auto-sync trigger for PostGIS location. Full-text search triggers with weighted vectors.
- From `postgresql-postgis-schema` skill: Dual location storage pattern (lat/long + PostGIS geometry with auto-sync trigger). API number as VARCHAR(14) with generated api_10 column. NUMERIC(5,4) for confidence scores (range 0.0000-1.0000). Naming convention for constraints.
- From `architecture-storage.md`: JSONB hybrid pattern -- relational columns for queryable fields, JSONB for variable/state-specific data. Separate extracted_data table with JSONB data column accommodates all document types.

## Implementation Plan

### Step 1: Create SQLAlchemy Base and Mixins

Create `backend/src/og_scraper/models/base.py`:

```python
"""SQLAlchemy 2.0 async base, mixins, and engine configuration."""

import uuid
from datetime import datetime

from sqlalchemy import TIMESTAMP, MetaData, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.ext.asyncio import AsyncAttrs, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# Consistent naming convention for all constraints
naming_convention = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(AsyncAttrs, DeclarativeBase):
    metadata = MetaData(naming_convention=naming_convention)


class TimestampMixin:
    """Adds created_at and updated_at columns."""
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class UUIDPrimaryKeyMixin:
    """Adds a UUID primary key column."""
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=func.uuid_generate_v4(),
    )
```

### Step 2: Create Enum Definitions

Create `backend/src/og_scraper/models/enums.py`:

```python
"""PostgreSQL enum types for the Oil & Gas schema."""

import enum


class DocType(str, enum.Enum):
    WELL_PERMIT = "well_permit"
    COMPLETION_REPORT = "completion_report"
    PRODUCTION_REPORT = "production_report"
    SPACING_ORDER = "spacing_order"
    POOLING_ORDER = "pooling_order"
    PLUGGING_REPORT = "plugging_report"
    INSPECTION_RECORD = "inspection_record"
    INCIDENT_REPORT = "incident_report"
    UNKNOWN = "unknown"
    OTHER = "other"


class DocumentStatus(str, enum.Enum):
    DISCOVERED = "discovered"
    DOWNLOADING = "downloading"
    DOWNLOADED = "downloaded"
    CLASSIFYING = "classifying"
    CLASSIFIED = "classified"
    EXTRACTING = "extracting"
    EXTRACTED = "extracted"
    NORMALIZED = "normalized"
    STORED = "stored"
    FLAGGED_FOR_REVIEW = "flagged_for_review"
    DOWNLOAD_FAILED = "download_failed"
    CLASSIFICATION_FAILED = "classification_failed"
    EXTRACTION_FAILED = "extraction_failed"


class ScrapeJobStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ReviewStatus(str, enum.Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    CORRECTED = "corrected"


class WellStatus(str, enum.Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    PLUGGED = "plugged"
    PERMITTED = "permitted"
    DRILLING = "drilling"
    COMPLETED = "completed"
    SHUT_IN = "shut_in"
    TEMPORARILY_ABANDONED = "temporarily_abandoned"
    UNKNOWN = "unknown"
```

### Step 3: Create All 8 Model Files

Create each model file following SQLAlchemy 2.0 async patterns with `Mapped` type annotations.

**`backend/src/og_scraper/models/state.py`**:

```python
"""State model -- 10 supported US states."""

from datetime import datetime

from sqlalchemy import SMALLINT, VARCHAR, TIMESTAMP
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
    config: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
```

**`backend/src/og_scraper/models/operator.py`**:

```python
"""Operator model -- normalized oil & gas operator entities."""

from sqlalchemy import VARCHAR, Index
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Operator(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "operators"

    name: Mapped[str] = mapped_column(VARCHAR(500), nullable=False)
    normalized_name: Mapped[str] = mapped_column(VARCHAR(500), nullable=False)
    aliases: Mapped[list] = mapped_column(JSONB, nullable=False, server_default="'[]'::jsonb")
    state_operator_ids: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="'{}'::jsonb")
    metadata_: Mapped[dict] = mapped_column("metadata", JSONB, nullable=False, server_default="'{}'::jsonb")
    search_vector: Mapped[str | None] = mapped_column(TSVECTOR, nullable=True)

    # Relationships
    wells = relationship("Well", back_populates="operator", lazy="selectin")

    __table_args__ = (
        Index("idx_operators_normalized_name", "normalized_name"),
        Index("idx_operators_name_trgm", "name", postgresql_using="gin", postgresql_ops={"name": "gin_trgm_ops"}),
        Index("idx_operators_search", "search_vector", postgresql_using="gin"),
    )
```

**`backend/src/og_scraper/models/well.py`**:

```python
"""Well model -- one row per physical well with PostGIS location."""

import uuid
from datetime import date

from geoalchemy2 import Geometry
from sqlalchemy import VARCHAR, DATE, DOUBLE_PRECISION, INTEGER, Computed, ForeignKey, Index, UniqueConstraint
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
    metadata_: Mapped[dict] = mapped_column("metadata", JSONB, nullable=False, server_default="'{}'::jsonb")
    alternate_ids: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="'{}'::jsonb")
    # Search
    search_vector: Mapped[str | None] = mapped_column(TSVECTOR, nullable=True)

    # Relationships
    operator = relationship("Operator", back_populates="wells", lazy="selectin")
    documents = relationship("Document", back_populates="well", lazy="selectin")

    __table_args__ = (
        UniqueConstraint("api_number", "state_code", name="uq_wells_api_state"),
        Index("idx_wells_api_number", "api_number"),
        Index("idx_wells_api_10", "api_10"),
        Index("idx_wells_api_trgm", "api_number", postgresql_using="gin", postgresql_ops={"api_number": "gin_trgm_ops"}),
        Index("idx_wells_operator", "operator_id"),
        Index("idx_wells_state_county", "state_code", "county"),
        Index("idx_wells_status", "well_status"),
        Index("idx_wells_lease_trgm", "lease_name", postgresql_using="gin", postgresql_ops={"lease_name": "gin_trgm_ops"}),
        Index("idx_wells_location_gist", "location", postgresql_using="gist"),
        Index("idx_wells_search", "search_vector", postgresql_using="gin"),
        Index("idx_wells_metadata_gin", "metadata", postgresql_using="gin"),
        Index("idx_wells_alt_ids_gin", "alternate_ids", postgresql_using="gin"),
    )
```

**`backend/src/og_scraper/models/document.py`**:

```python
"""Document model -- every scraped document with provenance tracking."""

import uuid
from datetime import date, datetime

from sqlalchemy import BIGINT, DATE, NUMERIC, TEXT, TIMESTAMP, VARCHAR, ForeignKey, Index
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
    raw_metadata: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="'{}'::jsonb")
    # Search
    search_vector: Mapped[str | None] = mapped_column(TSVECTOR, nullable=True)

    # Relationships
    well = relationship("Well", back_populates="documents", lazy="selectin")
    extracted_data = relationship("ExtractedData", back_populates="document", lazy="selectin", cascade="all, delete-orphan")
    review_items = relationship("ReviewQueue", back_populates="document", lazy="selectin", cascade="all, delete-orphan")

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
```

**`backend/src/og_scraper/models/extracted_data.py`**:

```python
"""ExtractedData model -- structured data from documents with per-field confidence."""

import uuid
from datetime import date, datetime

from sqlalchemy import DATE, NUMERIC, TIMESTAMP, VARCHAR, ForeignKey, Index
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
    data: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="'{}'::jsonb")
    field_confidence: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="'{}'::jsonb")
    confidence_score: Mapped[float | None] = mapped_column(NUMERIC(5, 4), nullable=True)
    extractor_used: Mapped[str | None] = mapped_column(VARCHAR(100), nullable=True)
    extraction_version: Mapped[str | None] = mapped_column(VARCHAR(20), nullable=True)
    reporting_period_start: Mapped[date | None] = mapped_column(DATE, nullable=True)
    reporting_period_end: Mapped[date | None] = mapped_column(DATE, nullable=True)
    extracted_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default="now()", nullable=False)

    # Relationships
    document = relationship("Document", back_populates="extracted_data")
    corrections = relationship("DataCorrection", back_populates="extracted_data", lazy="selectin", cascade="all, delete-orphan")

    __table_args__ = (
        Index("idx_extracted_document", "document_id"),
        Index("idx_extracted_well", "well_id"),
        Index("idx_extracted_data_type", "data_type"),
        Index("idx_extracted_period", "reporting_period_start", "reporting_period_end"),
        Index("idx_extracted_data_gin", "data", postgresql_using="gin"),
        Index("idx_extracted_confidence_gin", "field_confidence", postgresql_using="gin"),
    )
```

**`backend/src/og_scraper/models/review_queue.py`**:

```python
"""ReviewQueue model -- items flagged for human review."""

import uuid
from datetime import datetime

from sqlalchemy import NUMERIC, TEXT, TIMESTAMP, VARCHAR, ForeignKey, Index
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from .enums import ReviewStatus


class ReviewQueue(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "review_queue"

    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )
    extracted_data_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("extracted_data.id", ondelete="CASCADE"), nullable=True
    )
    status: Mapped[ReviewStatus] = mapped_column(default=ReviewStatus.PENDING, server_default="pending")
    reason: Mapped[str] = mapped_column(TEXT, nullable=False)
    flag_details: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="'{}'::jsonb")
    document_confidence: Mapped[float | None] = mapped_column(NUMERIC(5, 4), nullable=True)
    field_confidences: Mapped[dict | None] = mapped_column(JSONB, server_default="'{}'::jsonb")
    reviewed_by: Mapped[str | None] = mapped_column(VARCHAR(100), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    corrections: Mapped[dict | None] = mapped_column(JSONB, server_default="'{}'::jsonb")
    notes: Mapped[str | None] = mapped_column(TEXT, nullable=True)

    # Relationships
    document = relationship("Document", back_populates="review_items")

    __table_args__ = (
        Index("idx_review_status", "status"),
        Index("idx_review_document", "document_id"),
    )
```

**`backend/src/og_scraper/models/scrape_job.py`**:

```python
"""ScrapeJob model -- on-demand scrape job tracking."""

from datetime import datetime

from sqlalchemy import INTEGER, TIMESTAMP, VARCHAR, ForeignKey, Index
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from .enums import ScrapeJobStatus


class ScrapeJob(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "scrape_jobs"

    state_code: Mapped[str | None] = mapped_column(VARCHAR(2), ForeignKey("states.code"), nullable=True)
    status: Mapped[ScrapeJobStatus] = mapped_column(default=ScrapeJobStatus.PENDING, server_default="pending")
    job_type: Mapped[str] = mapped_column(VARCHAR(50), nullable=False, default="full", server_default="full")
    parameters: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="'{}'::jsonb")
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
    errors: Mapped[list] = mapped_column(JSONB, nullable=False, server_default="'[]'::jsonb")

    __table_args__ = (
        Index("idx_scrape_jobs_status", "status"),
        Index("idx_scrape_jobs_state", "state_code"),
    )
```

**`backend/src/og_scraper/models/data_correction.py`**:

```python
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
```

### Step 4: Update Models __init__.py

Update `backend/src/og_scraper/models/__init__.py` to import all models so Alembic can discover them:

```python
"""SQLAlchemy ORM models for the Oil & Gas Document Scraper."""

from .base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from .enums import DocType, DocumentStatus, ReviewStatus, ScrapeJobStatus, WellStatus
from .state import State
from .operator import Operator
from .well import Well
from .document import Document
from .extracted_data import ExtractedData
from .review_queue import ReviewQueue
from .scrape_job import ScrapeJob
from .data_correction import DataCorrection

__all__ = [
    "Base",
    "TimestampMixin",
    "UUIDPrimaryKeyMixin",
    "DocType",
    "DocumentStatus",
    "ReviewStatus",
    "ScrapeJobStatus",
    "WellStatus",
    "State",
    "Operator",
    "Well",
    "Document",
    "ExtractedData",
    "ReviewQueue",
    "ScrapeJob",
    "DataCorrection",
]
```

### Step 5: Create Database Connection Module

Create `backend/src/og_scraper/database.py`:

```python
"""Async database engine and session factory."""

import os

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql+asyncpg://ogdocs:ogdocs_dev@localhost:5432/ogdocs",
)

engine = create_async_engine(
    DATABASE_URL,
    pool_size=20,
    max_overflow=10,
    pool_pre_ping=True,
    echo=os.environ.get("SQL_ECHO", "false").lower() == "true",
)

async_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_db():
    """FastAPI dependency that yields an async database session."""
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
```

### Step 6: Configure Alembic

Create `backend/alembic.ini`:

```ini
[alembic]
script_location = alembic
prepend_sys_path = .
sqlalchemy.url = postgresql+asyncpg://ogdocs:ogdocs_dev@localhost:5432/ogdocs

[loggers]
keys = root,sqlalchemy,alembic

[handlers]
keys = console

[formatters]
keys = generic

[logger_root]
level = WARN
handlers = console

[logger_sqlalchemy]
level = WARN
handlers =
qualname = sqlalchemy.engine

[logger_alembic]
level = INFO
handlers =
qualname = alembic

[handler_console]
class = StreamHandler
args = (sys.stderr,)
level = NOTSET
formatter = generic

[formatter_generic]
format = %(levelname)-5.5s [%(name)s] %(message)s
datefmt = %H:%M:%S
```

Create `backend/alembic/env.py`:

```python
"""Alembic environment configuration for async SQLAlchemy."""

import asyncio
import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import async_engine_from_config

# Import all models so Alembic autogenerate can detect them
from og_scraper.models import Base  # noqa: F401

config = context.config

# Override sqlalchemy.url from environment variable if set
database_url = os.environ.get("DATABASE_URL")
if database_url:
    config.set_main_option("sqlalchemy.url", database_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection):
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Run migrations in 'online' mode with async engine."""
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
```

Create `backend/alembic/script.py.mako` (migration template):

```mako
"""${message}

Revision ID: ${up_revision}
Revises: ${down_revision | comma,n}
Create Date: ${create_date}

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import geoalchemy2
${imports if imports else ""}

# revision identifiers, used by Alembic.
revision: str = ${repr(up_revision)}
down_revision: Union[str, None] = ${repr(down_revision)}
branch_labels: Union[str, Sequence[str], None] = ${repr(branch_labels)}
depends_on: Union[str, Sequence[str], None] = ${repr(depends_on)}


def upgrade() -> None:
    ${upgrades if upgrades else "pass"}


def downgrade() -> None:
    ${downgrades if downgrades else "pass"}
```

Create `backend/alembic/versions/` directory (empty).

### Step 7: Create Initial Migration

Create `backend/alembic/versions/001_initial_schema.py` manually (not auto-generated) to include extensions, enums, triggers, and state seed data that Alembic autogenerate cannot produce:

The migration must:
1. Create extensions: `uuid-ossp`, `postgis`, `pg_trgm`
2. Create all 5 enum types
3. Create all 8 tables (via autogenerate or manual DDL)
4. Create all indexes
5. Create the `wells_location_update()` trigger function and trigger
6. Create full-text search trigger functions and triggers for wells, operators, and documents
7. Seed the `states` table with 10 rows:

```python
# State seed data in the upgrade() function:
states_data = [
    {"code": "TX", "name": "Texas", "api_state_code": "42", "tier": 1},
    {"code": "NM", "name": "New Mexico", "api_state_code": "30", "tier": 1},
    {"code": "ND", "name": "North Dakota", "api_state_code": "33", "tier": 1},
    {"code": "OK", "name": "Oklahoma", "api_state_code": "35", "tier": 1},
    {"code": "CO", "name": "Colorado", "api_state_code": "05", "tier": 1},
    {"code": "WY", "name": "Wyoming", "api_state_code": "49", "tier": 2},
    {"code": "LA", "name": "Louisiana", "api_state_code": "17", "tier": 2},
    {"code": "PA", "name": "Pennsylvania", "api_state_code": "37", "tier": 2},
    {"code": "CA", "name": "California", "api_state_code": "04", "tier": 2},
    {"code": "AK", "name": "Alaska", "api_state_code": "50", "tier": 2},
]
```

The location auto-sync trigger:

```sql
CREATE OR REPLACE FUNCTION wells_location_update() RETURNS trigger AS $$
BEGIN
    IF NEW.latitude IS NOT NULL AND NEW.longitude IS NOT NULL THEN
        NEW.location := ST_SetSRID(ST_MakePoint(NEW.longitude, NEW.latitude), 4326);
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_wells_location_update
    BEFORE INSERT OR UPDATE OF latitude, longitude
    ON wells FOR EACH ROW EXECUTE FUNCTION wells_location_update();
```

Full-text search trigger for wells:

```sql
CREATE OR REPLACE FUNCTION wells_search_vector_update() RETURNS trigger AS $$
BEGIN
    NEW.search_vector :=
        setweight(to_tsvector('english', COALESCE(NEW.api_number, '')), 'A') ||
        setweight(to_tsvector('english', COALESCE(NEW.well_name, '')), 'A') ||
        setweight(to_tsvector('english', COALESCE(NEW.lease_name, '')), 'B') ||
        setweight(to_tsvector('english', COALESCE(NEW.county, '')), 'C') ||
        setweight(to_tsvector('english', COALESCE(NEW.basin, '')), 'C') ||
        setweight(to_tsvector('english', COALESCE(NEW.field_name, '')), 'C');
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_wells_search_vector_update
    BEFORE INSERT OR UPDATE OF api_number, well_name, lease_name, county, basin, field_name
    ON wells FOR EACH ROW EXECUTE FUNCTION wells_search_vector_update();
```

Full-text search trigger for operators:

```sql
CREATE OR REPLACE FUNCTION operators_search_vector_update() RETURNS trigger AS $$
BEGIN
    NEW.search_vector :=
        setweight(to_tsvector('english', COALESCE(NEW.name, '')), 'A') ||
        setweight(to_tsvector('english', COALESCE(NEW.normalized_name, '')), 'A');
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_operators_search_vector_update
    BEFORE INSERT OR UPDATE OF name, normalized_name
    ON operators FOR EACH ROW EXECUTE FUNCTION operators_search_vector_update();
```

### Step 8: Create Test Fixtures and Tests

Create `backend/tests/conftest.py` with testcontainers PostgreSQL+PostGIS fixture:

```python
import asyncio
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from testcontainers.postgres import PostgresContainer

from og_scraper.models import Base


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session")
def postgres_container():
    with PostgresContainer(
        image="postgis/postgis:16-3.4",
        username="test",
        password="test",
        dbname="test_ogdocs",
    ) as pg:
        yield pg


@pytest.fixture(scope="session")
async def engine(postgres_container):
    url = postgres_container.get_connection_url().replace("postgresql://", "postgresql+asyncpg://")
    eng = create_async_engine(url, echo=True)
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    await eng.dispose()


@pytest.fixture
async def db_session(engine):
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session
        await session.rollback()
```

Create `backend/tests/test_models.py`:

```python
"""Tests for SQLAlchemy models and database schema."""

import pytest
from sqlalchemy import text

from og_scraper.models import (
    State, Operator, Well, Document, ExtractedData,
    ReviewQueue, ScrapeJob, DataCorrection,
    DocType, DocumentStatus, WellStatus, ReviewStatus, ScrapeJobStatus,
)


@pytest.mark.asyncio
async def test_all_tables_created(db_session):
    """Verify all 8 tables exist in the database."""
    result = await db_session.execute(
        text("SELECT table_name FROM information_schema.tables WHERE table_schema='public' ORDER BY table_name")
    )
    tables = {row[0] for row in result.fetchall()}
    expected = {"states", "operators", "wells", "documents", "extracted_data", "review_queue", "scrape_jobs", "data_corrections"}
    assert expected.issubset(tables), f"Missing tables: {expected - tables}"


@pytest.mark.asyncio
async def test_insert_state(db_session):
    """Insert a state and verify it persists."""
    state = State(code="TX", name="Texas", api_state_code="42", tier=1)
    db_session.add(state)
    await db_session.flush()
    assert state.code == "TX"


@pytest.mark.asyncio
async def test_insert_well_with_location(db_session):
    """Insert a well with lat/long and verify fields."""
    state = State(code="OK", name="Oklahoma", api_state_code="35", tier=1)
    db_session.add(state)
    await db_session.flush()

    well = Well(
        api_number="35019213370000",
        state_code="OK",
        well_name="Test Well #1",
        latitude=35.4676,
        longitude=-97.5164,
    )
    db_session.add(well)
    await db_session.flush()
    assert well.id is not None
    assert well.api_number == "35019213370000"


@pytest.mark.asyncio
async def test_enum_values_match_discovery():
    """Verify enum values match DISCOVERY.md document types."""
    doc_types = {e.value for e in DocType}
    expected_doc_types = {
        "well_permit", "completion_report", "production_report",
        "spacing_order", "pooling_order", "plugging_report",
        "inspection_record", "incident_report", "other",
    }
    assert doc_types == expected_doc_types

    well_statuses = {e.value for e in WellStatus}
    expected_well_statuses = {
        "active", "inactive", "plugged", "permitted", "drilling",
        "completed", "shut_in", "temporarily_abandoned", "unknown",
    }
    assert well_statuses == expected_well_statuses
```

## Files to Create

- `backend/src/og_scraper/models/base.py` - Base class, mixins, naming convention
- `backend/src/og_scraper/models/enums.py` - All 5 enum types
- `backend/src/og_scraper/models/state.py` - State model
- `backend/src/og_scraper/models/operator.py` - Operator model with FTS
- `backend/src/og_scraper/models/well.py` - Well model with PostGIS + FTS
- `backend/src/og_scraper/models/document.py` - Document model
- `backend/src/og_scraper/models/extracted_data.py` - ExtractedData model with JSONB
- `backend/src/og_scraper/models/review_queue.py` - ReviewQueue model
- `backend/src/og_scraper/models/scrape_job.py` - ScrapeJob model
- `backend/src/og_scraper/models/data_correction.py` - DataCorrection model
- `backend/src/og_scraper/database.py` - Async engine + session factory
- `backend/alembic.ini` - Alembic configuration
- `backend/alembic/env.py` - Async Alembic environment
- `backend/alembic/script.py.mako` - Migration template
- `backend/alembic/versions/001_initial_schema.py` - Initial migration with triggers + seeds
- `backend/tests/conftest.py` - Testcontainers PostgreSQL fixture
- `backend/tests/test_models.py` - Model and schema tests

## Files to Modify

- `backend/src/og_scraper/models/__init__.py` - Import all models and enums

## Contracts

### Provides (for downstream tasks)

- **8 SQLAlchemy models**: State, Operator, Well, Document, ExtractedData, ReviewQueue, ScrapeJob, DataCorrection
- **5 Enum types**: DocType, DocumentStatus, ScrapeJobStatus, ReviewStatus, WellStatus
- **Database session factory**: `og_scraper.database.get_db()` yields `AsyncSession`
- **Database engine**: `og_scraper.database.engine` for direct use
- **Base class**: `og_scraper.models.Base` with metadata naming convention
- **Mixins**: `TimestampMixin`, `UUIDPrimaryKeyMixin`
- **Table names**: `states`, `operators`, `wells`, `documents`, `extracted_data`, `review_queue`, `scrape_jobs`, `data_corrections`
- **Well location auto-sync**: Insert lat/long and the PostGIS geometry column updates via trigger
- **Full-text search**: tsvector columns on wells, operators, documents updated via trigger
- **State seed data**: 10 rows in `states` table with codes, names, API state codes, and tiers
- **Alembic**: `alembic upgrade head` applies the complete schema

### Consumes (from upstream tasks)

- Task 1.1: Project structure, Docker Compose with PostgreSQL, `backend/src/og_scraper/` package

## Acceptance Criteria

- [ ] `alembic upgrade head` creates all 8 tables in PostgreSQL without errors
- [ ] PostGIS extension is enabled: `SELECT PostGIS_Version();` returns a version
- [ ] `uuid-ossp` extension is enabled: `SELECT uuid_generate_v4();` returns a UUID
- [ ] `pg_trgm` extension is enabled: `SELECT similarity('test', 'tset');` returns a value
- [ ] All 5 enum types exist in PostgreSQL: `doc_type_enum`, `document_status_enum`, `scrape_job_status_enum`, `review_status_enum`, `well_status_enum`
- [ ] All 10 states are seeded in the `states` table
- [ ] Auto-sync trigger: insert a well with lat=35.0, lng=-97.0, then `SELECT ST_AsText(location) FROM wells` returns `POINT(-97 35)`
- [ ] Full-text search trigger: insert a well with well_name='Permian Basin #1', then `SELECT search_vector FROM wells` is not null
- [ ] GIN indexes exist on JSONB and tsvector columns
- [ ] GiST index exists on `wells.location`
- [ ] All unit tests pass: `uv run pytest backend/tests/test_models.py -v`

## Testing Protocol

### Unit/Integration Tests

- Test file: `backend/tests/test_models.py`
- Test cases:
  - [ ] All 8 tables exist in the database after migration
  - [ ] Insert a state and verify it persists
  - [ ] Insert a well with lat/long and verify the PostGIS geometry column is populated (via trigger)
  - [ ] Insert a well with a well_name and verify search_vector is populated (via trigger)
  - [ ] Verify all DocType enum values match DISCOVERY.md document types
  - [ ] Verify all WellStatus enum values match DISCOVERY.md
  - [ ] Insert a document with a file_hash and verify the UNIQUE constraint prevents duplicates
  - [ ] Insert extracted_data linked to a document and verify the CASCADE delete

### API/Script Testing

- `docker compose exec backend uv run alembic upgrade head` completes without errors
- `docker compose exec db psql -U ogdocs -d ogdocs -c "SELECT count(*) FROM states;"` returns 10
- `docker compose exec db psql -U ogdocs -d ogdocs -c "SELECT code, name, tier FROM states ORDER BY code;"` lists all 10 states

### Build/Lint/Type Checks

- [ ] `cd backend && uv run ruff check src/og_scraper/models/` passes
- [ ] `cd backend && uv run pytest tests/test_models.py -v` passes

## Skills to Read

- `postgresql-postgis-schema` - Complete schema details, indexes, triggers, PostGIS patterns
- `fastapi-backend` - SQLAlchemy 2.0 async patterns, database session dependency

## Research Files to Read

- `.claude/orchestration-og-doc-scraper/research/backend-schema-implementation.md` - Complete SQL DDL, all table definitions, indexes, triggers
- `.claude/orchestration-og-doc-scraper/research/og-data-models.md` - Domain-specific data modeling, API number format

## Git

- Branch: `task/1.2-database-schema`
- Commit message prefix: `Task 1.2:`
