"""API schemas package -- re-exports all Pydantic models."""

from .document import DocumentDetail, DocumentSummary, ExtractedDataSummary
from .enums import (
    DocType,
    DocumentStatus,
    ReviewStatus,
    ScrapeJobStatus,
    SortDirection,
    WellStatus,
)
from .operator import OperatorDetail, OperatorSummary
from .pagination import PaginatedResponse, PaginationParams
from .review import ReviewAction, ReviewItemDetail, ReviewQueueItem, ReviewStats
from .scrape import (
    ScrapeJobCreate,
    ScrapeJobDetail,
    ScrapeJobSummary,
    ScrapeProgressEvent,
)
from .state import StateSummary
from .well import WellDetail, WellSummary

__all__ = [
    # Enums
    "DocType",
    "DocumentStatus",
    "ReviewStatus",
    "ScrapeJobStatus",
    "SortDirection",
    "WellStatus",
    # Pagination
    "PaginatedResponse",
    "PaginationParams",
    # Wells
    "WellSummary",
    "WellDetail",
    # Documents
    "DocumentSummary",
    "DocumentDetail",
    "ExtractedDataSummary",
    # Operators
    "OperatorSummary",
    "OperatorDetail",
    # Review
    "ReviewQueueItem",
    "ReviewItemDetail",
    "ReviewAction",
    "ReviewStats",
    # States
    "StateSummary",
    # Scrape Jobs
    "ScrapeJobCreate",
    "ScrapeJobSummary",
    "ScrapeJobDetail",
    "ScrapeProgressEvent",
]
