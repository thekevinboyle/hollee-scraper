"""Deduplication pipeline -- skips documents with duplicate content hashes."""

import logging

from scrapy.exceptions import DropItem

from og_scraper.scrapers.items import DocumentItem

logger = logging.getLogger(__name__)


class DeduplicationPipeline:
    """Deduplicates items based on SHA-256 content hash.

    Maintains an in-memory set of seen hashes for the current crawl.
    Database-level deduplication is also enforced via UNIQUE constraint
    on documents.file_hash.
    """

    def __init__(self):
        self.seen_hashes: set[str] = set()

    def process_item(self, item, spider):
        if not isinstance(item, DocumentItem):
            return item

        if not item.file_hash:
            return item  # No hash yet (content not downloaded), pass through

        if item.file_hash in self.seen_hashes:
            raise DropItem(f"Duplicate content hash: {item.file_hash[:16]}...")

        self.seen_hashes.add(item.file_hash)
        return item
