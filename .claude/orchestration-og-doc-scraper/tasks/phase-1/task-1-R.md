# Task 1.R: Phase 1 Regression

## Objective

Full regression test of all Phase 1 tasks (1.1, 1.2, 1.3, 1.4) to verify the foundation is solid before moving to Phase 2. This task starts all Docker services, runs all tests, verifies database schema, confirms API connectivity, and validates the scraper framework. No new code is written -- this is a pure verification and bug-fixing task.

## Context

All Phase 1 tasks should be complete at this point:
- Task 1.1: Project scaffolding, Docker Compose, dev tooling
- Task 1.2: Database schema with 8 tables, Alembic migrations, PostGIS triggers
- Task 1.3: Base scraper framework, state registry, download pipelines
- Task 1.4: FastAPI skeleton, health check, CORS, Huey initialization

This regression task ensures everything works together as an integrated system. If any test fails, debug and fix the issue before marking complete. The goal is a clean, verified foundation that Phase 2 (Document Pipeline) and Phase 3 (Backend API) can build on confidently.

## Dependencies

- Task 1.1 - Project scaffolding
- Task 1.2 - Database schema and migrations
- Task 1.3 - Base scraper framework
- Task 1.4 - FastAPI skeleton

## Blocked By

- Tasks 1.1, 1.2, 1.3, and 1.4 (all must be complete)

## Research Findings

No new research needed. This task verifies the work done in Tasks 1.1-1.4 against their documented contracts and acceptance criteria.

## Implementation Plan

### Step 1: Verify Project Structure

Confirm the following directory structure exists and is complete:

```
og-doc-scraper/
├── pyproject.toml                          # UV workspace root
├── .python-version                         # 3.12
├── .gitignore
├── ruff.toml
├── justfile
├── .env.example
├── docker-compose.yml
├── backend/
│   ├── pyproject.toml
│   ├── Dockerfile.dev
│   ├── alembic.ini
│   ├── alembic/
│   │   ├── env.py
│   │   ├── script.py.mako
│   │   └── versions/
│   │       └── 001_initial_schema.py
│   ├── scripts/
│   │   └── init-db.sql
│   ├── src/og_scraper/
│   │   ├── __init__.py
│   │   ├── config.py
│   │   ├── database.py
│   │   ├── worker.py
│   │   ├── logging_config.py
│   │   ├── models/
│   │   │   ├── __init__.py
│   │   │   ├── base.py
│   │   │   ├── enums.py
│   │   │   ├── state.py
│   │   │   ├── operator.py
│   │   │   ├── well.py
│   │   │   ├── document.py
│   │   │   ├── extracted_data.py
│   │   │   ├── review_queue.py
│   │   │   ├── scrape_job.py
│   │   │   └── data_correction.py
│   │   ├── schemas/
│   │   │   └── __init__.py
│   │   ├── api/
│   │   │   ├── __init__.py
│   │   │   ├── app.py
│   │   │   ├── deps.py
│   │   │   └── routes/
│   │   │       ├── __init__.py
│   │   │       └── health.py
│   │   ├── services/
│   │   │   └── __init__.py
│   │   ├── scrapers/
│   │   │   ├── __init__.py
│   │   │   ├── settings.py
│   │   │   ├── items.py
│   │   │   ├── state_registry.py
│   │   │   ├── spiders/
│   │   │   │   ├── __init__.py
│   │   │   │   └── base.py
│   │   │   ├── pipelines/
│   │   │   │   ├── __init__.py
│   │   │   │   ├── validation.py
│   │   │   │   ├── deduplication.py
│   │   │   │   └── storage.py
│   │   │   ├── middlewares/
│   │   │   │   ├── __init__.py
│   │   │   │   ├── rate_limiter.py
│   │   │   │   └── user_agent.py
│   │   │   ├── adapters/
│   │   │   │   └── __init__.py
│   │   │   └── parsers/
│   │   │       └── __init__.py
│   │   ├── pipeline/
│   │   │   └── __init__.py
│   │   └── utils/
│   │       ├── __init__.py
│   │       └── api_number.py
│   └── tests/
│       ├── __init__.py
│       ├── conftest.py
│       ├── test_config.py
│       ├── test_models.py
│       ├── api/
│       │   ├── __init__.py
│       │   ├── test_health.py
│       │   └── test_cors.py
│       ├── scrapers/
│       │   ├── __init__.py
│       │   ├── test_base_spider.py
│       │   ├── test_state_registry.py
│       │   └── test_pipelines.py
│       └── utils/
│           ├── __init__.py
│           └── test_api_number.py
├── frontend/
│   ├── package.json
│   ├── tsconfig.json
│   ├── next.config.ts
│   ├── postcss.config.mjs
│   ├── Dockerfile.dev
│   ├── src/
│   │   └── app/
│   │       ├── globals.css
│   │       ├── layout.tsx
│   │       └── page.tsx
│   └── public/
│       └── .gitkeep
├── data/
│   ├── documents/
│   │   └── .gitkeep
│   └── exports/
│       └── .gitkeep
└── config/
    └── states/
        └── .gitkeep
```

Verify each file exists. If any are missing, create them. Check that all `__init__.py` files are in place.

### Step 2: Docker Compose -- Start All Services

Run each of these commands and verify the expected outcome:

```bash
# Validate the compose file
docker compose config

# Start all services
docker compose up -d

# Wait for services to be healthy
docker compose ps
```

**Expected**: All 4 services (`db`, `backend`, `worker`, `frontend`) are running. The `db` service should show as healthy. The `backend` service should show as healthy (may take up to 30s due to PaddleOCR model loading). The `frontend` may take 15-20s to start.

If any service fails to start:
1. Check logs: `docker compose logs <service>`
2. Common issues: port conflicts (5432, 8000, 3000), Docker Desktop not running, Dockerfile build errors
3. Fix the issue and restart: `docker compose up -d`

### Step 3: Database Verification

Connect to PostgreSQL and verify the schema:

```bash
# Verify PostgreSQL is reachable
docker compose exec db pg_isready -U ogdocs

# Verify PostGIS extension
docker compose exec db psql -U ogdocs -d ogdocs -c "SELECT PostGIS_Version();"
# Expected: "3.4 ..." or similar

# Verify uuid-ossp extension
docker compose exec db psql -U ogdocs -d ogdocs -c "SELECT uuid_generate_v4();"
# Expected: a UUID string

# Verify pg_trgm extension
docker compose exec db psql -U ogdocs -d ogdocs -c "SELECT similarity('test', 'tset');"
# Expected: a float value like 0.25

# Run migrations (if not auto-run)
docker compose exec backend uv run alembic upgrade head

# Verify all 8 tables exist
docker compose exec db psql -U ogdocs -d ogdocs -c "SELECT table_name FROM information_schema.tables WHERE table_schema='public' ORDER BY table_name;"
# Expected: data_corrections, documents, extracted_data, operators, review_queue, scrape_jobs, states, wells
# (plus alembic_version and spatial_ref_sys from PostGIS)

# Verify all 10 states are seeded
docker compose exec db psql -U ogdocs -d ogdocs -c "SELECT code, name, tier FROM states ORDER BY code;"
# Expected: AK, CA, CO, LA, ND, NM, OK, PA, TX, WY

# Verify enum types exist
docker compose exec db psql -U ogdocs -d ogdocs -c "SELECT typname FROM pg_type WHERE typname LIKE '%_enum';"
# Expected: doc_type_enum, document_status_enum, review_status_enum, scrape_job_status_enum, well_status_enum

# Test the auto-sync location trigger
docker compose exec db psql -U ogdocs -d ogdocs -c "
INSERT INTO wells (api_number, state_code, latitude, longitude, well_name)
VALUES ('42501201300300', 'TX', 32.0, -101.5, 'Regression Test Well');

SELECT api_number, latitude, longitude, ST_AsText(location) as location_wkt
FROM wells WHERE api_number = '42501201300300';
"
# Expected: location_wkt should be "POINT(-101.5 32)" (longitude first in WKT)

# Test the search vector trigger
docker compose exec db psql -U ogdocs -d ogdocs -c "
SELECT api_number, search_vector IS NOT NULL as has_search_vector
FROM wells WHERE api_number = '42501201300300';
"
# Expected: has_search_vector = true

# Test the generated api_10 column
docker compose exec db psql -U ogdocs -d ogdocs -c "
SELECT api_number, api_10 FROM wells WHERE api_number = '42501201300300';
"
# Expected: api_10 = '4250120130'

# Clean up test data
docker compose exec db psql -U ogdocs -d ogdocs -c "DELETE FROM wells WHERE api_number = '42501201300300';"
```

### Step 4: FastAPI Health Check

```bash
# Test health endpoint
curl -s http://localhost:8000/health | python3 -m json.tool

# Expected response:
# {
#     "status": "ok",
#     "version": "0.1.0",
#     "db": "connected",
#     "db_version": "PostgreSQL 16.x ...",
#     "postgis_version": "3.4 ..."
# }

# Test CORS preflight
curl -s -X OPTIONS http://localhost:8000/health \
  -H "Origin: http://localhost:3000" \
  -H "Access-Control-Request-Method: GET" \
  -v 2>&1 | grep -i "access-control-allow-origin"
# Expected: access-control-allow-origin: http://localhost:3000

# Test OpenAPI docs are accessible
curl -s http://localhost:8000/docs -o /dev/null -w "%{http_code}"
# Expected: 200

# Test OpenAPI JSON spec
curl -s http://localhost:8000/openapi.json | python3 -m json.tool | head -20
# Expected: Valid JSON with info.title = "Oil & Gas Document Scraper API"
```

### Step 5: Frontend Verification

```bash
# Test frontend is serving
curl -s http://localhost:3000 -o /dev/null -w "%{http_code}"
# Expected: 200

# Check frontend logs for errors
docker compose logs frontend | tail -20
# Expected: No errors, Next.js ready message
```

### Step 6: Run All Python Tests

```bash
# Run all tests from the backend directory
cd backend && uv run pytest tests/ -v --tb=short

# Or via Docker:
docker compose exec backend uv run pytest tests/ -v --tb=short
```

**Expected test categories and results:**

1. **test_models.py** (Task 1.2):
   - All 8 tables exist after migration
   - State insert works
   - Well with location insert works
   - Enum values match DISCOVERY.md
   - Note: Integration tests require PostgreSQL (testcontainers or Docker)

2. **api/test_health.py** (Task 1.4):
   - Health returns 200
   - Response has correct shape
   - Database connection status reported

3. **api/test_cors.py** (Task 1.4):
   - Frontend origin allowed
   - Unknown origins blocked

4. **test_config.py** (Task 1.4):
   - Settings have defaults
   - Settings load from env
   - OCR threshold configurable

5. **scrapers/test_base_spider.py** (Task 1.3):
   - Abstract class enforcement
   - Required attribute validation
   - API number normalization (multiple formats)
   - File hash computation
   - DocumentItem building

6. **scrapers/test_state_registry.py** (Task 1.3):
   - 10 states in registry
   - All state codes present
   - Config retrieval works
   - Tier filtering works

7. **scrapers/test_pipelines.py** (Task 1.3):
   - Validation passes/drops correctly
   - Deduplication detects duplicates
   - Storage creates correct directory structure

8. **utils/test_api_number.py** (Task 1.3):
   - Normalization, formatting, validation, state extraction

If any test fails:
1. Read the error traceback carefully
2. Identify whether the issue is in the test or the implementation
3. Fix the code
4. Re-run the specific test: `uv run pytest tests/<path>::<test_name> -v`
5. Then re-run the full suite to verify no regressions

### Step 7: Lint Check

```bash
cd backend && uv run ruff check src/ tests/
cd backend && uv run ruff format --check src/ tests/
```

Fix any lint errors found. Common issues:
- Unused imports
- Missing blank lines
- Import ordering

### Step 8: Verify Contracts

Manually verify that all contracts from Tasks 1.1-1.4 are satisfied:

**Task 1.1 Contracts:**
- [ ] Docker Compose service names: `db`, `backend`, `worker`, `frontend`
- [ ] Ports: db=5432, backend=8000, frontend=3000
- [ ] DATABASE_URL format correct
- [ ] SYNC_DATABASE_URL format correct
- [ ] DATA_DIR = `/app/data` in container

**Task 1.2 Contracts:**
- [ ] Table names: states, operators, wells, documents, extracted_data, review_queue, scrape_jobs, data_corrections
- [ ] UUID primary keys on all tables (except states)
- [ ] wells.api_number is VARCHAR(14)
- [ ] wells.api_10 is generated column
- [ ] wells.location is GEOMETRY(Point, 4326)
- [ ] Confidence columns are NUMERIC(5,4)
- [ ] All 5 enum types exist
- [ ] JSONB columns have server_default
- [ ] States table seeded with 10 rows

**Task 1.3 Contracts:**
- [ ] BaseOGSpider is abstract with state_code, start_requests()
- [ ] DocumentItem has: state_code, source_url, doc_type, api_number, file_hash, file_path
- [ ] Storage path format: `data/documents/{state}/{operator}/{doc_type}/{hash}.{ext}`
- [ ] State registry has 10 entries with correct config
- [ ] API number normalization handles 10/12/14-digit inputs

**Task 1.4 Contracts:**
- [ ] GET /health returns JSON with status, version, db fields
- [ ] create_app() returns a FastAPI app
- [ ] get_db() yields AsyncSession
- [ ] get_huey() returns SqliteHuey
- [ ] CORS allows http://localhost:3000
- [ ] OpenAPI docs at /docs

### Step 9: Docker Full Restart Test

Test a clean restart to verify persistence and startup ordering:

```bash
# Stop all services
docker compose down

# Start fresh (volumes persist)
docker compose up -d

# Wait for health
sleep 15

# Verify health
curl -s http://localhost:8000/health | python3 -m json.tool

# Verify states still present (volume persisted)
docker compose exec db psql -U ogdocs -d ogdocs -c "SELECT count(*) FROM states;"
# Expected: 10
```

### Step 10: Clean Database Test

Verify migrations work on a completely fresh database:

```bash
# Stop and destroy all volumes
docker compose down -v

# Start fresh
docker compose up -d

# Wait for services
sleep 20

# Verify migrations ran on fresh DB
docker compose exec db psql -U ogdocs -d ogdocs -c "SELECT count(*) FROM states;"
# Expected: 10 (seeded by migration)

# Verify health
curl -s http://localhost:8000/health | python3 -m json.tool
# Expected: "db": "connected"
```

## Files to Create

- None (regression testing only)

## Files to Modify

- Any files that have bugs discovered during regression testing

## Contracts

### Provides (for downstream tasks)

- **Verified foundation**: All Phase 1 components working together
- **Clean test suite**: All tests passing
- **Running services**: Docker Compose starts reliably

### Consumes (from upstream tasks)

- Everything from Tasks 1.1, 1.2, 1.3, and 1.4

## Acceptance Criteria

- [ ] `docker compose up -d` starts all 4 services (db, backend, worker, frontend)
- [ ] `docker compose ps` shows all services as healthy (or running for worker which has no health check)
- [ ] `alembic upgrade head` succeeds on a fresh database
- [ ] `GET http://localhost:8000/health` returns 200 with `"db": "connected"`
- [ ] All 8 tables exist with correct columns in PostgreSQL
- [ ] PostGIS extension is active: `SELECT PostGIS_Version();` returns a version
- [ ] 10 states are seeded in the `states` table
- [ ] Well location auto-sync trigger works: insert lat/long, geometry column is populated
- [ ] Well search vector trigger works: insert well_name, search_vector is populated
- [ ] Generated api_10 column works: insert api_number, api_10 is first 10 digits
- [ ] `uv run pytest backend/tests/ -v` -- ALL tests pass
- [ ] `uv run ruff check backend/src/ backend/tests/` -- no lint errors
- [ ] CORS allows frontend origin
- [ ] OpenAPI docs accessible at /docs
- [ ] Frontend serves at http://localhost:3000
- [ ] Clean restart (docker compose down && docker compose up -d) works
- [ ] Fresh database (docker compose down -v && docker compose up -d) works with auto-migration

## Testing Protocol

This entire task IS the testing protocol. Follow Steps 1-10 sequentially. Each step has explicit commands and expected outputs. If any step fails, fix the issue before proceeding.

### Summary of All Test Commands

```bash
# Step 2: Docker services
docker compose config
docker compose up -d
docker compose ps

# Step 3: Database
docker compose exec db pg_isready -U ogdocs
docker compose exec db psql -U ogdocs -d ogdocs -c "SELECT PostGIS_Version();"
docker compose exec db psql -U ogdocs -d ogdocs -c "SELECT count(*) FROM states;"
docker compose exec db psql -U ogdocs -d ogdocs -c "SELECT table_name FROM information_schema.tables WHERE table_schema='public' ORDER BY table_name;"

# Step 4: API
curl -s http://localhost:8000/health | python3 -m json.tool

# Step 5: Frontend
curl -s http://localhost:3000 -o /dev/null -w "%{http_code}"

# Step 6: All tests
cd backend && uv run pytest tests/ -v --tb=short

# Step 7: Lint
cd backend && uv run ruff check src/ tests/

# Step 9: Restart test
docker compose down && docker compose up -d && sleep 15 && curl -s http://localhost:8000/health

# Step 10: Clean database test
docker compose down -v && docker compose up -d && sleep 20 && docker compose exec db psql -U ogdocs -d ogdocs -c "SELECT count(*) FROM states;"
```

## Skills to Read

- `og-scraper-architecture` - Verify the overall structure matches
- `docker-local-deployment` - Verify Docker Compose configuration

## Research Files to Read

- None (regression testing only)

## Git

- Branch: `task/1.R-phase1-regression`
- Commit message prefix: `Task 1.R:`
