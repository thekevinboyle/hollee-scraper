"""Per-domain rate limiting middleware."""

import logging
import random
import time
from collections import defaultdict

logger = logging.getLogger(__name__)


class PerDomainRateLimitMiddleware:
    """Adds per-domain rate limiting with jitter.

    Tracks the last request time per domain and enforces a minimum
    delay with +/- 30% random jitter to avoid detection patterns.
    """

    def __init__(self):
        self._last_request_time: dict[str, float] = defaultdict(float)

    @classmethod
    def from_crawler(cls, crawler):
        return cls()

    def process_request(self, request, spider):
        domain = request.url.split("//")[-1].split("/")[0]
        delay = getattr(spider, "rate_limit_delay", 5.0)

        # Add jitter: +/- 30%
        jitter = delay * 0.3 * (2 * random.random() - 1)
        actual_delay = max(0.5, delay + jitter)

        elapsed = time.time() - self._last_request_time[domain]
        if elapsed < actual_delay:
            wait = actual_delay - elapsed
            logger.debug(f"Rate limiting {domain}: waiting {wait:.1f}s")
            time.sleep(wait)

        self._last_request_time[domain] = time.time()
        return None
