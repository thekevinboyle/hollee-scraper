# Testing Strategy & Local Docker Deployment
## Oil & Gas Document Scraper

**Research Date**: 2026-03-27
**Scope**: Testing strategies (scrapers, pipeline, backend, frontend), Docker Compose deployment, development workflow, monitoring
**Decisions Applied**: Local Docker Compose, Python + Next.js, PaddleOCR, Scrapy + Playwright, 1-2 users, full product quality

---

## Table of Contents

1. [Testing Strategy for Scrapers](#1-testing-strategy-for-scrapers)
2. [Testing Document Processing Pipeline](#2-testing-document-processing-pipeline)
3. [Testing FastAPI Backend](#3-testing-fastapi-backend)
4. [Testing Next.js Frontend](#4-testing-nextjs-frontend)
5. [Docker Compose Local Deployment](#5-docker-compose-local-deployment)
6. [Development Workflow](#6-development-workflow)
7. [Monitoring for Local Deployment](#7-monitoring-for-local-deployment)
8. [Recommendations Summary](#8-recommendations-summary)

---

## 1. Testing Strategy for Scrapers

### 1.1 HTTP Response Recording & Replay (VCR Pattern)

The VCR pattern is the foundation for scraper testing: record real HTTP interactions once, replay them in tests forever. This eliminates live network calls while ensuring tests use real-world response data.

**Recommended: VCR.py + pytest-recording**

```python
# conftest.py
import pytest

@pytest.fixture(scope="module")
def vcr_config():
    return {
        "filter_headers": ["authorization", "cookie"],
        "filter_query_parameters": ["api_key"],
        "record_mode": "once",  # Record first run, replay after
        "cassette_library_dir": "tests/cassettes",
        "decode_compressed_response": True,
    }
```

```python
# tests/scrapers/test_texas_rrc.py
import pytest

@pytest.mark.vcr()
def test_texas_rrc_production_listing(texas_spider):
    """Test that the Texas RRC spider extracts production report links."""
    url = "https://www.rrc.texas.gov/oil-and-gas/data-sets/"
    response = fake_response_from_file("texas/data_sets.html", url=url)
    items = list(texas_spider.parse_data_sets(response))
    assert len(items) > 0
    assert all(item.get("doc_type") for item in items)
```

**Library Comparison:**

| Library | Scope | Async Support | Best For |
|---------|-------|---------------|----------|
| **VCR.py** (v6+) | Any HTTP library | Yes (aiohttp, httpx) | General HTTP recording; widest library support |
| **pytest-recording** | pytest + VCR.py | Yes | Convenient pytest fixtures for VCR cassettes |
| **betamax** | requests only | No | Legacy projects already using requests |
| **responses** | requests only | No | Simple request mocking without cassette files |
| **respx** | httpx only | Yes | Mocking httpx async clients (FastAPI tests) |

**Decision: VCR.py via pytest-recording** for scraper tests (broadest library support, async-ready, cassette files provide real response fixtures). Use **respx** for httpx-based FastAPI client tests.

**Cassette Management Best Practices:**
- Store cassettes in `tests/cassettes/{state}/{spider_name}/` -- organized per state
- Commit cassettes to git (they are test fixtures, not secrets)
- Redact sensitive headers (cookies, auth tokens) via `filter_headers`
- Use `record_mode="none"` in CI to guarantee no live network calls
- Periodically re-record cassettes (quarterly) to detect site changes
- Name cassettes after test functions for easy mapping

```yaml
# Example cassette: tests/cassettes/texas/test_production_listing.yaml
interactions:
- request:
    body: null
    headers:
      User-Agent: [Mozilla/5.0 ...]
    method: GET
    uri: https://www.rrc.texas.gov/oil-and-gas/data-sets/
  response:
    body:
      string: '<html>...'
    headers:
      Content-Type: [text/html; charset=utf-8]
    status: {code: 200, message: OK}
version: 1
```

### 1.2 Scrapy-Specific Testing Patterns

**Testing Scrapy Spiders with Fake Responses:**

```python
# tests/helpers.py
import os
from scrapy.http import HtmlResponse, Request

def fake_response_from_file(filename, url="http://example.com", meta=None):
    """Create a Scrapy HtmlResponse from a local HTML fixture file."""
    filepath = os.path.join(os.path.dirname(__file__), "fixtures", "html", filename)
    with open(filepath, "r", encoding="utf-8") as f:
        body = f.read()

    request = Request(url=url, meta=meta or {})
    return HtmlResponse(
        url=url,
        request=request,
        body=body,
        encoding="utf-8",
    )
```

```python
# tests/scrapers/test_texas_rrc.py
from scrapers.spiders.texas_rrc import TexasRRCSpider
from tests.helpers import fake_response_from_file

class TestTexasRRCSpider:
    def setup_method(self):
        self.spider = TexasRRCSpider()

    def test_parse_data_sets_page(self):
        response = fake_response_from_file("texas/data_sets.html",
            url="https://www.rrc.texas.gov/oil-and-gas/data-sets/")
        results = list(self.spider.parse_data_sets(response))

        # Verify expected number of document links
        assert len(results) >= 10
        # Verify each result has required fields
        for item in results:
            assert "source_url" in item
            assert "doc_type" in item
            assert item["state_code"] == "TX"

    def test_parse_production_report(self):
        response = fake_response_from_file("texas/production_report.html",
            url="https://www.rrc.texas.gov/oil-and-gas/...")
        items = list(self.spider.parse_production_report(response))

        assert len(items) == 1
        item = items[0]
        assert item["api_number"] == "42-001-12345"
        assert item["operator"] == "EXAMPLE OIL CO"
        assert float(item["oil_bbls"]) > 0
```

**Scrapy Contracts for Quick Smoke Tests:**

```python
# scrapers/spiders/texas_rrc.py
class TexasRRCSpider(scrapy.Spider):
    name = "texas_rrc"

    def parse_data_sets(self, response):
        """Parse the main data sets listing page.

        @url https://www.rrc.texas.gov/oil-and-gas/data-sets/
        @returns items 5
        @scrapes source_url doc_type state_code
        """
        # ... spider logic ...
```

Run contracts with `scrapy check texas_rrc` -- useful for CI smoke tests that verify live sites haven't broken.

**scrapy-mock for Response Recording:**

```python
# Record real Scrapy responses as test fixtures
# pip install scrapy-mock
# settings.py (only during recording)
SPIDER_MIDDLEWARES = {
    "scrapy_mock.MockMiddleware": 543,
}
MOCK_PATH = "tests/fixtures/scrapy_responses"
```

### 1.3 Testing Playwright-Based Scrapers

For spiders that use `scrapy-playwright` for JavaScript-heavy sites:

**Strategy 1: Playwright Route Mocking (Preferred for Unit Tests)**

```python
# tests/scrapers/test_newmexico_ocd.py
import pytest
from playwright.async_api import async_playwright

@pytest.mark.asyncio
async def test_newmexico_search_form():
    """Test NM OCD search form interaction with mocked responses."""
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()

        # Intercept and mock the search API response
        async def handle_route(route):
            if "api/search" in route.request.url:
                await route.fulfill(
                    status=200,
                    content_type="application/json",
                    body=open("tests/fixtures/nm/search_results.json").read(),
                )
            else:
                await route.continue_()

        await page.route("**/*", handle_route)

        # Load the local HTML fixture instead of live site
        await page.goto("file:///tests/fixtures/nm/search_page.html")

        # Test form interaction
        await page.fill("#api-number", "30-015-12345")
        await page.click("#search-btn")
        await page.wait_for_selector(".results-table")

        results = await page.query_selector_all(".result-row")
        assert len(results) > 0

        await browser.close()
```

**Strategy 2: Saved Page Snapshots (HAR Files)**

```python
# Record HAR during development
async def record_har():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        context = await browser.new_context(
            record_har_path="tests/fixtures/nm/search.har"
        )
        page = await context.new_page()
        await page.goto("https://ocdimage.emnrd.nm.gov/...")
        # ... interact with the page ...
        await context.close()  # HAR is saved on close
        await browser.close()

# Replay HAR in tests
@pytest.mark.asyncio
async def test_from_har():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        context = await browser.new_context()
        page = await context.new_page()
        await page.route_from_har("tests/fixtures/nm/search.har",
                                   not_found="fallback")
        await page.goto("https://ocdimage.emnrd.nm.gov/...")
        # Assert on parsed content
        await browser.close()
```

**Strategy 3: Local Test Server for Complex Interactions**

```python
# tests/conftest.py
import pytest
from aiohttp import web

@pytest.fixture
async def mock_state_server():
    """Serve local HTML fixtures as a mock government site."""
    app = web.Application()
    app.router.add_static("/", "tests/fixtures/html/")
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "localhost", 8089)
    await site.start()
    yield "http://localhost:8089"
    await runner.cleanup()
```

### 1.4 Fixture Management for Test Documents

**Directory Structure:**

```
tests/
  fixtures/
    html/                          # Saved HTML pages per state
      texas/
        data_sets.html
        production_report.html
        permit_search_results.html
      newmexico/
        ocd_search.html
        well_detail.html
    documents/                     # Sample downloadable documents
      texas/
        sample_production.pdf       # Real PDF (small, anonymized)
        sample_permit.pdf
        sample_completion.csv
      newmexico/
        sample_spacing_order.pdf    # Scanned PDF for OCR testing
        sample_well_log.tif
    api_responses/                  # JSON API responses
      texas/
        search_results.json
        well_detail.json
    cassettes/                     # VCR.py cassette files
      texas/
        test_production_listing.yaml
      newmexico/
        test_ocd_search.yaml
    ocr/                           # OCR test fixtures
      known_good/                  # Documents with verified extraction
        texas_production_001.pdf
        texas_production_001.json  # Expected extraction output
      edge_cases/
        low_quality_scan.pdf
        rotated_page.pdf
        multi_column.pdf
```

**Fixture Selection Criteria:**
- **1-2 real documents per doc type per state** (anonymized if containing PII)
- **Known-good documents**: Manually verified extraction results stored as JSON
- **Edge case documents**: Low-quality scans, rotated pages, multi-column layouts
- **Small file sizes**: Keep test fixtures under 500KB each; use cropped/reduced versions
- **Git LFS** for binary fixtures (PDFs, TIFs) to avoid bloating the repo

```ini
# .gitattributes
tests/fixtures/documents/**/*.pdf filter=lfs diff=lfs merge=lfs -text
tests/fixtures/documents/**/*.tif filter=lfs diff=lfs merge=lfs -text
tests/fixtures/ocr/**/*.pdf filter=lfs diff=lfs merge=lfs -text
```

### 1.5 Scraper Regression Testing (Site Change Detection)

**Three-Layer Approach:**

**Layer 1: Structural Assertions (Unit Tests)**
```python
def test_texas_table_structure(texas_response):
    """Verify the expected HTML structure still exists on the page."""
    # These selectors breaking = site redesign
    assert texas_response.css("table.datagrid") is not None
    assert len(texas_response.css("table.datagrid th")) >= 5
    assert texas_response.css("form#searchForm") is not None
```

**Layer 2: Scrapy Contracts (CI Smoke Tests)**
```bash
# Run in CI weekly (or on-demand) to check live sites
scrapy check --list  # List all spiders with contracts
scrapy check texas_rrc newmexico_ocd  # Check specific spiders
```

**Layer 3: Content Hash Monitoring**
```python
# scripts/check_site_health.py
"""
Compare current page content hash against last known hash.
Run weekly via CI or manual trigger.
"""
import hashlib
import httpx
import json
from pathlib import Path

SITES = {
    "texas_rrc": "https://www.rrc.texas.gov/oil-and-gas/data-sets/",
    "newmexico_ocd": "https://ocdimage.emnrd.nm.gov/imaging/",
    # ... all 10 states
}

def check_site_changes():
    hashes_file = Path("tests/fixtures/site_hashes.json")
    known_hashes = json.loads(hashes_file.read_text()) if hashes_file.exists() else {}
    changes = []

    for name, url in SITES.items():
        resp = httpx.get(url, follow_redirects=True, timeout=30)
        # Hash only the structural elements, not dynamic content
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(resp.text, "html.parser")
        # Remove script/style/dynamic content before hashing
        for tag in soup(["script", "style", "noscript"]):
            tag.decompose()
        content_hash = hashlib.sha256(str(soup).encode()).hexdigest()

        if name in known_hashes and known_hashes[name] != content_hash:
            changes.append(f"CHANGED: {name} ({url})")

        known_hashes[name] = content_hash

    hashes_file.write_text(json.dumps(known_hashes, indent=2))
    return changes
```

**Layer 4: Extraction Result Comparison**
```python
def test_extraction_matches_baseline(texas_spider, baseline_dir):
    """Run spider against recorded response and compare extraction to baseline."""
    response = fake_response_from_file("texas/production_report.html")
    items = list(texas_spider.parse_production_report(response))

    baseline = json.loads(
        Path(baseline_dir / "texas_production_expected.json").read_text()
    )
    assert items == baseline, (
        f"Extraction output changed! Review diff and update baseline if correct."
    )
```

---

## 2. Testing Document Processing Pipeline

### 2.1 Pipeline Stage Testing

The seven-stage pipeline (discover -> download -> classify -> extract -> normalize -> validate -> store) should be tested both per-stage (unit) and end-to-end (integration).

**Per-Stage Unit Tests:**

```python
# tests/pipeline/test_classifier.py
import pytest
from pipeline.classifier import DocumentClassifier

class TestDocumentClassifier:
    @pytest.fixture
    def classifier(self):
        return DocumentClassifier()

    @pytest.mark.parametrize("filename,expected_type", [
        ("Production_Report_2025_01.pdf", "production_report"),
        ("APD_Permit_42-001-12345.pdf", "well_permit"),
        ("Completion_Report_Final.pdf", "completion_report"),
        ("Spacing_Order_No_12345.pdf", "spacing_order"),
        ("Plugging_Report.pdf", "plugging_report"),
        ("Inspection_Record_2025.csv", "inspection_record"),
        ("Unknown_Document.pdf", "unknown"),
    ])
    def test_classify_by_filename(self, classifier, filename, expected_type):
        result = classifier.classify_by_filename(filename)
        assert result.doc_type == expected_type

    @pytest.mark.parametrize("text_content,expected_type", [
        ("MONTHLY PRODUCTION REPORT OIL GAS", "production_report"),
        ("APPLICATION FOR PERMIT TO DRILL", "well_permit"),
        ("WELL COMPLETION OR RECOMPLETION REPORT", "completion_report"),
    ])
    def test_classify_by_content(self, classifier, text_content, expected_type):
        result = classifier.classify_by_content(text_content)
        assert result.doc_type == expected_type
        assert result.confidence >= 0.7
```

### 2.2 PaddleOCR Testing Strategy

**Three-Tier Approach:**

**Tier 1: Mock OCR for Unit Tests (Fast, No GPU)**

```python
# tests/pipeline/test_extractor.py
from unittest.mock import MagicMock, patch

def make_mock_ocr_result(text_blocks):
    """Create a mock PaddleOCR result structure."""
    result = []
    for i, (text, confidence) in enumerate(text_blocks):
        box = [[i*100, 0], [(i+1)*100, 0], [(i+1)*100, 30], [i*100, 30]]
        result.append((box, (text, confidence)))
    return [[r[0], r[1]] for r in result]

class TestProductionExtractor:
    @patch("pipeline.ocr.PaddleOCR")
    def test_extract_production_data(self, mock_ocr_class):
        """Test extraction logic with mocked OCR output."""
        mock_ocr = MagicMock()
        mock_ocr_class.return_value = mock_ocr

        # Simulate PaddleOCR output for a production report
        mock_ocr.ocr.return_value = [make_mock_ocr_result([
            ("API No: 42-001-12345", 0.95),
            ("Operator: EXAMPLE OIL CO", 0.92),
            ("Oil Production (bbls): 1,234", 0.88),
            ("Gas Production (mcf): 5,678", 0.91),
            ("Report Period: January 2025", 0.94),
        ])]

        from pipeline.extractors.production import ProductionExtractor
        extractor = ProductionExtractor(ocr_engine=mock_ocr)
        result = extractor.extract("dummy_path.pdf")

        assert result.api_number == "42-001-12345"
        assert result.operator == "EXAMPLE OIL CO"
        assert result.oil_bbls == 1234.0
        assert result.gas_mcf == 5678.0
        assert result.confidence.overall >= 0.85
```

**Tier 2: Integration Tests with Real PaddleOCR (Slower, Uses Model)**

```python
# tests/integration/test_ocr_integration.py
import pytest
from pathlib import Path

# Mark as slow -- skip in normal test runs
@pytest.mark.slow
@pytest.mark.integration
class TestOCRIntegration:
    @pytest.fixture(scope="class")
    def ocr_engine(self):
        """Initialize PaddleOCR once for all tests in this class."""
        from paddleocr import PaddleOCR
        return PaddleOCR(use_angle_cls=True, lang="en", use_gpu=False)

    @pytest.mark.parametrize("pdf_path,expected_fields", [
        (
            "tests/fixtures/ocr/known_good/texas_production_001.pdf",
            "tests/fixtures/ocr/known_good/texas_production_001.json",
        ),
        (
            "tests/fixtures/ocr/known_good/nm_permit_001.pdf",
            "tests/fixtures/ocr/known_good/nm_permit_001.json",
        ),
    ])
    def test_ocr_known_good_documents(self, ocr_engine, pdf_path, expected_fields):
        """Verify OCR produces expected output on known documents."""
        import json

        result = ocr_engine.ocr(pdf_path, cls=True)
        expected = json.loads(Path(expected_fields).read_text())

        extracted_text = " ".join(
            line[1][0] for page in result for line in page
        )

        # Check key fields are present in OCR output
        for field_name, expected_value in expected["required_fields"].items():
            assert expected_value in extracted_text, (
                f"OCR failed to extract {field_name}: expected '{expected_value}'"
            )
```

**Tier 3: Accuracy Benchmarking (Periodic)**

```python
# tests/benchmarks/test_ocr_accuracy.py
@pytest.mark.benchmark
def test_ocr_accuracy_benchmark(ocr_engine, benchmark_dataset):
    """
    Run against a benchmark dataset of 50+ documents with ground truth.
    Track accuracy over time. Run monthly or after PaddleOCR upgrades.
    """
    results = []
    for doc in benchmark_dataset:
        extracted = extract_all_fields(ocr_engine, doc.pdf_path)
        accuracy = compute_field_accuracy(extracted, doc.ground_truth)
        results.append({
            "document": doc.name,
            "field_accuracy": accuracy,
            "overall": sum(accuracy.values()) / len(accuracy),
        })

    avg_accuracy = sum(r["overall"] for r in results) / len(results)
    assert avg_accuracy >= 0.85, (
        f"OCR accuracy dropped to {avg_accuracy:.2%}, below 85% threshold"
    )

    # Save results for tracking
    save_benchmark_results(results)
```

### 2.3 Classification Accuracy Testing

```python
# tests/pipeline/test_classification_accuracy.py
import pytest
import json
from pathlib import Path

CLASSIFICATION_TEST_SET = json.loads(
    Path("tests/fixtures/classification_ground_truth.json").read_text()
)

@pytest.mark.parametrize("doc", CLASSIFICATION_TEST_SET)
def test_document_classification(classifier, doc):
    """Test classification against ground truth dataset."""
    result = classifier.classify(
        filename=doc["filename"],
        text_content=doc.get("text_sample", ""),
        metadata=doc.get("metadata", {}),
    )
    assert result.doc_type == doc["expected_type"], (
        f"Misclassified {doc['filename']}: "
        f"expected {doc['expected_type']}, got {result.doc_type}"
    )

def test_classification_accuracy_overall(classifier):
    """Verify overall classification accuracy meets threshold."""
    correct = 0
    for doc in CLASSIFICATION_TEST_SET:
        result = classifier.classify(
            filename=doc["filename"],
            text_content=doc.get("text_sample", ""),
        )
        if result.doc_type == doc["expected_type"]:
            correct += 1

    accuracy = correct / len(CLASSIFICATION_TEST_SET)
    assert accuracy >= 0.90, (
        f"Classification accuracy {accuracy:.2%} below 90% threshold"
    )
```

### 2.4 Confidence Scoring Validation

```python
# tests/pipeline/test_confidence.py
class TestConfidenceScoring:
    def test_high_quality_document_scores_high(self, extractor):
        """Clean, text-based PDF should have high confidence."""
        result = extractor.extract("tests/fixtures/documents/texas/clean_report.pdf")
        assert result.confidence.ocr >= 0.90
        assert result.confidence.overall >= 0.85

    def test_low_quality_scan_scores_low(self, extractor):
        """Poor-quality scan should have low confidence."""
        result = extractor.extract("tests/fixtures/ocr/edge_cases/low_quality_scan.pdf")
        assert result.confidence.ocr < 0.70
        assert result.confidence.overall < 0.60

    def test_confidence_triggers_review_queue(self, extractor):
        """Documents below threshold should be flagged for review."""
        result = extractor.extract("tests/fixtures/ocr/edge_cases/low_quality_scan.pdf")
        assert result.needs_review is True
        assert result.review_reason == "low_confidence"

    def test_field_level_confidence(self, extractor):
        """Each extracted field should have its own confidence score."""
        result = extractor.extract("tests/fixtures/documents/texas/sample_production.pdf")
        assert "api_number" in result.confidence.fields
        assert "operator" in result.confidence.fields
        assert all(0.0 <= score <= 1.0 for score in result.confidence.fields.values())

    def test_confidence_thresholds_configurable(self):
        """Confidence thresholds should be configurable per deployment."""
        from pipeline.config import PipelineConfig
        config = PipelineConfig(
            ocr_confidence_threshold=0.80,
            field_confidence_threshold=0.70,
            document_confidence_threshold=0.75,
        )
        assert config.ocr_confidence_threshold == 0.80
```

---

## 3. Testing FastAPI Backend

### 3.1 Async Testing with pytest + httpx

**Core Setup:**

```python
# tests/conftest.py
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

from app.main import app
from app.database import get_db
from app.models import Base

# Test database URL (use testcontainers or a dedicated test DB)
TEST_DATABASE_URL = "postgresql+asyncpg://test:test@localhost:5433/test_ogdocs"

@pytest_asyncio.fixture(scope="session")
async def engine():
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()

@pytest_asyncio.fixture
async def db_session(engine):
    async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session() as session:
        async with session.begin():
            yield session
        await session.rollback()

@pytest_asyncio.fixture
async def client(db_session):
    """Create an async test client with dependency overrides."""
    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()
```

```python
# tests/api/test_documents.py
import pytest

@pytest.mark.asyncio
async def test_list_documents(client, seed_documents):
    response = await client.get("/api/v1/documents", params={"state": "TX"})
    assert response.status_code == 200
    data = response.json()
    assert len(data["items"]) > 0
    assert all(doc["state_code"] == "TX" for doc in data["items"])

@pytest.mark.asyncio
async def test_get_document_detail(client, seed_documents):
    doc_id = seed_documents[0].id
    response = await client.get(f"/api/v1/documents/{doc_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == str(doc_id)
    assert "extracted_data" in data
    assert "confidence" in data

@pytest.mark.asyncio
async def test_search_documents(client, seed_documents):
    response = await client.get("/api/v1/search", params={"q": "EXAMPLE OIL"})
    assert response.status_code == 200
    data = response.json()
    assert data["total"] > 0

@pytest.mark.asyncio
async def test_trigger_scrape(client):
    response = await client.post("/api/v1/scrape", json={"state": "TX"})
    assert response.status_code == 202
    data = response.json()
    assert "job_id" in data
    assert data["status"] == "queued"

@pytest.mark.asyncio
async def test_document_not_found(client):
    response = await client.get("/api/v1/documents/nonexistent-id")
    assert response.status_code == 404
```

### 3.2 Test Database with Testcontainers

**Preferred approach: Testcontainers spins up a real PostgreSQL + PostGIS in Docker for tests.**

```python
# tests/conftest.py
import pytest
from testcontainers.postgres import PostgresContainer

@pytest.fixture(scope="session")
def postgres_container():
    """Start a PostgreSQL + PostGIS container for the test session."""
    with PostgresContainer(
        image="postgis/postgis:16-3.4",
        username="test",
        password="test",
        dbname="test_ogdocs",
    ) as postgres:
        yield postgres

@pytest.fixture(scope="session")
def database_url(postgres_container):
    """Get the async connection URL for the test database."""
    sync_url = postgres_container.get_connection_url()
    # Convert to async URL
    return sync_url.replace("postgresql://", "postgresql+asyncpg://")
```

**pytest.ini configuration:**

```ini
# pytest.ini
[pytest]
asyncio_mode = auto
markers =
    slow: marks tests as slow (deselect with '-m "not slow"')
    integration: marks tests as integration tests
    benchmark: marks tests as benchmark tests
testpaths = tests
filterwarnings =
    ignore::DeprecationWarning
```

### 3.3 Test Data Factories

**Factory Boy with SQLAlchemy for realistic test data:**

```python
# tests/factories.py
import factory
from factory import Faker, LazyFunction, SubFactory
from datetime import datetime, timezone
import uuid

from app.models import State, Operator, Well, Document, ExtractedData

class StateFactory(factory.Factory):
    class Meta:
        model = State

    code = factory.Iterator(["TX", "NM", "ND", "OK", "CO", "WY", "LA", "PA", "CA", "AK"])
    name = factory.LazyAttribute(lambda o: {
        "TX": "Texas", "NM": "New Mexico", "ND": "North Dakota",
        "OK": "Oklahoma", "CO": "Colorado", "WY": "Wyoming",
        "LA": "Louisiana", "PA": "Pennsylvania", "CA": "California",
        "AK": "Alaska",
    }[o.code])
    priority = factory.Iterator([1, 1, 1, 1, 1, 2, 2, 2, 2, 2])

class OperatorFactory(factory.Factory):
    class Meta:
        model = Operator

    id = LazyFunction(uuid.uuid4)
    name = Faker("company")
    normalized_name = factory.LazyAttribute(lambda o: o.name.upper().strip())

class WellFactory(factory.Factory):
    class Meta:
        model = Well

    id = LazyFunction(uuid.uuid4)
    api_number = factory.LazyFunction(
        lambda: f"42-{factory.Faker._get_faker().random_int(1,999):03d}-"
                f"{factory.Faker._get_faker().random_int(10000,99999)}"
    )
    well_name = Faker("catch_phrase")
    state_code = "TX"
    county = Faker("city")
    latitude = Faker("latitude")
    longitude = Faker("longitude")
    status = factory.Iterator(["active", "inactive", "plugged"])

class DocumentFactory(factory.Factory):
    class Meta:
        model = Document

    id = LazyFunction(uuid.uuid4)
    state_code = "TX"
    doc_type = factory.Iterator([
        "production_report", "well_permit", "completion_report",
        "spacing_order", "plugging_report", "inspection_record",
    ])
    source_url = Faker("url")
    file_path = factory.LazyAttribute(
        lambda o: f"data/{o.state_code}/example_operator/{o.doc_type}/doc_{o.id}.pdf"
    )
    file_hash = Faker("sha256")
    file_format = "pdf"
    file_size_bytes = Faker("random_int", min=10000, max=5000000)
    confidence_score = Faker("pyfloat", min_value=0.5, max_value=1.0)
    scraped_at = LazyFunction(lambda: datetime.now(timezone.utc))

class ExtractedDataFactory(factory.Factory):
    class Meta:
        model = ExtractedData

    id = LazyFunction(uuid.uuid4)
    data_type = "production"
    data = factory.LazyFunction(lambda: {
        "api_number": "42-001-12345",
        "operator": "EXAMPLE OIL CO",
        "oil_bbls": 1234.0,
        "gas_mcf": 5678.0,
        "water_bbls": 890.0,
        "report_period": "2025-01",
    })
    confidence = factory.LazyFunction(lambda: {
        "overall": 0.92,
        "fields": {
            "api_number": 0.98,
            "operator": 0.95,
            "oil_bbls": 0.88,
            "gas_mcf": 0.91,
        },
    })
    version = 1
```

```python
# tests/conftest.py -- seed fixture using factories
@pytest_asyncio.fixture
async def seed_documents(db_session):
    """Seed the test database with sample documents."""
    docs = []
    for _ in range(5):
        doc = DocumentFactory()
        db_session.add(doc)
        docs.append(doc)
    await db_session.flush()
    return docs
```

### 3.4 API Endpoint Testing Patterns

```python
# tests/api/test_wells.py
@pytest.mark.asyncio
async def test_wells_geojson(client, seed_wells):
    """Test GeoJSON output for map display."""
    response = await client.get("/api/v1/wells/geojson", params={"state": "TX"})
    assert response.status_code == 200
    data = response.json()
    assert data["type"] == "FeatureCollection"
    assert len(data["features"]) > 0
    feature = data["features"][0]
    assert feature["geometry"]["type"] == "Point"
    assert "api_number" in feature["properties"]

# tests/api/test_scrape_jobs.py
@pytest.mark.asyncio
async def test_scrape_job_status_websocket(client):
    """Test real-time scrape status via WebSocket."""
    async with client.websocket_connect("/ws/scrape/job-123") as ws:
        data = await ws.receive_json()
        assert data["status"] in ["queued", "running", "completed", "failed"]

# tests/api/test_review_queue.py
@pytest.mark.asyncio
async def test_review_queue_list(client, seed_low_confidence_docs):
    """Test the review queue returns low-confidence documents."""
    response = await client.get("/api/v1/review-queue")
    assert response.status_code == 200
    data = response.json()
    assert all(doc["confidence_score"] < 0.75 for doc in data["items"])

@pytest.mark.asyncio
async def test_approve_reviewed_document(client, seed_low_confidence_docs):
    """Test approving a document from the review queue."""
    doc_id = seed_low_confidence_docs[0].id
    response = await client.post(f"/api/v1/review-queue/{doc_id}/approve", json={
        "corrections": {"operator": "CORRECTED NAME"},
    })
    assert response.status_code == 200
    assert response.json()["status"] == "approved"
```

---

## 4. Testing Next.js Frontend

### 4.1 Vitest for Component Testing

**Setup:**

```typescript
// vitest.config.ts
import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import path from "path";

export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./tests/setup.ts"],
    include: ["**/*.test.{ts,tsx}"],
    coverage: {
      provider: "v8",
      reporter: ["text", "html", "lcov"],
      include: ["src/**/*.{ts,tsx}"],
      exclude: ["src/**/*.d.ts", "src/**/*.test.*"],
    },
  },
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
});
```

```typescript
// tests/setup.ts
import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";
import { server } from "./mocks/server";

// Start MSW server before all tests
beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => {
  cleanup();
  server.resetHandlers();
});
afterAll(() => server.close());
```

**Component Tests:**

```typescript
// tests/components/DocumentSearch.test.tsx
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect } from "vitest";
import DocumentSearch from "@/components/DocumentSearch";

describe("DocumentSearch", () => {
  it("renders search form with state filter", () => {
    render(<DocumentSearch />);
    expect(screen.getByPlaceholderText(/search/i)).toBeInTheDocument();
    expect(screen.getByRole("combobox", { name: /state/i })).toBeInTheDocument();
  });

  it("displays search results from API", async () => {
    const user = userEvent.setup();
    render(<DocumentSearch />);

    await user.type(screen.getByPlaceholderText(/search/i), "EXAMPLE OIL");
    await user.click(screen.getByRole("button", { name: /search/i }));

    await waitFor(() => {
      expect(screen.getByText("EXAMPLE OIL CO")).toBeInTheDocument();
      expect(screen.getByText("production_report")).toBeInTheDocument();
    });
  });

  it("shows loading state during search", async () => {
    const user = userEvent.setup();
    render(<DocumentSearch />);

    await user.type(screen.getByPlaceholderText(/search/i), "test");
    await user.click(screen.getByRole("button", { name: /search/i }));

    expect(screen.getByRole("progressbar")).toBeInTheDocument();
  });

  it("handles empty results", async () => {
    const user = userEvent.setup();
    render(<DocumentSearch />);

    await user.type(screen.getByPlaceholderText(/search/i), "NONEXISTENT");
    await user.click(screen.getByRole("button", { name: /search/i }));

    await waitFor(() => {
      expect(screen.getByText(/no results/i)).toBeInTheDocument();
    });
  });
});
```

### 4.2 MSW (Mock Service Worker) for API Mocking

```typescript
// tests/mocks/handlers.ts
import { http, HttpResponse } from "msw";

export const handlers = [
  // Document search
  http.get("/api/v1/search", ({ request }) => {
    const url = new URL(request.url);
    const query = url.searchParams.get("q");

    if (query === "NONEXISTENT") {
      return HttpResponse.json({ items: [], total: 0 });
    }

    return HttpResponse.json({
      items: [
        {
          id: "doc-1",
          state_code: "TX",
          doc_type: "production_report",
          operator: "EXAMPLE OIL CO",
          confidence_score: 0.92,
          scraped_at: "2026-03-15T10:00:00Z",
        },
      ],
      total: 1,
    });
  }),

  // Document detail
  http.get("/api/v1/documents/:id", ({ params }) => {
    return HttpResponse.json({
      id: params.id,
      state_code: "TX",
      doc_type: "production_report",
      extracted_data: {
        api_number: "42-001-12345",
        operator: "EXAMPLE OIL CO",
        oil_bbls: 1234.0,
      },
      confidence: { overall: 0.92 },
    });
  }),

  // Wells GeoJSON
  http.get("/api/v1/wells/geojson", () => {
    return HttpResponse.json({
      type: "FeatureCollection",
      features: [
        {
          type: "Feature",
          geometry: { type: "Point", coordinates: [-101.5, 31.8] },
          properties: {
            api_number: "42-001-12345",
            well_name: "Test Well #1",
            operator: "EXAMPLE OIL CO",
            status: "active",
          },
        },
      ],
    });
  }),

  // Scrape trigger
  http.post("/api/v1/scrape", async ({ request }) => {
    const body = await request.json() as { state: string };
    return HttpResponse.json(
      { job_id: "job-123", status: "queued", state: body.state },
      { status: 202 }
    );
  }),

  // Review queue
  http.get("/api/v1/review-queue", () => {
    return HttpResponse.json({
      items: [
        {
          id: "doc-low-1",
          state_code: "NM",
          doc_type: "spacing_order",
          confidence_score: 0.45,
          review_reason: "low_confidence",
        },
      ],
      total: 1,
    });
  }),
];

// tests/mocks/server.ts
import { setupServer } from "msw/node";
import { handlers } from "./handlers";

export const server = setupServer(...handlers);
```

### 4.3 Map Component Testing

Testing Leaflet/Mapbox GL JS map components requires special handling since they depend on DOM APIs and canvas rendering.

```typescript
// tests/components/WellMap.test.tsx
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi } from "vitest";
import WellMap from "@/components/WellMap";

// Mock Leaflet since it requires a real DOM with canvas
vi.mock("leaflet", () => ({
  map: vi.fn(() => ({
    setView: vi.fn().mockReturnThis(),
    addLayer: vi.fn(),
    on: vi.fn(),
    remove: vi.fn(),
    fitBounds: vi.fn(),
  })),
  tileLayer: vi.fn(() => ({ addTo: vi.fn() })),
  marker: vi.fn(() => ({
    addTo: vi.fn().mockReturnThis(),
    bindPopup: vi.fn().mockReturnThis(),
    on: vi.fn(),
  })),
  markerClusterGroup: vi.fn(() => ({
    addLayer: vi.fn(),
    addTo: vi.fn(),
  })),
  icon: vi.fn(),
  Icon: { Default: { mergeOptions: vi.fn() } },
}));

describe("WellMap", () => {
  it("renders the map container", () => {
    render(<WellMap wells={[]} />);
    expect(screen.getByTestId("well-map")).toBeInTheDocument();
  });

  it("displays well count", async () => {
    render(<WellMap state="TX" />);
    await waitFor(() => {
      expect(screen.getByText(/1 well/i)).toBeInTheDocument();
    });
  });

  it("shows well popup on click", async () => {
    const user = userEvent.setup();
    render(<WellMap state="TX" />);

    await waitFor(() => {
      const marker = screen.getByTestId("well-marker-42-001-12345");
      expect(marker).toBeInTheDocument();
    });
  });
});
```

**For more realistic map testing, use Playwright E2E tests (see below).**

### 4.4 Playwright E2E Testing

```typescript
// e2e/dashboard.spec.ts
import { test, expect } from "@playwright/test";

test.describe("Dashboard", () => {
  test("search and view document", async ({ page }) => {
    await page.goto("/");

    // Search for documents
    await page.fill('[placeholder="Search..."]', "EXAMPLE OIL");
    await page.click('button:has-text("Search")');

    // Wait for results
    await expect(page.locator(".search-results")).toBeVisible();
    await expect(page.locator(".result-row")).toHaveCount(1);

    // Click through to document detail
    await page.click(".result-row:first-child");
    await expect(page.locator(".document-detail")).toBeVisible();
    await expect(page.locator("text=42-001-12345")).toBeVisible();
  });

  test("trigger scrape and monitor progress", async ({ page }) => {
    await page.goto("/");

    // Click scrape button
    await page.click('button:has-text("Scrape Texas")');

    // Verify progress indicator appears
    await expect(page.locator(".scrape-progress")).toBeVisible();
    await expect(page.locator("text=queued")).toBeVisible();
  });

  test("map displays wells", async ({ page }) => {
    await page.goto("/map");

    // Wait for map to load
    await page.waitForSelector(".leaflet-container", { timeout: 10000 });

    // Verify map tiles loaded
    await expect(page.locator(".leaflet-tile-loaded")).toHaveCount.greaterThan(0);

    // Verify markers are present
    await expect(page.locator(".leaflet-marker-icon")).toHaveCount.greaterThan(0);

    // Click a marker
    await page.click(".leaflet-marker-icon:first-child");
    await expect(page.locator(".leaflet-popup")).toBeVisible();
  });

  test("review queue workflow", async ({ page }) => {
    await page.goto("/review");

    // Verify low-confidence documents appear
    await expect(page.locator(".review-item")).toHaveCount.greaterThan(0);

    // Approve a document with corrections
    await page.click(".review-item:first-child");
    await page.fill('[name="operator"]', "CORRECTED NAME");
    await page.click('button:has-text("Approve")');

    // Verify removal from queue
    await expect(page.locator("text=Approved")).toBeVisible();
  });
});
```

```typescript
// playwright.config.ts
import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: true,
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 1 : undefined,
  reporter: "html",
  use: {
    baseURL: "http://localhost:3000",
    trace: "on-first-retry",
    screenshot: "only-on-failure",
  },
  projects: [
    { name: "chromium", use: { ...devices["Desktop Chrome"] } },
  ],
  webServer: {
    command: "pnpm dev",
    url: "http://localhost:3000",
    reuseExistingServer: !process.env.CI,
  },
});
```

---

## 5. Docker Compose Local Deployment

### 5.1 Development docker-compose.yml

```yaml
# docker-compose.yml -- LOCAL DEVELOPMENT
# Usage: docker compose up -d

services:
  # ─── PostgreSQL + PostGIS ─────────────────────────────
  db:
    image: postgis/postgis:16-3.4
    container_name: ogdocs-db
    environment:
      POSTGRES_USER: ${POSTGRES_USER:-ogdocs}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:-ogdocs_dev}
      POSTGRES_DB: ${POSTGRES_DB:-ogdocs}
    ports:
      - "${DB_PORT:-5432}:5432"
    volumes:
      - pgdata:/var/lib/postgresql/data
      - ./backend/scripts/init-db.sql:/docker-entrypoint-initdb.d/01-init.sql
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER:-ogdocs} -d ${POSTGRES_DB:-ogdocs}"]
      interval: 5s
      timeout: 5s
      retries: 5
      start_period: 10s
    restart: unless-stopped

  # ─── FastAPI Backend ──────────────────────────────────
  backend:
    build:
      context: ./backend
      dockerfile: Dockerfile.dev
    container_name: ogdocs-backend
    environment:
      - DATABASE_URL=postgresql+asyncpg://${POSTGRES_USER:-ogdocs}:${POSTGRES_PASSWORD:-ogdocs_dev}@db:5432/${POSTGRES_DB:-ogdocs}
      - DOCUMENTS_DIR=/data/documents
      - LOG_LEVEL=${LOG_LEVEL:-debug}
      - ENVIRONMENT=development
    ports:
      - "${BACKEND_PORT:-8000}:8000"
    volumes:
      - ./backend/src:/app/src                # Hot reload: source code
      - ./backend/alembic:/app/alembic        # Hot reload: migrations
      - documents:/data/documents              # Shared document storage
      - paddleocr-models:/root/.paddleocr     # Persist OCR models
    depends_on:
      db:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "python", "-c", "import httpx; httpx.get('http://localhost:8000/health')"]
      interval: 10s
      timeout: 5s
      retries: 5
      start_period: 30s    # PaddleOCR model loading takes time
    restart: unless-stopped

  # ─── Next.js Frontend ────────────────────────────────
  frontend:
    build:
      context: ./frontend
      dockerfile: Dockerfile.dev
    container_name: ogdocs-frontend
    environment:
      - NEXT_PUBLIC_API_URL=http://localhost:${BACKEND_PORT:-8000}
      - WATCHPACK_POLLING=true                 # Enable file watching in Docker
    ports:
      - "${FRONTEND_PORT:-3000}:3000"
    volumes:
      - ./frontend/src:/app/src                # Hot reload: source code
      - ./frontend/public:/app/public          # Hot reload: static assets
      - frontend-node-modules:/app/node_modules # Persist node_modules in volume
    depends_on:
      backend:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:3000"]
      interval: 10s
      timeout: 5s
      retries: 5
      start_period: 20s
    restart: unless-stopped

volumes:
  pgdata:
    name: ogdocs-pgdata
  documents:
    name: ogdocs-documents
  paddleocr-models:
    name: ogdocs-paddleocr-models
  frontend-node-modules:
    name: ogdocs-frontend-node-modules

networks:
  default:
    name: ogdocs-network
```

### 5.2 Production-Like docker-compose.prod.yml

```yaml
# docker-compose.prod.yml -- PRODUCTION-LIKE LOCAL DEPLOYMENT
# Usage: docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d

services:
  db:
    # Inherits from base docker-compose.yml
    environment:
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:?POSTGRES_PASSWORD must be set}
    ports: []  # No exposed ports in production

  backend:
    build:
      context: ./backend
      dockerfile: Dockerfile
      target: production
    environment:
      - LOG_LEVEL=info
      - ENVIRONMENT=production
    volumes:
      # Remove source code mounts, only keep data volumes
      - documents:/data/documents
      - paddleocr-models:/root/.paddleocr
    ports:
      - "${BACKEND_PORT:-8000}:8000"

  frontend:
    build:
      context: ./frontend
      dockerfile: Dockerfile
      target: production
    environment:
      - NODE_ENV=production
    volumes: []  # No source code mounts
    ports:
      - "${FRONTEND_PORT:-3000}:3000"
```

### 5.3 Backend Dockerfile (Python + uv, Multi-Stage)

```dockerfile
# backend/Dockerfile
# Multi-stage build for FastAPI + PaddleOCR

# ─── Stage 1: Build dependencies ───────────────────────
FROM python:3.13-slim AS builder

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Install system dependencies for PaddleOCR
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy dependency files first (cache-friendly layer ordering)
COPY pyproject.toml uv.lock ./

# Install dependencies with cache mount for speed
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project

# ─── Stage 2: Development ──────────────────────────────
FROM python:3.13-slim AS development

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    libgomp1 \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY pyproject.toml uv.lock ./

# Install ALL dependencies including dev
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project

COPY . .

# Set environment variables
ENV UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

EXPOSE 8000

CMD ["uv", "run", "uvicorn", "src.app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]

# ─── Stage 3: Production ───────────────────────────────
FROM python:3.13-slim AS production

RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    libgomp1 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN groupadd -r ogdocs && useradd -r -g ogdocs ogdocs

WORKDIR /app

# Copy installed dependencies from builder
COPY --from=builder /app/.venv /app/.venv

# Copy application code
COPY src/ ./src/
COPY alembic/ ./alembic/
COPY alembic.ini ./

# Set environment variables
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Create data directories
RUN mkdir -p /data/documents && chown -R ogdocs:ogdocs /data

USER ogdocs

EXPOSE 8000

CMD ["uvicorn", "src.app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
```

```dockerfile
# backend/Dockerfile.dev -- Simplified dev Dockerfile
FROM python:3.13-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    libgomp1 \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY pyproject.toml uv.lock ./

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project

COPY . .

ENV PYTHONUNBUFFERED=1

EXPOSE 8000

CMD ["uv", "run", "uvicorn", "src.app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
```

### 5.4 Frontend Dockerfile (Next.js Standalone)

```dockerfile
# frontend/Dockerfile
# Multi-stage build for Next.js standalone output

# ─── Stage 1: Dependencies ─────────────────────────────
FROM node:22-alpine AS deps

RUN corepack enable && corepack prepare pnpm@latest --activate

WORKDIR /app

COPY package.json pnpm-lock.yaml ./

RUN pnpm install --frozen-lockfile

# ─── Stage 2: Build ────────────────────────────────────
FROM node:22-alpine AS build

RUN corepack enable && corepack prepare pnpm@latest --activate

WORKDIR /app

COPY --from=deps /app/node_modules ./node_modules
COPY . .

# Build with standalone output
ENV NEXT_TELEMETRY_DISABLED=1
RUN pnpm build

# ─── Stage 3: Development ──────────────────────────────
FROM node:22-alpine AS development

RUN corepack enable && corepack prepare pnpm@latest --activate

WORKDIR /app

COPY package.json pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile

COPY . .

ENV NEXT_TELEMETRY_DISABLED=1

EXPOSE 3000

CMD ["pnpm", "dev"]

# ─── Stage 4: Production ───────────────────────────────
FROM node:22-alpine AS production

WORKDIR /app

# Create non-root user
RUN addgroup --system --gid 1001 nodejs && \
    adduser --system --uid 1001 nextjs

# Copy standalone build output
COPY --from=build /app/public ./public
COPY --from=build --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=build --chown=nextjs:nodejs /app/.next/static ./.next/static

USER nextjs

ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=3000

EXPOSE 3000

CMD ["node", "server.js"]
```

```dockerfile
# frontend/Dockerfile.dev -- Simplified dev Dockerfile
FROM node:22-alpine

RUN corepack enable && corepack prepare pnpm@latest --activate

WORKDIR /app

COPY package.json pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile

COPY . .

ENV NEXT_TELEMETRY_DISABLED=1

EXPOSE 3000

CMD ["pnpm", "dev"]
```

### 5.5 Environment Variable Management

```bash
# .env.example -- committed to git, documents all variables
# Copy to .env and fill in values

# ─── Database ───────────────────────────────────────────
POSTGRES_USER=ogdocs
POSTGRES_PASSWORD=ogdocs_dev
POSTGRES_DB=ogdocs
DB_PORT=5432

# ─── Backend ───────────────────────────────────────────
BACKEND_PORT=8000
LOG_LEVEL=debug
# OCR confidence thresholds
OCR_CONFIDENCE_THRESHOLD=0.80
FIELD_CONFIDENCE_THRESHOLD=0.70
DOCUMENT_CONFIDENCE_THRESHOLD=0.75

# ─── Frontend ──────────────────────────────────────────
FRONTEND_PORT=3000
NEXT_PUBLIC_API_URL=http://localhost:8000
NEXT_PUBLIC_MAP_TILE_URL=https://tile.openstreetmap.org/{z}/{x}/{y}.png

# ─── Scraping ──────────────────────────────────────────
SCRAPE_RATE_LIMIT_MS=10000
SCRAPE_MAX_CONCURRENT=2
SCRAPE_USER_AGENT=OGDocsScraper/1.0 (research; contact@example.com)
```

```bash
# .env -- not committed to git (in .gitignore)
POSTGRES_USER=ogdocs
POSTGRES_PASSWORD=my_secure_password_here
POSTGRES_DB=ogdocs
# ... rest of values ...
```

```gitignore
# .gitignore
.env
.env.local
.env.production
!.env.example
```

### 5.6 Volume Architecture

```
Volumes (Docker-managed):
  pgdata          → PostgreSQL data (persistent across restarts)
  paddleocr-models → PaddleOCR model files (~1.5GB, cached after first download)
  frontend-node-modules → node_modules (avoids slow npm installs on mount)

Bind Mounts (development only):
  ./backend/src    → /app/src          (hot reload Python source)
  ./backend/alembic → /app/alembic     (hot reload migrations)
  ./frontend/src   → /app/src          (hot reload Next.js source)
  ./frontend/public → /app/public      (hot reload static assets)

Shared Volumes:
  documents       → /data/documents    (accessed by backend for read/write)
                                        (organized as data/{state}/{operator}/{doc_type}/)
```

### 5.7 Networking

All services communicate over the `ogdocs-network` Docker network using service names:

```
frontend (port 3000) ──→ backend (port 8000) ──→ db (port 5432)
                              │
                              ▼
                    documents volume (/data/documents)
```

- **frontend** calls backend at `http://backend:8000` (server-side) or `http://localhost:8000` (client-side browser)
- **backend** connects to database at `db:5432`
- **db** is only exposed on host for development tooling (pgAdmin, psql)
- In production overlay, db port is not exposed

---

## 6. Development Workflow

### 6.1 Dependency Management

**Python Backend: uv**

```bash
# Initial setup
cd backend
uv init
uv add fastapi uvicorn[standard] sqlalchemy[asyncio] asyncpg alembic
uv add paddleocr paddlepaddle  # OCR engine
uv add scrapy scrapy-playwright playwright httpx
uv add structlog python-json-logger

# Dev dependencies
uv add --dev pytest pytest-asyncio pytest-cov pytest-recording
uv add --dev vcrpy respx httpx factory-boy testcontainers[postgresql]
uv add --dev ruff mypy

# Lock and sync
uv lock
uv sync
```

**Next.js Frontend: pnpm**

```bash
# Initial setup
cd frontend
pnpm init
pnpm add next react react-dom
pnpm add leaflet react-leaflet @types/leaflet
pnpm add @tanstack/react-query axios
pnpm add tailwindcss postcss autoprefixer

# Dev dependencies
pnpm add -D vitest @vitejs/plugin-react @testing-library/react
pnpm add -D @testing-library/jest-dom @testing-library/user-event
pnpm add -D msw @playwright/test
pnpm add -D eslint prettier eslint-config-next
pnpm add -D typescript @types/react @types/node
```

### 6.2 Justfile (Task Runner)

```justfile
# justfile -- Project task runner
# Install: brew install just (macOS) or cargo install just
# Usage: just <recipe>

# Default recipe: show available commands
default:
    @just --list

# ─── Docker Commands ────────────────────────────────────

# Start all services in development mode
up:
    docker compose up -d

# Start all services and follow logs
up-logs:
    docker compose up

# Stop all services
down:
    docker compose down

# Stop all services and remove volumes (DESTRUCTIVE)
down-clean:
    docker compose down -v

# Rebuild all images
rebuild:
    docker compose build --no-cache

# View logs for a specific service
logs service="backend":
    docker compose logs -f {{service}}

# ─── Backend Commands ───────────────────────────────────

# Run backend tests
test-backend:
    cd backend && uv run pytest -x -v

# Run backend tests with coverage
test-backend-cov:
    cd backend && uv run pytest --cov=src --cov-report=html --cov-report=term

# Run only fast tests (no integration/slow)
test-backend-fast:
    cd backend && uv run pytest -x -v -m "not slow and not integration"

# Run backend linting
lint-backend:
    cd backend && uv run ruff check src/ tests/
    cd backend && uv run ruff format --check src/ tests/

# Fix backend lint issues
fix-backend:
    cd backend && uv run ruff check --fix src/ tests/
    cd backend && uv run ruff format src/ tests/

# Run type checking
typecheck-backend:
    cd backend && uv run mypy src/

# Run database migrations
migrate:
    docker compose exec backend uv run alembic upgrade head

# Create a new migration
migration name:
    docker compose exec backend uv run alembic revision --autogenerate -m "{{name}}"

# ─── Frontend Commands ──────────────────────────────────

# Run frontend tests
test-frontend:
    cd frontend && pnpm test

# Run frontend tests with coverage
test-frontend-cov:
    cd frontend && pnpm test -- --coverage

# Run frontend E2E tests
test-e2e:
    cd frontend && pnpm exec playwright test

# Run frontend linting
lint-frontend:
    cd frontend && pnpm lint
    cd frontend && pnpm exec prettier --check "src/**/*.{ts,tsx}"

# Fix frontend lint issues
fix-frontend:
    cd frontend && pnpm lint --fix
    cd frontend && pnpm exec prettier --write "src/**/*.{ts,tsx}"

# ─── Scraper Commands ───────────────────────────────────

# Run a specific state scraper
scrape state:
    docker compose exec backend uv run scrapy crawl {{state}} -L INFO

# List all available spiders
spiders:
    docker compose exec backend uv run scrapy list

# Run scrapy shell for debugging
shell url:
    docker compose exec backend uv run scrapy shell "{{url}}"

# Check spider contracts (smoke test against live sites)
check-spiders:
    docker compose exec backend uv run scrapy check

# ─── Full Project Commands ──────────────────────────────

# Run all tests
test: test-backend test-frontend

# Run all linting
lint: lint-backend lint-frontend

# Fix all lint issues
fix: fix-backend fix-frontend

# Run pre-commit hooks manually
pre-commit:
    pre-commit run --all-files

# Full CI pipeline locally
ci: lint typecheck-backend test

# Open database shell
psql:
    docker compose exec db psql -U ${POSTGRES_USER:-ogdocs} -d ${POSTGRES_DB:-ogdocs}

# Check service health
health:
    @echo "Database:" && docker compose exec db pg_isready -U ogdocs && echo "OK" || echo "UNHEALTHY"
    @echo "Backend:" && curl -sf http://localhost:8000/health && echo " OK" || echo "UNHEALTHY"
    @echo "Frontend:" && curl -sf http://localhost:3000 > /dev/null && echo "OK" || echo "UNHEALTHY"

# Show disk usage for documents
disk:
    du -sh data/ 2>/dev/null || echo "No data directory yet"
    docker system df
```

### 6.3 Pre-Commit Hooks

```yaml
# .pre-commit-config.yaml
repos:
  # ─── Python (Backend) ─────────────────────────────────
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.15.0    # Use latest stable
    hooks:
      - id: ruff
        args: [--fix, --exit-non-zero-on-fix]
        files: ^backend/
      - id: ruff-format
        files: ^backend/

  # ─── JavaScript/TypeScript (Frontend) ──────────────────
  - repo: https://github.com/pre-commit/mirrors-eslint
    rev: v9.20.0
    hooks:
      - id: eslint
        files: ^frontend/src/.*\.(ts|tsx)$
        additional_dependencies:
          - eslint@9
          - eslint-config-next@15

  - repo: https://github.com/pre-commit/mirrors-prettier
    rev: v4.0.0
    hooks:
      - id: prettier
        files: ^frontend/src/.*\.(ts|tsx|css|json)$

  # ─── General ──────────────────────────────────────────
  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v5.0.0
    hooks:
      - id: trailing-whitespace
      - id: end-of-file-fixer
      - id: check-yaml
      - id: check-json
      - id: check-added-large-files
        args: [--maxkb=1000]
      - id: detect-private-key
      - id: check-merge-conflict

  # ─── Docker ───────────────────────────────────────────
  - repo: https://github.com/hadolint/hadolint
    rev: v2.12.0
    hooks:
      - id: hadolint
        args: [--ignore, DL3008, --ignore, DL3013]  # Allow unpinned apt/pip versions
```

```bash
# Setup
pip install pre-commit
pre-commit install
pre-commit run --all-files  # Verify
```

### 6.4 Running Individual Scrapers During Development

```bash
# Option 1: Inside the Docker container
docker compose exec backend uv run scrapy crawl texas_rrc -L DEBUG

# Option 2: Locally (requires local Python + uv setup)
cd backend
uv run scrapy crawl texas_rrc -L DEBUG -s LOG_FILE=logs/texas.log

# Option 3: Scrapy shell for interactive debugging
docker compose exec backend uv run scrapy shell "https://www.rrc.texas.gov/oil-and-gas/data-sets/"

# Option 4: Run a single spider callback with a saved response
cd backend
uv run python -c "
from scrapers.spiders.texas_rrc import TexasRRCSpider
from tests.helpers import fake_response_from_file

spider = TexasRRCSpider()
response = fake_response_from_file('texas/data_sets.html')
for item in spider.parse_data_sets(response):
    print(item)
"

# Option 5: Trigger via API (once backend is running)
curl -X POST http://localhost:8000/api/v1/scrape \
  -H "Content-Type: application/json" \
  -d '{"state": "TX", "doc_types": ["production_report"]}'
```

### 6.5 pytest Configuration

```toml
# backend/pyproject.toml

[project]
name = "ogdocs-backend"
version = "0.1.0"
requires-python = ">=3.12"

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
markers = [
    "slow: marks tests as slow (deselect with '-m \"not slow\"')",
    "integration: integration tests requiring external services",
    "benchmark: OCR accuracy benchmark tests",
    "e2e: end-to-end tests",
]
filterwarnings = [
    "ignore::DeprecationWarning",
]
addopts = "-x --strict-markers --tb=short"

[tool.ruff]
target-version = "py312"
line-length = 100
src = ["src", "tests"]

[tool.ruff.lint]
select = ["E", "F", "W", "I", "UP", "B", "SIM", "RUF"]
ignore = ["E501"]  # Line length handled by formatter

[tool.ruff.format]
quote-style = "double"

[tool.mypy]
python_version = "3.12"
plugins = ["sqlalchemy.ext.mypy.plugin"]
strict = true
warn_return_any = true
warn_unused_configs = true
```

---

## 7. Monitoring for Local Deployment

### 7.1 Structured JSON Logging

```python
# backend/src/app/logging_config.py
import structlog
import logging
import sys

def setup_logging(environment: str = "development", log_level: str = "DEBUG"):
    """Configure structured logging with structlog."""

    # Shared processors
    shared_processors = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.UnicodeDecoder(),
    ]

    if environment == "production":
        # JSON output for production (machine-parseable)
        renderer = structlog.processors.JSONRenderer()
    else:
        # Pretty console output for development
        renderer = structlog.dev.ConsoleRenderer(colors=True)

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.addHandler(handler)
    root_logger.setLevel(getattr(logging, log_level.upper()))

    # Quiet noisy libraries
    logging.getLogger("scrapy").setLevel(logging.WARNING)
    logging.getLogger("playwright").setLevel(logging.WARNING)
    logging.getLogger("paddleocr").setLevel(logging.WARNING)
```

```python
# backend/src/app/middleware.py
import structlog
import time
import uuid
from starlette.middleware.base import BaseHTTPMiddleware

logger = structlog.get_logger()

class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        request_id = str(uuid.uuid4())[:8]
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=request_id)

        start_time = time.perf_counter()
        response = await call_next(request)
        duration_ms = (time.perf_counter() - start_time) * 1000

        logger.info(
            "http_request",
            method=request.method,
            path=request.url.path,
            status=response.status_code,
            duration_ms=round(duration_ms, 2),
        )
        return response
```

### 7.2 Scraper Health Monitoring

```python
# backend/src/scrapers/monitoring.py
import structlog
from datetime import datetime, timezone
from dataclasses import dataclass, field

logger = structlog.get_logger()

@dataclass
class ScrapeMetrics:
    state: str
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    finished_at: datetime | None = None
    pages_crawled: int = 0
    documents_found: int = 0
    documents_downloaded: int = 0
    documents_skipped: int = 0  # Already exists / deduplicated
    errors: list[dict] = field(default_factory=list)
    bytes_downloaded: int = 0

    @property
    def success_rate(self) -> float:
        total = self.documents_found
        if total == 0:
            return 0.0
        return (self.documents_downloaded + self.documents_skipped) / total

    @property
    def duration_seconds(self) -> float | None:
        if self.finished_at is None:
            return None
        return (self.finished_at - self.started_at).total_seconds()

    def log_summary(self):
        logger.info(
            "scrape_complete",
            state=self.state,
            duration_s=self.duration_seconds,
            pages_crawled=self.pages_crawled,
            docs_found=self.documents_found,
            docs_downloaded=self.documents_downloaded,
            docs_skipped=self.documents_skipped,
            errors_count=len(self.errors),
            success_rate=f"{self.success_rate:.1%}",
            bytes_downloaded=self.bytes_downloaded,
        )


# backend/src/app/api/health.py
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
import shutil
import structlog

router = APIRouter()
logger = structlog.get_logger()

@router.get("/health")
async def health_check(db: AsyncSession = Depends(get_db)):
    """Health check endpoint with component status."""
    checks = {}

    # Database check
    try:
        await db.execute("SELECT 1")
        checks["database"] = "healthy"
    except Exception as e:
        checks["database"] = f"unhealthy: {e}"

    # Disk space check
    disk = shutil.disk_usage("/data/documents")
    disk_free_gb = disk.free / (1024 ** 3)
    checks["disk_free_gb"] = round(disk_free_gb, 2)
    checks["disk_status"] = "healthy" if disk_free_gb > 5 else "warning"

    # PaddleOCR model check
    from pathlib import Path
    model_dir = Path("/root/.paddleocr")
    checks["ocr_models"] = "loaded" if model_dir.exists() and any(model_dir.iterdir()) else "missing"

    overall = "healthy" if all(
        v in ("healthy", "loaded") or isinstance(v, (int, float))
        for v in checks.values()
    ) else "degraded"

    return {"status": overall, "checks": checks}
```

### 7.3 Scraper Job Status (API Endpoints)

```python
# backend/src/app/api/scrape_jobs.py
from fastapi import APIRouter, WebSocket
import structlog

router = APIRouter()
logger = structlog.get_logger()

@router.get("/api/v1/scrape/status")
async def get_all_scrape_status(db: AsyncSession = Depends(get_db)):
    """Get status overview of all scrape jobs and per-state health."""
    result = await db.execute("""
        SELECT
            state_code,
            COUNT(*) as total_runs,
            COUNT(*) FILTER (WHERE status = 'completed') as successful,
            COUNT(*) FILTER (WHERE status = 'failed') as failed,
            MAX(finished_at) as last_run,
            AVG(EXTRACT(EPOCH FROM finished_at - started_at)) as avg_duration_s
        FROM scrape_runs
        GROUP BY state_code
        ORDER BY state_code
    """)
    return {"states": [dict(row) for row in result]}

@router.websocket("/ws/scrape/{job_id}")
async def scrape_progress_ws(websocket: WebSocket, job_id: str):
    """WebSocket endpoint for real-time scrape progress."""
    await websocket.accept()
    try:
        # Stream progress updates from the scrape job
        async for update in get_job_updates(job_id):
            await websocket.send_json({
                "job_id": job_id,
                "status": update.status,
                "progress": {
                    "pages_crawled": update.pages_crawled,
                    "docs_found": update.documents_found,
                    "docs_downloaded": update.documents_downloaded,
                },
                "errors": update.recent_errors,
            })
    except Exception:
        pass
    finally:
        await websocket.close()
```

### 7.4 Disk Space Monitoring

```python
# backend/src/app/monitoring/disk.py
import shutil
import structlog
from pathlib import Path

logger = structlog.get_logger()

def check_disk_usage(documents_dir: str = "/data/documents") -> dict:
    """Check disk usage and warn if running low."""
    usage = shutil.disk_usage(documents_dir)

    total_gb = usage.total / (1024 ** 3)
    used_gb = usage.used / (1024 ** 3)
    free_gb = usage.free / (1024 ** 3)
    percent_used = (usage.used / usage.total) * 100

    status = {
        "total_gb": round(total_gb, 2),
        "used_gb": round(used_gb, 2),
        "free_gb": round(free_gb, 2),
        "percent_used": round(percent_used, 1),
    }

    # Per-state breakdown
    docs_path = Path(documents_dir)
    if docs_path.exists():
        state_sizes = {}
        for state_dir in docs_path.iterdir():
            if state_dir.is_dir():
                size = sum(f.stat().st_size for f in state_dir.rglob("*") if f.is_file())
                state_sizes[state_dir.name] = round(size / (1024 ** 2), 2)  # MB
        status["per_state_mb"] = state_sizes

    # Log warnings
    if free_gb < 2:
        logger.error("disk_space_critical", free_gb=free_gb)
    elif free_gb < 5:
        logger.warning("disk_space_low", free_gb=free_gb)
    else:
        logger.info("disk_space_ok", free_gb=free_gb, percent_used=round(percent_used, 1))

    return status


def get_document_stats(documents_dir: str = "/data/documents") -> dict:
    """Get document storage statistics."""
    docs_path = Path(documents_dir)
    stats = {
        "total_files": 0,
        "total_size_mb": 0,
        "by_state": {},
        "by_type": {},
    }

    if not docs_path.exists():
        return stats

    for f in docs_path.rglob("*"):
        if f.is_file():
            stats["total_files"] += 1
            size_mb = f.stat().st_size / (1024 ** 2)
            stats["total_size_mb"] += size_mb

            # Parse path: data/{state}/{operator}/{doc_type}/{filename}
            parts = f.relative_to(docs_path).parts
            if len(parts) >= 3:
                state = parts[0]
                doc_type = parts[2] if len(parts) >= 3 else "unknown"
                stats["by_state"][state] = stats["by_state"].get(state, 0) + 1
                stats["by_type"][doc_type] = stats["by_type"].get(doc_type, 0) + 1

    stats["total_size_mb"] = round(stats["total_size_mb"], 2)
    return stats
```

---

## 8. Recommendations Summary

### Testing Strategy

| Layer | Tool | Purpose | Speed |
|-------|------|---------|-------|
| Scraper unit tests | pytest + VCR.py + fake responses | Test parsing logic with recorded HTTP responses | Fast (ms) |
| Playwright scraper tests | Playwright route mocking + HAR replay | Test JS-heavy scraper interactions | Medium (s) |
| Scraper regression | Scrapy contracts + content hash monitoring | Detect when state sites change | Medium (live HTTP) |
| Pipeline unit tests | pytest + mocked PaddleOCR | Test classification/extraction logic | Fast (ms) |
| Pipeline integration | pytest + real PaddleOCR on fixtures | Verify OCR accuracy on known documents | Slow (s per doc) |
| OCR benchmarks | Monthly benchmark suite | Track accuracy over time | Very slow (minutes) |
| Backend API tests | pytest + httpx AsyncClient + testcontainers | Test API endpoints with real PostgreSQL | Medium (s) |
| Frontend unit tests | Vitest + RTL + MSW | Test React components with mocked API | Fast (ms) |
| Frontend E2E tests | Playwright | Test full dashboard workflows | Slow (s per test) |

### Docker Architecture

| Service | Dev Image | Prod Image | Hot Reload |
|---------|-----------|------------|------------|
| PostgreSQL + PostGIS | postgis/postgis:16-3.4 | Same | N/A (persistent volume) |
| FastAPI backend | python:3.13-slim + uv | Multi-stage slim (production target) | Yes (uvicorn --reload + bind mount) |
| Next.js frontend | node:22-alpine + pnpm | Multi-stage standalone | Yes (pnpm dev + bind mount + WATCHPACK_POLLING) |

### Development Tools

| Category | Tool | Justification |
|----------|------|---------------|
| Python deps | uv | 10-100x faster than pip, lockfile support, Rust-based |
| JS deps | pnpm | Efficient disk usage, strict dependency resolution |
| Task runner | just | Cross-platform, simple syntax, per-language recipe support |
| Python linting | ruff | 200x faster than flake8, replaces black+isort+flake8 |
| JS linting | eslint + prettier | Industry standard for Next.js projects |
| Pre-commit | pre-commit framework | Runs ruff, eslint, prettier before each commit |
| Logging | structlog | Structured JSON logs in prod, pretty console in dev |

### Key Principles

1. **Test pyramid**: Many fast unit tests, fewer integration tests, minimal E2E tests
2. **No live network in CI**: Use VCR cassettes, mocks, and fixtures -- `record_mode="none"` in CI
3. **Real databases in tests**: Testcontainers for PostgreSQL -- no SQLite substitution
4. **Separate test markers**: `@pytest.mark.slow`, `@pytest.mark.integration`, `@pytest.mark.benchmark` to control test scope
5. **Docker-first development**: All services run in Docker Compose; local Python/Node for IDE support
6. **Environment parity**: docker-compose.prod.yml mirrors production behavior locally
7. **Volume separation**: Data volumes persist across rebuilds; source mounts only in development

---

## Sources

### Scraper Testing
- [VCR.py Documentation](https://vcrpy.readthedocs.io/)
- [Using vcrpy to test HTTP interactions -- alexwlchan](https://alexwlchan.net/2025/testing-with-vcrpy/)
- [pytest-recording Plugin](https://github.com/kiwicom/pytest-recording)
- [Test a Web Scraper using VCR -- datawookie](https://datawookie.dev/blog/2025-01-28-test-a-web-scraper-using-vcr/)
- [scrapy-mock: Record Scrapy responses as fixtures](https://github.com/tcurvelo/scrapy-mock)
- [Scrapy Contracts Documentation](https://docs.scrapy.org/en/latest/topics/contracts.html)
- [Test a Playwright Web Scraper -- datawookie](https://datawookie.dev/blog/2025/04/test-a-playwright-web-scraper)
- [pytest-playwright Plugin](https://pypi.org/project/pytest-playwright/)

### Backend Testing
- [FastAPI Async Tests Documentation](https://fastapi.tiangolo.com/advanced/async-tests/)
- [Async Testing with Pytest -- Hash Block](https://medium.com/@connect.hashblock/async-testing-with-pytest-mastering-pytest-asyncio-and-event-loops-for-fastapi-and-beyond-37c613f1cfa3)
- [Fast and furious: async testing with FastAPI and pytest -- WeirdSheepLabs](https://weirdsheeplabs.com/blog/fast-and-furious-async-testing-with-fastapi-and-pytest)
- [Testing FastAPI with async database session](https://dev.to/whchi/testing-fastapi-with-async-database-session-1b5d)
- [Testcontainers for Python](https://testcontainers.com/guides/getting-started-with-testcontainers-for-python/)
- [Factory Boy with SQLAlchemy and Pytest](https://medium.com/@aasispaudelthp2/factoryboy-tutorial-with-sqlalchemy-and-pytest-1cda908d783a)
- [Generating Test Data with factory_boy -- Lynn Kwong](https://lynn-kwong.medium.com/generating-test-data-with-factory-boy-for-sqlalchemy-orm-models-f04822289d43)

### Frontend Testing
- [MSW Quick Start](https://mswjs.io/docs/quick-start/)
- [Vitest Browser Mode with MSW](https://mswjs.io/docs/recipes/vitest-browser-mode/)
- [Using MSW with Vitest -- Steve Kinney](https://stevekinney.com/courses/testing/testing-with-mock-service-worker)
- [MSW in Next.js Guide](https://dev.to/mehakb7/mock-service-worker-msw-in-nextjs-a-guide-for-api-mocking-and-testing-e9m)
- [Next.js Testing: Playwright](https://nextjs.org/docs/app/guides/testing/playwright)
- [Next.js E2E Testing Guide](https://eastondev.com/blog/en/posts/dev/20260107-nextjs-playwright-e2e/)
- [Next.js Testing Guide: Vitest and Playwright -- Strapi](https://strapi.io/blog/nextjs-testing-guide-unit-and-e2e-tests-with-vitest-and-playwright)

### Docker & Deployment
- [Using uv in Docker -- Official Docs](https://docs.astral.sh/uv/guides/integration/docker/)
- [Production-ready Python Docker Containers with uv -- Hynek](https://hynek.me/articles/docker-uv/)
- [Optimal Dockerfile for Python with uv -- Depot](https://depot.dev/docs/container-builds/optimal-dockerfiles/python-uv-dockerfile)
- [Multi-Stage Docker Builds for Python with uv](https://dev.to/kummerer94/multi-stage-docker-builds-for-pyton-projects-using-uv-223g)
- [Dockerizing a Next.js Application in 2025 -- Kristiyan Velkov](https://medium.com/front-end-world/dockerizing-a-next-js-application-in-2025-bacdca4810fe)
- [Next.js Self-Hosting Guide](https://nextjs.org/docs/app/guides/self-hosting)
- [Next.js Standalone Dockerfile -- kristiyan-velkov](https://github.com/kristiyan-velkov/nextjs-prod-dockerfile)
- [Docker Compose Health Checks Guide](https://last9.io/blog/docker-compose-health-checks/)
- [Docker Compose depends_on with Health Checks](https://oneuptime.com/blog/post/2026-01-16-docker-compose-depends-on-healthcheck/view)
- [Docker Compose Environment Variables Best Practices](https://docs.docker.com/compose/how-tos/environment-variables/best-practices/)
- [Full Stack FastAPI Template](https://github.com/tiangolo/full-stack-fastapi-postgresql)

### Development Workflow
- [Python Dependency Management in 2026 -- Cuttlesoft](https://cuttlesoft.com/blog/2026/01/27/python-dependency-management-in-2026/)
- [Just Command Runner](https://github.com/casey/just)
- [Justfile as favorite task runner -- Duy NG](https://tduyng.com/blog/justfile-my-favorite-task-runner/)
- [Code Quality Automation: Linters, Formatters, Pre-commit Hooks](https://dasroot.net/posts/2026/03/code-quality-automation-linters-formatters-pre-commit-hooks/)
- [Ultimate Pre-Commit Hooks Guide 2025](https://gatlenculp.medium.com/effortless-code-quality-the-ultimate-pre-commit-hooks-guide-for-2025-57ca501d9835)
- [Ruff Pre-Commit Hook](https://github.com/astral-sh/ruff-pre-commit)

### Logging & Monitoring
- [How to Add Structured Logging to FastAPI](https://oneuptime.com/blog/post/2026-02-02-fastapi-structured-logging/view)
- [Setting Up Structured Logging in FastAPI with structlog](https://ouassim.tech/notes/setting-up-structured-logging-in-fastapi-with-structlog/)
- [structlog Documentation](https://www.structlog.org/)
- [Structured JSON Logging using FastAPI -- Shesh Babu](https://www.sheshbabu.com/posts/fastapi-structured-json-logging/)
