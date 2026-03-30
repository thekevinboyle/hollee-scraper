"""Scrapy item definitions for the Oil & Gas Document Scraper."""

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any


@dataclass
class DocumentItem:
    """Represents a scraped document before database persistence.

    Yielded by state spiders, processed through the pipeline.
    """

    # Required fields
    state_code: str  # 2-letter code, e.g. "TX"
    source_url: str  # URL the document was scraped from
    doc_type: str  # e.g. "production_report", "well_permit"

    # Well identification (at least one should be populated)
    api_number: str | None = None  # 14-digit normalized
    operator_name: str | None = None
    well_name: str | None = None
    lease_name: str | None = None

    # File info (populated by download pipeline)
    file_path: str | None = None
    file_hash: str | None = None  # SHA-256
    file_format: str | None = None  # "pdf", "csv", "xlsx", "html"
    file_size_bytes: int | None = None
    file_content: bytes | None = None  # Raw file bytes (before save)

    # Dates
    document_date: date | None = None
    scraped_at: datetime = field(default_factory=datetime.utcnow)

    # Location (if available from scrape)
    latitude: float | None = None
    longitude: float | None = None

    # County/basin/field
    county: str | None = None
    basin: str | None = None
    field_name: str | None = None

    # Raw metadata from the source page
    raw_metadata: dict[str, Any] = field(default_factory=dict)

    # Scrape job tracking
    scrape_job_id: str | None = None


@dataclass
class WellItem:
    """Represents a well discovered during scraping."""

    api_number: str  # 14-digit normalized
    state_code: str
    well_name: str | None = None
    well_number: str | None = None
    operator_name: str | None = None
    county: str | None = None
    basin: str | None = None
    field_name: str | None = None
    lease_name: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    well_status: str | None = None
    well_type: str | None = None
    spud_date: date | None = None
    completion_date: date | None = None
    total_depth: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    alternate_ids: dict[str, str] = field(default_factory=dict)
