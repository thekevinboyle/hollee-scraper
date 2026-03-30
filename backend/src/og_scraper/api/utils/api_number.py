"""API number normalization utilities.

API numbers are the primary business identifier for wells.
Format: XX-YYY-ZZZZZ[-SS[-EE]] where:
  XX = state code (e.g., 42 for Texas)
  YYY = county code
  ZZZZZ = unique well number
  SS = sidetrack code (optional)
  EE = event code (optional)

Stored as VARCHAR(14) without dashes, zero-padded.
"""

import re


def normalize_api_number(raw: str) -> str:
    """Strip dashes/spaces, preserve leading zeros. Returns 10-14 char string."""
    cleaned = re.sub(r"[^0-9]", "", raw)
    # Zero-pad to at least 10 digits
    if len(cleaned) < 10:
        cleaned = cleaned.zfill(10)
    return cleaned[:14]  # Truncate to max 14


def format_api_number(api: str) -> str:
    """Format for display: XX-YYY-ZZZZZ[-SS[-EE]]."""
    if len(api) >= 10:
        parts = [api[:2], api[2:5], api[5:10]]
        if len(api) > 10:
            parts.append(api[10:12])
        if len(api) > 12:
            parts.append(api[12:14])
        return "-".join(parts)
    return api
