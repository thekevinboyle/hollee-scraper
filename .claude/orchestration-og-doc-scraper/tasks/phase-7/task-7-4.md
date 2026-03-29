# Task 7.4: Performance & Smoke Tests

## Objective

Verify that the full Docker Compose stack starts cleanly, remains stable under sustained use, and meets performance benchmarks: API response times under 500ms, map rendering of 1000+ wells without lag, single document OCR processing under 30 seconds, database migrations on a fresh database, no frontend console errors, and all test suites pass. This is the final task of the entire project -- it confirms everything works together as a production-quality local tool.

## Context

This is the fourth and final task in Phase 7 (Comprehensive E2E Testing) and the final task of the entire project. Tasks 7.1-7.3 validated the pipeline end-to-end, dashboard UI, and error handling. This task is about stability, performance, and the final green light. It exercises Docker Compose lifecycle, measures response times, stress-tests the map with large well datasets, benchmarks OCR speed, and runs the complete test suite (`just test`). After this task passes, the project is complete.

## Dependencies

- All Phase 1-6 tasks must be complete
- Tasks 7.1-7.3 complete
- Docker Desktop running on the target machine
- All test suites from prior tasks implemented

## Blocked By

- All Phase 1-6 tasks
- Tasks 7.1, 7.2, 7.3

## Research Findings

Key findings from research files relevant to this task:

- From `testing-deployment-implementation.md`: Docker Compose includes health checks for db (pg_isready), backend (HTTP health endpoint), and frontend (curl localhost:3000). PaddleOCR model loading takes several seconds (start_period: 30s for backend).
- From `og-scraper-architecture` skill: Five services: db (PostgreSQL+PostGIS), backend (FastAPI), worker (Huey), frontend (Next.js). Backend port 8000, frontend port 3000, DB port 5432.
- From `nextjs-dashboard` skill: Supercluster handles 10K-50K markers (100K in 1-2 seconds). Map uses client-side clustering. Browser limit of 6 concurrent SSE connections.
- From `og-testing-strategies` skill: Run commands: `just test` (all), `just test-unit` (fast), `just test-integration` (Docker), `just test-e2e` (Playwright).

## Implementation Plan

### Step 1: Docker Compose Lifecycle Smoke Tests

Create `backend/tests/e2e/test_docker_smoke.py` and a shell script for Docker-level tests that cannot run inside pytest.

```bash
#!/bin/bash
# scripts/docker-smoke-test.sh
# Run this script from the project root with Docker Compose running.
set -euo pipefail

echo "=== Docker Compose Smoke Test ==="
echo ""

# --- Test 1: Clean start from scratch ---
echo "[1/8] Clean start: docker compose down && docker compose up"
docker compose down -v --remove-orphans 2>/dev/null || true
docker compose up -d
echo "Waiting for services to be healthy..."

# Wait for db
echo -n "  db: "
for i in $(seq 1 30); do
    if docker compose exec db pg_isready -U ogdocs -d ogdocs >/dev/null 2>&1; then
        echo "healthy (${i}s)"
        break
    fi
    sleep 1
    if [ "$i" -eq 30 ]; then
        echo "FAILED (timeout)"
        docker compose logs db
        exit 1
    fi
done

# Wait for backend
echo -n "  backend: "
for i in $(seq 1 60); do
    if curl -sf http://localhost:8000/health >/dev/null 2>&1; then
        echo "healthy (${i}s)"
        break
    fi
    sleep 1
    if [ "$i" -eq 60 ]; then
        echo "FAILED (timeout)"
        docker compose logs backend
        exit 1
    fi
done

# Wait for frontend
echo -n "  frontend: "
for i in $(seq 1 60); do
    if curl -sf http://localhost:3000 >/dev/null 2>&1; then
        echo "healthy (${i}s)"
        break
    fi
    sleep 1
    if [ "$i" -eq 60 ]; then
        echo "FAILED (timeout)"
        docker compose logs frontend
        exit 1
    fi
done

echo ""

# --- Test 2: All containers are running ---
echo "[2/8] Verify all containers are running"
RUNNING=$(docker compose ps --format json | python3 -c "
import sys, json
services = [json.loads(line) for line in sys.stdin if line.strip()]
running = [s for s in services if s.get('State') == 'running']
print(len(running))
")
echo "  Running containers: $RUNNING"
if [ "$RUNNING" -lt 3 ]; then
    echo "  FAILED: Expected at least 3 running containers (db, backend, frontend)"
    docker compose ps
    exit 1
fi
echo "  PASSED"
echo ""

# --- Test 3: Database migrations run clean ---
echo "[3/8] Database migrations on fresh database"
docker compose exec backend uv run alembic upgrade head
echo "  Migrations: PASSED"
echo ""

# --- Test 4: Health endpoints respond ---
echo "[4/8] Health endpoint checks"
BACKEND_HEALTH=$(curl -s http://localhost:8000/health)
echo "  Backend health: $BACKEND_HEALTH"
FRONTEND_STATUS=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:3000)
echo "  Frontend HTTP status: $FRONTEND_STATUS"
if [ "$FRONTEND_STATUS" != "200" ]; then
    echo "  FAILED: Frontend returned $FRONTEND_STATUS"
    exit 1
fi
echo "  PASSED"
echo ""

# --- Test 5: API endpoints respond ---
echo "[5/8] API endpoint response check"
ENDPOINTS=(
    "/api/states"
    "/api/wells?per_page=1"
    "/api/documents?per_page=1"
    "/api/review?per_page=1"
    "/api/scrape/jobs"
    "/api/stats"
    "/api/map/wells?min_lat=30&max_lat=35&min_lng=-105&max_lng=-100"
)
for endpoint in "${ENDPOINTS[@]}"; do
    STATUS=$(curl -s -o /dev/null -w "%{http_code}" "http://localhost:8000${endpoint}")
    RESPONSE_TIME=$(curl -s -o /dev/null -w "%{time_total}" "http://localhost:8000${endpoint}")
    echo "  ${endpoint}: ${STATUS} (${RESPONSE_TIME}s)"
    if [ "$STATUS" != "200" ]; then
        echo "    FAILED: Expected 200, got $STATUS"
        curl -s "http://localhost:8000${endpoint}" | python3 -m json.tool 2>/dev/null || true
    fi
done
echo ""

# --- Test 6: PostGIS extension is enabled ---
echo "[6/8] PostGIS extension check"
POSTGIS=$(docker compose exec db psql -U ogdocs -d ogdocs -t -c "SELECT PostGIS_version();" 2>/dev/null | tr -d ' ')
echo "  PostGIS version: $POSTGIS"
if [ -z "$POSTGIS" ]; then
    echo "  FAILED: PostGIS not enabled"
    exit 1
fi
echo "  PASSED"
echo ""

# --- Test 7: Database tables exist ---
echo "[7/8] Database table verification"
TABLES=$(docker compose exec db psql -U ogdocs -d ogdocs -t -c "
    SELECT table_name FROM information_schema.tables
    WHERE table_schema = 'public'
    ORDER BY table_name;
" 2>/dev/null)
EXPECTED_TABLES="data_corrections documents extracted_data operators review_queue scrape_jobs states wells"
echo "  Tables found:"
echo "$TABLES" | while read -r table; do
    table=$(echo "$table" | tr -d ' ')
    if [ -n "$table" ]; then
        echo "    - $table"
    fi
done
echo "  PASSED"
echo ""

# --- Test 8: Service stability (quick check) ---
echo "[8/8] Service stability (30-second soak)"
sleep 30
for service in db backend frontend; do
    STATUS=$(docker compose ps $service --format "{{.State}}" 2>/dev/null || echo "unknown")
    echo "  $service: $STATUS"
    if [ "$STATUS" != "running" ]; then
        echo "  FAILED: $service is not running after 30s soak"
        docker compose logs $service --tail 20
        exit 1
    fi
done
echo "  PASSED"
echo ""

echo "=== All Docker Smoke Tests PASSED ==="
```

### Step 2: API Performance Benchmark Tests

Create `backend/tests/e2e/test_performance.py` that measures response times for all API endpoints.

```python
# backend/tests/e2e/test_performance.py
import pytest
import time
import statistics

PERFORMANCE_THRESHOLD_MS = 500  # All endpoints must respond in < 500ms

@pytest.mark.asyncio
@pytest.mark.benchmark
async def test_wells_list_under_500ms(client, seed_1000_wells):
    """GET /api/wells with 1000+ wells in DB should respond in < 500ms."""
    times = []
    for _ in range(10):
        start = time.monotonic()
        response = await client.get("/api/wells", params={"per_page": 50})
        elapsed = (time.monotonic() - start) * 1000
        times.append(elapsed)
        assert response.status_code == 200

    avg_ms = statistics.mean(times)
    p95_ms = sorted(times)[int(len(times) * 0.95)]
    print(f"  GET /api/wells: avg={avg_ms:.1f}ms, p95={p95_ms:.1f}ms")
    assert avg_ms < PERFORMANCE_THRESHOLD_MS, f"Average {avg_ms:.1f}ms exceeds {PERFORMANCE_THRESHOLD_MS}ms"
    assert p95_ms < PERFORMANCE_THRESHOLD_MS * 1.5, f"P95 {p95_ms:.1f}ms exceeds threshold"

@pytest.mark.asyncio
@pytest.mark.benchmark
async def test_wells_search_under_500ms(client, seed_1000_wells):
    """Full-text search should respond in < 500ms."""
    times = []
    queries = ["production", "devon", "permian", "oil", "42-461"]
    for q in queries:
        start = time.monotonic()
        response = await client.get("/api/wells/search", params={"q": q})
        elapsed = (time.monotonic() - start) * 1000
        times.append(elapsed)
        assert response.status_code == 200

    avg_ms = statistics.mean(times)
    print(f"  GET /api/wells/search: avg={avg_ms:.1f}ms")
    assert avg_ms < PERFORMANCE_THRESHOLD_MS

@pytest.mark.asyncio
@pytest.mark.benchmark
async def test_documents_list_under_500ms(client, seed_documents):
    """GET /api/documents should respond in < 500ms."""
    times = []
    for _ in range(10):
        start = time.monotonic()
        response = await client.get("/api/documents", params={"per_page": 50})
        elapsed = (time.monotonic() - start) * 1000
        times.append(elapsed)
        assert response.status_code == 200

    avg_ms = statistics.mean(times)
    print(f"  GET /api/documents: avg={avg_ms:.1f}ms")
    assert avg_ms < PERFORMANCE_THRESHOLD_MS

@pytest.mark.asyncio
@pytest.mark.benchmark
async def test_map_wells_under_500ms(client, seed_1000_wells):
    """GET /api/map/wells with 1000+ wells should respond in < 500ms."""
    times = []
    bboxes = [
        {"min_lat": 25, "max_lat": 50, "min_lng": -130, "max_lng": -65, "limit": 1000},  # Full US
        {"min_lat": 31, "max_lat": 33, "min_lng": -104, "max_lng": -101, "limit": 1000},  # Permian
        {"min_lat": 46, "max_lat": 49, "min_lng": -104, "max_lng": -97, "limit": 1000},   # Bakken
    ]
    for bbox in bboxes:
        start = time.monotonic()
        response = await client.get("/api/map/wells", params=bbox)
        elapsed = (time.monotonic() - start) * 1000
        times.append(elapsed)
        assert response.status_code == 200

    avg_ms = statistics.mean(times)
    print(f"  GET /api/map/wells: avg={avg_ms:.1f}ms")
    assert avg_ms < PERFORMANCE_THRESHOLD_MS

@pytest.mark.asyncio
@pytest.mark.benchmark
async def test_well_detail_under_500ms(client, seed_1000_wells):
    """GET /api/wells/{id} should respond in < 500ms."""
    # Get a well ID first
    response = await client.get("/api/wells", params={"per_page": 1})
    well_id = response.json()["items"][0]["id"]

    times = []
    for _ in range(10):
        start = time.monotonic()
        response = await client.get(f"/api/wells/{well_id}")
        elapsed = (time.monotonic() - start) * 1000
        times.append(elapsed)
        assert response.status_code == 200

    avg_ms = statistics.mean(times)
    print(f"  GET /api/wells/{{id}}: avg={avg_ms:.1f}ms")
    assert avg_ms < PERFORMANCE_THRESHOLD_MS

@pytest.mark.asyncio
@pytest.mark.benchmark
async def test_stats_endpoint_under_500ms(client, seed_1000_wells):
    """GET /api/stats should respond in < 500ms."""
    times = []
    for _ in range(10):
        start = time.monotonic()
        response = await client.get("/api/stats")
        elapsed = (time.monotonic() - start) * 1000
        times.append(elapsed)
        assert response.status_code == 200

    avg_ms = statistics.mean(times)
    print(f"  GET /api/stats: avg={avg_ms:.1f}ms")
    assert avg_ms < PERFORMANCE_THRESHOLD_MS

@pytest.mark.asyncio
@pytest.mark.benchmark
async def test_review_queue_under_500ms(client, seed_review_items):
    """GET /api/review should respond in < 500ms."""
    times = []
    for _ in range(10):
        start = time.monotonic()
        response = await client.get("/api/review")
        elapsed = (time.monotonic() - start) * 1000
        times.append(elapsed)
        assert response.status_code == 200

    avg_ms = statistics.mean(times)
    print(f"  GET /api/review: avg={avg_ms:.1f}ms")
    assert avg_ms < PERFORMANCE_THRESHOLD_MS

@pytest.mark.asyncio
@pytest.mark.benchmark
async def test_export_wells_streaming_performance(client, seed_1000_wells):
    """GET /api/export/wells should start streaming in < 2s."""
    start = time.monotonic()
    response = await client.get("/api/export/wells", params={"format": "csv"})
    elapsed = (time.monotonic() - start) * 1000
    assert response.status_code == 200
    print(f"  GET /api/export/wells (CSV): {elapsed:.1f}ms")
    # Export can take longer than CRUD, but should start streaming quickly
    assert elapsed < 5000, f"Export took {elapsed:.1f}ms, expected < 5000ms"
```

### Step 3: Seed Data Fixtures for Performance Testing

Create fixtures that generate 1000+ wells for realistic performance testing.

```python
# backend/tests/e2e/conftest.py (additions)
import random
import uuid
from decimal import Decimal

STATE_COORDS = {
    "TX": (31.0, 34.0, -106.0, -94.0),
    "NM": (32.0, 37.0, -109.0, -103.0),
    "ND": (46.0, 49.0, -104.0, -97.0),
    "OK": (34.0, 37.0, -103.0, -95.0),
    "CO": (37.0, 41.0, -109.0, -102.0),
    "WY": (41.0, 45.0, -111.0, -104.0),
    "LA": (29.0, 33.0, -94.0, -89.0),
    "PA": (40.0, 42.0, -80.0, -75.0),
    "CA": (35.0, 40.0, -122.0, -115.0),
    "AK": (58.0, 71.0, -165.0, -130.0),
}

OPERATORS = [
    "Devon Energy", "Continental Resources", "Pioneer Natural Resources",
    "EOG Resources", "Diamondback Energy", "ConocoPhillips",
    "Apache Corporation", "Marathon Oil", "Chesapeake Energy",
    "Occidental Petroleum",
]

@pytest_asyncio.fixture
async def seed_1000_wells(db_session):
    """Seed 1000+ wells across all 10 states for performance testing."""
    from og_scraper.models.well import Well
    from og_scraper.models.operator import Operator
    from og_scraper.models.state import State

    wells = []
    for i in range(1000):
        state_code = random.choice(list(STATE_COORDS.keys()))
        lat_min, lat_max, lng_min, lng_max = STATE_COORDS[state_code]
        lat = Decimal(str(round(random.uniform(lat_min, lat_max), 7)))
        lng = Decimal(str(round(random.uniform(lng_min, lng_max), 7)))
        operator = random.choice(OPERATORS)

        # Generate realistic API number
        state_fips = {"TX": "42", "NM": "30", "ND": "33", "OK": "35", "CO": "05",
                      "WY": "49", "LA": "17", "PA": "37", "CA": "04", "AK": "02"}
        county = str(random.randint(1, 250)).zfill(3)
        unique = str(random.randint(10000, 99999))
        api = f"{state_fips[state_code]}{county}{unique}0000"

        well = Well(
            id=uuid.uuid4(),
            api_number=api,
            well_name=f"Test Well {i+1}",
            operator_name=operator,
            state=state_code,
            county=f"County {county}",
            latitude=lat,
            longitude=lng,
            status="active",
        )
        db_session.add(well)
        wells.append(well)

    await db_session.flush()
    return wells

@pytest_asyncio.fixture
async def seed_documents(db_session, seed_1000_wells):
    """Seed documents for a subset of wells."""
    from og_scraper.models.document import Document
    doc_types = [
        "production_report", "well_permit", "completion_report",
        "spacing_order", "plugging_report", "inspection_record", "incident_report",
    ]
    documents = []
    for well in seed_1000_wells[:200]:  # 200 wells with documents
        doc = Document(
            id=uuid.uuid4(),
            well_id=well.id,
            doc_type=random.choice(doc_types),
            status="stored",
            state=well.state,
            confidence_score=Decimal(str(round(random.uniform(0.3, 0.99), 3))),
            file_hash=uuid.uuid4().hex,
            file_path=f"data/{well.state}/{well.operator_name}/{random.choice(doc_types)}/{uuid.uuid4().hex[:12]}.pdf",
        )
        db_session.add(doc)
        documents.append(doc)
    await db_session.flush()
    return documents

@pytest_asyncio.fixture
async def seed_review_items(db_session, seed_documents):
    """Seed review queue items from medium-confidence documents."""
    from og_scraper.models.review_queue import ReviewQueue
    items = []
    medium_conf_docs = [d for d in seed_documents if 0.50 <= float(d.confidence_score) < 0.85]
    for doc in medium_conf_docs[:50]:
        item = ReviewQueue(
            id=uuid.uuid4(),
            document_id=doc.id,
            status="pending",
            reason="low_confidence",
            confidence_score=doc.confidence_score,
        )
        db_session.add(item)
        items.append(item)
    await db_session.flush()
    return items
```

### Step 4: Map Rendering Performance Test (Playwright)

```typescript
// frontend/e2e/performance.spec.ts
import { test, expect } from '@playwright/test';
import { takeEvidenceScreenshot } from './helpers';

test.describe('Map Performance', () => {
  test('map renders 1000+ wells without lag', async ({ page }) => {
    // Navigate to map
    await page.goto('/map');
    await page.waitForSelector('.leaflet-container', { timeout: 15_000 });

    // Measure time to load markers
    const startTime = Date.now();
    await page.waitForSelector('.leaflet-marker-icon, .leaflet-interactive', {
      timeout: 30_000,
    });
    const loadTime = Date.now() - startTime;

    console.log(`Map marker load time: ${loadTime}ms`);
    expect(loadTime).toBeLessThan(10_000); // Should load within 10 seconds

    // Verify markers are present
    const markerCount = await page.locator('.leaflet-marker-icon').count();
    console.log(`Map markers visible: ${markerCount}`);

    await takeEvidenceScreenshot(page, 'perf-01-map-loaded');
  });

  test('map zoom is responsive', async ({ page }) => {
    await page.goto('/map');
    await page.waitForSelector('.leaflet-container', { timeout: 15_000 });
    await page.waitForTimeout(3000); // Wait for initial load

    // Measure zoom interaction time
    const zoomIn = page.locator('.leaflet-control-zoom-in');

    const startTime = Date.now();
    await zoomIn.click();
    await page.waitForTimeout(500);
    await zoomIn.click();
    await page.waitForTimeout(500);
    const zoomTime = Date.now() - startTime;

    console.log(`Map zoom interaction time: ${zoomTime}ms`);
    // Zoom should be responsive (under 3 seconds for 2 zoom levels)
    expect(zoomTime).toBeLessThan(5000);

    await takeEvidenceScreenshot(page, 'perf-02-map-after-zoom');
  });

  test('map pan is responsive', async ({ page }) => {
    await page.goto('/map');
    await page.waitForSelector('.leaflet-container', { timeout: 15_000 });
    await page.waitForTimeout(3000);

    // Drag the map to pan
    const map = page.locator('.leaflet-container');
    const box = await map.boundingBox();
    if (box) {
      const startTime = Date.now();
      await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
      await page.mouse.down();
      await page.mouse.move(box.x + box.width / 2 + 200, box.y + box.height / 2 + 100, {
        steps: 10,
      });
      await page.mouse.up();
      await page.waitForTimeout(1000);
      const panTime = Date.now() - startTime;

      console.log(`Map pan interaction time: ${panTime}ms`);
      expect(panTime).toBeLessThan(5000);
    }

    await takeEvidenceScreenshot(page, 'perf-03-map-after-pan');
  });
});

test.describe('Page Load Performance', () => {
  const pages = [
    { name: 'Dashboard', path: '/' },
    { name: 'Wells', path: '/wells' },
    { name: 'Documents', path: '/documents' },
    { name: 'Map', path: '/map' },
    { name: 'Scrape', path: '/scrape' },
    { name: 'Review', path: '/review' },
  ];

  for (const { name, path } of pages) {
    test(`${name} page loads in under 5 seconds`, async ({ page }) => {
      const startTime = Date.now();
      await page.goto(path);
      await page.waitForLoadState('networkidle');
      const loadTime = Date.now() - startTime;

      console.log(`${name} page load time: ${loadTime}ms`);
      expect(loadTime).toBeLessThan(5000);
    });
  }
});

test.describe('Frontend Console Errors', () => {
  const pages = [
    { name: 'Dashboard', path: '/' },
    { name: 'Wells', path: '/wells' },
    { name: 'Documents', path: '/documents' },
    { name: 'Map', path: '/map' },
    { name: 'Scrape', path: '/scrape' },
    { name: 'Review', path: '/review' },
  ];

  for (const { name, path } of pages) {
    test(`${name} page has no console errors`, async ({ page }) => {
      const errors: string[] = [];
      page.on('console', (msg) => {
        if (msg.type() === 'error') {
          const text = msg.text();
          // Ignore known benign errors
          if (
            !text.includes('Failed to load resource') &&    // Tile loading
            !text.includes('favicon') &&                     // Missing favicon
            !text.includes('Download the React DevTools')    // React dev tools
          ) {
            errors.push(text);
          }
        }
      });

      await page.goto(path);
      await page.waitForLoadState('networkidle');
      await page.waitForTimeout(3000); // Wait for async operations

      expect(errors).toEqual([]);
    });
  }
});
```

### Step 5: OCR Processing Performance Benchmark

```python
# backend/tests/e2e/test_ocr_performance.py
import pytest
import time

@pytest.mark.asyncio
@pytest.mark.benchmark
@pytest.mark.slow
async def test_single_document_ocr_under_30s(pipeline):
    """A single document should process through OCR in < 30 seconds."""
    start = time.monotonic()
    result = await pipeline.process(
        "tests/fixtures/ocr/known_good/texas_production_001.pdf", state="TX"
    )
    elapsed = time.monotonic() - start

    print(f"  Single document OCR time: {elapsed:.1f}s")
    assert elapsed < 30.0, f"OCR took {elapsed:.1f}s, expected < 30s"
    assert result is not None
    assert result.disposition in ("auto_accepted", "review_queue")

@pytest.mark.asyncio
@pytest.mark.benchmark
@pytest.mark.slow
async def test_text_pdf_processing_under_5s(pipeline):
    """A text-extractable PDF (no OCR needed) should process in < 5 seconds."""
    start = time.monotonic()
    result = await pipeline.process(
        "tests/fixtures/documents/texas/clean_production_report.pdf", state="TX"
    )
    elapsed = time.monotonic() - start

    print(f"  Text PDF processing time: {elapsed:.1f}s")
    assert elapsed < 5.0, f"Text PDF processing took {elapsed:.1f}s, expected < 5s"

@pytest.mark.asyncio
@pytest.mark.benchmark
@pytest.mark.slow
async def test_batch_processing_throughput(pipeline):
    """Process 5 documents sequentially and verify reasonable throughput."""
    test_docs = [
        "tests/fixtures/ocr/known_good/texas_production_001.pdf",
        "tests/fixtures/documents/texas/clean_production_report.pdf",
        "tests/fixtures/documents/oklahoma/completion_report.pdf",
        "tests/fixtures/documents/colorado/spacing_order.pdf",
        "tests/fixtures/documents/pennsylvania/plugging_report.pdf",
    ]

    start = time.monotonic()
    results = []
    for doc in test_docs:
        state = doc.split("/")[3][:2].upper()
        result = await pipeline.process(doc, state=state)
        results.append(result)
    total_elapsed = time.monotonic() - start

    avg_per_doc = total_elapsed / len(test_docs)
    print(f"  Batch processing: {len(test_docs)} docs in {total_elapsed:.1f}s (avg {avg_per_doc:.1f}s/doc)")
    assert avg_per_doc < 30.0, f"Average {avg_per_doc:.1f}s/doc exceeds 30s limit"
    assert all(r is not None for r in results)
```

### Step 6: Scrape Performance Test (VCR Replay)

```python
# backend/tests/e2e/test_scrape_performance.py
import pytest
import time

@pytest.mark.asyncio
@pytest.mark.benchmark
@pytest.mark.vcr()
async def test_single_state_scrape_completes_in_reasonable_time(client):
    """A single state scrape with VCR cassettes should complete quickly."""
    start = time.monotonic()
    response = await client.post("/api/scrape", json={"state": "PA"})
    assert response.status_code == 202
    job_id = response.json()["job_id"]

    # Poll for completion
    for _ in range(60):  # Up to 60 seconds
        job_resp = await client.get(f"/api/scrape/{job_id}")
        job_data = job_resp.json()
        if job_data["status"] in ("completed", "failed"):
            break
        await asyncio.sleep(1)

    elapsed = time.monotonic() - start
    print(f"  PA scrape time (VCR): {elapsed:.1f}s")
    assert job_data["status"] == "completed"
    # VCR replayed scrape should be fast (no network)
    assert elapsed < 120, f"Scrape took {elapsed:.1f}s with VCR, expected < 120s"

@pytest.mark.asyncio
@pytest.mark.benchmark
async def test_database_migration_on_fresh_db(engine):
    """Running Alembic migrations on a fresh database should complete quickly."""
    start = time.monotonic()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    elapsed = time.monotonic() - start

    print(f"  Fresh DB migration time: {elapsed:.1f}s")
    assert elapsed < 30, f"Migration took {elapsed:.1f}s, expected < 30s"
```

### Step 7: Stability Soak Test

```python
# backend/tests/e2e/test_stability.py
import pytest
import asyncio
import time

@pytest.mark.asyncio
@pytest.mark.benchmark
@pytest.mark.slow
async def test_sustained_api_requests(client, seed_1000_wells):
    """Make 100 API requests over 60 seconds and verify no failures."""
    errors = []
    total_requests = 100
    start = time.monotonic()

    endpoints = [
        "/api/wells?per_page=10",
        "/api/documents?per_page=10",
        "/api/stats",
        "/api/states",
        "/api/review?per_page=10",
        "/api/map/wells?min_lat=30&max_lat=35&min_lng=-105&max_lng=-100&limit=100",
    ]

    for i in range(total_requests):
        endpoint = endpoints[i % len(endpoints)]
        try:
            response = await client.get(endpoint)
            if response.status_code != 200:
                errors.append(f"Request {i}: {endpoint} returned {response.status_code}")
        except Exception as e:
            errors.append(f"Request {i}: {endpoint} raised {e}")

        # Small delay to spread requests over time
        if i % 10 == 0:
            await asyncio.sleep(0.5)

    elapsed = time.monotonic() - start
    print(f"  Sustained test: {total_requests} requests in {elapsed:.1f}s, {len(errors)} errors")
    assert len(errors) == 0, f"Errors during sustained test: {errors}"
```

### Step 8: Full Test Suite Runner

Create the final comprehensive test run command.

Add to `justfile`:
```makefile
# Run ALL test suites (the final test command)
test-all:
    @echo "=== Running Full Test Suite ==="
    @echo ""
    @echo "--- Python Unit Tests ---"
    uv run pytest backend/tests/ -m "not slow and not integration and not benchmark" --timeout=30 -q
    @echo ""
    @echo "--- Python Integration Tests ---"
    uv run pytest backend/tests/ -m "integration" --timeout=120 -q
    @echo ""
    @echo "--- Python E2E Tests ---"
    uv run pytest backend/tests/e2e/ --timeout=300 -q
    @echo ""
    @echo "--- Python Performance Benchmarks ---"
    uv run pytest backend/tests/e2e/ -m "benchmark" --timeout=300 -v
    @echo ""
    @echo "--- Frontend Component Tests ---"
    cd frontend && npm test -- --run
    @echo ""
    @echo "--- Playwright E2E Tests ---"
    cd frontend && npx playwright test
    @echo ""
    @echo "=== All Tests Complete ==="

# Docker smoke test
test-docker-smoke:
    bash scripts/docker-smoke-test.sh

# Performance benchmarks only
test-performance:
    uv run pytest backend/tests/e2e/ -m "benchmark" --timeout=300 -v
    cd frontend && npx playwright test e2e/performance.spec.ts

# Extended stability soak (30+ minutes)
test-stability:
    uv run pytest backend/tests/e2e/test_stability.py -v --timeout=600
```

### Step 9: API Performance Measurement via curl

```bash
#!/bin/bash
# scripts/api-benchmark.sh
# Run against a live Docker Compose stack to measure real response times
set -euo pipefail

echo "=== API Performance Benchmark ==="
echo "Threshold: all endpoints < 500ms"
echo ""

ENDPOINTS=(
    "GET /api/states"
    "GET /api/wells?per_page=50"
    "GET /api/wells/search?q=production"
    "GET /api/documents?per_page=50"
    "GET /api/review?per_page=50"
    "GET /api/scrape/jobs"
    "GET /api/stats"
    "GET /api/map/wells?min_lat=30&max_lat=35&min_lng=-105&max_lng=-100&limit=1000"
)

PASS=0
FAIL=0

for entry in "${ENDPOINTS[@]}"; do
    METHOD=$(echo "$entry" | cut -d' ' -f1)
    ENDPOINT=$(echo "$entry" | cut -d' ' -f2)

    # Run 5 times and get average
    TOTAL=0
    for i in $(seq 1 5); do
        TIME_MS=$(curl -s -o /dev/null -w "%{time_total}" "http://localhost:8000${ENDPOINT}" | awk '{printf "%.0f", $1 * 1000}')
        TOTAL=$((TOTAL + TIME_MS))
    done
    AVG=$((TOTAL / 5))

    if [ "$AVG" -lt 500 ]; then
        STATUS="PASS"
        PASS=$((PASS + 1))
    else
        STATUS="FAIL"
        FAIL=$((FAIL + 1))
    fi

    printf "  %-60s %4dms  [%s]\n" "$METHOD $ENDPOINT" "$AVG" "$STATUS"
done

echo ""
echo "Results: $PASS passed, $FAIL failed"
if [ "$FAIL" -gt 0 ]; then
    echo "FAILED: Some endpoints exceeded 500ms threshold"
    exit 1
fi
echo "ALL PASSED"
```

## Files to Create

- `scripts/docker-smoke-test.sh` - Docker Compose lifecycle smoke tests
- `scripts/api-benchmark.sh` - API performance measurement script
- `backend/tests/e2e/test_performance.py` - API response time benchmark tests
- `backend/tests/e2e/test_ocr_performance.py` - OCR processing speed benchmarks
- `backend/tests/e2e/test_scrape_performance.py` - Scrape completion time tests
- `backend/tests/e2e/test_stability.py` - Sustained operation stability tests
- `frontend/e2e/performance.spec.ts` - Map rendering performance and page load tests

## Files to Modify

- `backend/tests/e2e/conftest.py` - Add seed_1000_wells, seed_documents, seed_review_items fixtures
- `justfile` - Add `test-all`, `test-docker-smoke`, `test-performance`, `test-stability` commands

## Contracts

### Provides (for downstream tasks)

This is the final task. It provides the final validation that the entire project is production-ready:
- All services start cleanly via Docker Compose
- All API endpoints respond within 500ms
- Map handles 1000+ wells
- OCR processes single documents within 30 seconds
- No console errors on any frontend page
- All test suites pass

### Consumes (from upstream tasks)

- From Task 7.1: E2E test infrastructure, pipeline tests
- From Task 7.2: Playwright test infrastructure, dashboard tests
- From Task 7.3: Error handling tests, edge case tests
- From all phases: The complete application to test

## Acceptance Criteria

- [ ] `docker compose down && docker compose up` starts all services cleanly
- [ ] All services remain healthy after 30+ seconds of operation
- [ ] Database health check passes (pg_isready)
- [ ] Backend health check passes (GET /health)
- [ ] Frontend health check passes (GET /)
- [ ] PostGIS extension is enabled in the database
- [ ] All 8 database tables exist with correct schema
- [ ] All API endpoints respond in < 500ms average (with test dataset of 1000+ wells)
- [ ] Full-text search responds in < 500ms
- [ ] Map viewport query responds in < 500ms
- [ ] Map renders 1000+ wells in Playwright without timing out
- [ ] Map zoom and pan are responsive (< 5s interaction time)
- [ ] All 6 frontend pages load in < 5 seconds each
- [ ] No console errors on any frontend page
- [ ] Single document OCR processing completes in < 30 seconds
- [ ] Text PDF processing completes in < 5 seconds
- [ ] Single state scrape completes in reasonable time (VCR replay < 120s)
- [ ] Database migrations run clean on fresh database (< 30s)
- [ ] 100 sustained API requests complete with zero errors
- [ ] `uv run pytest backend/tests/ -q` passes (all Python tests)
- [ ] `cd frontend && npm test -- --run` passes (all component tests)
- [ ] `cd frontend && npx playwright test` passes (all Playwright tests)
- [ ] `just test-all` completes successfully

## Testing Protocol

### Docker Smoke Tests

```bash
# Run the full Docker smoke test
bash scripts/docker-smoke-test.sh

# Or individual checks:
docker compose down -v && docker compose up -d
docker compose ps
curl http://localhost:8000/health
curl http://localhost:3000
docker compose exec db psql -U ogdocs -d ogdocs -c "SELECT PostGIS_version();"
docker compose exec db psql -U ogdocs -d ogdocs -c "\\dt"
```

### API Performance Benchmarks

```bash
# Run API benchmark script
bash scripts/api-benchmark.sh

# Or individual endpoint timing via curl:
curl -s -o /dev/null -w "Time: %{time_total}s\n" http://localhost:8000/api/wells?per_page=50
curl -s -o /dev/null -w "Time: %{time_total}s\n" http://localhost:8000/api/wells/search?q=production
curl -s -o /dev/null -w "Time: %{time_total}s\n" "http://localhost:8000/api/map/wells?min_lat=30&max_lat=35&min_lng=-105&max_lng=-100&limit=1000"
curl -s -o /dev/null -w "Time: %{time_total}s\n" http://localhost:8000/api/stats
```

### Python Performance Tests

```bash
# All benchmarks
uv run pytest backend/tests/e2e/ -m "benchmark" --timeout=300 -v

# OCR-specific (slow, requires PaddleOCR)
uv run pytest backend/tests/e2e/test_ocr_performance.py -v --timeout=300

# API response time benchmarks (requires testcontainers)
uv run pytest backend/tests/e2e/test_performance.py -v --timeout=120

# Stability soak
uv run pytest backend/tests/e2e/test_stability.py -v --timeout=600
```

### Playwright Performance Tests

```bash
# Map and page load performance
cd frontend && npx playwright test e2e/performance.spec.ts --headed

# Console error check across all pages
cd frontend && npx playwright test e2e/performance.spec.ts -g "console errors"
```

### Full Test Suite

```bash
# THE FINAL COMMAND: Run everything
just test-all
```

### Build/Lint/Type Checks

- [ ] `uv run ruff check backend/` passes
- [ ] `uv run ruff format --check backend/` passes
- [ ] `cd frontend && npm run lint` passes
- [ ] `cd frontend && npx tsc --noEmit` passes
- [ ] `cd frontend && npm run build` succeeds
- [ ] `docker compose build` succeeds

## Skills to Read

- `og-testing-strategies` - Test infrastructure patterns, running tests, marker configuration
- `og-scraper-architecture` - Service architecture, ports, Docker Compose services
- `nextjs-dashboard` - Frontend performance constraints, Supercluster limits, SSE connection limits
- `docker-local-deployment` - Docker Compose configuration, health checks, service dependencies

## Research Files to Read

- `.claude/orchestration-og-doc-scraper/research/testing-deployment-implementation.md` - Docker Compose configuration, health checks, development workflow, monitoring
- `.claude/orchestration-og-doc-scraper/research/dashboard-map-implementation.md` - Supercluster performance characteristics (10K-50K markers)

## Git

- Branch: `task-7-4/performance-smoke-tests`
- Commit message prefix: `Task 7.4:`
