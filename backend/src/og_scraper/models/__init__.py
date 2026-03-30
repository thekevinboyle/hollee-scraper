"""SQLAlchemy ORM models for the Oil & Gas Document Scraper."""

from .base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from .data_correction import DataCorrection
from .document import Document
from .enums import DocType, DocumentStatus, ReviewStatus, ScrapeJobStatus, WellStatus
from .extracted_data import ExtractedData
from .operator import Operator
from .review_queue import ReviewQueue
from .scrape_job import ScrapeJob
from .state import State
from .well import Well

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
