"""User-Agent rotation middleware."""

import random


# Realistic browser User-Agent strings
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:133.0) Gecko/20100101 Firefox/133.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.2 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
]

# The bot identifier used when robots.txt requires it
BOT_USER_AGENT = "OGDocScraper/1.0 (Research tool; oil-gas-regulatory-data)"


class UserAgentRotatorMiddleware:
    """Rotates User-Agent strings for non-Playwright requests.

    Playwright requests already have a real browser UA, so this
    middleware only applies to standard Scrapy HTTP requests.
    For robots.txt requests, the bot UA is always used.
    """

    @classmethod
    def from_crawler(cls, crawler):
        return cls()

    def process_request(self, request, spider):
        # Don't override for Playwright requests (they have real browser UAs)
        if request.meta.get("playwright"):
            return None

        # Use bot UA for robots.txt
        if "robots.txt" in request.url:
            request.headers["User-Agent"] = BOT_USER_AGENT
            return None

        # Rotate UA for regular requests
        request.headers["User-Agent"] = random.choice(USER_AGENTS)
        return None
