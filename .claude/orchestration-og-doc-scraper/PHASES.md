# Oil & Gas Document Scraper - Implementation Phases

**Target**: Full product, quality over speed
**Execution**: Sequential phases, autonomous subagent execution
**Authority**: DISCOVERY.md overrides everything

> **Synergy Note**: Where PHASES.md endpoint paths differ from task files, **task files are authoritative**. All API endpoints use the `/api/v1/` prefix (e.g., `GET /api/v1/wells`). The review endpoint is `PATCH /api/v1/review/{id}` with action in body (not separate POST endpoints). SSE endpoint is `GET /api/v1/scrape/jobs/{id}/events`. Scrape trigger body uses `state_code` (not `state`). Pagination uses `page_size` / `total_pages` field names. See `reports/synergy-review.md` for full details.

---

## Scope Constraints (from DISCOVERY.md D26)

These are OUT of scope. Do NOT implement:
- No user authentication or multi-tenancy
- No scheduled/automated scraping (on-demand only via dashboard)
- No paid OCR or LLM API services (PaddleOCR only)
- No cloud deployment (local Docker only)
- No mobile app
- No integration with existing ETL or commercial data vendors
- No real-time data streaming
- No data correction/amendment tracking across time (just current state)

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python 3.12, FastAPI, Uvicorn |
| Scraping | Scrapy + scrapy-playwright (Playwright for JS-heavy sites) |
| OCR | PaddleOCR v3 (free, local, ~90% accuracy) |
| PDF Text | PyMuPDF4LLM |
| Task Queue | Huey with SQLite backend (no Redis) |
| Database | PostgreSQL 16 + PostGIS 3.4 |
| ORM | SQLAlchemy 2.0 async + asyncpg |
| Migrations | Alembic |
| Frontend | Next.js, React, TypeScript, Tailwind CSS |
| UI Components | shadcn/ui |
| Map | Leaflet + react-leaflet + OpenStreetMap tiles |
| Map Clustering | Supercluster via use-supercluster |
| PDF Viewer | react-pdf |
| Real-time | SSE via sse-starlette |
| Package Mgmt | UV (Python), npm (Node) |
| Task Runner | just |
| Linting | ruff (Python), ESLint (JS/TS) |
| Logging | structlog (JSON) |
| Containers | Docker Compose |
| Testing | pytest, VCR.py, testcontainers, Playwright |

---

## Skills Reference

All skills at `.claude/skills/`. Agents MUST read relevant skills before starting a task.

| Skill | Use When |
|-------|----------|
| `og-scraper-architecture` | Understanding project structure, folder layout, how services connect |
| `scrapy-playwright-scraping` | Implementing or modifying scrapers, adding states, rate limiting |
| `document-processing-pipeline` | Working with OCR, PDF extraction, classification, confidence scoring |
| `fastapi-backend` | Implementing API endpoints, database models, task queue, SSE |
| `postgresql-postgis-schema` | Database schema, queries, migrations, spatial data |
| `nextjs-dashboard` | Frontend pages, map features, UI components, SSE integration |
| `state-regulatory-sites` | State-specific scraper implementation, site URLs, quirks |
| `confidence-scoring` | Data quality validation, thresholds, review queue logic |
| `og-testing-strategies` | Writing tests, VCR cassettes, testcontainers, E2E |
| `docker-local-deployment` | Docker Compose config, environment variables, container debugging |

---

## Tools Reference

| Server/Tool | Use For | Key Operations |
|-------------|---------|----------------|
| **Playwright MCP** | Browser E2E testing on localhost | navigate, click, fill, screenshot, evaluate |
| **Docker** | Running PostgreSQL+PostGIS, full dev stack | docker compose up/down/logs |
| **just** | Task runner for dev commands | just test, just dev, just migrate |
| **ruff** | Python linting/formatting | ruff check, ruff format |
| **psql** | Direct database access for debugging | queries, schema inspection |

---

## Testing Methods

| Method | Tool | Description |
|--------|------|-------------|
| Unit tests | pytest | Service logic, utilities, regex patterns, classification rules |
| Integration tests | pytest + testcontainers | Database operations, full pipeline stages |
| API tests | pytest + httpx.AsyncClient | All 17 REST endpoints |
| Scraper tests | pytest + VCR.py | Recorded HTTP replay per state |
| OCR tests | pytest | PaddleOCR against sample documents |
| Component tests | React Testing Library | Frontend component behavior |
| E2E browser tests | Playwright MCP | Full user flows on localhost |
| Docker smoke test | docker compose | All services start and connect |

---

## Phase Overview

| Phase | Goal | Tasks |
|-------|------|-------|
| 1: Foundation | Project scaffolding, Docker, database, base frameworks | 5 |
| 2: Document Pipeline | OCR, PDF extraction, classification, confidence scoring | 5 |
| 3: Backend API | REST endpoints, task queue, SSE, search, export | 5 |
| 4: First Scrapers | PA + CO + OK scrapers — prove full pipeline end-to-end | 4 |
| 5: Frontend Dashboard | Search, map, scrape trigger, review queue, document viewer | 6 |
| 6: Remaining Scrapers | TX, NM, ND, WY, CA, AK, LA (7 states) | 4 |
| 7: E2E Testing | Comprehensive multi-angle testing on full system | 4 |
| **Total** | | **33** |

---

## Phase 1: Foundation

**Goal**: Project scaffolding, Docker Compose dev stack, PostgreSQL+PostGIS schema, base scraper framework, and FastAPI skeleton — everything needed before building features.

### Task 1.1: Project Scaffolding
- **Objective**: Create the monorepo structure with UV Python workspace, Next.js frontend, Docker Compose, and dev tooling
- **Dependencies**: None
- **Blocked by**: None
- **Files**:
  - `pyproject.toml` (UV workspace root)
  - `backend/pyproject.toml` (FastAPI + all Python deps)
  - `frontend/package.json` (Next.js + all Node deps)
  - `docker-compose.yml` (4 services: db, backend, worker, frontend)
  - `backend/Dockerfile`, `frontend/Dockerfile`
  - `justfile` (dev commands)
  - `.env.example`
  - `ruff.toml`
  - `.gitignore`
  - `backend/src/og_scraper/__init__.py` (package init)
- **Contracts**:
  - Docker Compose service names: `db`, `backend`, `worker`, `frontend`
  - Backend port: 8000, Frontend port: 3000, DB port: 5432
  - DATABASE_URL format: `postgresql+asyncpg://postgres:postgres@db:5432/ogdocs`
  - SYNC_DATABASE_URL: `postgresql://postgres:postgres@db:5432/ogdocs`
  - DATA_DIR: `/app/data` (in container), `./data` (host mount)
- **Acceptance Criteria**:
  - [ ] `uv sync` installs all Python dependencies
  - [ ] `cd frontend && npm install` installs all Node dependencies
  - [ ] `docker compose up db` starts PostgreSQL+PostGIS and is reachable via psql
  - [ ] `just --list` shows available dev commands
  - [ ] Project directory structure matches architecture skill layout
- **Testing**:
  - [ ] Docker: `docker compose up db` → psql can connect
  - [ ] Python: `uv run python -c "import fastapi; print(fastapi.__version__)"` succeeds
  - [ ] Node: `cd frontend && npx next --version` succeeds
- **Skills**: `og-scraper-architecture`, `docker-local-deployment`

### Task 1.2: Database Schema & Migrations
- **Objective**: Create all 8 database tables with Alembic migrations, PostGIS extension, full-text search indexes, and auto-sync triggers
- **Dependencies**: Task 1.1 (project structure exists)
- **Blocked by**: 1.1
- **Files**:
  - `backend/src/og_scraper/models/` (SQLAlchemy 2.0 async models for all 8 tables)
  - `backend/src/og_scraper/models/base.py` (Base, engine, session factory)
  - `backend/src/og_scraper/models/state.py`
  - `backend/src/og_scraper/models/operator.py`
  - `backend/src/og_scraper/models/well.py`
  - `backend/src/og_scraper/models/document.py`
  - `backend/src/og_scraper/models/extracted_data.py`
  - `backend/src/og_scraper/models/review_queue.py`
  - `backend/src/og_scraper/models/scrape_job.py`
  - `backend/src/og_scraper/models/data_correction.py`
  - `backend/alembic.ini`, `backend/alembic/env.py`
  - `backend/alembic/versions/001_initial_schema.py`
- **Contracts**:
  - Table names: `states`, `operators`, `wells`, `documents`, `extracted_data`, `review_queue`, `scrape_jobs`, `data_corrections`
  - Primary keys: UUID for all tables
  - API number: `VARCHAR(14)` with generated `api_10` column
  - Well location: `latitude DECIMAL(10,7)`, `longitude DECIMAL(10,7)`, `location GEOMETRY(Point, 4326)` with auto-sync trigger
  - Confidence: `DECIMAL(4,3)` (0.000 to 1.000)
  - Enum types: `DocumentType`, `DocumentStatus`, `ScrapeJobStatus`, `ReviewAction`, `DataSource`
  - JSONB: `extracted_data.data` column for flexible field storage
  - Full-text: `search_vector tsvector` on wells and documents with GIN index
- **Acceptance Criteria**:
  - [ ] `alembic upgrade head` creates all 8 tables in PostgreSQL
  - [ ] PostGIS extension is enabled
  - [ ] Auto-sync trigger updates PostGIS geometry when lat/long change
  - [ ] Full-text search trigger updates tsvector on insert/update
  - [ ] All enum types are created
  - [ ] GIN indexes exist on JSONB and tsvector columns
- **Testing**:
  - [ ] Integration: testcontainers spins up PostGIS DB, runs migrations, verifies all tables exist
  - [ ] Unit: Insert a well with lat/long, verify PostGIS geometry column is populated
  - [ ] Unit: Insert a well, verify search_vector is populated
  - [ ] Unit: Verify all enum values match DISCOVERY.md document types
- **Skills**: `postgresql-postgis-schema`, `fastapi-backend`

### Task 1.3: Base Scraper Framework
- **Objective**: Create the BaseOGSpider adapter class, Scrapy settings, download pipeline, and per-state configuration registry
- **Dependencies**: Task 1.1 (project structure)
- **Blocked by**: 1.1
- **Files**:
  - `backend/src/og_scraper/scrapers/base.py` (BaseOGSpider class)
  - `backend/src/og_scraper/scrapers/settings.py` (Scrapy settings: AutoThrottle, concurrency, retry)
  - `backend/src/og_scraper/scrapers/pipelines.py` (download pipeline: save to data/{state}/{operator}/{doc_type}/)
  - `backend/src/og_scraper/scrapers/middlewares.py` (rate limiting, user-agent rotation)
  - `backend/src/og_scraper/scrapers/state_registry.py` (state config: URLs, delays, spider class mapping)
  - `backend/src/og_scraper/scrapers/__init__.py`
- **Contracts**:
  - `BaseOGSpider` abstract class with: `state_code`, `start_requests()`, `parse_document()`, `normalize_api_number()`
  - Spider yields `DocumentItem` with: state, operator, well_name, api_number, doc_type, file_path, source_url, raw_metadata
  - Download pipeline saves to: `data/{state_code}/{operator_slug}/{doc_type}/{sha256_hash}.{ext}`
  - State registry maps state_code → {spider_class, base_url, delay, concurrency, requires_playwright}
- **Acceptance Criteria**:
  - [ ] BaseOGSpider defines all abstract methods
  - [ ] DocumentItem dataclass/Pydantic model has all required fields
  - [ ] Download pipeline creates correct directory structure
  - [ ] State registry contains entries for all 10 states (spider classes are placeholders for now)
  - [ ] Scrapy settings enable AutoThrottle and respectful crawling
- **Testing**:
  - [ ] Unit: Verify BaseOGSpider enforces abstract method implementation
  - [ ] Unit: Download pipeline creates correct file paths
  - [ ] Unit: API number normalization handles various formats
  - [ ] Unit: State registry returns correct config for each state code
- **Skills**: `scrapy-playwright-scraping`, `state-regulatory-sites`

### Task 1.4: FastAPI Skeleton
- **Objective**: Create the FastAPI application with database connection, health check, CORS, and Huey task queue initialization
- **Dependencies**: Task 1.2 (database models)
- **Blocked by**: 1.2
- **Files**:
  - `backend/src/og_scraper/api/app.py` (FastAPI app factory, lifespan, CORS)
  - `backend/src/og_scraper/api/deps.py` (dependency injection: db session, Huey instance)
  - `backend/src/og_scraper/api/routes/__init__.py` (router aggregation)
  - `backend/src/og_scraper/api/routes/health.py` (health check endpoint)
  - `backend/src/og_scraper/worker.py` (Huey SqliteHuey instance)
  - `backend/src/og_scraper/config.py` (Pydantic Settings)
- **Contracts**:
  - `GET /health` → `{"status": "ok", "db": "connected", "version": "0.1.0"}`
  - `get_db()` dependency yields async SQLAlchemy session
  - `get_huey()` returns SqliteHuey instance
  - Settings via pydantic-settings from environment variables
  - CORS allows `http://localhost:3000` (frontend)
- **Acceptance Criteria**:
  - [ ] `uvicorn og_scraper.api.app:create_app --factory` starts the server
  - [ ] `GET /health` returns 200 with db connection status
  - [ ] CORS headers allow frontend origin
  - [ ] Huey instance is configured with SQLite storage
  - [ ] Database session dependency works with async context
- **Testing**:
  - [ ] API: httpx GET /health returns 200
  - [ ] Integration: Health check reports db connected when PostgreSQL is up
  - [ ] Unit: Config loads from environment variables with defaults
- **Skills**: `fastapi-backend`, `docker-local-deployment`

### Task 1.R: Phase 1 Regression
- **Objective**: Full regression test of all Phase 1 tasks — verify the foundation is solid
- **Dependencies**: All Phase 1 tasks complete (1.1, 1.2, 1.3, 1.4)
- **Testing**:
  - [ ] `docker compose up` starts all 4 services (db, backend, worker, frontend)
  - [ ] `docker compose ps` shows all services healthy
  - [ ] `alembic upgrade head` succeeds on fresh database
  - [ ] `GET http://localhost:8000/health` returns 200 with db connected
  - [ ] psql can connect and all 8 tables exist with correct columns
  - [ ] PostGIS extension is active: `SELECT PostGIS_Version();`
  - [ ] Insert a well via psql, verify auto-sync trigger populates geometry
  - [ ] `uv run pytest backend/tests/` — all unit tests pass
  - [ ] Screenshot: Docker services running, health endpoint response

---

## Phase 2: Document Pipeline

**Goal**: Complete 7-stage document processing pipeline — from raw downloaded files through classification, OCR/text extraction, data extraction, normalization, validation, confidence scoring, and storage.

### Task 2.1: PDF Text Extraction & OCR
- **Objective**: Implement text extraction from PDFs using PyMuPDF4LLM (text-based) and PaddleOCR (scanned), with automatic detection of which to use
- **Dependencies**: Task 1.1 (project structure)
- **Blocked by**: 1.1
- **Files**:
  - `backend/src/og_scraper/pipeline/text_extractor.py` (PyMuPDF4LLM + PaddleOCR hybrid)
  - `backend/src/og_scraper/pipeline/ocr.py` (PaddleOCR wrapper with confidence tracking)
  - `backend/src/og_scraper/pipeline/__init__.py`
  - `backend/tests/pipeline/test_text_extractor.py`
  - `backend/tests/fixtures/sample_text.pdf` (text-based test PDF)
  - `backend/tests/fixtures/sample_scan.pdf` (scanned test PDF)
- **Contracts**:
  - `TextExtractor.extract(file_path: Path) -> ExtractionResult`
  - `ExtractionResult`: `{text: str, pages: list[PageResult], method: "pymupdf"|"paddleocr", ocr_confidence: float}`
  - `PageResult`: `{page_num: int, text: str, confidence: float, method: str}`
  - Auto-detection: if PyMuPDF extracts <50 chars per page, fall back to PaddleOCR
- **Acceptance Criteria**:
  - [ ] Text-based PDFs extracted via PyMuPDF4LLM with high confidence
  - [ ] Scanned PDFs extracted via PaddleOCR with confidence scores
  - [ ] Auto-detection correctly routes to appropriate engine
  - [ ] OCR confidence tracked per page and rolled up to document level
  - [ ] Handles multi-page PDFs
- **Testing**:
  - [ ] Unit: Text PDF extraction returns text with confidence ~1.0
  - [ ] Unit: Scanned PDF extraction returns text with confidence 0.7-0.95
  - [ ] Unit: Auto-detection uses PyMuPDF for text PDFs, PaddleOCR for scans
  - [ ] Unit: Multi-page PDF returns per-page results
- **Skills**: `document-processing-pipeline`

### Task 2.2: Document Classification
- **Objective**: Classify documents by type using rule-based keyword matching and form number detection
- **Dependencies**: Task 2.1 (text extraction)
- **Blocked by**: 2.1
- **Files**:
  - `backend/src/og_scraper/pipeline/classifier.py` (rule-based classifier)
  - `backend/src/og_scraper/pipeline/classification_rules.py` (keyword dictionaries per doc type)
  - `backend/tests/pipeline/test_classifier.py`
- **Contracts**:
  - `DocumentClassifier.classify(text: str, metadata: dict) -> ClassificationResult`
  - `ClassificationResult`: `{doc_type: DocumentType, confidence: float, matched_keywords: list[str], form_number: str|None}`
  - `DocumentType` enum: `PRODUCTION_REPORT`, `WELL_PERMIT`, `COMPLETION_REPORT`, `INSPECTION_RECORD`, `SPACING_ORDER`, `PLUGGING_REPORT`, `INCIDENT_REPORT`, `UNKNOWN`
  - Classification confidence: keyword match count / total possible × weight factor
- **Acceptance Criteria**:
  - [ ] Correctly classifies all 7 document types with >80% accuracy on test samples
  - [ ] Form number detection extracts state-specific form identifiers
  - [ ] Returns confidence score for classification
  - [ ] Falls back to UNKNOWN with low confidence if no clear match
  - [ ] Keyword dictionaries cover all 10 states' document formats
- **Testing**:
  - [ ] Unit: Each document type classified correctly from sample text
  - [ ] Unit: Form number extraction works for TX, NM, OK form numbers
  - [ ] Unit: Ambiguous text returns UNKNOWN with low confidence
  - [ ] Unit: Classification confidence scales with keyword match strength
- **Skills**: `document-processing-pipeline`, `state-regulatory-sites`

### Task 2.3: Data Extraction & Normalization
- **Objective**: Extract structured data fields from document text using regex patterns, then normalize across states into a consistent schema
- **Dependencies**: Task 2.1 (text extraction), Task 1.2 (database schema defines target fields)
- **Blocked by**: 2.1, 1.2
- **Files**:
  - `backend/src/og_scraper/pipeline/extractor.py` (field extraction via regex)
  - `backend/src/og_scraper/pipeline/patterns.py` (regex patterns for all field types)
  - `backend/src/og_scraper/pipeline/normalizer.py` (cross-state normalization)
  - `backend/tests/pipeline/test_extractor.py`
  - `backend/tests/pipeline/test_normalizer.py`
- **Contracts**:
  - `DataExtractor.extract(text: str, doc_type: DocumentType, state: str) -> ExtractionResult`
  - `ExtractionResult`: `{fields: dict[str, FieldValue], raw_text: str}`
  - `FieldValue`: `{value: Any, confidence: float, source_text: str, pattern_used: str}`
  - Standard fields: `api_number`, `operator_name`, `well_name`, `county`, `latitude`, `longitude`, `production_oil_bbl`, `production_gas_mcf`, `production_water_bbl`, `well_depth_ft`, `permit_number`, `permit_date`, `completion_date`, `spud_date`
  - Normalizer converts state-specific formats to standard: dates → ISO 8601, volumes → standard units (BBL, MCF), depths → feet, API numbers → 14-digit padded
- **Acceptance Criteria**:
  - [ ] Extracts API numbers in various formats (with/without dashes)
  - [ ] Extracts production volumes with unit detection
  - [ ] Extracts dates in multiple formats, normalizes to ISO 8601
  - [ ] Extracts well coordinates (DMS, decimal degrees, various formats)
  - [ ] Per-field confidence scores based on regex match strength
  - [ ] Normalizer produces consistent output regardless of source state
- **Testing**:
  - [ ] Unit: API number extraction from 10+ format variations
  - [ ] Unit: Production volume extraction with unit conversion
  - [ ] Unit: Date parsing from 5+ format variations
  - [ ] Unit: Coordinate extraction and normalization
  - [ ] Unit: Cross-state normalization produces identical output format
- **Skills**: `document-processing-pipeline`, `confidence-scoring`

### Task 2.4: Validation & Confidence Scoring
- **Objective**: Implement three-tier confidence scoring (OCR → field → document) and validation pipeline that routes documents to auto-accept, review queue, or reject
- **Dependencies**: Task 2.3 (extraction provides field-level data), Task 1.2 (review_queue table)
- **Blocked by**: 2.3, 1.2
- **Files**:
  - `backend/src/og_scraper/pipeline/validator.py` (field validation rules)
  - `backend/src/og_scraper/pipeline/confidence.py` (three-tier scoring system)
  - `backend/src/og_scraper/pipeline/pipeline.py` (orchestrates all stages: extract → classify → extract → normalize → validate → score → route)
  - `backend/tests/pipeline/test_validator.py`
  - `backend/tests/pipeline/test_confidence.py`
  - `backend/tests/pipeline/test_pipeline.py`
- **Contracts**:
  - `ConfidenceScorer.score(ocr_result: ExtractionResult, fields: dict[str, FieldValue], classification: ClassificationResult) -> DocumentScore`
  - `DocumentScore`: `{ocr_confidence: float, field_confidences: dict[str, float], document_confidence: float, disposition: "accept"|"review"|"reject"}`
  - Thresholds per DISCOVERY D10/D23: accept >= 0.85, review 0.50-0.84, reject < 0.50
  - Document confidence formula: `0.3 * classification_conf + 0.5 * weighted_field_avg + 0.2 * ocr_conf`
  - Field weights: api_number=3.0, production_volumes=2.0, dates=1.5, coordinates=2.0, names=1.0
  - `DocumentPipeline.process(file_path: Path, state: str) -> ProcessingResult`
  - `ProcessingResult`: full result including all extraction data, scores, and disposition
- **Acceptance Criteria**:
  - [ ] Three-tier scoring produces correct confidence at each level
  - [ ] High-quality text PDF scores >= 0.85 (auto-accept)
  - [ ] Medium-quality scan scores 0.50-0.84 (review queue)
  - [ ] Garbage/unreadable document scores < 0.50 (reject)
  - [ ] Field validation catches invalid API numbers, impossible dates, out-of-range coordinates
  - [ ] Full pipeline processes a document through all 7 stages
- **Testing**:
  - [ ] Unit: Confidence scoring math with known inputs
  - [ ] Unit: High-confidence document routes to accept
  - [ ] Unit: Medium-confidence document routes to review
  - [ ] Unit: Low-confidence document routes to reject
  - [ ] Unit: Field validation catches 5+ invalid field types
  - [ ] Integration: Full pipeline from file → ProcessingResult
- **Skills**: `confidence-scoring`, `document-processing-pipeline`

### Task 2.R: Phase 2 Regression
- **Objective**: Full regression test of the entire document pipeline
- **Dependencies**: All Phase 2 tasks complete (2.1-2.4)
- **Testing**:
  - [ ] End-to-end: Text PDF → full pipeline → auto-accepted result with all fields
  - [ ] End-to-end: Scanned PDF → full pipeline → review-queue result with OCR text
  - [ ] End-to-end: Corrupt/unreadable file → pipeline → rejected result
  - [ ] All unit tests pass: `uv run pytest backend/tests/pipeline/`
  - [ ] Confidence scores are mathematically correct across 10+ test documents
  - [ ] Classification accuracy >80% across test document set
  - [ ] Performance: Single document processes in <30 seconds (including OCR)

---

## Phase 3: Backend API

**Goal**: Complete REST API with all 17 endpoints, Huey task queue for async scraping, SSE for real-time progress, full-text search, and data export.

### Task 3.1: Core CRUD Endpoints
- **Objective**: Implement CRUD endpoints for wells, documents, operators, and states
- **Dependencies**: Task 1.4 (FastAPI skeleton), Task 1.2 (database models)
- **Blocked by**: 1.4, 1.2
- **Files**:
  - `backend/src/og_scraper/api/routes/wells.py` (GET /wells, GET /wells/{id}, GET /wells/search)
  - `backend/src/og_scraper/api/routes/documents.py` (GET /documents, GET /documents/{id}, GET /wells/{id}/documents)
  - `backend/src/og_scraper/api/routes/operators.py` (GET /operators)
  - `backend/src/og_scraper/api/routes/states.py` (GET /states)
  - `backend/src/og_scraper/api/schemas/` (Pydantic request/response models)
  - `backend/tests/api/test_wells.py`
  - `backend/tests/api/test_documents.py`
- **Contracts**:
  - `GET /api/wells?state=TX&operator=&county=&page=1&per_page=50` → paginated well list
  - `GET /api/wells/{id}` → well detail with related documents
  - `GET /api/wells/search?q=<query>` → full-text search results
  - `GET /api/documents?state=&type=&status=&page=1&per_page=50` → paginated document list
  - `GET /api/documents/{id}` → document detail with extracted data
  - `GET /api/wells/{id}/documents` → documents for a specific well
  - `GET /api/operators?state=` → operator list with optional state filter
  - `GET /api/states` → all states with scrape status summary
  - All paginated responses: `{items: [], total: int, page: int, per_page: int, pages: int}`
- **Acceptance Criteria**:
  - [ ] All 8 endpoints return correct data with pagination
  - [ ] Full-text search works via PostgreSQL tsvector
  - [ ] Filtering by state, operator, type, date range works
  - [ ] Responses use Pydantic models with proper serialization
  - [ ] 404 returned for non-existent resources
- **Testing**:
  - [ ] API: Each endpoint tested with httpx (happy path + edge cases)
  - [ ] Integration: Search returns results matching query
  - [ ] Integration: Filters correctly narrow results
  - [ ] Unit: Pydantic schemas validate correctly
- **Skills**: `fastapi-backend`, `postgresql-postgis-schema`

### Task 3.2: Scrape Job Endpoints & Huey Integration
- **Objective**: Implement scrape trigger endpoints with Huey async task execution, job status tracking, and SSE for real-time progress
- **Dependencies**: Task 3.1 (base API structure), Task 1.3 (scraper framework)
- **Blocked by**: 3.1, 1.3
- **Files**:
  - `backend/src/og_scraper/api/routes/scrape.py` (POST /scrape, GET /scrape/{id}, GET /scrape/{id}/progress)
  - `backend/src/og_scraper/tasks/scrape_task.py` (Huey task that runs scrapers)
  - `backend/src/og_scraper/tasks/__init__.py`
  - `backend/tests/api/test_scrape.py`
- **Contracts**:
  - `POST /api/scrape` body: `{state: str|"all", search_params?: {operator?, api_number?, county?}}` → `{job_id: uuid, status: "pending"}`
  - `GET /api/scrape/{job_id}` → `{id, state, status, progress_pct, documents_found, documents_processed, started_at, completed_at, errors}`
  - `GET /api/scrape/{job_id}/progress` → SSE stream: `data: {progress_pct, current_stage, documents_processed, message}`
  - Huey task: receives job_id, runs spider, updates scrape_job row in DB, processes documents through pipeline
  - Job statuses: `pending` → `running` → `completed`|`failed`
- **Acceptance Criteria**:
  - [ ] POST /scrape creates a scrape job and returns job_id
  - [ ] Huey worker picks up and executes the scrape task
  - [ ] Job status updates in database as scrape progresses
  - [ ] SSE endpoint streams real-time progress
  - [ ] Job completion records summary stats
  - [ ] Failed jobs record error details
- **Testing**:
  - [ ] API: POST /scrape returns 202 with job_id
  - [ ] API: GET /scrape/{id} returns job status
  - [ ] Integration: Huey task executes with `immediate=True` in tests
  - [ ] Unit: SSE endpoint streams events
- **Skills**: `fastapi-backend`, `scrapy-playwright-scraping`

### Task 3.3: Review Queue & Data Correction Endpoints
- **Objective**: Implement review queue endpoints for listing, approving, correcting, and rejecting low-confidence documents
- **Dependencies**: Task 3.1 (base API structure), Task 2.4 (pipeline routes to review queue)
- **Blocked by**: 3.1, 2.4
- **Files**:
  - `backend/src/og_scraper/api/routes/review.py` (GET /review, POST /review/{id}/approve, POST /review/{id}/correct, POST /review/{id}/reject)
  - `backend/tests/api/test_review.py`
- **Contracts**:
  - `GET /api/review?state=&type=&page=1&per_page=50` → paginated review queue items with document + extracted data
  - `POST /api/review/{id}/approve` → moves to accepted, removes from queue
  - `POST /api/review/{id}/correct` body: `{corrections: {field: value}}` → updates extracted_data, logs correction, removes from queue
  - `POST /api/review/{id}/reject` → marks as rejected, removes from queue
  - Each action creates a `data_corrections` record for audit trail
- **Acceptance Criteria**:
  - [ ] Review queue lists documents needing review with extracted data
  - [ ] Approve moves document to accepted status
  - [ ] Correct updates specific fields and logs the correction
  - [ ] Reject marks document and removes from queue
  - [ ] All actions create audit trail in data_corrections table
- **Testing**:
  - [ ] API: GET /review returns paginated review items
  - [ ] API: Approve/correct/reject update document status correctly
  - [ ] Integration: Correction updates extracted_data fields
  - [ ] Integration: Audit trail created for each action
- **Skills**: `fastapi-backend`, `confidence-scoring`

### Task 3.4: Map & Export Endpoints
- **Objective**: Implement map data endpoint (wells within viewport) and data export (CSV, JSON)
- **Dependencies**: Task 3.1 (base API structure)
- **Blocked by**: 3.1
- **Files**:
  - `backend/src/og_scraper/api/routes/map.py` (GET /map/wells)
  - `backend/src/og_scraper/api/routes/export.py` (GET /export/wells, GET /export/documents)
  - `backend/tests/api/test_map.py`
  - `backend/tests/api/test_export.py`
- **Contracts**:
  - `GET /api/map/wells?bbox=<west,south,east,north>&zoom=<level>` → GeoJSON FeatureCollection of wells within bounding box
  - At low zoom: return cluster summaries (count, center point)
  - At high zoom: return individual well pins
  - `GET /api/export/wells?state=&format=csv|json` → streaming file download
  - `GET /api/export/documents?state=&type=&format=csv|json` → streaming file download
- **Acceptance Criteria**:
  - [ ] Map endpoint returns wells within bounding box using PostGIS spatial query
  - [ ] Zoom-dependent response: clusters at low zoom, pins at high zoom
  - [ ] CSV export streams correctly formatted data
  - [ ] JSON export streams correctly formatted data
  - [ ] Exports respect filters (state, type, date range)
- **Testing**:
  - [ ] API: Map returns wells within test bounding box
  - [ ] API: Map returns clusters at low zoom level
  - [ ] API: CSV export downloads valid CSV
  - [ ] API: JSON export downloads valid JSON
  - [ ] Integration: PostGIS spatial query works with test well data
- **Skills**: `fastapi-backend`, `postgresql-postgis-schema`

### Task 3.R: Phase 3 Regression
- **Objective**: Full regression test of all API endpoints
- **Dependencies**: All Phase 3 tasks complete (3.1-3.4)
- **Testing**:
  - [ ] All 17 endpoints tested via httpx
  - [ ] Full workflow: create scrape job → check status → review queue → approve
  - [ ] Search returns relevant results
  - [ ] Map viewport query returns correct wells
  - [ ] Export produces valid CSV and JSON
  - [ ] All tests pass: `uv run pytest backend/tests/api/`
  - [ ] Docker: backend + worker + db all running and communicating

---

## Phase 4: First Scrapers

**Goal**: Implement 3 state scrapers (PA, CO, OK) to prove the full end-to-end pipeline works: scrape → download → pipeline → database → API.

### Task 4.1: Pennsylvania Scraper (GreenPort CSV)
- **Objective**: Implement the PA scraper targeting DEP GreenPort — the easiest state (CSV exports)
- **Dependencies**: Task 1.3 (base scraper framework), Task 2.4 (document pipeline)
- **Blocked by**: 1.3, 2.4
- **Files**:
  - `backend/src/og_scraper/scrapers/spiders/pa_spider.py`
  - `backend/tests/scrapers/test_pa_spider.py`
  - `backend/tests/scrapers/cassettes/pa/` (VCR.py cassettes)
- **Contracts**:
  - Inherits from BaseOGSpider
  - Scrapes PA DEP GreenPort CSV exports (production, permits, well data)
  - Downloads CSV files, processes through pipeline
  - Yields DocumentItem for each document found
- **Acceptance Criteria**:
  - [ ] Spider navigates PA GreenPort and downloads CSV data
  - [ ] CSV parsing extracts well data, production, permits
  - [ ] Data flows through full pipeline and is stored in database
  - [ ] API number normalization for PA format
  - [ ] Rate limiting respects PA site
- **Testing**:
  - [ ] VCR.py: Recorded cassette replays PA GreenPort responses
  - [ ] Integration: Spider → pipeline → database stores correct data
  - [ ] Unit: PA-specific parsing handles CSV format
- **Skills**: `scrapy-playwright-scraping`, `state-regulatory-sites`, `document-processing-pipeline`

### Task 4.2: Colorado Scraper (COGCC API)
- **Objective**: Implement the CO scraper targeting COGCC — modernized site with API endpoints
- **Dependencies**: Task 1.3 (base scraper framework), Task 2.4 (document pipeline)
- **Blocked by**: 1.3, 2.4
- **Files**:
  - `backend/src/og_scraper/scrapers/spiders/co_spider.py`
  - `backend/tests/scrapers/test_co_spider.py`
  - `backend/tests/scrapers/cassettes/co/`
- **Contracts**:
  - Inherits from BaseOGSpider
  - Uses COGCC API endpoints for well data, production, documents
  - Handles API pagination
- **Acceptance Criteria**:
  - [ ] Spider queries COGCC API and retrieves well/document data
  - [ ] Handles API pagination correctly
  - [ ] Documents downloaded and processed through pipeline
  - [ ] CO-specific data formats normalized correctly
- **Testing**:
  - [ ] VCR.py: Recorded cassette replays COGCC API responses
  - [ ] Integration: Spider → pipeline → database stores correct data
  - [ ] Unit: CO API response parsing
- **Skills**: `scrapy-playwright-scraping`, `state-regulatory-sites`, `document-processing-pipeline`

### Task 4.3: Oklahoma Scraper (OCC)
- **Objective**: Implement the OK scraper targeting OCC well data system
- **Dependencies**: Task 1.3 (base scraper framework), Task 2.4 (document pipeline)
- **Blocked by**: 1.3, 2.4
- **Files**:
  - `backend/src/og_scraper/scrapers/spiders/ok_spider.py`
  - `backend/tests/scrapers/test_ok_spider.py`
  - `backend/tests/scrapers/cassettes/ok/`
- **Contracts**:
  - Inherits from BaseOGSpider
  - Scrapes OCC well data pages
  - Handles OK-specific document formats
- **Acceptance Criteria**:
  - [ ] Spider navigates OCC and retrieves well/document data
  - [ ] OK-specific formats parsed correctly
  - [ ] Full pipeline integration works
- **Testing**:
  - [ ] VCR.py: Recorded cassette replays OCC responses
  - [ ] Integration: Spider → pipeline → database
  - [ ] Unit: OK-specific parsing
- **Skills**: `scrapy-playwright-scraping`, `state-regulatory-sites`, `document-processing-pipeline`

### Task 4.R: Phase 4 Regression
- **Objective**: Full end-to-end test: scrape 3 states → pipeline → database → API query returns results
- **Dependencies**: All Phase 4 tasks + Phase 3 (API endpoints)
- **Testing**:
  - [ ] VCR-based: Run all 3 spiders against recorded cassettes
  - [ ] Pipeline: All downloaded documents processed correctly
  - [ ] Database: Wells, documents, extracted_data populated for PA, CO, OK
  - [ ] API: `GET /api/wells?state=PA` returns PA wells
  - [ ] API: `GET /api/documents?state=CO&type=PRODUCTION_REPORT` returns CO production reports
  - [ ] API: `GET /api/wells/search?q=<operator>` returns matching wells
  - [ ] Review queue: Documents below threshold appear in review queue
  - [ ] `uv run pytest backend/tests/scrapers/` — all scraper tests pass

---

## Phase 5: Frontend Dashboard

**Goal**: Complete Next.js dashboard with search/browse, interactive map, scrape trigger with progress, review queue, and document viewer.

### Task 5.1: Frontend Foundation & Layout
- **Objective**: Set up Next.js with shadcn/ui, Tailwind, API proxy, and base layout (header, sidebar, main content area)
- **Dependencies**: Task 1.1 (frontend project exists)
- **Blocked by**: 1.1
- **Files**:
  - `frontend/src/app/layout.tsx` (root layout with sidebar + header)
  - `frontend/src/app/page.tsx` (dashboard home / redirect to wells)
  - `frontend/src/components/layout/sidebar.tsx`
  - `frontend/src/components/layout/header.tsx`
  - `frontend/src/lib/api.ts` (API client wrapping fetch to backend)
  - `frontend/next.config.ts` (API proxy rewrite to localhost:8000)
  - `frontend/tailwind.config.ts`
  - `frontend/src/app/globals.css`
- **Contracts**:
  - API proxy: `/api/*` → `http://localhost:8000/api/*`
  - Sidebar navigation: Dashboard, Wells, Documents, Map, Scrape, Review Queue
  - API client: typed fetch wrapper with error handling
- **Acceptance Criteria**:
  - [ ] `npm run dev` starts frontend on port 3000
  - [ ] Layout renders with sidebar navigation
  - [ ] API proxy correctly forwards to backend
  - [ ] shadcn/ui components available (Button, Card, Table, etc.)
  - [ ] Dark mode support via Tailwind
- **Testing**:
  - [ ] Browser: Navigate to localhost:3000, layout renders
  - [ ] Browser: All sidebar links navigate correctly
  - [ ] API: Proxy forwards /api/health to backend
- **Skills**: `nextjs-dashboard`

### Task 5.2: Search & Browse Interface
- **Objective**: Implement the main wells search/browse page with DataTable, filters, and well detail side panel
- **Dependencies**: Task 5.1 (frontend foundation), Task 3.1 (API endpoints exist)
- **Blocked by**: 5.1, 3.1
- **Files**:
  - `frontend/src/app/wells/page.tsx` (wells list page)
  - `frontend/src/app/wells/columns.tsx` (DataTable column definitions)
  - `frontend/src/components/wells/well-filters.tsx` (state, operator, type, date filters)
  - `frontend/src/components/wells/well-detail-panel.tsx` (side panel for well details)
  - `frontend/src/app/documents/page.tsx` (documents list page)
  - `frontend/src/components/documents/document-filters.tsx`
- **Contracts**:
  - Wells table columns: API Number, Well Name, Operator, State, County, Status, Documents Count
  - Click row → slide-out side panel with well detail + associated documents
  - Filters update URL query params and re-fetch data
  - Pagination via @tanstack/react-table
- **Acceptance Criteria**:
  - [ ] Wells table displays paginated well data
  - [ ] Search bar performs full-text search
  - [ ] Filters (state, operator, type, date) narrow results
  - [ ] Click well row opens detail side panel
  - [ ] Side panel shows well info + linked documents
  - [ ] Documents page with similar table + filters
- **Testing**:
  - [ ] Browser: Wells table loads with data (seed data or API)
  - [ ] Browser: Search returns relevant results
  - [ ] Browser: Filters update table
  - [ ] Browser: Side panel opens on row click
- **Skills**: `nextjs-dashboard`

### Task 5.3: Interactive Map
- **Objective**: Implement Leaflet map with well pins, Supercluster for clustering, and click-to-detail interaction
- **Dependencies**: Task 5.1 (frontend foundation), Task 3.4 (map endpoint)
- **Blocked by**: 5.1, 3.4
- **Files**:
  - `frontend/src/app/map/page.tsx` (map page)
  - `frontend/src/components/map/well-map.tsx` (Leaflet map with dynamic import)
  - `frontend/src/components/map/map-cluster-layer.tsx` (Supercluster integration)
  - `frontend/src/components/map/well-popup.tsx` (click popup with well summary)
  - `frontend/src/components/map/map-controls.tsx` (zoom, filters, layer toggle)
- **Contracts**:
  - Map fetches wells from `GET /api/map/wells?bbox=...&zoom=...`
  - Supercluster clusters wells at low zoom, individual pins at high zoom
  - Click pin → popup with well name, operator, API number, document count
  - Click "View Details" in popup → navigate to well detail
  - OpenStreetMap tiles (free, no API key)
- **Acceptance Criteria**:
  - [ ] Map renders with OpenStreetMap tiles
  - [ ] Well pins display on the map from API data
  - [ ] Supercluster clusters pins at low zoom
  - [ ] Individual pins visible at high zoom
  - [ ] Click pin shows popup with well info
  - [ ] Map viewport changes trigger new data fetch
  - [ ] No SSR errors (Leaflet loaded client-side only)
- **Testing**:
  - [ ] Browser: Map renders without console errors
  - [ ] Browser: Pins appear for seed data
  - [ ] Browser: Zoom in/out shows cluster/individual pins
  - [ ] Browser: Click pin shows popup
- **Skills**: `nextjs-dashboard`

### Task 5.4: Scrape Trigger & Progress
- **Objective**: Implement scrape trigger UI with state selection buttons and real-time SSE progress display
- **Dependencies**: Task 5.1 (frontend foundation), Task 3.2 (scrape endpoints + SSE)
- **Blocked by**: 5.1, 3.2
- **Files**:
  - `frontend/src/app/scrape/page.tsx` (scrape management page)
  - `frontend/src/components/scrape/state-scrape-grid.tsx` (grid of state buttons)
  - `frontend/src/components/scrape/scrape-progress.tsx` (real-time progress display)
  - `frontend/src/hooks/use-sse.ts` (EventSource hook for SSE)
  - `frontend/src/components/scrape/scrape-history.tsx` (past scrape jobs list)
- **Contracts**:
  - "Scrape [State]" button per state + "Scrape All" button
  - Click triggers `POST /api/scrape` with state parameter
  - SSE connection to `GET /api/scrape/{job_id}/progress`
  - Progress display: percentage bar, current stage, documents found/processed, elapsed time
  - Scrape history: list of past jobs with status, timestamps, document counts
- **Acceptance Criteria**:
  - [ ] State grid shows all 10 states with scrape buttons
  - [ ] Click "Scrape [State]" triggers scrape job
  - [ ] Progress bar updates in real-time via SSE
  - [ ] Current stage and document count shown during scrape
  - [ ] Completed jobs show in history list
  - [ ] "Scrape All" triggers scrapes for all states
- **Testing**:
  - [ ] Browser: State grid renders all 10 states
  - [ ] Browser: Click scrape button, progress bar appears
  - [ ] Browser: SSE updates progress in real-time
  - [ ] Browser: Completed job appears in history
- **Skills**: `nextjs-dashboard`, `fastapi-backend`

### Task 5.5: Review Queue & Document Viewer
- **Objective**: Implement the review queue page with side-by-side document viewer (PDF) and editable extracted fields, plus approve/correct/reject actions
- **Dependencies**: Task 5.1 (frontend foundation), Task 3.3 (review queue endpoints)
- **Blocked by**: 5.1, 3.3
- **Files**:
  - `frontend/src/app/review/page.tsx` (review queue page)
  - `frontend/src/components/review/review-list.tsx` (list of items needing review)
  - `frontend/src/components/review/review-detail.tsx` (side-by-side: PDF + fields)
  - `frontend/src/components/review/document-viewer.tsx` (react-pdf viewer)
  - `frontend/src/components/review/extracted-fields-form.tsx` (editable field form with confidence indicators)
  - `frontend/src/components/review/review-actions.tsx` (approve/correct/reject buttons)
- **Contracts**:
  - Review list fetches from `GET /api/review`
  - Click item → side-by-side view: PDF on left, extracted fields on right
  - Each field shows its confidence score (color-coded: green/yellow/red)
  - User can edit field values for corrections
  - Approve: `POST /api/review/{id}/approve`
  - Correct: `POST /api/review/{id}/correct` with modified field values
  - Reject: `POST /api/review/{id}/reject`
- **Acceptance Criteria**:
  - [ ] Review queue lists documents needing review with confidence scores
  - [ ] Click item shows PDF alongside extracted data
  - [ ] Confidence scores color-coded by threshold
  - [ ] Fields are editable for corrections
  - [ ] Approve/correct/reject buttons update status via API
  - [ ] After action, item removed from list and next item shown
- **Testing**:
  - [ ] Browser: Review queue lists items
  - [ ] Browser: PDF renders in viewer
  - [ ] Browser: Fields are editable
  - [ ] Browser: Approve removes item from queue
  - [ ] Browser: Correct sends updated fields
- **Skills**: `nextjs-dashboard`, `confidence-scoring`

### Task 5.R: Phase 5 Regression
- **Objective**: Full E2E test of the dashboard
- **Dependencies**: All Phase 5 tasks complete
- **Testing**:
  - [ ] Playwright: Full user flow — open dashboard → search wells → view well detail → view on map
  - [ ] Playwright: Trigger scrape → watch progress → verify new data appears
  - [ ] Playwright: Review queue → approve/correct/reject items
  - [ ] Playwright: Export data as CSV
  - [ ] Playwright: Map interaction — zoom, click pins, view popups
  - [ ] All pages render without console errors
  - [ ] API proxy works correctly for all endpoints
  - [ ] Responsive layout at different viewport sizes

---

## Phase 6: Remaining Scrapers

**Goal**: Implement the remaining 7 state scrapers (TX, NM, ND, WY, CA, AK, LA), covering all difficulty levels from bulk downloads to browser automation.

### Task 6.1: Texas & New Mexico Scrapers
- **Objective**: TX (RRC bulk downloads with EBCDIC encoding) and NM (OCD/ONGARD system)
- **Dependencies**: Task 1.3 (base scraper), Task 2.4 (pipeline)
- **Blocked by**: 1.3, 2.4
- **Files**:
  - `backend/src/og_scraper/scrapers/spiders/tx_spider.py`
  - `backend/src/og_scraper/scrapers/spiders/nm_spider.py`
  - `backend/src/og_scraper/scrapers/utils/ebcdic.py` (EBCDIC parser for TX)
  - `backend/tests/scrapers/test_tx_spider.py`
  - `backend/tests/scrapers/test_nm_spider.py`
  - `backend/tests/scrapers/cassettes/tx/`, `cassettes/nm/`
- **Acceptance Criteria**:
  - [ ] TX spider downloads bulk files and parses EBCDIC encoding
  - [ ] TX alternative: monthly CSV PDQ dump as fallback
  - [ ] NM spider navigates ONGARD system
  - [ ] Both spiders feed into full pipeline
- **Testing**:
  - [ ] VCR.py: TX bulk download cassette replay
  - [ ] Unit: EBCDIC parsing produces readable text
  - [ ] VCR.py: NM ONGARD cassette replay
  - [ ] Integration: Both states → pipeline → database
- **Skills**: `scrapy-playwright-scraping`, `state-regulatory-sites`

### Task 6.2: North Dakota, Wyoming & Alaska Scrapers
- **Objective**: ND (NDIC - note paywall), WY (WOGCC - older site), AK (AOGCC - simpler site)
- **Dependencies**: Task 1.3 (base scraper), Task 2.4 (pipeline)
- **Blocked by**: 1.3, 2.4
- **Files**:
  - `backend/src/og_scraper/scrapers/spiders/nd_spider.py`
  - `backend/src/og_scraper/scrapers/spiders/wy_spider.py`
  - `backend/src/og_scraper/scrapers/spiders/ak_spider.py`
  - `backend/tests/scrapers/` (tests + cassettes for each)
- **Acceptance Criteria**:
  - [ ] ND spider handles the paywall (graceful failure if no subscription, success if credentialed)
  - [ ] WY spider handles older site layout
  - [ ] AK spider handles simpler AOGCC site
  - [ ] All feed into pipeline correctly
- **Testing**:
  - [ ] VCR.py: Cassettes for each state
  - [ ] Integration: All 3 states → pipeline → database
- **Skills**: `scrapy-playwright-scraping`, `state-regulatory-sites`

### Task 6.3: California & Louisiana Scrapers
- **Objective**: CA (CalGEM WellSTAR) and LA (SONRIS - hardest site, Oracle backend)
- **Dependencies**: Task 1.3 (base scraper), Task 2.4 (pipeline)
- **Blocked by**: 1.3, 2.4
- **Files**:
  - `backend/src/og_scraper/scrapers/spiders/ca_spider.py`
  - `backend/src/og_scraper/scrapers/spiders/la_spider.py`
  - `backend/tests/scrapers/` (tests + cassettes for each)
- **Acceptance Criteria**:
  - [ ] CA spider navigates WellSTAR system
  - [ ] LA spider handles SONRIS Oracle-backed site (likely needs Playwright)
  - [ ] Both handle their state-specific document formats
  - [ ] All feed into pipeline correctly
- **Testing**:
  - [ ] VCR.py/HAR: Cassettes for each state (HAR for Playwright states)
  - [ ] Integration: Both states → pipeline → database
- **Skills**: `scrapy-playwright-scraping`, `state-regulatory-sites`

### Task 6.R: Phase 6 Regression
- **Objective**: All 10 state scrapers working end-to-end
- **Dependencies**: All Phase 6 tasks + Phase 4 scrapers
- **Testing**:
  - [ ] VCR-based: Run all 10 state spiders against cassettes
  - [ ] Database: All 10 states have wells and documents
  - [ ] API: `GET /api/states` shows all 10 states with data
  - [ ] API: `GET /api/wells?state=<each>` returns wells for each state
  - [ ] Dashboard: Map shows wells across all states
  - [ ] Dashboard: Scrape page shows all 10 state buttons
  - [ ] All scraper tests pass: `uv run pytest backend/tests/scrapers/`

---

## Phase 7: Comprehensive E2E Testing

**Goal**: Multi-angle end-to-end testing on the fully deployed local system. Every user path, every edge case, every integration verified.

### Task 7.1: Full Pipeline E2E
- **Objective**: Test the complete flow from scrape trigger through data access for every state and document type
- **Testing**:
  - [ ] Trigger scrape for each state → verify documents appear in database
  - [ ] Verify all document types are classified correctly
  - [ ] Verify extracted data is accurate against known test documents
  - [ ] Verify confidence scoring routes correctly (accept/review/reject)
  - [ ] Verify review queue contains only medium-confidence docs
  - [ ] Verify file storage: data/{state}/{operator}/{doc_type}/ structure correct

### Task 7.2: Dashboard E2E (Playwright)
- **Objective**: Full Playwright browser testing of every dashboard feature
- **Testing**:
  - [ ] Playwright: Navigate to dashboard, verify layout
  - [ ] Playwright: Search for a well by API number → results appear
  - [ ] Playwright: Filter wells by state → table updates
  - [ ] Playwright: Click well → side panel shows details + documents
  - [ ] Playwright: Navigate to map → pins render
  - [ ] Playwright: Zoom in/out → clusters collapse/expand
  - [ ] Playwright: Click map pin → popup shows well info
  - [ ] Playwright: Trigger scrape → progress bar updates → completes
  - [ ] Playwright: Review queue → open item → PDF renders alongside fields
  - [ ] Playwright: Approve an item → removed from queue
  - [ ] Playwright: Correct an item → fields update → removed from queue
  - [ ] Playwright: Export wells as CSV → file downloads
  - [ ] Screenshot all key screens as evidence

### Task 7.3: Error Handling & Edge Cases
- **Objective**: Test failure modes, edge cases, and error recovery
- **Testing**:
  - [ ] Scrape a state when site is unreachable → graceful error, job marked failed
  - [ ] Process a corrupt/unreadable PDF → rejected with low confidence
  - [ ] Process a zero-byte file → handled gracefully
  - [ ] Search with no results → empty state displayed
  - [ ] Map with no data → empty map renders
  - [ ] Scrape while another scrape is running → appropriate response
  - [ ] Review queue when empty → empty state displayed
  - [ ] API with invalid parameters → proper 400/422 error responses
  - [ ] Database connection loss → health endpoint reports unhealthy

### Task 7.4: Performance & Smoke Tests
- **Objective**: Verify performance meets requirements and Docker stack is stable
- **Testing**:
  - [ ] Docker: `docker compose down && docker compose up` → all services start cleanly
  - [ ] Docker: Services remain stable after 30+ minutes of operation
  - [ ] API: All endpoints respond in <500ms with test dataset
  - [ ] Map: Renders 1000+ wells without lag
  - [ ] Scrape: Single state completes within reasonable time (VCR replay)
  - [ ] OCR: Single document processes in <30 seconds
  - [ ] Database: Migrations run clean on fresh database
  - [ ] Frontend: No console errors on any page
  - [ ] All test suites pass: `just test`

---

## Dependency Graph

```
Phase 1: Foundation
1.1 (scaffolding) ──┬──> 1.2 (database) ──> 1.4 (FastAPI skeleton)
                    └──> 1.3 (base scraper)

Phase 2: Document Pipeline
1.1 ──> 2.1 (text/OCR) ──> 2.2 (classify) ──> 2.3 (extract) ──> 2.4 (validate/score)

Phase 3: Backend API
1.2 + 1.4 ──> 3.1 (CRUD) ──┬──> 3.2 (scrape/Huey/SSE)
                            ├──> 3.3 (review queue)
                            └──> 3.4 (map/export)

Phase 4: First Scrapers (PA, CO, OK)
1.3 + 2.4 ──┬──> 4.1 (PA)
             ├──> 4.2 (CO)
             └──> 4.3 (OK)

Phase 5: Frontend Dashboard
1.1 ──> 5.1 (foundation) ──┬──> 5.2 (search/browse)
                           ├──> 5.3 (map)
                           ├──> 5.4 (scrape/progress)
                           └──> 5.5 (review/viewer)

Phase 6: Remaining Scrapers (TX, NM, ND, WY, CA, AK, LA)
1.3 + 2.4 ──┬──> 6.1 (TX + NM)
             ├──> 6.2 (ND + WY + AK)
             └──> 6.3 (CA + LA)

Phase 7: E2E Testing
All phases ──> 7.1-7.4
```

---

## Task Execution Protocol

### For each task:
1. **Orient**: Read task file, skills, PROGRESS.md
2. **Plan**: Explore codebase, plan approach
3. **Implement**: Feature branch, write code, write tests
4. **Test**: Run all applicable testing methods locally
5. **Complete**: Update PROGRESS.md, commit, merge to target branch

### For regression tasks:
1. Deploy to local Docker stack (`docker compose up`)
2. Run ALL task tests from the phase
3. Full e2e testing from every angle
4. Fix any failures, redeploy, retest
5. Merge phase branch to main

### For final phase:
1. All tasks are e2e testing on fully deployed local software
2. Every user path and edge case covered
3. Every testing method applied
4. Iterate on main/target branch until all green
