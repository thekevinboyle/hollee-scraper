"""Tests for scraper pipelines."""

import os
import tempfile

import pytest
from scrapy.exceptions import DropItem

from og_scraper.scrapers.items import DocumentItem
from og_scraper.scrapers.pipelines.validation import ValidationPipeline
from og_scraper.scrapers.pipelines.deduplication import DeduplicationPipeline
from og_scraper.scrapers.pipelines.storage import FileStoragePipeline, slugify


class TestValidationPipeline:
    def setup_method(self):
        self.pipeline = ValidationPipeline()

    def test_valid_item_passes(self):
        item = DocumentItem(state_code="TX", source_url="https://example.com", doc_type="well_permit")
        result = self.pipeline.process_item(item, None)
        assert result is item

    def test_missing_state_code_drops(self):
        item = DocumentItem(state_code="", source_url="https://example.com", doc_type="well_permit")
        with pytest.raises(DropItem, match="state_code"):
            self.pipeline.process_item(item, type("Spider", (), {"state_code": "TX"}))

    def test_invalid_state_drops(self):
        item = DocumentItem(state_code="ZZ", source_url="https://example.com", doc_type="well_permit")
        with pytest.raises(DropItem, match="Invalid state_code"):
            self.pipeline.process_item(item, type("Spider", (), {"state_code": "ZZ"}))


class TestDeduplicationPipeline:
    def setup_method(self):
        self.pipeline = DeduplicationPipeline()

    def test_first_hash_passes(self):
        item = DocumentItem(state_code="TX", source_url="https://example.com", doc_type="well_permit", file_hash="abc123")
        result = self.pipeline.process_item(item, None)
        assert result is item

    def test_duplicate_hash_drops(self):
        item1 = DocumentItem(state_code="TX", source_url="https://example.com/1", doc_type="well_permit", file_hash="abc123")
        item2 = DocumentItem(state_code="TX", source_url="https://example.com/2", doc_type="well_permit", file_hash="abc123")
        self.pipeline.process_item(item1, None)
        with pytest.raises(DropItem, match="Duplicate"):
            self.pipeline.process_item(item2, None)

    def test_no_hash_passes_through(self):
        item = DocumentItem(state_code="TX", source_url="https://example.com", doc_type="well_permit")
        result = self.pipeline.process_item(item, None)
        assert result is item


class TestFileStoragePipeline:
    def test_creates_correct_directory_structure(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            os.environ["DOCUMENTS_DIR"] = tmpdir
            # Re-import to pick up the env var change
            import og_scraper.scrapers.pipelines.storage as storage_mod

            original_data_dir = storage_mod.DATA_DIR
            storage_mod.DATA_DIR = tmpdir
            try:
                pipeline = FileStoragePipeline()

                item = DocumentItem(
                    state_code="TX",
                    source_url="https://example.com",
                    doc_type="production_report",
                    operator_name="Devon Energy",
                    file_content=b"test pdf content",
                    file_format="pdf",
                )
                result = pipeline.process_item(item, None)

                assert result.file_path is not None
                assert "TX" in result.file_path
                assert "devon-energy" in result.file_path
                assert "production-report" in result.file_path
                assert result.file_path.endswith(".pdf")
                assert os.path.exists(result.file_path)
                assert result.file_content is None  # Cleared after save
            finally:
                storage_mod.DATA_DIR = original_data_dir
                os.environ.pop("DOCUMENTS_DIR", None)


class TestSlugify:
    def test_basic(self):
        assert slugify("Devon Energy") == "devon-energy"

    def test_special_chars(self):
        assert slugify("Devon Energy Corp.") == "devon-energy-corp"

    def test_long_name_truncated(self):
        result = slugify("A" * 200)
        assert len(result) <= 100
