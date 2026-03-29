# Web Scraping Architecture & Strategies Research

**Research Date:** 2026-03-27
**Project:** Oil & Gas Document Scraper
**Context:** Scraping regulatory documents from 50+ US state government sites with varying technology stacks, from static HTML to JavaScript-heavy portals.

---

## Table of Contents

1. [Framework Comparison](#1-framework-comparison)
2. [Recommended Architecture: Scrapy + Playwright Hybrid](#2-recommended-architecture-scrapy--playwright-hybrid)
3. [HTTP Client Libraries](#3-http-client-libraries)
4. [Anti-Bot Evasion Strategies](#4-anti-bot-evasion-strategies)
5. [CAPTCHA Handling](#5-captcha-handling)
6. [Proxy Services & IP Rotation](#6-proxy-services--ip-rotation)
7. [Crawl Scheduling & Queue Management](#7-crawl-scheduling--queue-management)
8. [Pagination, Search Forms & Dynamic Content](#8-pagination-search-forms--dynamic-content)
9. [Retry & Resilience Patterns](#9-retry--resilience-patterns)
10. [Incremental Scraping & Deduplication](#10-incremental-scraping--deduplication)
11. [Storage Strategies](#11-storage-strategies)
12. [Site Change Detection & Monitoring](#12-site-change-detection--monitoring)
13. [Architecture Pattern: Per-State Adapter](#13-architecture-pattern-per-state-adapter)
14. [Legal Considerations](#14-legal-considerations)
15. [Oil & Gas State Site Landscape](#15-oil--gas-state-site-landscape)
16. [Final Recommendation: System Architecture](#16-final-recommendation-system-architecture)

---

## 1. Framework Comparison

### Scrapy (Python)

**Strengths:**
- Purpose-built for large-scale web crawling with an asynchronous, event-driven architecture
- Built-in support for: request queuing, automatic retries, configurable concurrency, data export (JSON/CSV/XML), item pipelines, middleware system, proxy integration, IP rotation
- Handles millions of pages efficiently via direct HTTP requests (no browser overhead)
- Mature ecosystem with extensive middleware: `scrapy-redis` for distributed crawling, `scrapy-playwright` for JS rendering, `scrapy-deltafetch` for incremental scraping
- Component-based architecture (spiders, middlewares, pipelines) maps cleanly to per-state adapters
- Performance: tied with Scrapling for fastest HTML parsing in Python

**Weaknesses:**
- Cannot execute JavaScript natively -- struggles with JS-rendered content without plugins
- Steeper learning curve due to modular architecture (spiders, middlewares, pipelines, items)
- Requires `scrapy-playwright` middleware for dynamic sites, adding complexity

### Playwright (Python)

**Strengths:**
- Full browser automation: renders JavaScript, handles SPAs (React/Angular/Vue), infinite scroll, complex form interactions
- Native Python support (unlike Puppeteer which requires Node.js or unofficial ports)
- Multi-browser support: Chromium, Firefox, WebKit -- both headed and headless
- Smart auto-waiting for elements/network calls -- less flaky than Selenium
- Modern API, easier to write and maintain than Selenium
- Playwright Stealth plugin (v2.0.2, Feb 2026) masks automation markers to evade bot detection
- Playwright Extra extends functionality with anti-detection plugins

**Weaknesses:**
- Slower than Scrapy -- must render full pages in a browser environment
- Higher resource consumption (memory, CPU) per request
- No built-in crawling framework -- must build queue management, retry logic, data pipelines yourself
- Not designed for large-scale crawling without significant infrastructure work

### Selenium

**Strengths:**
- Longest track record (10+ years), massive community and resources
- Broadest browser support including Safari and Edge
- Well-understood in enterprise environments with legacy system integration

**Weaknesses:**
- Slower and more fragile than Playwright for scraping use cases
- Requires more explicit waits and conditions for dynamic content
- More verbose API compared to Playwright
- **Verdict: Not recommended for new projects in 2025-2026.** Playwright supersedes Selenium for scraping.

### Puppeteer (Node.js)

**Strengths:**
- Maintained by Chrome DevTools team, excellent Chrome integration
- Strong Node.js ecosystem, fast for simple Chrome-based scraping

**Weaknesses:**
- Only supports Chromium (limited Firefox support)
- Node.js only -- no native Python support (pyppeteer is unofficial and poorly maintained)
- **Verdict: Not recommended if using Python.** Playwright has native Python support and broader browser coverage.

### BeautifulSoup + Requests

**Strengths:**
- Simplest possible approach for static HTML parsing
- Excellent for quick prototyping and simple page structures
- Minimal dependencies and learning curve

**Weaknesses:**
- No JavaScript execution, no browser automation
- No built-in crawling, retries, or concurrency
- Not suitable as a standalone framework for this project's scale
- Best used as a parsing component within Scrapy item pipelines

### Scrapling (New -- 2025-2026)

**Strengths:**
- Adaptive element tracking -- automatically relocates selectors when HTML structure changes
- Performance on par with Scrapy for HTML parsing
- Built-in anti-bot bypass (Cloudflare Turnstile)
- Spider framework with pause/resume and auto proxy rotation
- 10.6k GitHub stars, active development (v0.4, Feb 2026)

**Weaknesses:**
- Relatively new, smaller ecosystem than Scrapy
- Less battle-tested at production scale
- **Verdict: Worth monitoring.** Could be valuable for self-healing selectors but too young to bet the architecture on.

---

## 2. Recommended Architecture: Scrapy + Playwright Hybrid

### Why Hybrid?

Government oil & gas sites present a mixed landscape:
- **Most state sites (estimated 60-70%)** serve static HTML or simple server-rendered pages -- Scrapy handles these efficiently with direct HTTP requests
- **Some sites (estimated 30-40%)** use JavaScript-heavy frameworks, dynamic search forms, or require browser interaction -- these need Playwright

The `scrapy-playwright` middleware is the best-of-both-worlds solution.

### How scrapy-playwright Works

```python
# settings.py
DOWNLOAD_HANDLERS = {
    "http": "scrapy_playwright.handler.ScrapyPlaywrightDownloadHandler",
    "https": "scrapy_playwright.handler.ScrapyPlaywrightDownloadHandler",
}
TWISTED_REACTOR = "twisted.internet.asyncioreactor.AsyncioSelectorReactor"

PLAYWRIGHT_BROWSER_TYPE = "chromium"
PLAYWRIGHT_LAUNCH_OPTIONS = {"headless": True}
PLAYWRIGHT_MAX_PAGES_PER_CONTEXT = 4
PLAYWRIGHT_DEFAULT_NAVIGATION_TIMEOUT = 30000  # 30s

# Abort unnecessary resources for speed
PLAYWRIGHT_ABORT_REQUEST = lambda req: req.resource_type in ["image", "stylesheet", "font", "media"]
```

```python
# In spider: selectively use Playwright only where needed
class TexasRRCSpider(scrapy.Spider):
    name = "texas_rrc"

    def start_requests(self):
        # Static page -- use default HTTP handler (fast)
        yield scrapy.Request("https://www.rrc.texas.gov/oil-and-gas/data-sets/",
                             callback=self.parse_data_sets)

        # JS-heavy search form -- use Playwright (slower but necessary)
        yield scrapy.Request("https://webapps.rrc.texas.gov/...",
                             meta={"playwright": True},
                             callback=self.parse_search_results)
```

### Key Configuration Options

| Setting | Purpose | Recommendation |
|---------|---------|----------------|
| `PLAYWRIGHT_BROWSER_TYPE` | Browser engine | `"chromium"` for best compatibility |
| `PLAYWRIGHT_MAX_PAGES_PER_CONTEXT` | Concurrent browser pages | 4-8 per context |
| `PLAYWRIGHT_MAX_CONTEXTS` | Browser context limit | Match to CONCURRENT_REQUESTS |
| `PLAYWRIGHT_ABORT_REQUEST` | Block unnecessary resources | Block images, fonts, media for speed |
| `PLAYWRIGHT_RESTART_DISCONNECTED_BROWSER` | Auto-restart crashed browsers | `True` (default) |
| `PLAYWRIGHT_CDP_URL` | Remote browser via CDP | Use for Browserless/cloud browsers |
| `PLAYWRIGHT_PROCESS_REQUEST_HEADERS` | Header injection control | Default emulates Scrapy behavior |

### Pros of the Hybrid Approach

- Static pages get Scrapy's full speed (direct HTTP, no browser overhead)
- Dynamic pages get Playwright's full browser rendering
- Single codebase, single framework, single pipeline for data processing
- Per-request routing: each spider decides which pages need Playwright
- Scrapy's built-in retry, middleware, and pipeline systems apply to both types
- Can run Playwright in headed mode for debugging, headless for production

### Cons / Limitations

- Playwright pages consume significantly more memory than plain HTTP requests
- Windows compatibility requires ProactorEventLoop workarounds
- Must carefully manage concurrency to avoid browser memory exhaustion
- Cannot use persistent browser contexts with auto-restart feature

---

## 3. HTTP Client Libraries

For requests that don't need Scrapy or Playwright (e.g., direct API calls, file downloads):

| Library | Async Support | HTTP/2 | Best For |
|---------|--------------|--------|----------|
| **httpx** | Sync + Async | Yes | Modern default. Best balance of features and ease. |
| **aiohttp** | Async only | No | Highest throughput for massive concurrent requests |
| **requests** | Sync only | No | Simple scripts, prototyping |

**Recommendation:** Use `httpx` for any standalone HTTP requests outside of Scrapy spiders. Its HTTP/2 support and sync+async flexibility make it the best modern default.

---

## 4. Anti-Bot Evasion Strategies

### Government Site Threat Landscape

Government sites generally have **less aggressive** anti-bot protection than commercial sites, but some do employ:
- Basic rate limiting (IP-based)
- Session-based access controls
- Simple bot detection (checking for headless browser markers)
- The Texas Railroad Commission explicitly warns: "The use of automated tools to retrieve volumes of data can cause severe degradation... if the query system detects automated data retrieval, the RRC will end the session"

### Evasion Strategy Layers

**Layer 1: Request Hygiene (Always Apply)**
- Realistic User-Agent rotation (maintain a pool of 20+ current browser UAs)
- Complete HTTP headers matching real browsers (Accept, Accept-Language, Accept-Encoding, Referer, sec-ch-ua)
- Respect `robots.txt` crawl-delay directives
- Conservative rate limiting: 1 request per 10-15 seconds per domain as a safe baseline
- Randomize delays between requests (add jitter: base_delay +/- 30%)

**Layer 2: Browser Fingerprint Masking (For Playwright Requests)**
- Use `playwright-stealth` (v2.0.2) to:
  - Remove `navigator.webdriver` flag
  - Spoof browser plugins and WebGL metadata
  - Mock Chrome runtime object
  - Fix missing browser quirks detected by bot detection
- Use `playwright-extra` for additional evasion plugins
- Rotate browser viewport sizes and screen resolutions
- Set realistic timezone and locale settings

**Layer 3: IP & Session Management**
- Rotate IP addresses via proxy pool (see Section 6)
- Maintain separate sessions per state site
- Use residential proxies for sites with strict IP filtering
- Rotate session cookies periodically

**Layer 4: Behavioral Simulation (If Needed)**
- Simulate realistic mouse movements and scroll patterns
- Add random pauses between actions
- Vary navigation patterns (don't always follow the same path)
- Click through intermediate pages rather than jumping directly to deep URLs

### Detection Systems to Be Aware Of

Modern anti-bot systems combine multiple signals into a trust score:
- IP reputation
- TLS fingerprints
- Browser fingerprints
- HTTP header consistency
- Behavioral analysis
- JavaScript challenges

For government sites, layers 1-2 should be sufficient in most cases. Layers 3-4 are fallbacks for particularly restrictive sites.

---

## 5. CAPTCHA Handling

### Common CAPTCHAs on Government Sites

Government sites occasionally use:
- **reCAPTCHA v2** (image selection challenges) -- most common
- **reCAPTCHA v3** (invisible scoring) -- increasingly common
- **Simple image CAPTCHAs** (text in distorted images) -- on older sites
- **Cloudflare Turnstile** -- on modernized government sites

### CAPTCHA Solving Services (2026 Landscape)

| Service | Type | reCAPTCHA v2 Cost | Speed | Notes |
|---------|------|-------------------|-------|-------|
| **CapSolver** | AI-based | ~$1-2/1000 | Sub-second | 99%+ accuracy, handles reCAPTCHA, hCaptcha, Turnstile |
| **2Captcha** | Hybrid (AI + human) | ~$1-3/1000 | 10-30s | Long-running, reliable, good for complex CAPTCHAs |
| **Anti-Captcha** | Hybrid | ~$1-3/1000 | 10-30s | Similar to 2Captcha, good API |
| **Bright Data CAPTCHA Solver** | AI-based | Bundled with proxy | Fast | Integrated with their proxy/unlocker product |

### Industry Trend: Web Unlockers

The market has shifted toward "Web Unlockers" -- fully managed APIs that handle:
- Proxy rotation
- Browser fingerprinting
- CAPTCHA solving
- All in a single API call

Services like Bright Data Web Unlocker, ScraperAPI, and Scrapfly eliminate the need to manage separate CAPTCHA solvers.

### Recommendation for This Project

1. **First priority:** Avoid CAPTCHAs entirely through respectful rate limiting and proper browser fingerprinting
2. **Second priority:** Use state-provided bulk data downloads and APIs where available (many O&G commissions offer these)
3. **Third priority:** Integrate CapSolver or 2Captcha API for sites that consistently present CAPTCHAs
4. **Budget consideration:** At typical government site scraping volumes (thousands, not millions of pages), CAPTCHA costs should be under $50/month

---

## 6. Proxy Services & IP Rotation

### When Proxies Are Needed

For government sites specifically:
- **Low priority sites** (no rate limiting): Direct connection is fine
- **Medium priority** (rate limiting detected): Datacenter proxies with rotation
- **High priority** (aggressive blocking like Texas RRC): Residential proxies

### Proxy Provider Comparison (2026)

| Provider | Pool Size | Residential Cost | Best For |
|----------|-----------|------------------|----------|
| **Bright Data** | 72M+ residential IPs | $5.04/GB | Enterprise, largest pool, best geo-targeting |
| **Oxylabs** | 100M+ residential IPs | $8/GB | Enterprise, compliance-focused, city-level targeting |
| **ScraperAPI** | Managed pool | $49/mo (100K requests) | Getting started, handles proxies + CAPTCHAs |
| **Decodo (Smartproxy)** | 115M+ residential IPs | $2.20/GB | Best value for mid-scale |
| **IPRoyal** | 8M+ residential IPs | $1.75/GB | Budget option for starting out |

### Proxy Types

| Type | Trust Level | Speed | Cost | Use Case |
|------|------------|-------|------|----------|
| **Datacenter** | Low | Fast | $0.50-2/GB | Bulk scraping on permissive sites |
| **Residential** | High | Medium | $2-10/GB | Sites with IP reputation checks |
| **ISP** | Very High | Fast | $3-15/GB | When residential gets flagged |
| **Mobile** | Highest | Slow | $10-30/GB | Last resort for hardest sites |

### Recommendation for This Project

- **Start with ScraperAPI** ($49-99/mo) for simplicity -- it handles proxy rotation, retries, and basic CAPTCHA solving in one API
- **Graduate to Bright Data or Decodo** residential proxies if ScraperAPI isn't sufficient for specific state sites
- **Implement intelligent proxy health tracking:** bench proxies after 3 consecutive failures, auto-recover after cooldown period
- **Budget estimate:** $100-300/month for scraping all major O&G state sites at moderate frequency

---

## 7. Crawl Scheduling & Queue Management

### Architecture Levels

| Level | Description | URLs/Run | When to Use |
|-------|-------------|----------|-------------|
| **Level 1: Single Script** | Python script with in-memory processing | < 1,000 | Prototyping, single-site testing |
| **Level 2: Queue-Based** | Redis/RabbitMQ queue + workers + DB | 1K - 100K | Production for this project |
| **Level 3: Distributed** | Multiple worker nodes + centralized queue | 100K - millions | If scale requires it |
| **Level 4: Managed Platform** | Apify, Bright Data, etc. | Any | When infra maintenance is too costly |

### Recommended Stack: Scrapy + Redis + Celery Beat

```
[Celery Beat Scheduler]
        |
        v
[Redis Queue] <-- URL feed from state registry
        |
        v
[Scrapy Workers (1-N)] --> [Item Pipelines] --> [Database + S3]
        |
        v
[Flower Dashboard] -- monitoring
```

**Components:**

- **Celery Beat:** Triggers scraping jobs on schedule (daily, weekly per state)
  ```python
  # Example schedule
  beat_schedule = {
      'scrape-texas-daily': {
          'task': 'scraper.tasks.scrape_state',
          'schedule': crontab(hour=2, minute=0),  # 2 AM daily
          'args': ('texas',),
      },
      'scrape-oklahoma-weekly': {
          'task': 'scraper.tasks.scrape_state',
          'schedule': crontab(hour=3, minute=0, day_of_week='monday'),
          'args': ('oklahoma',),
      },
  }
  ```

- **Redis:** Message broker + URL deduplication store + scrape state tracking
- **Scrapy-Redis:** Distributed spider support, shared request queue
- **Celery Workers:** Execute scraping tasks, auto-retry on failure
- **Flower:** Web dashboard for monitoring queue sizes, worker health, retry rates

### Queue Routing for Priority

```python
# Prevent slow sites from blocking fast ones
CELERY_TASK_ROUTES = {
    'scraper.tasks.scrape_texas': {'queue': 'high_volume'},
    'scraper.tasks.scrape_oklahoma': {'queue': 'high_volume'},
    'scraper.tasks.scrape_small_state': {'queue': 'low_volume'},
}
```

### Performance Expectations

- Single-machine Scrapy: ~1,000-5,000 pages/hour (with rate limiting)
- Distributed (3-5 workers): ~5,000-20,000 pages/hour
- With Playwright (browser rendering): ~200-500 pages/hour per worker

---

## 8. Pagination, Search Forms & Dynamic Content

### Pagination Types on Government Sites

**Type 1: URL-Parameter Pagination (Most Common on Gov Sites)**
```
https://site.gov/results?page=1
https://site.gov/results?page=2
https://site.gov/results?offset=25&limit=25
```
- Handle with simple Scrapy URL generation
- Iterate until empty results or known page count

**Type 2: Form-Based Search with POST Pagination**
- Many state sites require form submission to search for wells/operators
- Results paginated via POST requests with hidden form fields (ViewState, etc.)
- Handle with Scrapy FormRequest or Playwright for complex JS forms

**Type 3: AJAX/API-Driven Pagination**
- Inspect network tab to find underlying API endpoints
- Often use JSON responses with cursor/offset parameters
- Replicate API calls directly with httpx/Scrapy (skip the browser entirely)

**Type 4: Infinite Scroll / Load More**
- Less common on government sites but present on modernized portals
- Handle with Playwright: scroll to bottom, wait for new content, repeat
- Or intercept the underlying AJAX calls and replicate them directly

### Search Form Handling Strategy

1. **Inspect the form:** Determine if it submits via GET, POST, or AJAX
2. **Check for underlying API:** Use browser DevTools Network tab to find XHR/Fetch requests -- often the fastest approach
3. **For simple forms:** Use Scrapy's `FormRequest` with appropriate parameters
4. **For JavaScript-heavy forms:** Use Playwright with `scrapy-playwright`:
   ```python
   yield scrapy.Request(
       url="https://state-site.gov/search",
       meta={
           "playwright": True,
           "playwright_page_methods": [
               PageMethod("fill", "#operator-name", "Devon Energy"),
               PageMethod("click", "#search-button"),
               PageMethod("wait_for_selector", ".results-table"),
           ],
       },
       callback=self.parse_results,
   )
   ```

### Best Practices

- Always look for bulk data downloads first (many O&G commissions provide these)
- Identify API endpoints behind search forms before resorting to browser automation
- Handle empty result pages gracefully -- don't loop forever
- Track pagination state to support resume-after-failure

---

## 9. Retry & Resilience Patterns

### Government Site Failure Modes

Government websites are notoriously unreliable:
- Random 500 errors on aging infrastructure
- Timeout on database-heavy queries
- Maintenance windows (often unannounced)
- Session expiration during long crawls
- Rate limiting returning 403/429 responses
- Connection resets under load

### Retry Strategy: Exponential Backoff with Jitter

```python
# Using tenacity library
from tenacity import retry, wait_random_exponential, stop_after_attempt, retry_if_exception_type

@retry(
    wait=wait_random_exponential(min=2, max=120),  # 2s to 2min
    stop=stop_after_attempt(5),
    retry=retry_if_exception_type((TimeoutError, ConnectionError, ServerError))
)
async def fetch_page(url):
    ...
```

**Scrapy built-in retry settings:**
```python
# settings.py
RETRY_ENABLED = True
RETRY_TIMES = 5
RETRY_HTTP_CODES = [500, 502, 503, 504, 408, 429]
DOWNLOAD_TIMEOUT = 30
RETRY_PRIORITY_ADJUST = -1  # Lower priority for retried requests
```

### Circuit Breaker Pattern

Prevent hammering a site that's clearly down:

```python
import pybreaker

state_breaker = pybreaker.CircuitBreaker(
    fail_max=5,           # Open after 5 consecutive failures
    reset_timeout=300,    # Try again after 5 minutes
    exclude=[lambda e: isinstance(e, (NotFoundError,))]  # Don't trip on 404s
)
```

**Circuit breaker states:**
- **CLOSED:** Normal operation, requests flow through
- **OPEN:** Site is down, fail immediately without sending requests (saves resources, avoids bans)
- **HALF-OPEN:** After timeout, allow one test request to check recovery

### Silent Failure Detection

HTTP 200 responses can still contain bad data:

```python
# Validate scraped data with Pydantic
from pydantic import BaseModel, validator

class WellRecord(BaseModel):
    api_number: str
    operator: str
    state: str

    @validator('api_number')
    def validate_api(cls, v):
        if not re.match(r'^\d{2}-\d{3}-\d{5}$', v):
            raise ValueError(f'Invalid API number: {v}')
        return v
```

### Resilience Architecture

```
Request --> Rate Limiter --> Circuit Breaker --> Retry (with backoff) --> Proxy Rotation --> Target
                                                        |
                                                        v (on failure)
                                                  Dead Letter Queue --> Alert + Manual Review
```

### Per-Domain Rate Limiting

```python
# Scrapy AutoThrottle -- adjusts delay based on server response time
AUTOTHROTTLE_ENABLED = True
AUTOTHROTTLE_START_DELAY = 5
AUTOTHROTTLE_MAX_DELAY = 60
AUTOTHROTTLE_TARGET_CONCURRENCY = 1.0  # Conservative for gov sites
```

---

## 10. Incremental Scraping & Deduplication

### Core Strategies

**Strategy 1: URL-Based Tracking**
- Maintain a database table of all scraped URLs with timestamps
- On each run, check if URL has been visited before
- Use `scrapy-deltafetch` middleware with Redis/SQLite backend

**Strategy 2: Content Hash Fingerprinting**
- Compute SHA-256 hash of downloaded document content
- Store hash in database alongside metadata
- Skip documents with matching hashes (even if URL changed)
- Detect duplicates across different state sites that mirror content

**Strategy 3: HTTP Conditional Requests**
- Send `If-Modified-Since` header with last scrape timestamp
- Send `If-None-Match` with stored ETag value
- Server responds with 304 (Not Modified) if content unchanged
- Saves bandwidth and processing time
- Note: many government sites don't support conditional requests properly

**Strategy 4: Timestamp Monitoring**
- Track "last updated" dates on listing pages
- Only visit detail pages with newer timestamps
- Works well for sites that display modification dates

**Strategy 5: Deep Pagination with Known-ID Cutoff**
- Maintain set of known document IDs
- Paginate through results until encountering previously-seen IDs
- Stop when consecutive known results exceed threshold (e.g., 10 in a row)

### Implementation Architecture

```python
class IncrementalMiddleware:
    """Skip already-scraped URLs unless force_refresh is set."""

    def __init__(self):
        self.seen_urls = redis.Redis()  # Redis set with 30-day expiry
        self.content_hashes = {}  # DB-backed hash store

    def process_request(self, request, spider):
        url_hash = hashlib.sha256(request.url.encode()).hexdigest()

        if not request.meta.get('force_refresh'):
            if self.seen_urls.sismember('scraped_urls', url_hash):
                raise IgnoreRequest(f"Already scraped: {request.url}")

    def process_response(self, request, response, spider):
        # Store URL as seen
        url_hash = hashlib.sha256(request.url.encode()).hexdigest()
        self.seen_urls.sadd('scraped_urls', url_hash)
        self.seen_urls.expire('scraped_urls', 30 * 86400)  # 30-day expiry
        return response
```

### State Tracking Database Schema

```sql
CREATE TABLE scrape_state (
    id SERIAL PRIMARY KEY,
    state_code VARCHAR(2) NOT NULL,
    site_url TEXT NOT NULL,
    last_scrape_at TIMESTAMP,
    last_successful_at TIMESTAMP,
    last_document_date DATE,      -- Most recent document found
    total_documents_scraped INT,
    status VARCHAR(20),           -- 'active', 'failed', 'paused'
    error_message TEXT,
    next_scrape_at TIMESTAMP
);

CREATE TABLE scraped_documents (
    id SERIAL PRIMARY KEY,
    source_url TEXT NOT NULL,
    content_hash VARCHAR(64) NOT NULL,  -- SHA-256
    file_path TEXT,                      -- S3 key or local path
    state_code VARCHAR(2),
    document_type VARCHAR(50),
    scraped_at TIMESTAMP DEFAULT NOW(),
    file_size_bytes BIGINT,
    http_status INT,
    UNIQUE(content_hash)                -- Prevent duplicate storage
);
```

---

## 11. Storage Strategies

### Recommended: Hybrid Storage Architecture

```
Downloaded Documents (PDFs, XLSX, etc.)  -->  Object Storage (S3 / MinIO)
Extracted Metadata + Structured Data     -->  PostgreSQL Database
URL Queue + Scrape State + Dedup Cache   -->  Redis
Search Index (optional)                  -->  Elasticsearch
```

### Document Storage: S3 / MinIO

**Why object storage for documents:**
- Scalable to petabytes without infrastructure changes
- Content-addressable storage via hash-based keys enables natural deduplication
- Cheap storage ($0.023/GB/month on S3 Standard)
- No filesystem limits on file count
- Built-in versioning for tracking document updates
- MinIO provides S3-compatible local alternative for development

**Key design: Content-addressable paths**
```
s3://og-documents/
  tx/                        # State prefix
    2026/03/                  # Date prefix (scrape date)
      sha256_abc123.pdf       # Content hash as filename
      sha256_def456.xlsx
  ok/
    2026/03/
      sha256_789ghi.pdf
```

- Content hash as filename guarantees deduplication at the storage level
- State and date prefixes enable efficient listing and lifecycle policies
- Metadata (original filename, source URL, document type) stored in database, not filesystem

**Scrapy S3 integration (built-in):**
```python
# settings.py -- Scrapy's Files Pipeline uploads directly to S3
FILES_STORE = 's3://og-documents/'
AWS_ACCESS_KEY_ID = '...'
AWS_SECRET_ACCESS_KEY = '...'
```

### Database Storage: PostgreSQL

**Why PostgreSQL:**
- Rich querying for metadata (find all production reports for operator X in state Y)
- JSON columns for flexible, state-specific metadata fields
- Full-text search capability
- PostGIS extension for spatial queries (well coordinates)
- Mature, reliable, well-supported

**Do NOT store documents as database BLOBs:**
- BLOBs bloat the database, complicate backups, degrade query performance
- Object storage is purpose-built for binary files
- Database should only store metadata + S3 keys

### Redis

**Use for:**
- URL queue and deduplication (30-day expiry sets)
- Scrape state caching (last scraped timestamps)
- Rate limiter state (per-domain request counters)
- Celery message broker

### Local Filesystem (Development Only)

For local development and testing:
```
data/
  raw/                      # Raw downloaded files
    tx/2026-03-27/
      abc123.pdf
  processed/                # Extracted/classified data
    tx/2026-03-27/
      abc123.json
  logs/
    scrape-2026-03-27.jsonl
```

### Storage Cost Estimates

| Component | Estimated Size | Monthly Cost |
|-----------|---------------|--------------|
| S3 (documents) | 50-200 GB | $1-5/month |
| PostgreSQL (RDS) | 10-50 GB | $15-50/month |
| Redis (ElastiCache) | 1-2 GB | $15-30/month |
| **Total** | | **$31-85/month** |

---

## 12. Site Change Detection & Monitoring

### The Problem

Government sites redesign without warning. Scraper breakage rates across the industry are 10-15% of crawlers requiring weekly fixes due to DOM changes, fingerprinting, or endpoint throttling.

### Detection Strategies

**Strategy 1: Schema Validation on Extracted Data**
```python
# If a spider suddenly returns empty fields, the site probably changed
class ValidationPipeline:
    def process_item(self, item, spider):
        required_fields = ['api_number', 'operator', 'document_type']
        missing = [f for f in required_fields if not item.get(f)]
        if missing:
            spider.logger.error(f"Missing fields: {missing} -- possible site change")
            alert_team(spider.name, missing)
        return item
```

**Strategy 2: Structural Fingerprinting**
- Hash the CSS selector paths of key page elements
- Compare against stored fingerprints on each run
- Alert when fingerprints change (even if data still extracts successfully)

**Strategy 3: Response Pattern Monitoring**
- Track success rate per spider over time
- Alert when success rate drops below threshold (e.g., < 90%)
- Track average items extracted per page -- sudden drop indicates breakage

**Strategy 4: Visual Regression (Advanced)**
- Screenshot key pages periodically
- Compare against baseline screenshots using perceptual hashing
- Flag significant visual changes for manual review

### Monitoring Dashboard Metrics

| Metric | Alert Threshold | Action |
|--------|----------------|--------|
| Spider success rate | < 90% over 24h | Investigate site changes |
| Items per page | < 50% of average | Check selectors |
| Empty required fields | > 10% of items | Review extraction logic |
| HTTP error rate | > 20% | Check site availability |
| Scrape duration | > 200% of average | Check for new anti-bot measures |
| Zero documents found | Any occurrence | Immediate alert |

### Self-Healing Approaches

- **Scrapling's adaptive selectors:** Auto-relocate elements using similarity algorithms when HTML changes
- **AI-assisted repair:** Use LLMs to analyze new page structure and suggest updated selectors
- **Fallback selectors:** Define primary + backup selectors for critical elements
- **Version-aware selectors:** Track multiple selector versions per site, fall back to older patterns

### Practical Recommendation

1. Implement schema validation (Strategy 1) as the minimum baseline -- catches most breakages
2. Add success rate monitoring (Strategy 3) for early warning
3. Consider Scrapling for adaptive selectors on the most volatile sites
4. Run a weekly "health check" spider that validates all state sites are accessible and returning expected page structures

---

## 13. Architecture Pattern: Per-State Adapter

### Why Per-State Adapters?

Every state O&G commission site is different:
- Different URL structures
- Different HTML layouts
- Different search interfaces
- Different document formats and naming conventions
- Different pagination patterns
- Some offer APIs, some are pure HTML, some are JS-heavy

A monolithic scraper cannot handle this diversity. The per-state adapter pattern is the correct architecture.

### Design: Configuration-Driven Adapter Registry

```python
# State adapter registry -- each state gets its own configuration + spider
STATE_REGISTRY = {
    "TX": {
        "name": "Texas Railroad Commission",
        "base_url": "https://www.rrc.texas.gov",
        "spider_class": "TexasRRCSpider",
        "requires_playwright": False,  # Has bulk data downloads
        "rate_limit": 10,  # seconds between requests
        "priority": 1,  # Top producing state
        "document_types": ["production", "completion", "permit", "inspection"],
        "bulk_download_urls": [
            "https://www.rrc.texas.gov/resource-center/research/data-sets-available-for-download/"
        ],
        "search_url": "https://webapps.rrc.texas.gov/...",
        "schedule": "daily",
    },
    "OK": {
        "name": "Oklahoma Corporation Commission",
        "base_url": "https://oklahoma.gov/occ/divisions/oil-gas",
        "spider_class": "OklahomaCCSpider",
        "requires_playwright": True,  # JS-heavy search interface
        "rate_limit": 15,
        "priority": 2,
        "document_types": ["production", "well_data", "gis"],
        "bulk_download_urls": [
            "https://oklahoma.gov/occ/divisions/oil-gas/oil-gas-data.html"
        ],
        "schedule": "weekly",
    },
    # ... 48 more states
}
```

### Spider Base Class

```python
class BaseStateSpider(scrapy.Spider):
    """Base spider with common functionality for all state adapters."""

    def __init__(self, state_code, *args, **kwargs):
        self.state_config = STATE_REGISTRY[state_code]
        self.name = f"og_{state_code.lower()}"
        super().__init__(*args, **kwargs)

    # Common methods: pagination handling, document download,
    # metadata extraction, error handling, etc.

    def download_document(self, response):
        """Common document download + dedup logic."""
        content_hash = hashlib.sha256(response.body).hexdigest()
        # Check for duplicate, store to S3, record metadata
        ...

class TexasRRCSpider(BaseStateSpider):
    """Texas-specific scraping logic."""

    def start_requests(self):
        # Texas-specific: start with bulk data downloads
        for url in self.state_config['bulk_download_urls']:
            yield scrapy.Request(url, callback=self.parse_bulk_downloads)

    def parse_bulk_downloads(self, response):
        # Texas-specific parsing logic
        ...
```

### Adding a New State

The goal is that adding a new state is mostly configuration + a thin spider class:

1. Add entry to `STATE_REGISTRY` with URLs, rate limits, schedule
2. Create a spider class inheriting from `BaseStateSpider`
3. Implement state-specific parsing methods
4. Test with a limited crawl
5. Enable in production schedule

For states with simple structures, the spider class might be very thin (just URL patterns + CSS selectors). For complex states, it will have more custom logic.

### Directory Structure

```
scrapers/
  base/
    spider.py          # BaseStateSpider
    pipelines.py       # Common pipelines (dedup, classification, storage)
    middlewares.py      # Common middlewares (rate limiting, proxy, auth)
    items.py           # Common data models
  states/
    tx/
      spider.py        # TexasRRCSpider
      config.py        # Texas-specific configuration
      parsers.py       # Texas-specific parsing helpers
    ok/
      spider.py        # OklahomaCCSpider
      config.py
      parsers.py
    nd/
      spider.py
      config.py
      parsers.py
    # ... etc
  registry.py          # STATE_REGISTRY
  settings.py          # Scrapy settings
```

---

## 14. Legal Considerations

### Government Data: Generally Safe Territory

**Key legal principles:**

1. **hiQ v. LinkedIn (9th Circuit, affirmed 2022):** Scraping publicly available data does not violate the Computer Fraud and Abuse Act (CFAA). The court held that accessing data viewable without authentication is not "unauthorized access" under the CFAA.

2. **Public government data carries different protections** than private commercial data. Government records are subject to FOIA and state equivalents, establishing a strong presumption of public access.

3. **The simple test:** If you can view the data in an incognito browser window without logging in, it is public data, and scraping is likely legal under current US case law.

4. **No federal law prohibits web scraping** in the United States when scraping publicly accessible data that doesn't harm the website.

### Risk Areas to Watch

| Risk | Level | Mitigation |
|------|-------|------------|
| CFAA violation (accessing password-protected data) | **High** | Never scrape behind login walls without explicit authorization |
| Terms of Service violation | **Medium** | Review each state site's ToS; note that ToS violations are civil, not criminal |
| Server overload / denial of service | **Medium** | Implement strict rate limiting, respect robots.txt |
| Copyright on documents | **Low** | Government documents are generally not copyrightable (17 USC 105) |
| State-specific data access laws | **Low** | Some states have specific rules about bulk data access |
| GDPR/CCPA (personal data) | **Low** | O&G regulatory data is primarily about wells/companies, not individuals |

### Best Practices for Legal Compliance

1. **Respect robots.txt:** Check and obey robots.txt directives for every state site. While not legally binding, it demonstrates good faith.
2. **Rate limit aggressively:** Never send requests faster than the site can handle. The Texas RRC explicitly warns against automated retrieval.
3. **Identify your scraper:** Use a descriptive User-Agent that includes contact information: `OGDocScraper/1.0 (contact@company.com)`
4. **Prefer official data downloads:** Many state commissions offer bulk data downloads specifically for automated access. Use these instead of scraping where available.
5. **Don't circumvent access controls:** Never bypass login requirements, CAPTCHAs designed to gate access, or explicit technical blocks.
6. **Keep records:** Log all scraping activity, including timestamps, URLs, and response codes. This demonstrates responsible behavior if questioned.
7. **Monitor for cease-and-desist:** Have a process to respond quickly if any state commission contacts you about scraping activity.

### Federal Government Data (17 USC 105)

Works produced by the US federal government are not copyrightable. This includes USGS, BSEE (Bureau of Safety and Environmental Enforcement), and other federal O&G data sources. State government data may have different rules depending on the state.

---

## 15. Oil & Gas State Site Landscape

### Priority States (Top Producers)

| Priority | State | Commission | Data Access | Notes |
|----------|-------|-----------|-------------|-------|
| 1 | **Texas** | Railroad Commission of Texas (RRC) | Bulk downloads + online queries | Largest producer. Has bulk data files. Warns against automated scraping of query system. |
| 2 | **New Mexico** | Oil Conservation Division (OCD) | OCD Imaging system | Major Permian Basin producer |
| 3 | **North Dakota** | Dept. of Mineral Resources | GIS viewer + downloads | Bakken formation. Provides free datasets. |
| 4 | **Oklahoma** | Corporation Commission (OCC) | Downloadable files + Well Data Finder | Good data availability. JS-heavy search. |
| 5 | **Colorado** | Oil & Gas Conservation Commission (COGCC) | Online database | Provides permit, violation, well data |
| 6 | **Wyoming** | Oil & Gas Conservation Commission | Online lookup | |
| 7 | **Louisiana** | Dept. of Natural Resources (SONRIS) | SONRIS online system | Complex multi-system interface |
| 8 | **Alaska** | Oil & Gas Conservation Commission | AOGCC data portal | |
| 9 | **Pennsylvania** | Dept. of Environmental Protection | Marcellus/Utica data | |
| 10 | **Ohio** | Dept. of Natural Resources | RBDMS database | |

### Common Data Available Across States

- Well permits and applications
- Completion reports
- Production data (oil, gas, water volumes)
- Inspection records
- Violation records
- Plugging reports
- Directional surveys
- Spacing orders
- GIS/mapping data

### Existing Resources

- **USGS Links to State Well Data:** Comprehensive directory of all state data sources (https://www.usgs.gov/core-research-center/links-state-well-data)
- **FracTracker Alliance Data Library:** Aggregated O&G data resources
- **WellDatabase:** Commercial API for O&G well data (potential integration or validation source)
- **BSEE Data Center:** Federal offshore well data (https://www.data.bsee.gov)
- **Existing open-source scrapers:** `rrc-scraper` on GitHub for Texas RRC production data

### API Number Standard

All US oil and gas wells use the API Well Number system:
- Format: `SS-CCC-NNNNN-SS-SS` (State-County-Unique-Sidetrack-Completion)
- This is the universal identifier across all state systems
- Critical for deduplication and cross-state matching

---

## 16. Final Recommendation: System Architecture

### Technology Stack

| Component | Technology | Rationale |
|-----------|-----------|-----------|
| **Scraping Framework** | Scrapy + scrapy-playwright | Best hybrid: fast HTTP for static, Playwright for JS-heavy |
| **Browser Automation** | Playwright (Python) | Modern, reliable, stealth plugins available |
| **HTTP Client** | httpx | For direct API calls and file downloads outside Scrapy |
| **Task Queue** | Celery + Redis | Distributed task management, scheduling, retry |
| **Scheduler** | Celery Beat | Cron-like scheduling per state |
| **Document Storage** | S3 / MinIO | Scalable, content-addressable, cheap |
| **Database** | PostgreSQL | Metadata, extracted data, scrape state |
| **Cache / Dedup** | Redis | URL deduplication, rate limiter state |
| **Monitoring** | Flower + custom alerts | Task monitoring, spider health |
| **Anti-Bot** | playwright-stealth + proxy rotation | Layered evasion when needed |
| **Data Validation** | Pydantic | Schema enforcement, silent failure detection |

### Architecture Diagram

```
                    ┌─────────────────┐
                    │  Celery Beat     │  (Cron scheduler)
                    │  Scheduler       │
                    └────────┬────────┘
                             │ Triggers scrape tasks per state
                             v
                    ┌─────────────────┐
                    │  Redis           │  (Message broker + dedup cache)
                    │  Queue           │
                    └────────┬────────┘
                             │
              ┌──────────────┼──────────────┐
              v              v              v
     ┌───────────────┐ ┌──────────┐ ┌──────────────┐
     │ Scrapy Worker  │ │ Worker 2 │ │ Worker N     │
     │ (TX spider)    │ │ (OK)     │ │ (ND, CO...) │
     │                │ │          │ │              │
     │ ┌────────────┐ │ │          │ │              │
     │ │ Playwright  │ │ │          │ │              │
     │ │ (JS pages)  │ │ │          │ │              │
     │ └────────────┘ │ │          │ │              │
     └───────┬────────┘ └────┬─────┘ └──────┬───────┘
             │               │               │
             └───────────────┼───────────────┘
                             │ Item Pipeline
                             v
              ┌──────────────────────────────┐
              │  Processing Pipeline          │
              │  1. Deduplication (hash check) │
              │  2. Schema validation          │
              │  3. Document classification    │
              │  4. Data extraction            │
              │  5. Normalization              │
              └──────────────┬───────────────┘
                             │
                    ┌────────┴────────┐
                    v                 v
           ┌──────────────┐  ┌──────────────┐
           │  PostgreSQL   │  │  S3 / MinIO  │
           │  (metadata,   │  │  (raw docs,  │
           │   extracted   │  │   PDFs,      │
           │   data)       │  │   XLSX...)   │
           └──────────────┘  └──────────────┘
                    │
                    v
           ┌──────────────┐
           │  Monitoring   │
           │  (Flower +    │
           │   alerts)     │
           └──────────────┘
```

### Phase Plan

**Phase 1: Foundation (Weeks 1-3)**
- Set up Scrapy project with scrapy-playwright
- Implement base spider class and per-state adapter pattern
- Set up PostgreSQL schema and S3 storage
- Build first adapter: Texas RRC (highest priority, best data access)

**Phase 2: Core Pipeline (Weeks 4-6)**
- Implement incremental scraping (URL tracking, content hashing)
- Add retry/resilience patterns (circuit breaker, exponential backoff)
- Set up Celery + Redis for scheduling
- Add 2-3 more state adapters (Oklahoma, North Dakota, New Mexico)

**Phase 3: Scale & Monitor (Weeks 7-9)**
- Add monitoring and alerting (Flower, schema validation alerts)
- Implement site change detection
- Add proxy rotation for restrictive sites
- Expand to 5-10 state adapters

**Phase 4: Production Hardening (Weeks 10-12)**
- Load testing and performance optimization
- CAPTCHA handling integration (if needed)
- Complete documentation for adding new state adapters
- Deploy to production infrastructure

---

## Sources

### Framework Comparisons
- [ScrapingBee: Best Python Web Scraping Libraries](https://www.scrapingbee.com/blog/best-python-web-scraping-libraries/)
- [Bright Data: Scrapy vs Playwright](https://brightdata.com/blog/web-data/scrapy-vs-playwright)
- [Apify: Playwright vs Selenium](https://blog.apify.com/playwright-vs-selenium/)
- [Browserless: Playwright vs Selenium 2025](https://www.browserless.io/blog/playwright-vs-selenium-2025-browser-automation-comparison)
- [BrowserStack: Playwright vs Puppeteer 2026](https://www.browserstack.com/guide/playwright-vs-puppeteer)
- [ZenRows: Playwright vs Puppeteer 2026](https://www.zenrows.com/blog/playwright-vs-puppeteer)
- [Oxylabs: HTTPX vs Requests vs AIOHTTP](https://oxylabs.io/blog/httpx-vs-requests-vs-aiohttp)

### Scrapy-Playwright Integration
- [scrapy-playwright GitHub](https://github.com/scrapy-plugins/scrapy-playwright)
- [Apify: Scrapy Playwright Tutorial 2025](https://blog.apify.com/scrapy-playwright/)
- [ZenRows: Scrapy Playwright 2026](https://www.zenrows.com/blog/scrapy-playwright)
- [ScrapingBee: Scrapy Playwright Tutorial](https://www.scrapingbee.com/blog/scrapy-playwright-tutorial/)

### Anti-Bot & Stealth
- [ZenRows: Bypass Bot Detection](https://www.zenrows.com/blog/bypass-bot-detection)
- [ZenRows: Playwright Stealth](https://www.zenrows.com/blog/playwright-stealth)
- [Bright Data: Avoid Bot Detection with Playwright Stealth](https://brightdata.com/blog/how-tos/avoid-bot-detection-with-playwright-stealth)
- [Bright Data: Anti-Scraping Techniques](https://brightdata.com/blog/web-data/anti-scraping-techniques)
- [playwright-stealth on PyPI](https://pypi.org/project/playwright-stealth/)
- [ZenRows: Playwright Extra 2026](https://www.zenrows.com/blog/playwright-extra)

### CAPTCHA Solving
- [Octoparse: Top CAPTCHA Solvers 2026](https://www.octoparse.com/blog/top-captcha-solvers)
- [Bright Data: Best CAPTCHA Solvers 2026](https://brightdata.com/blog/web-data/best-captcha-solvers)
- [Scrapfly: Best CAPTCHA Solving APIs 2026](https://scrapfly.io/blog/posts/best-captcha-solving-api)

### Proxy Services
- [KDnuggets: Best Proxy Providers 2026](https://www.kdnuggets.com/2025/11/brightdata/the-best-proxy-providers-for-large-scale-scraping-for-2026)
- [DEV Community: ScraperAPI vs ScrapeOps vs Bright Data vs Oxylabs 2026](https://dev.to/agenthustler/best-web-scraping-apis-in-2026-scraperapi-vs-scrapeops-vs-bright-data-vs-oxylabs-honest-51d)
- [ScraperAPI: Rotating Proxy Services](https://www.scraperapi.com/blog/the-10-best-rotating-proxy-services-for-web-scraping/)

### Queue Management & Scheduling
- [Bright Data: Distributed Web Crawling](https://brightdata.com/blog/web-data/distributed-web-crawling)
- [ScrapeOps: Celery RabbitMQ Scraper Scheduling](https://scrapeops.io/web-scraping-playbook/celery-rabbitmq-scraper-scheduling/)
- [ScrapeOps: Scrapy Redis Guide](https://scrapeops.io/python-scrapy-playbook/scrapy-redis/)
- [ZenRows: Distributed Web Crawling](https://www.zenrows.com/blog/distributed-web-crawling)

### Resilience & Retry
- [Scrapfly: Automatic Failover Strategies](https://scrapfly.io/blog/posts/automatic-failover-strategies-for-reliable-data-extraction)
- [ProxiesAPI: Handling Failed Requests in Python](https://proxiesapi.com/articles/handling-failed-requests-in-python-techniques-for-resilience)
- [The Web Scraping Club: Rate Limiting with Exponential Backoff](https://substack.thewebscraping.club/p/rate-limit-scraping-exponential-backoff)

### Incremental Scraping
- [Stabler: How to Perform Incremental Web Scraping](https://stabler.tech/blog/how-to-perform-incremental-web-scraping)
- [Scrapy Media Pipeline Documentation](https://docs.scrapy.org/en/latest/topics/media-pipeline.html)

### Architecture Patterns
- [Use Apify: Web Scraping Architecture Patterns 2026](https://use-apify.com/blog/web-scraping-architecture-patterns)
- [GitHub Discussion: Designing Adaptive Scraping Engines](https://github.com/orgs/community/discussions/174081)
- [Scrapling GitHub](https://github.com/D4Vinci/Scrapling)
- [Use Apify: Scrapling Python Framework 2026](https://use-apify.com/blog/scrapling-python-web-scraping-framework)

### Site Change Detection
- [Browserless: State of Web Scraping 2026](https://www.browserless.io/blog/state-of-web-scraping-2026)
- [PromptCloud: Web Scraping Report 2026](https://www.promptcloud.com/blog/state-of-web-scraping-2026-report/)

### Pagination & Dynamic Content
- [Bright Data: Pagination Web Scraping 2026](https://brightdata.com/blog/web-data/pagination-web-scraping)
- [ScrapingBee: Web Scraping Pagination](https://www.scrapingbee.com/blog/web-scraping-pagination/)

### Legal
- [hiQ v. LinkedIn (9th Circuit)](https://calawyers.org/privacy-law/ninth-circuit-holds-data-scraping-is-legal-in-hiq-v-linkedin/)
- [AIMultiple: Is Web Scraping Legal 2026](https://research.aimultiple.com/is-web-scraping-legal/)
- [ScraperAPI: Is Web Scraping Legal 2026](https://www.scraperapi.com/web-scraping/is-web-scraping-legal/)
- [Apify: Is Web Scraping Legal](https://blog.apify.com/is-web-scraping-legal/)
- [PromptCloud: Robots.txt Compliance Guide](https://www.promptcloud.com/blog/robots-txt-scraping-compliance-guide/)

### Oil & Gas State Data Sources
- [Texas RRC: Data Sets for Download](https://www.rrc.texas.gov/resource-center/research/data-sets-available-for-download/)
- [Texas RRC: Oil & Gas Well Records Online](https://www.rrc.texas.gov/oil-and-gas/research-and-statistics/obtaining-commission-records/oil-and-gas-well-records-online/)
- [Oklahoma OCC: Oil & Gas Data Files](https://oklahoma.gov/occ/divisions/oil-gas/oil-gas-data.html)
- [USGS: Links to State Well Data](https://www.usgs.gov/core-research-center/links-state-well-data)
- [BSEE Data Center](https://www.data.bsee.gov/Well/API/Default.aspx)
- [GitHub: rrc-scraper for Texas RRC](https://github.com/derrickturk/rrc-scraper)
