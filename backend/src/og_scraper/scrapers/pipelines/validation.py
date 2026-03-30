"""Validation pipeline -- ensures required fields are present."""

import logging

from scrapy.exceptions import DropItem

from og_scraper.scrapers.items import DocumentItem

logger = logging.getLogger(__name__)


class ValidationPipeline:
    """Validates that scraped items have required fields."""

    REQUIRED_FIELDS = ["state_code", "source_url", "doc_type"]

    def process_item(self, item, spider):
        if not isinstance(item, DocumentItem):
            return item

        for field_name in self.REQUIRED_FIELDS:
            value = getattr(item, field_name, None)
            if not value:
                raise DropItem(f"Missing required field '{field_name}' in item from {getattr(spider, 'state_code', 'unknown') if spider else 'unknown'}")

        # Validate state code is one of the 10 supported states
        valid_states = {"TX", "NM", "ND", "OK", "CO", "WY", "LA", "PA", "CA", "AK"}
        if item.state_code not in valid_states:
            raise DropItem(f"Invalid state_code '{item.state_code}'")

        return item
