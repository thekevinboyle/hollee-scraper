---
name: og-scraper-architecture
description: Overall Oil & Gas Document Scraper project architecture. Use when understanding project structure, service connections, folder layout, or how components interact.
---

# Oil & Gas Document Scraper - Project Architecture

## What It Is

A monorepo application that automates scraping oil & gas regulatory documents from US state government websites, classifying unlabeled documents, extracting structured data via OCR, and presenting everything through a searchable dashboard with an interactive map. It replaces a full day of manual work collecting fragmented regulatory data across 10 states.

**Target states (10 total):**
- Tier 1: Texas, New Mexico, North Dakota, Oklahoma, Colorado
- Tier 2: Wyoming, Louisiana, Pennsylvania, California, Alaska

**Document types scraped:** well permits, completion reports, production reports, spacing/pooling orders, plugging reports, inspection records, incident reports.

**Key constraints:**
- Local deployment only (Docker Compose on a laptop/desktop)
- No paid APIs -- PaddleOCR (~90% accuracy) as the sole OCR engine
- No authentication (internal tool for 1-2 users)
- On-demand scraping only (user triggers from dashboard)

---

## When To Use This Skill

Use this skill when any execution agent needs to:
- Understand where code lives in the monorepo
- Know how services connect to each other
- Understand the overall folder layout
- Know which database tables exist and how they relate
- Understand the API contract between frontend and backend
- Know the document processing pipeline stages
- Set up or configure the development environment
- Understand architectural decisions and their rationale

---

## Project Structure

```
og-doc-scraper/
|-- pyproject.toml                    # Root UV workspace configuration
|-- uv.lock                          # Single lockfile for all Python packages
|-- .python-version                  # Pin Python version (>=3.12)
|-- docker-compose.yml               # All services: DB, Redis, API, worker, frontend
|-- Dockerfile                       # Multi-stage build for Python services
|-- justfile                         # Task runner commands
|
|-- backend/
|   |-- alembic/                     # Database migrations
|   |   |-- versions/
|   |   |-- env.py
|   |   |-- alembic.ini
|   |-- app/
|   |   |-- __init__.py
|   |   |-- main.py                  # FastAPI application factory
|   |   |-- config.py                # Settings via pydantic-settings
|   |   |-- database.py              # Async engine + session factory (asyncpg)
|   |   |-- models/                  # SQLAlchemy 2.0 async ORM models
|   |   |   |-- base.py              # DeclarativeBase, TimestampMixin, UUIDPrimaryKeyMixin
|   |   |   |-- state.py
|   |   |   |-- operator.py
|   |   |   |-- well.py
|   |   |   |-- document.py
|   |   |   |-- extracted_data.py
|   |   |   |-- review_queue.py
|   |   |   |-- scrape_job.py
|   |   |   |-- data_correction.py
|   |   |-- schemas/                 # Pydantic request/response models
|   |   |   |-- well.py
|   |   |   |-- document.py
|   |   |   |-- scrape.py
|   |   |   |-- review.py
|   |   |   |-- map.py
|   |   |   |-- stats.py
|   |   |   |-- export.py
|   |   |-- api/                     # FastAPI routers (one per domain)
|   |   |   |-- wells.py
|   |   |   |-- documents.py
|   |   |   |-- scrape.py
|   |   |   |-- review.py
|   |   |   |-- map.py
|   |   |   |-- stats.py
|   |   |   |-- export.py
|   |   |-- services/                # Business logic layer
|   |   |   |-- well_service.py
|   |   |   |-- document_service.py
|   |   |   |-- search_service.py
|   |   |   |-- review_service.py
|   |   |   |-- stats_service.py
|   |   |-- tasks/                   # Huey task definitions
|   |   |   |-- scrape_tasks.py
|   |   |   |-- process_tasks.py
|   |   |   |-- review_tasks.py
|   |   |-- utils/
|   |       |-- api_number.py        # API number normalization (strip dashes, zero-pad)
|   |       |-- pagination.py
|   |       |-- query_builder.py
|   |-- tests/
|   |-- pyproject.toml
|   |-- Dockerfile
|
|-- frontend/                        # Next.js 16 + TypeScript dashboard
|   |-- package.json
|   |-- src/
|   |   |-- app/                     # Next.js App Router
|   |   |   |-- dashboard/           # Overview, scrape monitoring
|   |   |   |-- documents/           # Document search and browse
|   |   |   |-- review/              # Data quality review queue
|   |   |   |-- exports/             # Configure and download exports
|   |   |   |-- settings/            # State registry, scraper config
|   |   |-- components/              # React components (shadcn/ui)
|   |   |-- lib/                     # API client, utilities
|
|-- packages/                        # UV workspace packages
|   |-- core/                        # Shared core library
|   |   |-- src/og_scraper_core/
|   |   |   |-- models/              # SQLAlchemy models (shared)
|   |   |   |-- db/                  # Database connection, queries
|   |   |   |-- storage/             # File storage abstraction (Local/S3/MinIO)
|   |   |   |-- schemas/             # Pydantic schemas (shared)
|   |   |   |-- config.py
|   |   |   |-- constants.py
|   |
|   |-- scraper/                     # Scraping engine (Scrapy + Playwright)
|   |   |-- src/og_scraper/
|   |   |   |-- spiders/             # One spider per state
|   |   |   |   |-- base.py          # Base state spider class
|   |   |   |   |-- texas.py
|   |   |   |   |-- oklahoma.py
|   |   |   |   |-- north_dakota.py
|   |   |   |   |-- (... per state)
|   |   |   |-- pipelines/           # Scrapy item pipelines
|   |   |   |-- middlewares/
|   |   |   |-- adapters/            # State-specific site adapters
|   |   |   |-- settings.py
|   |
|   |-- classifier/                  # Document classification engine
|   |   |-- src/og_classifier/
|   |   |   |-- classifiers/         # Per-doc-type classifiers
|   |   |   |-- rules/               # Rule-based classification (~80% of docs)
|   |
|   |-- extractor/                   # Data extraction engine
|   |   |-- src/og_extractor/
|   |   |   |-- extractors/          # Per-format extractors
|   |   |   |   |-- pdf.py
|   |   |   |   |-- xlsx.py
|   |   |   |   |-- csv_ext.py
|   |   |   |   |-- html.py
|   |   |   |-- ocr/                 # PaddleOCR utilities
|   |   |   |-- normalizers/         # State-specific field normalizers
|   |
|   |-- worker/                      # Huey task queue workers
|   |   |-- src/og_worker/
|   |   |   |-- tasks/
|   |   |   |-- main.py
|   |
|   |-- cli/                         # CLI tool (Typer)
|       |-- src/og_cli/
|       |   |-- commands/
|       |   |-- main.py
|
|-- migrations/                      # Alembic migrations (shared)
|   |-- alembic.ini
|   |-- versions/
|
|-- data/                            # Local data storage (gitignored)
|   |-- documents/                   # Original scraped documents
|   |   |-- {state}/
|   |   |   |-- {operator}/
|   |   |   |   |-- {doc_type}/
|   |   |   |       |-- {filename}
|   |-- exports/                     # Generated export files
|
|-- config/                          # Configuration files
|   |-- states/                      # Per-state scraper configs (YAML)
|   |   |-- TX.yaml
|   |   |-- OK.yaml
|   |   |-- (... per state)
|   |-- logging.yaml
|
|-- tests/                           # Integration tests
    |-- conftest.py
    |-- test_pipeline/
    |-- test_api/
```

---

## Service Architecture

Five services orchestrated by Docker Compose:

```
+-----------+     +-------------------+     +------------------+
|  Next.js  |---->|   FastAPI (API)   |---->|   PostgreSQL     |
|  Frontend |     |   Port 8000       |     |   + PostGIS      |
|  Port 3000|     +-------------------+     |   Port 5432      |
+-----------+            |                  +------------------+
                         |                          ^
                         v                          |
                  +-------------------+             |
                  |   Redis           |             |
                  |   Port 6379       |             |
                  |   (Huey broker)   |             |
                  +-------------------+             |
                         ^                          |
                         |                          |
                  +-------------------+             |
                  |   Huey Workers    |-------------+
                  |   (scraping,      |
                  |    processing,    |
                  |    review tasks)  |
                  +-------------------+
```

### Service Details

| Service | Technology | Role |
|---------|-----------|------|
| **API** | FastAPI (Python 3.12+) | REST API, serves frontend requests, triggers scrape jobs |
| **Workers** | Huey + Redis | Execute long-running scrape jobs, document processing pipeline |
| **Database** | PostgreSQL 17 + PostGIS 3.5 | Primary data store, full-text search, spatial queries |
| **Cache/Broker** | Redis 7 | Task queue broker for Huey, caching, rate limiting |
| **Frontend** | Next.js 16 + TypeScript + shadcn/ui | Dashboard, search, map, review queue UI |

### Communication Patterns

- **Frontend -> Backend**: REST API calls over HTTP (`/api/v1/*`)
- **Backend -> Workers**: Huey task enqueue via Redis
- **Workers -> Database**: Direct async database access via asyncpg
- **Real-time progress**: Server-Sent Events (SSE) from API to frontend for scrape job progress (`/api/v1/scrape/jobs/{id}/events`)
- **File serving**: FastAPI serves original documents directly from local filesystem via `FileResponse`

---

## Key Architectural Patterns

### 1. Per-State Adapter Pattern

Each of the 10 states has its own scraper spider inheriting from a base class. State-specific configuration lives in YAML files under `config/states/` and in the database `states.config` JSONB column. Each adapter handles that state's unique site structure, URL patterns, and rate limits.

```
BaseStateSpider (base.py)
  |-- TexasSpider (texas.py)       # Texas Railroad Commission
  |-- OklahomaSpider (oklahoma.py) # Oklahoma Corporation Commission
  |-- NorthDakotaSpider (north_dakota.py)
  |-- (... one per state)
```

### 2. Seven-Stage Document Pipeline

Each stage is independently retriable and updates document status in the database:

```
[1. DISCOVER]  --> State adapter navigates site, finds document URLs
       |
[2. DOWNLOAD]  --> Fetch document, compute SHA-256 hash, deduplication check
       |
[3. CLASSIFY]  --> Identify document type (rule-based keywords ~80%, OCR for remainder)
       |
[4. EXTRACT]   --> Pull structured data from document (PaddleOCR, tabula, regex)
       |
[5. NORMALIZE] --> Map state-specific fields to common schema
       |
[6. VALIDATE]  --> Assign confidence scores, flag low-confidence for review
       |
[7. STORE]     --> Persist to PostgreSQL + local filesystem
```

**Document status state machine:**
```
DISCOVERED -> DOWNLOADING -> DOWNLOADED -> CLASSIFYING -> CLASSIFIED -> EXTRACTING -> EXTRACTED -> NORMALIZED -> STORED
                  |                             |                            |
                  v                             v                            v
           DOWNLOAD_FAILED          CLASSIFICATION_FAILED          EXTRACTION_FAILED
                                                                         |
                                                                         v
                                                                 FLAGGED_FOR_REVIEW
```

### 3. Three-Level Confidence Scoring

Every piece of extracted data carries confidence information:

| Level | Column | Source | Purpose |
|-------|--------|--------|---------|
| OCR Confidence | `documents.ocr_confidence` | PaddleOCR | Raw text extraction quality |
| Field Confidence | `extracted_data.field_confidence` (JSONB) | Extraction engine | Per-field scores, e.g. `{"oil_bbl": 0.97, "operator": 0.65}` |
| Document Confidence | `documents.confidence_score` | Aggregate | Used for review queue threshold (default: 0.80) |

Documents or fields below the confidence threshold (0.80 default) are automatically sent to the review queue.

### 4. Review Queue

Low-confidence documents are flagged in the `review_queue` table. The dashboard provides a side-by-side view: original document on the left, extracted data on the right. Users can approve, reject, or correct extracted values. All corrections are tracked in the `data_corrections` table as a full audit trail.

---

## Database Schema Overview

**8 core tables** in PostgreSQL with PostGIS extension:

```
states (10 rows)
  |
  +-- operators (many)
  |     |
  |     +-- wells (many)
  |           |
  |           +-- documents (many)
  |                 |
  |                 +-- extracted_data (many per document)
  |                 |     |
  |                 |     +-- data_corrections (audit trail)
  |                 |
  |                 +-- review_queue (flagged items)
  |
  +-- scrape_jobs (many, linked to documents)
```

### Table Summary

| Table | Primary Key | Purpose | Key Columns |
|-------|------------|---------|-------------|
| **states** | `code` (VARCHAR 2) | 10 supported states with config | `tier`, `config` (JSONB), `last_scraped_at` |
| **operators** | `id` (UUID) | Normalized operator entities | `name`, `normalized_name`, `aliases` (JSONB), `search_vector` |
| **wells** | `id` (UUID) | Physical wells with location | `api_number` (VARCHAR 14), `location` (PostGIS Point), `metadata` (JSONB) |
| **documents** | `id` (UUID) | Every scraped document | `doc_type` (enum), `status` (enum), `file_hash` (SHA-256), `confidence_score` |
| **extracted_data** | `id` (UUID) | Structured data from documents | `data` (JSONB), `field_confidence` (JSONB), `data_type`, `extractor_used` |
| **review_queue** | `id` (UUID) | Items flagged for human review | `status` (pending/approved/rejected/corrected), `reason`, `corrections` (JSONB) |
| **scrape_jobs** | `id` (UUID) | On-demand scrape job tracking | `status` (enum), progress counters, `errors` (JSONB) |
| **data_corrections** | `id` (UUID) | Audit trail for manual fixes | `field_path`, `old_value`, `new_value`, `corrected_by` |

### Key Schema Features

- **JSONB hybrid pattern**: Relational columns for queryable fields, JSONB for variable/state-specific data
- **PostGIS**: `wells.location` GEOMETRY(Point, 4326) with GiST index for map bounding box queries
- **Full-text search**: `tsvector` columns on wells, operators, and documents with GIN indexes
- **Fuzzy search**: `pg_trgm` extension with trigram indexes on API numbers, operator names, lease names
- **Deduplication**: `documents.file_hash` (SHA-256) with UNIQUE constraint
- **API number handling**: Stored as VARCHAR(14) without dashes, auto-computed `api_10` column for cross-referencing

### Enum Types

- `doc_type_enum`: well_permit, completion_report, production_report, spacing_order, pooling_order, plugging_report, inspection_record, incident_report, other
- `document_status_enum`: discovered, downloading, downloaded, classifying, classified, extracting, extracted, normalized, stored, flagged_for_review, download_failed, classification_failed, extraction_failed
- `scrape_job_status_enum`: pending, running, completed, failed, cancelled
- `review_status_enum`: pending, approved, rejected, corrected
- `well_status_enum`: active, inactive, plugged, permitted, drilling, completed, shut_in, temporarily_abandoned, unknown

---

## API Contract

**Base URL:** `http://localhost:8000/api/v1`

### 17 REST Endpoints

| # | Method | Endpoint | Purpose |
|---|--------|----------|---------|
| 1 | GET | `/wells` | Search/filter/paginate wells (supports full-text, fuzzy, state/county/operator filters) |
| 2 | GET | `/wells/{api_number}` | Well detail with associated documents and extracted data |
| 3 | GET | `/documents` | Search/filter/paginate documents (state, doc_type, date range, confidence) |
| 4 | GET | `/documents/{id}` | Document detail with nested extracted data records |
| 5 | GET | `/documents/{id}/file` | Serve original document file (PDF inline, others as download) |
| 6 | POST | `/scrape` | Trigger a new scrape job (returns immediately with job ID) |
| 7 | GET | `/scrape/jobs` | List scrape jobs with status and progress |
| 8 | GET | `/scrape/jobs/{id}` | Detailed job status with progress counters and error list |
| 9 | GET | `/scrape/jobs/{id}/events` | SSE stream for real-time scrape progress |
| 10 | GET | `/review` | List items needing review (default: pending status) |
| 11 | GET | `/review/{id}` | Review item detail with document, extracted data, and file URL |
| 12 | PATCH | `/review/{id}` | Approve, reject, or correct a review item |
| 13 | GET | `/map/wells` | Wells within bounding box (min/max lat/lng) for map viewport |
| 14 | GET | `/stats` | Dashboard statistics (totals, by-state, by-type, avg confidence) |
| 15 | GET | `/stats/state/{state_code}` | Per-state statistics breakdown |
| 16 | GET | `/export/wells` | Export wells data as CSV or JSON (streaming) |
| 17 | GET | `/export/production` | Export production data as CSV or JSON (streaming) |

### Common Query Patterns

- **Pagination**: `?page=1&page_size=50` (max 200)
- **Sorting**: `?sort_by=api_number&sort_dir=asc`
- **Filtering**: `?state=TX&doc_type=production_report&operator=Devon+Energy`
- **Date range**: `?date_from=2026-01-01&date_to=2026-03-27`
- **Full-text search**: `?q=permian+basin+production`
- **Map viewport**: `?min_lat=31.0&max_lat=33.0&min_lng=-104.0&max_lng=-101.0&limit=1000`

---

## File Organization

Original scraped documents are stored on the local filesystem in a labeled folder structure:

```
data/{state}/{operator}/{doc_type}/{filename}
```

Example:
```
data/
  documents/
    TX/
      devon-energy/
        production-reports/
          abc123def456.pdf
        well-permits/
          789ghi012jkl.pdf
    OK/
      continental-resources/
        completion-reports/
          mno345pqr678.xlsx
```

- File hash (SHA-256 prefix) is used as the filename for deduplication
- The `documents.file_path` column in the database stores the full path
- The `documents.file_hash` column stores the SHA-256 hash with a UNIQUE constraint
- FastAPI serves files directly via `FileResponse` at `/api/v1/documents/{id}/file`

---

## Environment Setup

### Python Backend

- **Python**: >= 3.12
- **Package manager**: UV (Astral) with workspace support
- **Virtual environment**: Single `.venv` at workspace root via UV
- **ORM**: SQLAlchemy 2.0 with async support (asyncpg driver)
- **Migrations**: Alembic with autogeneration
- **Linting**: Ruff

```bash
# Install UV (if not already installed)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Install all Python dependencies
uv sync

# Run database migrations
uv run alembic upgrade head

# Start the FastAPI server
uv run uvicorn app.main:app --reload

# Start Huey workers
uv run huey_consumer app.tasks.huey
```

### Node.js Frontend

- **Runtime**: Node.js (LTS)
- **Framework**: Next.js 16 with App Router
- **UI**: shadcn/ui (Tailwind-based), TanStack Table, TanStack Query
- **Map**: Leaflet or Mapbox GL JS with OpenStreetMap tiles
- **Charts**: Recharts or Tremor
- **Document viewer**: react-pdf

```bash
cd frontend
npm install
npm run dev
```

### Docker Compose (All Services)

```bash
# Start everything
docker compose up -d

# Services started:
#   - db:        PostgreSQL 17 + PostGIS 3.5 (port 5432)
#   - redis:     Redis 7 Alpine (port 6379)
#   - api:       FastAPI backend (port 8000)
#   - worker:    Huey task workers
#   - frontend:  Next.js dashboard (port 3000)
```

### Task Runner

`just` is used as the task runner for common development commands. See the `justfile` at the project root.

---

## Technology Stack Summary

| Layer | Technology | Rationale |
|-------|-----------|-----------|
| Language (Backend) | Python 3.12+ | Best ecosystem for scraping, PDF, OCR, ML |
| Language (Frontend) | TypeScript | Type safety for dashboard UI |
| Package Manager (Python) | UV | Modern, fast, workspace support |
| Package Manager (Node) | npm | Standard for Next.js projects |
| Database | PostgreSQL 17 + PostGIS 3.5 | Relational + JSONB hybrid, FTS, spatial |
| Cache / Broker | Redis 7 | Task queue broker, caching |
| API Framework | FastAPI | Async, auto-docs, Pydantic validation |
| ORM | SQLAlchemy 2.0 (async) | Mature, Alembic migrations |
| Task Queue | Huey (Redis-backed) | Lightweight, fast, retries, scheduling |
| Scraping | Scrapy + Playwright | Mature framework + JS rendering |
| OCR | PaddleOCR | Free, local, ~90% accuracy |
| Frontend | Next.js 16 + shadcn/ui | SSR dashboard, component library |
| Search | PostgreSQL FTS + pg_trgm | Built-in, zero infrastructure |
| Deployment | Docker Compose | Local, reproducible |
| Task Runner | just | Cross-platform command runner |

---

## References

All research and planning documents live under `.claude/orchestration-og-doc-scraper/`:

| Document | Path | Contents |
|----------|------|----------|
| Discovery (Q&A) | `.claude/orchestration-og-doc-scraper/DISCOVERY.md` | 26 answered questions defining scope and constraints |
| PRD | `.claude/orchestration-og-doc-scraper/PRD.md` | Product requirements, user flows, success criteria |
| Architecture & Storage | `.claude/orchestration-og-doc-scraper/research/architecture-storage.md` | Database selection, schema design, monorepo structure, deployment, monitoring |
| Backend Schema & API | `.claude/orchestration-og-doc-scraper/research/backend-schema-implementation.md` | Complete SQL DDL, FastAPI endpoints, SQLAlchemy models, Docker Compose |
| O&G Data Models | `.claude/orchestration-og-doc-scraper/research/og-data-models.md` | Domain-specific data modeling for oil & gas entities |
| Document Processing | `.claude/orchestration-og-doc-scraper/research/document-processing.md` | OCR, classification, extraction pipeline details |
| Scraping Strategies | `.claude/orchestration-og-doc-scraper/research/scraping-strategies.md` | Scrapy + Playwright patterns, anti-bot handling |
| State Regulatory Sites | `.claude/orchestration-og-doc-scraper/research/state-regulatory-sites.md` | Per-state site analysis and scraping strategies |
| Dashboard & Map | `.claude/orchestration-og-doc-scraper/research/dashboard-map-implementation.md` | Next.js dashboard pages, Leaflet map, component stack |
| Per-State Scrapers | `.claude/orchestration-og-doc-scraper/research/per-state-scrapers-implementation.md` | State-by-state spider implementation details |
| Document Pipeline | `.claude/orchestration-og-doc-scraper/research/document-pipeline-implementation.md` | Pipeline stage implementation, Huey tasks |
| Testing & Deployment | `.claude/orchestration-og-doc-scraper/research/testing-deployment-implementation.md` | Test strategy, Docker configuration, CI/CD |
