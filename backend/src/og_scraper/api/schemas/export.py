"""Export format enum for streaming download endpoints."""

import enum


class ExportFormat(enum.StrEnum):
    CSV = "csv"
    JSON = "json"
