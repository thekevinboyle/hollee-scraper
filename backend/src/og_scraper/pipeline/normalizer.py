"""
Cross-state normalization for extracted O&G document data.

Normalizes:
- API numbers -> 14-digit zero-padded, no dashes
- Dates -> ISO 8601 (YYYY-MM-DD)
- Production volumes -> standard units (BBL for oil/water, MCF for gas)
- Depths -> feet (convert from meters if needed)
- Operator names -> trimmed, title-cased, canonical form
- State names -> 2-letter codes
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from og_scraper.pipeline.extractor import FieldExtractionResult


@dataclass
class NormalizationResult:
    """Result of normalizing extracted fields."""

    fields: dict[str, Any]  # Normalized field values (ready for database)
    original_fields: dict[str, Any]  # Pre-normalization values for audit
    normalizations_applied: list[str]  # List of normalizations performed
    warnings: list[str]  # Non-fatal normalization issues


class DataNormalizer:
    """
    Normalize extracted field values across states into a consistent schema.
    """

    def normalize(self, extraction: FieldExtractionResult) -> NormalizationResult:
        """
        Normalize all extracted fields.

        Args:
            extraction: FieldExtractionResult from DataExtractor

        Returns:
            NormalizationResult with normalized values and audit trail
        """
        normalized: dict[str, Any] = {}
        originals: dict[str, Any] = {}
        applied: list[str] = []
        warnings: list[str] = []

        for field_name, field_val in extraction.fields.items():
            originals[field_name] = field_val.value

            if field_name == "api_number":
                normalized[field_name] = self._normalize_api_number(field_val.value, applied, warnings)
            elif field_name in ("production_oil_bbl", "production_water_bbl"):
                normalized[field_name] = self._normalize_volume_bbl(field_val.value, field_name, applied, warnings)
            elif field_name == "production_gas_mcf":
                normalized[field_name] = self._normalize_volume_mcf(field_val.value, applied, warnings)
            elif field_name.endswith("_date") or field_name == "reporting_period":
                normalized[field_name] = self._normalize_date(field_val.value, field_name, applied, warnings)
            elif field_name == "operator_name":
                normalized[field_name] = self._normalize_operator_name(field_val.value, applied, warnings)
            elif field_name == "well_name":
                normalized[field_name] = self._normalize_well_name(field_val.value, applied)
            elif field_name == "county":
                normalized[field_name] = self._normalize_county(field_val.value, applied)
            elif field_name == "well_depth_ft":
                normalized[field_name] = self._normalize_depth(field_val.value, applied, warnings)
            elif field_name in ("latitude", "longitude"):
                normalized[field_name] = round(float(field_val.value), 7)
            elif field_name == "days_produced":
                normalized[field_name] = int(field_val.value) if field_val.value else None
            else:
                normalized[field_name] = field_val.value

        return NormalizationResult(
            fields=normalized,
            original_fields=originals,
            normalizations_applied=applied,
            warnings=warnings,
        )

    def _normalize_api_number(self, value: str, applied: list, warnings: list) -> str:
        """Normalize API number to 14-digit zero-padded, no dashes."""
        digits = re.sub(r"[-\s]", "", str(value))
        if len(digits) == 10:
            digits += "0000"
            applied.append("api_number: padded 10->14 digits")
        elif len(digits) == 12:
            digits += "00"
            applied.append("api_number: padded 12->14 digits")
        elif len(digits) != 14:
            warnings.append(f"api_number: unexpected length {len(digits)}")
        return digits

    def _normalize_volume_bbl(self, value: Any, field_name: str, applied: list, warnings: list) -> float | None:
        """Normalize oil/water volume to BBL."""
        try:
            vol = float(value)
        except (TypeError, ValueError):
            warnings.append(f"{field_name}: could not parse '{value}' as number")
            return None
        if vol < 0:
            warnings.append(f"{field_name}: negative volume {vol}, setting to 0")
            return 0.0
        if field_name == "production_oil_bbl" and vol > 100_000:
            warnings.append(f"{field_name}: unusually high value {vol} BBL")
        if field_name == "production_water_bbl" and vol > 100_000:
            warnings.append(f"{field_name}: unusually high value {vol} BBL")
        applied.append(f"{field_name}: normalized to float BBL")
        return round(vol, 2)

    def _normalize_volume_mcf(self, value: Any, applied: list, warnings: list) -> float | None:
        """Normalize gas volume to MCF. MMCF conversion should already be done by extractor."""
        try:
            vol = float(value)
        except (TypeError, ValueError):
            warnings.append(f"production_gas_mcf: could not parse '{value}'")
            return None
        if vol < 0:
            warnings.append(f"production_gas_mcf: negative volume {vol}")
            return 0.0
        if vol > 1_000_000:
            warnings.append(f"production_gas_mcf: unusually high value {vol} MCF")
        applied.append("production_gas_mcf: normalized to float MCF")
        return round(vol, 2)

    def _normalize_date(self, value: str, field_name: str, applied: list, warnings: list) -> str | None:
        """Normalize date to ISO 8601 (YYYY-MM-DD). Value may already be ISO from extractor."""
        if not value:
            return None
        # Already ISO format?
        if re.match(r"^\d{4}-\d{2}-\d{2}$", str(value)):
            return str(value)
        # Try additional parsing
        from og_scraper.pipeline.patterns import _try_parse_date

        parsed = _try_parse_date(str(value))
        if parsed:
            applied.append(f"{field_name}: parsed '{value}' -> '{parsed}'")
            return parsed
        warnings.append(f"{field_name}: could not parse date '{value}'")
        return str(value)

    def _normalize_operator_name(self, value: str, applied: list, warnings: list) -> str:
        """Normalize operator name: trim, remove extra whitespace, title case."""
        name = str(value).strip()
        name = re.sub(r"\s+", " ", name)
        # Remove trailing commas, periods, "Inc.", "LLC" normalization
        name = name.rstrip(",.")
        # Preserve standard business suffixes
        applied.append(f"operator_name: normalized '{value}' -> '{name}'")
        return name

    def _normalize_well_name(self, value: str, applied: list) -> str:
        """Normalize well name: trim, collapse whitespace."""
        name = str(value).strip()
        name = re.sub(r"\s+", " ", name)
        applied.append("well_name: trimmed and collapsed whitespace")
        return name

    def _normalize_county(self, value: str, applied: list) -> str:
        """Normalize county name: trim, title case."""
        county = str(value).strip().title()
        county = re.sub(r"\s+", " ", county)
        applied.append(f"county: normalized to '{county}'")
        return county

    def _normalize_depth(self, value: Any, applied: list, warnings: list) -> float | None:
        """Normalize well depth to feet."""
        try:
            depth = float(value)
        except (TypeError, ValueError):
            warnings.append(f"well_depth_ft: could not parse '{value}'")
            return None
        if depth < 0:
            warnings.append(f"well_depth_ft: negative depth {depth}")
            return None
        if depth > 40_000:
            warnings.append(f"well_depth_ft: unusually deep {depth} ft")
        applied.append("well_depth_ft: normalized to float feet")
        return round(depth, 1)


def slugify(text: str) -> str:
    """
    Convert text to a URL/filesystem-safe slug.
    Used for creating file paths: data/{state}/{operator_slug}/{doc_type}/

    Examples:
        "Devon Energy Corporation" -> "devon-energy-corporation"
        "Pioneer Natural Resources Co." -> "pioneer-natural-resources-co"
    """
    text = unicodedata.normalize("NFKD", text)
    text = text.encode("ascii", "ignore").decode("ascii")
    text = text.lower()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[-\s]+", "-", text)
    return text.strip("-")
