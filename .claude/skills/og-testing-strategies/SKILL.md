---
name: og-testing-strategies
description: Complete testing strategy including VCR.py scraper tests, testcontainers DB tests, and Playwright E2E. Use when writing or running tests for any component.
---

# Oil & Gas Document Scraper - Testing Strategies

## What This Is

A comprehensive testing strategy covering every layer of the Oil & Gas Document Scraper project. This includes scraper tests with recorded HTTP responses, database tests against real PostgreSQL+PostGIS containers, async API endpoint tests, document processing pipeline unit tests, OCR accuracy validation, React component tests, and full end-to-end browser tests.

The project is a Python (Scrapy + FastAPI) backend with a Next.js frontend, deployed locally via Docker Compose. It scrapes oil and gas regulatory documents from 10 US states, runs OCR via PaddleOCR, and stores structured data in PostgreSQL.

## When to Use This Skill

- Writing tests for any project component (scrapers, pipeline, API, frontend)
- Setting up test infrastructure (testcontainers, VCR cassettes, Playwright)
- Running test suites locally or debugging test failures
- Adding a new state scraper and needing test fixtures
- Evaluating OCR accuracy or confidence scoring behavior
- Building CI test pipelines

---

## Testing Layers

### 1. Scraper Testing (VCR.py Cassettes)

Record real HTTP responses once, replay them in all future test runs. This guarantees no live network calls in CI while testing against real-world data.

**Tools**: VCR.py via pytest-recording, Scrapy fake responses, Playwright HAR files

**How it works**:
- VCR.py intercepts HTTP requests and records responses to YAML cassette files
- One cassette set per state, stored in `tests/cassettes/{state}/`
- Use `record_mode="once"` during development, `record_mode="none"` in CI
- Filter sensitive headers (cookies, auth tokens) via `filter_headers`

**Cassette organization**:
```
tests/cassettes/
  texas/
    test_production_listing.yaml
  newmexico/
    test_ocd_search.yaml
  ... (one directory per state)
```

**Configuration** (`conftest.py`):
```python
@pytest.fixture(scope="module")
def vcr_config():
    return {
        "filter_headers": ["authorization", "cookie"],
        "filter_query_parameters": ["api_key"],
        "record_mode": "once",
        "cassette_library_dir": "tests/cassettes",
        "decode_compressed_response": True,
    }
```

**Spider test pattern**:
```python
@pytest.mark.vcr()
def test_texas_rrc_production_listing(texas_spider):
    response = fake_response_from_file("texas/data_sets.html",
        url="https://www.rrc.texas.gov/oil-and-gas/data-sets/")
    items = list(texas_spider.parse_data_sets(response))
    assert len(items) > 0
    assert all(item.get("doc_type") for item in items)
```

**Playwright-based scrapers** (for JS-heavy state sites): Use route mocking or HAR file replay.
```python
await page.route_from_har("tests/fixtures/nm/search.har", not_found="fallback")
```

**Regression detection** (4 layers):
1. Structural assertions -- verify expected HTML selectors still exist
2. Scrapy contracts -- `scrapy check texas_rrc` for live smoke tests
3. Content hash monitoring -- detect page structure changes
4. Extraction result comparison -- compare output against stored baselines

### 2. Database Testing (testcontainers)

Spin up a real PostgreSQL+PostGIS instance in Docker per test session. Tests run against a real database, not mocks, then clean up automatically.

**Tools**: testcontainers-python, pytest-asyncio, SQLAlchemy async

**Container fixture** (`conftest.py`):
```python
@pytest.fixture(scope="session")
def postgres_container():
    with PostgresContainer(
        image="postgis/postgis:16-3.4",
        username="test",
        password="test",
        dbname="test_ogdocs",
    ) as postgres:
        yield postgres

@pytest.fixture(scope="session")
def database_url(postgres_container):
    sync_url = postgres_container.get_connection_url()
    return sync_url.replace("postgresql://", "postgresql+asyncpg://")
```

**Session-scoped engine with automatic schema creation/teardown**:
```python
@pytest_asyncio.fixture(scope="session")
async def engine(database_url):
    engine = create_async_engine(database_url, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()
```

**Per-test session with automatic rollback** ensures test isolation:
```python
@pytest_asyncio.fixture
async def db_session(engine):
    async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session() as session:
        async with session.begin():
            yield session
        await session.rollback()
```

### 3. API Testing (pytest-asyncio + httpx)

Test FastAPI endpoints asynchronously using httpx.AsyncClient with ASGI transport. Tests hit real database via testcontainers, with dependency injection overrides.

**Tools**: pytest-asyncio, httpx (AsyncClient + ASGITransport), respx (for mocking external httpx calls)

**Client fixture**:
```python
@pytest_asyncio.fixture
async def client(db_session):
    async def override_get_db():
        yield db_session
    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()
```

**Endpoint test patterns**:
```python
@pytest.mark.asyncio
async def test_list_documents(client, seed_documents):
    response = await client.get("/api/v1/documents", params={"state": "TX"})
    assert response.status_code == 200
    data = response.json()
    assert len(data["items"]) > 0

@pytest.mark.asyncio
async def test_trigger_scrape(client):
    response = await client.post("/api/v1/scrape", json={"state": "TX"})
    assert response.status_code == 202
    assert response.json()["status"] == "queued"

@pytest.mark.asyncio
async def test_review_queue_list(client, seed_low_confidence_docs):
    response = await client.get("/api/v1/review-queue")
    assert response.status_code == 200
    data = response.json()
    assert all(doc["confidence_score"] < 0.75 for doc in data["items"])
```

### 4. Pipeline Testing (Per-Stage Unit Tests)

The seven-stage pipeline (discover, download, classify, extract, normalize, validate, store) is tested per-stage with sample documents and parametrized inputs.

**Tools**: pytest, pytest.mark.parametrize, unittest.mock

**Classification tests**:
```python
@pytest.mark.parametrize("filename,expected_type", [
    ("Production_Report_2025_01.pdf", "production_report"),
    ("APD_Permit_42-001-12345.pdf", "well_permit"),
    ("Completion_Report_Final.pdf", "completion_report"),
    ("Spacing_Order_No_12345.pdf", "spacing_order"),
    ("Plugging_Report.pdf", "plugging_report"),
    ("Unknown_Document.pdf", "unknown"),
])
def test_classify_by_filename(classifier, filename, expected_type):
    result = classifier.classify_by_filename(filename)
    assert result.doc_type == expected_type
```

**Confidence scoring tests**:
```python
def test_high_quality_document_scores_high(extractor):
    result = extractor.extract("tests/fixtures/documents/texas/clean_report.pdf")
    assert result.confidence.overall >= 0.85

def test_low_quality_scan_triggers_review(extractor):
    result = extractor.extract("tests/fixtures/ocr/edge_cases/low_quality_scan.pdf")
    assert result.needs_review is True
    assert result.review_reason == "low_confidence"
```

**Normalization and validation** tests verify data cleaning rules (API number formatting, operator name normalization, date parsing, numeric conversions).

### 5. OCR Testing (PaddleOCR)

Three-tier approach from fast mocked tests to slow real-model integration tests.

**Tools**: PaddleOCR, unittest.mock, pytest markers

**Tier 1 -- Mocked OCR (unit tests, fast, no GPU)**:
```python
@patch("pipeline.ocr.PaddleOCR")
def test_extract_production_data(mock_ocr_class):
    mock_ocr = MagicMock()
    mock_ocr_class.return_value = mock_ocr
    mock_ocr.ocr.return_value = [make_mock_ocr_result([
        ("API No: 42-001-12345", 0.95),
        ("Operator: EXAMPLE OIL CO", 0.92),
    ])]
    # ... test extraction logic against mocked OCR output
```

**Tier 2 -- Real PaddleOCR integration tests** (marked `@pytest.mark.slow` and `@pytest.mark.integration`):
```python
@pytest.mark.slow
@pytest.mark.integration
def test_ocr_known_good_documents(ocr_engine, pdf_path, expected_fields):
    result = ocr_engine.ocr(pdf_path, cls=True)
    extracted_text = " ".join(line[1][0] for page in result for line in page)
    for field_name, expected_value in expected["required_fields"].items():
        assert expected_value in extracted_text
```

**Tier 3 -- Accuracy benchmarking** (periodic, run monthly or after PaddleOCR upgrades):
- Run against 50+ documents with ground truth
- Assert average accuracy >= 85%
- Save results for tracking over time

### 6. Frontend Testing (React Testing Library + Playwright)

**Component tests** use Vitest + React Testing Library + MSW (Mock Service Worker).

**Tools**: Vitest, @testing-library/react, @testing-library/user-event, MSW

**Setup** (`tests/setup.ts`):
```typescript
import "@testing-library/jest-dom/vitest";
import { server } from "./mocks/server";
beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => { cleanup(); server.resetHandlers(); });
afterAll(() => server.close());
```

**MSW handlers** mock the FastAPI backend at the network level (`tests/mocks/handlers.ts`), covering search, document detail, wells GeoJSON, scrape trigger, and review queue endpoints.

**Component test pattern**:
```typescript
it("displays search results from API", async () => {
    const user = userEvent.setup();
    render(<DocumentSearch />);
    await user.type(screen.getByPlaceholderText(/search/i), "EXAMPLE OIL");
    await user.click(screen.getByRole("button", { name: /search/i }));
    await waitFor(() => {
        expect(screen.getByText("EXAMPLE OIL CO")).toBeInTheDocument();
    });
});
```

**Map component tests** mock Leaflet since it requires real DOM canvas. Use Playwright for realistic map testing.

**E2E browser tests** (Playwright):
```typescript
// e2e/dashboard.spec.ts
test("search and view document", async ({ page }) => {
    await page.goto("/");
    await page.fill('[placeholder="Search..."]', "EXAMPLE OIL");
    await page.click('button:has-text("Search")');
    await expect(page.locator(".search-results")).toBeVisible();
});
```

Playwright config targets Chromium, uses `http://localhost:3000` as base URL, and starts the dev server automatically.

### 7. Integration Testing (Full Pipeline)

End-to-end pipeline tests exercise the full flow: scrape trigger through data storage and review queue population.

- Combine VCR cassettes (no live HTTP) with testcontainers (real DB)
- Trigger a scrape via API, verify documents are stored, extracted data is correct
- Verify low-confidence documents appear in the review queue
- Verify high-confidence documents are auto-accepted

---

## Key Tools Summary

| Tool | Purpose | Layer |
|------|---------|-------|
| **pytest** + **pytest-asyncio** | Python test runner, async test support | All Python tests |
| **VCR.py** / **pytest-recording** | Record/replay HTTP responses | Scraper tests |
| **testcontainers** | Spin up PostgreSQL+PostGIS in Docker | Database + API tests |
| **httpx** (AsyncClient) | Async HTTP client for FastAPI testing | API tests |
| **respx** | Mock httpx calls to external services | API tests |
| **Factory Boy** | Generate realistic test data | Database fixtures |
| **Vitest** | Frontend test runner | Component tests |
| **React Testing Library** | DOM-based component testing | Component tests |
| **MSW** (Mock Service Worker) | Network-level API mocking in browser | Component tests |
| **Playwright** | Browser automation for E2E testing | E2E tests |

---

## Test Data Strategy

### Sample PDFs
- 1-2 real documents per doc type per state (anonymized)
- Both text-based PDFs and scanned image PDFs
- Keep fixtures under 500KB each; use cropped/reduced versions
- Store in Git LFS (`tests/fixtures/documents/**/*.pdf`)

### VCR Cassettes
- One cassette set per state, recorded from real site responses
- Committed to git (test fixtures, not secrets)
- Sensitive headers redacted automatically
- Re-record quarterly to stay current

### Database Fixtures (Factory Boy)
- `StateFactory`, `OperatorFactory`, `WellFactory`, `DocumentFactory`, `ExtractedDataFactory`
- Seed data covers wells, operators, and documents for each state
- Seed fixtures created via `@pytest_asyncio.fixture` and injected into tests

### Confidence Threshold Scenarios
- **Auto-accept**: Documents with overall confidence >= 0.85
- **Review queue**: Documents with confidence between 0.60-0.85
- **Reject**: Documents with confidence < 0.60
- Test all three scenarios with dedicated fixtures

### OCR Test Fixtures
```
tests/fixtures/ocr/
  known_good/           # Documents with manually verified extraction
    texas_production_001.pdf
    texas_production_001.json   # Expected extraction output
  edge_cases/
    low_quality_scan.pdf
    rotated_page.pdf
    multi_column.pdf
```

### Full Fixture Directory Structure
```
tests/
  fixtures/
    html/                  # Saved HTML pages per state
      texas/
      newmexico/
    documents/             # Sample downloadable documents
      texas/
      newmexico/
    api_responses/         # JSON API responses
      texas/
    cassettes/             # VCR.py cassette files
      texas/
      newmexico/
    ocr/                   # OCR test fixtures
      known_good/
      edge_cases/
```

---

## Common Pitfalls

1. **Stale VCR cassettes**: State government sites change without notice. Cassettes become stale and tests pass against outdated HTML. Re-record cassettes quarterly. Run `scrapy check` smoke tests against live sites periodically to detect changes early.

2. **testcontainers requires Docker**: Docker Desktop (or equivalent) must be running for any test that uses testcontainers. If Docker is not running, database and integration tests will fail with connection errors. Ensure Docker is started before running `just test-integration`.

3. **PaddleOCR tests are slow**: PaddleOCR model loading takes several seconds and each inference is CPU-intensive. Mark OCR integration tests with `@pytest.mark.slow` and `@pytest.mark.integration`. Skip them in fast unit test runs (`-m "not slow"`). Use mocked OCR output for unit tests of extraction logic.

4. **Playwright needs browser binaries**: Run `npx playwright install chromium` before first use. Browser binaries are large (~200MB) and not included by default. CI pipelines need an explicit install step.

5. **Async test gotchas**: Use `pytest-asyncio` with `asyncio_mode = auto` in `pytest.ini`. Ensure fixtures that yield async sessions properly roll back transactions to maintain test isolation.

6. **Git LFS for binary fixtures**: PDF and TIF test fixtures must use Git LFS to avoid bloating the repository. Configure `.gitattributes` accordingly:
   ```
   tests/fixtures/documents/**/*.pdf filter=lfs diff=lfs merge=lfs -text
   tests/fixtures/ocr/**/*.pdf filter=lfs diff=lfs merge=lfs -text
   ```

7. **Map component mocking**: Leaflet requires real DOM canvas which jsdom does not provide. Mock Leaflet in Vitest component tests. Use Playwright E2E tests for realistic map interaction testing.

---

## Running Tests

All test commands are defined in the project `justfile`:

```bash
# Run all tests
just test

# Fast unit tests only (no Docker, no OCR, no browser)
just test-unit

# Integration tests (requires Docker for testcontainers)
just test-integration

# Playwright E2E browser tests (requires browser binaries)
just test-e2e
```

**Underlying pytest commands**:
```bash
# Unit tests (fast, no external dependencies)
pytest -m "not slow and not integration and not benchmark" --timeout=30

# Integration tests (testcontainers + real OCR)
pytest -m "integration" --timeout=120

# All tests with coverage
pytest --cov=src --cov-report=html --cov-report=term

# Re-record VCR cassettes for a specific state
pytest tests/scrapers/test_texas_rrc.py --vcr-record=all

# Run frontend component tests
cd frontend && pnpm test

# Run Playwright E2E tests
cd frontend && npx playwright test
```

**pytest.ini markers**:
```ini
[pytest]
asyncio_mode = auto
markers =
    slow: marks tests as slow (deselect with '-m "not slow"')
    integration: marks tests as integration tests
    benchmark: marks tests as benchmark tests
```

---

## References

- **Discovery document**: `.claude/orchestration-og-doc-scraper/DISCOVERY.md` -- project scope, tech stack decisions, architecture
- **Testing & deployment research**: `.claude/orchestration-og-doc-scraper/research/testing-deployment-implementation.md` -- detailed code examples, tool comparisons, Docker Compose configuration
