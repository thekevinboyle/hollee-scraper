"""PostgreSQL enum types for the Oil & Gas schema.

The `schema` parameter on each enum must match the name used in the Alembic
migration (001_initial_schema.py) so SQLAlchemy emits the correct CAST.
"""

import enum

from sqlalchemy.dialects.postgresql import ENUM as PG_ENUM


class DocType(enum.StrEnum):
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


DocTypePG = PG_ENUM(
    *[e.value for e in DocType], name="doc_type_enum", create_type=False
)


class DocumentStatus(enum.StrEnum):
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


DocumentStatusPG = PG_ENUM(
    *[e.value for e in DocumentStatus], name="document_status_enum", create_type=False
)


class ScrapeJobStatus(enum.StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


ScrapeJobStatusPG = PG_ENUM(
    *[e.value for e in ScrapeJobStatus], name="scrape_job_status_enum", create_type=False
)


class ReviewStatus(enum.StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    CORRECTED = "corrected"


ReviewStatusPG = PG_ENUM(
    *[e.value for e in ReviewStatus], name="review_status_enum", create_type=False
)


class WellStatus(enum.StrEnum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    PLUGGED = "plugged"
    PERMITTED = "permitted"
    DRILLING = "drilling"
    COMPLETED = "completed"
    SHUT_IN = "shut_in"
    TEMPORARILY_ABANDONED = "temporarily_abandoned"
    UNKNOWN = "unknown"


WellStatusPG = PG_ENUM(
    *[e.value for e in WellStatus], name="well_status_enum", create_type=False
)
