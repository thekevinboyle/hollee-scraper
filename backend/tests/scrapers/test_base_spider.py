"""Tests for BaseOGSpider."""

import pytest

from og_scraper.scrapers.spiders.base import BaseOGSpider
from og_scraper.scrapers.items import DocumentItem


class ConcreteSpider(BaseOGSpider):
    """Concrete implementation for testing."""

    name = "test_spider"
    state_code = "TX"
    state_name = "Texas"
    agency_name = "Railroad Commission of Texas"
    base_url = "https://www.rrc.texas.gov/"

    def start_requests(self):
        yield None  # Not testing actual requests


class TestBaseOGSpider:
    def test_enforces_abstract_methods(self):
        """BaseOGSpider cannot be instantiated directly."""
        with pytest.raises((TypeError, ValueError)):
            BaseOGSpider()

    def test_validates_required_attributes(self):
        """Spider without required attributes raises ValueError."""

        class BadSpider(BaseOGSpider):
            name = "bad"
            state_code = None  # Missing!
            state_name = "Test"
            agency_name = "Test"
            base_url = "http://test.com"

            def start_requests(self):
                pass

        with pytest.raises(ValueError, match="state_code"):
            BadSpider()

    def test_concrete_spider_instantiates(self):
        """Properly configured spider instantiates."""
        spider = ConcreteSpider()
        assert spider.state_code == "TX"
        assert spider.documents_found == 0

    def test_normalize_api_number_14_digits(self):
        spider = ConcreteSpider()
        assert spider.normalize_api_number("42-501-20130-03-00") == "42501201300300"

    def test_normalize_api_number_10_digits(self):
        spider = ConcreteSpider()
        assert spider.normalize_api_number("4250120130") == "42501201300000"

    def test_normalize_api_number_12_digits(self):
        spider = ConcreteSpider()
        assert spider.normalize_api_number("425012013003") == "42501201300300"

    def test_normalize_api_number_already_normalized(self):
        spider = ConcreteSpider()
        assert spider.normalize_api_number("42501201300300") == "42501201300300"

    def test_normalize_api_number_too_short(self):
        spider = ConcreteSpider()
        assert spider.normalize_api_number("12345") == "12345"

    def test_compute_file_hash(self):
        spider = ConcreteSpider()
        content = b"test content"
        hash1 = spider.compute_file_hash(content)
        hash2 = spider.compute_file_hash(content)
        assert hash1 == hash2
        assert len(hash1) == 64  # SHA-256 hex digest

    def test_build_document_item(self):
        spider = ConcreteSpider()
        item = spider.build_document_item(
            source_url="https://example.com/doc.pdf",
            doc_type="production_report",
            api_number="42-501-20130-03-00",
            operator_name="Devon Energy",
        )
        assert isinstance(item, DocumentItem)
        assert item.state_code == "TX"
        assert item.api_number == "42501201300300"
        assert item.operator_name == "Devon Energy"
        assert spider.documents_found == 1
