"""String enum types for API request/response models.

These mirror the PostgreSQL enum types defined in og_scraper.models.enums
but are separate Pydantic-friendly enums for the API layer.
"""

import enum


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


class ScrapeJobStatus(enum.StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ReviewStatus(enum.StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    CORRECTED = "corrected"


class SortDirection(enum.StrEnum):
    ASC = "asc"
    DESC = "desc"
