"""Run a Scrapy spider and collect items without the full Scrapy framework.

Uses httpx to fetch URLs and the spider's parse methods to extract items.
This avoids Twisted reactor issues when running from a threaded Huey worker.
"""

import importlib
import logging

import httpx
from scrapy.http import Request as ScrapyRequest
from scrapy.http import TextResponse

from og_scraper.scrapers.items import DocumentItem, WellItem

logger = logging.getLogger(__name__)


def load_spider_class(dotted_path: str):
    """Import and return a spider class from its dotted path."""
    module_path, class_name = dotted_path.rsplit(".", 1)
    module = importlib.import_module(module_path)
    return getattr(module, class_name)


def run_spider_sync(
    spider_class_path: str,
    limit: int = 50,
) -> tuple[list[WellItem], list[DocumentItem]]:
    """Run a spider synchronously and collect all yielded items.

    Args:
        spider_class_path: Dotted path to spider class
        limit: Max items to collect per endpoint

    Returns:
        Tuple of (well_items, document_items)
    """
    spider_cls = load_spider_class(spider_class_path)
    # Pass limit and max_records to handle different spider signatures
    try:
        spider = spider_cls(limit=str(limit), max_records=str(limit), batch_size=str(min(limit, 1000)))
    except TypeError:
        spider = spider_cls()

    wells: list[WellItem] = []
    docs: list[DocumentItem] = []

    # Get the start requests
    try:
        start_requests = list(spider.start_requests())
    except Exception as e:
        logger.error("Failed to get start_requests: %s", e)
        return wells, docs

    client = httpx.Client(
        timeout=30.0,
        follow_redirects=True,
        headers={"User-Agent": "OGDocScraper/1.0 (research)"},
    )

    try:
        for request in start_requests:
            url = request.url
            callback = request.callback or spider.parse
            meta = request.meta or {}

            logger.info("Fetching %s", url)
            try:
                resp = client.get(url)
                if resp.status_code >= 400:
                    logger.warning("HTTP %d for %s", resp.status_code, url)
                    spider.errors += 1
                    continue
            except Exception as e:
                logger.warning("Failed to fetch %s: %s", url, e)
                spider.errors += 1
                continue

            # Build a real Scrapy TextResponse so spider parse methods work
            scrapy_req = ScrapyRequest(url=str(resp.url), meta=meta)
            scrapy_headers = {k.encode(): [v.encode()] for k, v in resp.headers.items()}
            fake_resp = TextResponse(
                url=str(resp.url),
                body=resp.content,
                encoding="utf-8",
                request=scrapy_req,
                headers=scrapy_headers,
            )

            try:
                raw_items = list(callback(fake_resp))
                items = raw_items
                logger.info("Parsed %s: %d raw items yielded", url, len(raw_items))
            except Exception as e:
                logger.warning("Failed to parse %s: %s", url, e)
                spider.errors += 1
                continue

            for item in items:
                if isinstance(item, WellItem):
                    wells.append(item)
                elif isinstance(item, DocumentItem):
                    docs.append(item)
                # Skip Scrapy Request objects (pagination etc.)

            logger.info(
                "Fetched %s: %d wells, %d docs so far",
                url, len(wells), len(docs),
            )
    finally:
        client.close()

    logger.info(
        "Spider %s finished: %d wells, %d documents",
        spider.name, len(wells), len(docs),
    )
    return wells, docs
