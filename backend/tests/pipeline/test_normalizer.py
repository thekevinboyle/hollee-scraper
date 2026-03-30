"""Tests for data normalization and the slugify utility.

Tests cover API number padding, date normalization, volume handling,
operator name trimming, county title-casing, and cross-state consistency.
"""

import pytest

from og_scraper.pipeline.extractor import FieldExtractionResult, FieldValue
from og_scraper.pipeline.normalizer import DataNormalizer, NormalizationResult, slugify


class TestDataNormalizer:
    def _make_extraction(self, fields: dict[str, tuple]) -> FieldExtractionResult:
        """Helper to create FieldExtractionResult from simple values."""
        fv = {}
        for name, (value, confidence) in fields.items():
            fv[name] = FieldValue(
                value=value,
                confidence=confidence,
                source_text="",
                pattern_used="",
                extraction_method="regex",
                pattern_specificity=0.85,
            )
        return FieldExtractionResult(
            fields=fv, raw_text="", doc_type="production_report", state="TX"
        )

    # ---- API Number Normalization ----

    def test_api_number_normalization_10_to_14(self):
        extraction = self._make_extraction({"api_number": ("4250120130", 0.85)})
        normalizer = DataNormalizer()
        result = normalizer.normalize(extraction)
        assert result.fields["api_number"] == "42501201300000"

    def test_api_number_normalization_12_to_14(self):
        extraction = self._make_extraction({"api_number": ("425012013003", 0.88)})
        normalizer = DataNormalizer()
        result = normalizer.normalize(extraction)
        assert result.fields["api_number"] == "42501201300300"

    def test_api_number_already_14(self):
        extraction = self._make_extraction({"api_number": ("42501201300300", 0.90)})
        normalizer = DataNormalizer()
        result = normalizer.normalize(extraction)
        assert result.fields["api_number"] == "42501201300300"

    def test_api_number_with_dashes(self):
        extraction = self._make_extraction({"api_number": ("42-501-20130-03-00", 0.90)})
        normalizer = DataNormalizer()
        result = normalizer.normalize(extraction)
        assert result.fields["api_number"] == "42501201300300"

    def test_api_number_unexpected_length_warning(self):
        extraction = self._make_extraction({"api_number": ("42501", 0.50)})
        normalizer = DataNormalizer()
        result = normalizer.normalize(extraction)
        assert any("unexpected length" in w for w in result.warnings)

    # ---- Date Normalization ----

    def test_date_normalization(self):
        extraction = self._make_extraction({"spud_date": ("03/15/2026", 0.90)})
        normalizer = DataNormalizer()
        result = normalizer.normalize(extraction)
        assert result.fields["spud_date"] == "2026-03-15"

    def test_date_already_iso(self):
        extraction = self._make_extraction({"completion_date": ("2026-01-15", 0.92)})
        normalizer = DataNormalizer()
        result = normalizer.normalize(extraction)
        assert result.fields["completion_date"] == "2026-01-15"

    def test_date_unparseable_warning(self):
        extraction = self._make_extraction({"permit_date": ("January 2026", 0.80)})
        normalizer = DataNormalizer()
        result = normalizer.normalize(extraction)
        # Should return the original string and warn
        assert result.fields["permit_date"] == "January 2026"
        assert any("could not parse date" in w for w in result.warnings)

    def test_date_empty_returns_none(self):
        extraction = self._make_extraction({"spud_date": ("", 0.50)})
        normalizer = DataNormalizer()
        result = normalizer.normalize(extraction)
        assert result.fields["spud_date"] is None

    # ---- Operator Name Normalization ----

    def test_operator_name_trimmed(self):
        extraction = self._make_extraction({"operator_name": ("  Devon Energy Corp.  ", 0.85)})
        normalizer = DataNormalizer()
        result = normalizer.normalize(extraction)
        assert result.fields["operator_name"] == "Devon Energy Corp"

    def test_operator_name_whitespace_collapsed(self):
        extraction = self._make_extraction({"operator_name": ("Pioneer  Natural   Resources", 0.85)})
        normalizer = DataNormalizer()
        result = normalizer.normalize(extraction)
        assert result.fields["operator_name"] == "Pioneer Natural Resources"

    def test_operator_name_trailing_comma(self):
        extraction = self._make_extraction({"operator_name": ("Devon Energy,", 0.85)})
        normalizer = DataNormalizer()
        result = normalizer.normalize(extraction)
        assert result.fields["operator_name"] == "Devon Energy"

    # ---- Volume Normalization ----

    def test_volume_normalization(self):
        extraction = self._make_extraction({"production_oil_bbl": (1234.567, 0.90)})
        normalizer = DataNormalizer()
        result = normalizer.normalize(extraction)
        assert result.fields["production_oil_bbl"] == 1234.57

    def test_negative_volume_warning(self):
        extraction = self._make_extraction({"production_oil_bbl": (-100, 0.90)})
        normalizer = DataNormalizer()
        result = normalizer.normalize(extraction)
        assert result.fields["production_oil_bbl"] == 0.0
        assert any("negative" in w for w in result.warnings)

    def test_high_oil_volume_warning(self):
        extraction = self._make_extraction({"production_oil_bbl": (200000, 0.90)})
        normalizer = DataNormalizer()
        result = normalizer.normalize(extraction)
        assert result.fields["production_oil_bbl"] == 200000.0
        assert any("unusually high" in w for w in result.warnings)

    def test_gas_volume_normalization(self):
        extraction = self._make_extraction({"production_gas_mcf": (5678.123, 0.90)})
        normalizer = DataNormalizer()
        result = normalizer.normalize(extraction)
        assert result.fields["production_gas_mcf"] == 5678.12

    def test_negative_gas_volume(self):
        extraction = self._make_extraction({"production_gas_mcf": (-50, 0.90)})
        normalizer = DataNormalizer()
        result = normalizer.normalize(extraction)
        assert result.fields["production_gas_mcf"] == 0.0
        assert any("negative" in w for w in result.warnings)

    def test_water_volume(self):
        extraction = self._make_extraction({"production_water_bbl": (890.0, 0.90)})
        normalizer = DataNormalizer()
        result = normalizer.normalize(extraction)
        assert result.fields["production_water_bbl"] == 890.0

    def test_volume_unparseable_warning(self):
        extraction = self._make_extraction({"production_oil_bbl": ("not a number", 0.70)})
        normalizer = DataNormalizer()
        result = normalizer.normalize(extraction)
        assert result.fields["production_oil_bbl"] is None
        assert any("could not parse" in w for w in result.warnings)

    # ---- County Normalization ----

    def test_county_title_case(self):
        extraction = self._make_extraction({"county": ("ector county", 0.85)})
        normalizer = DataNormalizer()
        result = normalizer.normalize(extraction)
        assert result.fields["county"] == "Ector County"

    def test_county_already_title_case(self):
        extraction = self._make_extraction({"county": ("Midland", 0.85)})
        normalizer = DataNormalizer()
        result = normalizer.normalize(extraction)
        assert result.fields["county"] == "Midland"

    # ---- Well Name Normalization ----

    def test_well_name_trimmed(self):
        extraction = self._make_extraction({"well_name": ("  Permian Basin #42  ", 0.85)})
        normalizer = DataNormalizer()
        result = normalizer.normalize(extraction)
        assert result.fields["well_name"] == "Permian Basin #42"

    # ---- Depth Normalization ----

    def test_depth_normalization(self):
        extraction = self._make_extraction({"well_depth_ft": (10500.0, 0.88)})
        normalizer = DataNormalizer()
        result = normalizer.normalize(extraction)
        assert result.fields["well_depth_ft"] == 10500.0

    def test_negative_depth_rejected(self):
        extraction = self._make_extraction({"well_depth_ft": (-100, 0.50)})
        normalizer = DataNormalizer()
        result = normalizer.normalize(extraction)
        assert result.fields["well_depth_ft"] is None
        assert any("negative" in w for w in result.warnings)

    def test_very_deep_well_warning(self):
        extraction = self._make_extraction({"well_depth_ft": (45000, 0.80)})
        normalizer = DataNormalizer()
        result = normalizer.normalize(extraction)
        assert result.fields["well_depth_ft"] == 45000.0
        assert any("unusually deep" in w for w in result.warnings)

    # ---- Coordinate Normalization ----

    def test_coordinate_normalization(self):
        extraction = self._make_extraction({
            "latitude": (31.9505123456, 0.90),
            "longitude": (-102.0775123456, 0.90),
        })
        normalizer = DataNormalizer()
        result = normalizer.normalize(extraction)
        assert result.fields["latitude"] == 31.9505123
        assert result.fields["longitude"] == -102.0775123

    # ---- Days Produced ----

    def test_days_produced(self):
        extraction = self._make_extraction({"days_produced": (31, 0.90)})
        normalizer = DataNormalizer()
        result = normalizer.normalize(extraction)
        assert result.fields["days_produced"] == 31

    # ---- Audit Trail ----

    def test_original_fields_preserved(self):
        extraction = self._make_extraction({"api_number": ("4250120130", 0.85)})
        normalizer = DataNormalizer()
        result = normalizer.normalize(extraction)
        assert result.original_fields["api_number"] == "4250120130"
        assert result.fields["api_number"] == "42501201300000"

    def test_normalizations_applied_list(self):
        extraction = self._make_extraction({
            "api_number": ("4250120130", 0.85),
            "operator_name": ("Devon Energy", 0.85),
        })
        normalizer = DataNormalizer()
        result = normalizer.normalize(extraction)
        assert len(result.normalizations_applied) > 0

    # ---- Cross-State Consistency ----

    def test_cross_state_api_normalization(self):
        """Same well API number from different state formats should normalize identically."""
        normalizer = DataNormalizer()

        # Texas format (10-digit)
        tx = self._make_extraction({"api_number": ("4250120130", 0.85)})
        tx_result = normalizer.normalize(tx)

        # Texas format (14-digit with dashes)
        tx2 = self._make_extraction({"api_number": ("42-501-20130-00-00", 0.90)})
        tx2_result = normalizer.normalize(tx2)

        assert tx_result.fields["api_number"] == tx2_result.fields["api_number"]


# ============================================================
# Slugify Utility
# ============================================================


class TestSlugify:
    def test_basic(self):
        assert slugify("Devon Energy Corporation") == "devon-energy-corporation"

    def test_special_chars(self):
        assert slugify("Pioneer Natural Resources Co.") == "pioneer-natural-resources-co"

    def test_ampersand(self):
        # Ampersand is stripped as non-word character, spaces collapse to single dash
        result = slugify("Smith & Jones LLC")
        assert result == "smith-jones-llc"

    def test_already_slug(self):
        assert slugify("devon-energy") == "devon-energy"

    def test_unicode(self):
        assert slugify("Compania de Petroleo") == "compania-de-petroleo"

    def test_empty(self):
        assert slugify("") == ""

    def test_leading_trailing_special(self):
        assert slugify("...Devon Energy...") == "devon-energy"

    def test_uppercase(self):
        assert slugify("DEVON ENERGY CORP") == "devon-energy-corp"

    def test_multiple_spaces(self):
        assert slugify("Devon   Energy   Corp") == "devon-energy-corp"
