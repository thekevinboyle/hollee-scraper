"""Scrapy settings for the Oil & Gas Document Scraper."""

# --- Bot identity ---
BOT_NAME = "og-doc-scraper"
USER_AGENT = "OGDocScraper/1.0 (Research tool; oil-gas-regulatory-data)"

# --- Spider modules ---
SPIDER_MODULES = ["og_scraper.scrapers.spiders"]
NEWSPIDER_MODULE = "og_scraper.scrapers.spiders"

# --- scrapy-playwright Download Handlers ---
DOWNLOAD_HANDLERS = {
    "http": "scrapy_playwright.handler.ScrapyPlaywrightDownloadHandler",
    "https": "scrapy_playwright.handler.ScrapyPlaywrightDownloadHandler",
}
TWISTED_REACTOR = "twisted.internet.asyncioreactor.AsyncioSelectorReactor"

# --- Playwright Browser Config ---
PLAYWRIGHT_BROWSER_TYPE = "chromium"
PLAYWRIGHT_LAUNCH_OPTIONS = {
    "headless": True,
    "args": ["--disable-blink-features=AutomationControlled", "--no-sandbox"],
}
PLAYWRIGHT_MAX_PAGES_PER_CONTEXT = 4
PLAYWRIGHT_MAX_CONTEXTS = 4
PLAYWRIGHT_DEFAULT_NAVIGATION_TIMEOUT = 30_000  # 30 seconds
PLAYWRIGHT_ABORT_REQUEST = lambda req: req.resource_type in ["image", "stylesheet", "font", "media"]
PLAYWRIGHT_RESTART_DISCONNECTED_BROWSER = True

# --- Concurrency & Rate Limiting ---
CONCURRENT_REQUESTS = 4
CONCURRENT_REQUESTS_PER_DOMAIN = 2
DOWNLOAD_DELAY = 5
DOWNLOAD_TIMEOUT = 60

# --- AutoThrottle ---
AUTOTHROTTLE_ENABLED = True
AUTOTHROTTLE_START_DELAY = 5
AUTOTHROTTLE_MAX_DELAY = 60
AUTOTHROTTLE_TARGET_CONCURRENCY = 1.0

# --- Retry ---
RETRY_ENABLED = True
RETRY_TIMES = 5
RETRY_HTTP_CODES = [500, 502, 503, 504, 408, 429]
RETRY_PRIORITY_ADJUST = -1

# --- Respectful Crawling ---
ROBOTSTXT_OBEY = True

# --- Item Pipelines (ordered by priority) ---
ITEM_PIPELINES = {
    "og_scraper.scrapers.pipelines.validation.ValidationPipeline": 100,
    "og_scraper.scrapers.pipelines.deduplication.DeduplicationPipeline": 300,
    "og_scraper.scrapers.pipelines.storage.FileStoragePipeline": 400,
}

# --- File Storage ---
FILES_STORE = "data/"

# --- Logging ---
LOG_LEVEL = "INFO"
LOG_FORMAT = "%(asctime)s [%(name)s] %(levelname)s: %(message)s"

# --- Downloader Middlewares ---
DOWNLOADER_MIDDLEWARES = {
    "og_scraper.scrapers.middlewares.rate_limiter.PerDomainRateLimitMiddleware": 100,
    "og_scraper.scrapers.middlewares.user_agent.UserAgentRotatorMiddleware": 200,
}
