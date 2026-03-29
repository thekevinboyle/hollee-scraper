# Data Storage, App Architecture & Deployment Research
## Oil & Gas Document Scraper

**Research Date**: 2026-03-27
**Scope**: Database, search, file storage, architecture, deployment, monitoring, scheduling, cost optimization

---

## Table of Contents

1. [Database Selection](#1-database-selection)
2. [Schema Design](#2-schema-design)
3. [Full-Text Search](#3-full-text-search)
4. [File Storage Strategy](#4-file-storage-strategy)
5. [App Architecture Patterns](#5-app-architecture-patterns)
6. [Pipeline Architecture](#6-pipeline-architecture)
7. [Task Queue / Job System](#7-task-queue--job-system)
8. [Scheduling](#8-scheduling)
9. [Frontend Options](#9-frontend-options)
10. [API Design](#10-api-design)
11. [Export Formats](#11-export-formats)
12. [Deployment Options](#12-deployment-options)
13. [Monitoring & Alerting](#13-monitoring--alerting)
14. [Cost Optimization](#14-cost-optimization)
15. [Language Choice: Python vs Node.js](#15-language-choice-python-vs-nodejs)
16. [Monorepo Structure](#16-monorepo-structure)
17. [Domain-Specific Considerations](#17-domain-specific-considerations)
18. [Recommendations Summary](#18-recommendations-summary)

---

## 1. Database Selection

### Candidates Evaluated

| Database   | Type             | Best For                              | Operational Overhead |
|------------|------------------|---------------------------------------|----------------------|
| PostgreSQL | Relational + JSONB | Structured + semi-structured hybrid  | Medium               |
| SQLite     | Embedded relational | Single-user, local-first tools      | Zero                 |
| MongoDB    | Document store   | Flexible, schema-free ingestion       | Medium-High          |
| DuckDB     | Embedded OLAP    | Analytics, aggregations, exports      | Zero                 |

### PostgreSQL (RECOMMENDED PRIMARY)

**Why it fits this project:**
- The O&G data has strong relational structure (states, operators, wells, documents, data points) that benefits from foreign keys and constraints.
- JSONB columns handle the semi-structured parts: each state's extracted data has different fields, document metadata varies by type, and raw extraction results are naturally JSON.
- PostgreSQL 18 (released September 2025) introduced async I/O and faster JSON operators, improving document-style query performance.
- Built-in full-text search (tsvector/tsquery) eliminates the need for a separate search engine at the project's initial scale.
- GIN indexes on JSONB columns allow efficient querying of nested metadata.
- ACID compliance ensures data integrity for provenance tracking (critical for regulatory data).
- Extensive ecosystem: SQLAlchemy, Alembic migrations, asyncpg for async access.

**JSONB hybrid pattern for this project:**
```
-- Core relational columns for queryable fields
-- JSONB column for variable/state-specific extracted data
CREATE TABLE documents (
    id UUID PRIMARY KEY,
    state VARCHAR(2) NOT NULL,
    doc_type VARCHAR(50),
    operator VARCHAR(255),
    api_number VARCHAR(20),
    -- ... fixed fields ...
    extracted_data JSONB,      -- variable data per doc type
    raw_metadata JSONB,        -- original scrape metadata
    created_at TIMESTAMPTZ
);
```

**Key consideration:** PostgreSQL JSONB gives "80% of MongoDB's flexibility with 100% of PostgreSQL's reliability." For a regulatory data project where data integrity matters, this is the right tradeoff.

### SQLite

**Role: Development, testing, and potential embedded analytics companion.**
- Excellent for local development and testing without requiring a database server.
- Could serve as a cache or offline data store for a CLI tool component.
- Not suitable as the primary production database due to single-writer limitations and lack of concurrent access support.

### MongoDB

**Why NOT recommended as primary:**
- The O&G data is fundamentally relational (wells belong to operators, in counties, in states; documents reference wells; extracted data references documents).
- Schema flexibility sounds appealing for varying state data, but PostgreSQL JSONB provides this without sacrificing relational integrity.
- Adds operational complexity (separate database server, different query language, separate backup strategy).
- The "schema-free" nature can lead to data quality issues -- exactly what the PRD warns against.

**Potential secondary use:** Could be useful if storing large volumes of raw, unprocessed scrape results before classification, but a staging table in PostgreSQL with JSONB serves the same purpose.

### DuckDB

**Role: Analytics companion, NOT primary storage.**
- Excellent for ad-hoc analytical queries over extracted data (production trends, aggregations across states).
- Can read directly from PostgreSQL, Parquet files, and CSV -- making it ideal for the export/analysis layer.
- Embeds directly in the Python process (no server needed).
- Use case: Power the export pipeline and analytics dashboard queries by reading from PostgreSQL or Parquet snapshots.
- DuckDB 1.0+ (mid-2024) introduced stable on-disk format, making it viable for persistent analytics caches.

### Decision

```
PRIMARY DATABASE:     PostgreSQL (relational + JSONB hybrid)
ANALYTICS COMPANION:  DuckDB (embedded, for exports and analytics)
DEVELOPMENT/TESTING:  SQLite (via SQLAlchemy dialect swapping)
```

---

## 2. Schema Design

### Relational vs. Document Store

**Recommendation: Relational core with JSONB extensions (PostgreSQL hybrid approach).**

The O&G domain has clear entity relationships that benefit from relational modeling, but the variability across states and document types demands flexibility in certain columns.

### Proposed Schema (Text-Based ERD)

```
+------------------+       +-------------------+       +-------------------+
|   states         |       |   site_configs    |       |   scrape_runs     |
|------------------|       |-------------------|       |-------------------|
| code (PK)        |<------| state_code (FK)   |       | id (PK)           |
| name             |       | site_url          |       | state_code (FK)   |
| priority         |       | scraper_class     |       | started_at        |
| last_scraped     |       | url_patterns JSONB|       | finished_at       |
| status           |       | auth_config JSONB |       | status            |
+------------------+       | rate_limit_ms     |       | docs_found        |
                           | last_validated    |       | docs_downloaded   |
                           +-------------------+       | errors JSONB      |
                                                       +-------------------+
                                                              |
+------------------+       +-------------------+              |
|   operators      |       |   wells           |              |
|------------------|       |-------------------|              |
| id (PK)          |       | id (PK)           |              |
| name             |       | api_number (UQ)   |              |
| normalized_name  |       | well_name         |              |
| aliases JSONB    |       | well_number       |              |
+------------------+       | operator_id (FK)  |              |
       |                   | state_code (FK)   |              |
       |                   | county            |              |
       |                   | lat/lon           |              |
       |                   | status            |              |
       +-------------------| metadata JSONB    |              |
                           +-------------------+              |
                                  |                           |
                           +-------------------+              |
                           |   documents       |--------------+
                           |-------------------|
                           | id (PK)           |
                           | well_id (FK, NULL)|
                           | state_code (FK)   |
                           | scrape_run_id(FK) |
                           | doc_type          |
                           | source_url        |
                           | file_path         |
                           | file_hash (SHA256)|
                           | file_format       |
                           | file_size_bytes   |
                           | classification    |
                           | confidence_score  |
                           | scraped_at        |
                           | raw_metadata JSONB|
                           | search_vector     |  -- tsvector for FTS
                           +-------------------+
                                  |
                           +-------------------+
                           | extracted_data    |
                           |-------------------|
                           | id (PK)           |
                           | document_id (FK)  |
                           | data_type         |  -- 'production', 'permit', etc.
                           | data JSONB        |  -- flexible per doc_type
                           | confidence JSONB  |  -- per-field confidence
                           | version           |  -- extraction version
                           | extracted_at      |
                           | extractor_used    |
                           +-------------------+
                                  |
                           +-------------------+
                           | data_corrections  |
                           |-------------------|
                           | id (PK)           |
                           | extracted_data_id |
                           | field_path        |
                           | old_value JSONB   |
                           | new_value JSONB   |
                           | corrected_by      |
                           | corrected_at      |
                           +-------------------+
```

### Key Design Decisions

1. **Separate `extracted_data` table with JSONB `data` column**: Each document type (production report, permit, completion report) has different fields. Rather than creating a table per document type, a single table with a JSONB `data` column accommodates all types. The `data_type` column enables type-specific queries.

2. **Confidence tracking per field**: The `confidence` JSONB column stores per-field confidence scores, directly addressing the PRD's requirement to "surface confidence, not pretend data is clean."

3. **File hash for deduplication**: SHA256 hash prevents re-downloading and re-processing identical documents across scrape runs.

4. **Provenance chain**: `scrape_run_id` + `source_url` + `scraped_at` provides full provenance tracking per the PRD requirements.

5. **Correction tracking**: The `data_corrections` table supports Flow 3 (Data Quality Review) and enables learning from corrections.

### Indexing Strategy

```sql
-- Primary query patterns
CREATE INDEX idx_documents_state_type ON documents(state_code, doc_type);
CREATE INDEX idx_documents_file_hash ON documents(file_hash);
CREATE INDEX idx_documents_source_url ON documents(source_url);

-- JSONB GIN indexes for flexible querying
CREATE INDEX idx_extracted_data_gin ON extracted_data USING GIN (data jsonb_path_ops);
CREATE INDEX idx_documents_metadata_gin ON documents USING GIN (raw_metadata jsonb_path_ops);

-- Full-text search index
CREATE INDEX idx_documents_search ON documents USING GIN (search_vector);

-- API number lookups (critical for O&G)
CREATE INDEX idx_wells_api ON wells(api_number);
CREATE INDEX idx_wells_operator ON wells(operator_id);
```

### Migration Strategy

- **SQLAlchemy** as the ORM with async support (via asyncpg).
- **Alembic** for schema migrations with autogeneration.
- Best practice: Always review autogenerated migrations manually; keep migrations independent of current model state for reliable rollbacks.

---

## 3. Full-Text Search

### Options Evaluated

| Solution         | Infrastructure | Typo Tolerance | Faceted Search | Scale          |
|------------------|---------------|----------------|----------------|----------------|
| PostgreSQL FTS   | None (built-in) | Via pg_trgm  | Manual (complex) | ~10M docs    |
| Meilisearch      | Lightweight   | Built-in       | Built-in       | ~10M docs      |
| Elasticsearch    | Heavy         | Built-in       | Built-in       | Billions       |
| ParadeDB (pg_search) | PG extension | Built-in   | Built-in       | ~100M docs   |

### Recommendation: Start with PostgreSQL FTS, Graduate to Meilisearch if Needed

**Phase 1: PostgreSQL FTS (Immediate)**

For the initial deployment, PostgreSQL's built-in full-text search is sufficient:
- Searching documents by content, operator name, well name, API number.
- The `tsvector` + `tsquery` system handles tokenization, stemming, and ranking.
- Add the `pg_trgm` extension for fuzzy/typo-tolerant matching.
- No additional infrastructure to deploy, monitor, or sync.

```sql
-- Example: search across document text content
ALTER TABLE documents ADD COLUMN search_vector tsvector;

CREATE FUNCTION documents_search_update() RETURNS trigger AS $$
BEGIN
  NEW.search_vector := to_tsvector('english',
    coalesce(NEW.doc_type, '') || ' ' ||
    coalesce(NEW.state_code, '') || ' ' ||
    coalesce(NEW.raw_metadata->>'operator', '') || ' ' ||
    coalesce(NEW.raw_metadata->>'well_name', '')
  );
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;
```

**Phase 2: Meilisearch (When search UX matters)**

If a web dashboard is built and search experience becomes important:
- Meilisearch provides instant, typo-tolerant search with faceted filtering.
- Lightweight (~290MB RAM vs Elasticsearch's ~1.3GB for same dataset).
- Easy sync from PostgreSQL via a background job.
- Built-in facets for filtering by state, document type, operator, date range.

**Phase 3: Elasticsearch (Only if needed)**

Upgrade path if the system grows to billions of documents or needs complex aggregations, deep relevance tuning, or enterprise search patterns. For this project's likely scale (millions of documents across ~50 states), Meilisearch or PostgreSQL FTS will suffice for years.

### ParadeDB Alternative

ParadeDB's `pg_search` extension brings BM25 full-text search, fuzzy matching, and faceted search directly into PostgreSQL. This is a compelling middle ground: Elasticsearch-quality search without leaving PostgreSQL. Worth evaluating as the project matures.

---

## 4. File Storage Strategy

### Requirements

- Store downloaded documents (PDFs, XLSX, CSV, HTML) with reliable retrieval.
- Track file provenance (which URL, when downloaded, file hash).
- Support deduplication (same document from different scrape runs).
- Handle potentially large volumes (thousands to millions of files).
- Support both local development and production deployment.

### Strategy: Local Filesystem with DB Pointers (Start) + MinIO/S3 (Scale)

```
PHASE 1 (Local/Dev):
  Downloaded files --> Local filesystem (organized directory structure)
  File metadata   --> PostgreSQL (path, hash, size, mime type)

PHASE 2 (Production):
  Downloaded files --> MinIO (self-hosted, S3-compatible)
  File metadata   --> PostgreSQL (S3 key, hash, size, mime type)

PHASE 3 (Cloud):
  Downloaded files --> AWS S3 or equivalent
  File metadata   --> PostgreSQL (S3 URI, hash, size, mime type)
```

### Directory Structure (Local Filesystem)

```
data/
  documents/
    TX/                         # State code
      2026/                     # Year
        03/                     # Month
          well-permits/         # Document type
            abc123def456.pdf    # SHA256 prefix as filename
          production-reports/
            789ghi012jkl.xlsx
    OK/
      2026/
        03/
          ...
```

### Why This Layered Approach Works

1. **Local filesystem for development**: Zero setup, fast iteration, easy debugging. Files are organized by state/year/month/type for human browsability.

2. **MinIO for self-hosted production**: S3-compatible API means the application code uses the same `boto3` client for both MinIO and AWS S3. MinIO runs as a single Docker container. Switching from MinIO to S3 requires only changing credentials -- no code changes.

3. **S3 for cloud production**: If the project moves to cloud deployment, the same code works with real S3.

### Abstraction Layer

```python
# Storage abstraction -- same interface for local, MinIO, and S3
class DocumentStore(Protocol):
    async def put(self, key: str, data: bytes, metadata: dict) -> str: ...
    async def get(self, key: str) -> bytes: ...
    async def exists(self, key: str) -> bool: ...
    async def delete(self, key: str) -> None: ...

class LocalDocumentStore(DocumentStore): ...   # Phase 1
class S3DocumentStore(DocumentStore): ...      # Phase 2-3 (works with MinIO and S3)
```

### Deduplication Strategy

- Compute SHA256 hash of every downloaded file before storage.
- Check hash against database before storing (skip if already exists).
- Store hash in `documents.file_hash` column with a unique index.
- This prevents wasting storage on duplicate documents across scrape runs.

---

## 5. App Architecture Patterns

### CLI Tool vs. Web App vs. Hybrid

**Recommendation: Hybrid -- CLI-first with optional web dashboard.**

```
ARCHITECTURE DECISION:

  CLI Tool (Primary Interface)
    |
    +-- Scraping commands (run scrapers, check status)
    +-- Query commands (search documents, export data)
    +-- Admin commands (manage state configs, validate scrapers)
    |
  Web Dashboard (Secondary Interface, Phase 2)
    |
    +-- Scrape monitoring dashboard
    +-- Document search/browse UI
    +-- Data quality review interface (Flow 3)
    +-- Export builder
    |
  Shared Core Library
    |
    +-- Database models & queries
    +-- Scraping engine
    +-- Classification engine
    +-- Extraction engine
    +-- File storage layer
    +-- Export utilities
```

**Why CLI-first:**
- The primary users are technical (O&G data workers who currently do manual scraping).
- CLI is faster to build and iterate on.
- Easier to automate (cron jobs, CI/CD pipelines).
- Can be run on any server without a web server.
- The scraping pipeline is inherently a batch/background process.

**Why add a web dashboard later:**
- Flow 3 (Data Quality Review) requires showing documents alongside extracted values -- this is much better in a browser.
- Monitoring scraper health is easier with a visual dashboard.
- Non-technical stakeholders may want to search and browse data.
- Export configuration is more intuitive with a form UI.

### High-Level System Architecture

```
+-------------------------------------------------------------------+
|                        USER INTERFACES                             |
|  +------------------+   +------------------+   +----------------+  |
|  |   CLI (Typer)    |   | Web Dashboard    |   |  REST API      |  |
|  |                  |   | (Next.js)        |   |  (FastAPI)     |  |
|  +--------+---------+   +--------+---------+   +-------+--------+  |
|           |                      |                      |          |
+-----------+----------------------+----------------------+----------+
            |                      |                      |
+-----------v----------------------v----------------------v----------+
|                        CORE APPLICATION                            |
|  +------------------+   +------------------+   +----------------+  |
|  | Scraping Engine  |   | Classification   |   | Extraction     |  |
|  | (Scrapy +        |   | Engine           |   | Engine         |  |
|  |  Playwright)     |   | (ML/Rule-based)  |   | (PDF/OCR/XLSX) |  |
|  +--------+---------+   +--------+---------+   +-------+--------+  |
|           |                      |                      |          |
|  +--------v---------+   +--------v---------+   +-------v--------+  |
|  | State Adapters   |   | Doc Classifiers  |   | Data Extractors|  |
|  | (per-state       |   | (per doc type)   |   | (per format)   |  |
|  |  scraper logic)  |   |                  |   |                |  |
|  +------------------+   +------------------+   +----------------+  |
|                                                                    |
|  +------------------+   +------------------+   +----------------+  |
|  | Task Queue       |   | Document Store   |   | Database Layer |  |
|  | (Dramatiq/Huey)  |   | (Local/MinIO/S3) |   | (PostgreSQL)   |  |
|  +------------------+   +------------------+   +----------------+  |
+-------------------------------------------------------------------+
```

---

## 6. Pipeline Architecture

### Scrape --> Download --> Classify --> Extract --> Store

The pipeline follows a staged processing model where each stage is decoupled and can be retried independently.

```
PIPELINE FLOW:

  [1. DISCOVER]     State adapter navigates site, finds document URLs
       |
       v
  [2. DOWNLOAD]     Fetch document, compute hash, check deduplication
       |
       v
  [3. CLASSIFY]     Identify document type (permit, production report, etc.)
       |
       v
  [4. EXTRACT]      Pull structured data from document content
       |
       v
  [5. NORMALIZE]    Map state-specific fields to common schema
       |
       v
  [6. VALIDATE]     Check data quality, assign confidence scores
       |
       v
  [7. STORE]        Persist to database + file storage
       |
       v
  [8. NOTIFY]       Alert on new data, errors, quality issues
```

### Pipeline Implementation Options

**Option A: Scrapy Pipeline (Recommended for Scraping Stages)**

Scrapy's built-in pipeline architecture naturally handles stages 1-2:
- Spiders handle discovery (stage 1).
- FilesPipeline handles downloads (stage 2) with built-in deduplication, retry logic, and storage backends (local, S3, GCS).
- Item Pipeline handles post-processing (stages 3-7).
- Each pipeline component is a Python class with a `process_item` method.
- Pipeline stages run sequentially with configurable priority ordering.

**Option B: Task Queue for Post-Download Processing (Recommended for Stages 3-7)**

After Scrapy downloads a document, enqueue it for classification and extraction:
```
Scrapy Spider --> FilesPipeline --> [Message Queue] --> Classification Worker
                                                              |
                                                              v
                                                       Extraction Worker
                                                              |
                                                              v
                                                       Normalization Worker
                                                              |
                                                              v
                                                       Storage Worker
```

This decoupling provides:
- Independent scaling (more extraction workers if that is the bottleneck).
- Independent retry (classification failure does not require re-downloading).
- Progress tracking (each stage updates document status in database).
- Graceful degradation (extraction service down does not stop scraping).

### Document Status State Machine

```
  DISCOVERED --> DOWNLOADING --> DOWNLOADED --> CLASSIFYING --> CLASSIFIED
                     |                             |
                     v                             v
                DOWNLOAD_FAILED            CLASSIFICATION_FAILED
                                                   |
                                                   v
                                           EXTRACTING --> EXTRACTED
                                                   |
                                                   v
                                           EXTRACTION_FAILED
                                                   |
                                                   v
                                           NORMALIZED --> STORED
                                                   |
                                                   v
                                           FLAGGED_FOR_REVIEW
```

---

## 7. Task Queue / Job System

### Candidates Evaluated

| Queue     | Broker      | Complexity | Performance    | Best For                     |
|-----------|-------------|------------|----------------|------------------------------|
| Celery    | Redis/RMQ   | High       | High           | Large-scale distributed      |
| Dramatiq  | Redis/RMQ   | Medium     | High           | Modern, reliable, mid-scale  |
| Huey      | Redis       | Low        | Very High      | Lightweight, fast            |
| RQ        | Redis       | Very Low   | Low-Medium     | Simple prototypes            |
| Taskiq    | Redis/etc   | Medium     | Very High      | Async-native                 |

### Recommendation: Huey (Start) or Dramatiq (Scale)

**Huey for initial development:**
- Extremely lightweight -- minimal code and setup.
- Very fast (nearly 10x faster than RQ in benchmarks for 20K jobs).
- Redis-backed with built-in scheduling, retries, and result storage.
- Perfect for a project that starts as a single-server deployment.
- Supports periodic tasks (for scheduled scraping).
- Minimal boilerplate compared to Celery.

**Dramatiq for production scale:**
- Modern API design with built-in retry logic, rate limiting, and result backends.
- Supports both Redis and RabbitMQ as brokers.
- Better error handling and middleware system than Celery.
- Active development and growing community.
- Recommended by the Python community for greenfield projects in 2025-2026.

**Why not Celery:**
- Overkill for this project's likely scale.
- Higher configuration complexity.
- More operational overhead.
- The "enterprise features" (Canvas workflows, complex routing) add complexity without proportional benefit for this use case.

### Task Definitions

```python
# Example task definitions
@task(retries=3, retry_delay=60)
def classify_document(document_id: str):
    """Classify a downloaded document by type."""
    ...

@task(retries=2, retry_delay=30)
def extract_data(document_id: str):
    """Extract structured data from a classified document."""
    ...

@task()
def notify_new_data(scrape_run_id: str):
    """Send notifications about newly available data."""
    ...
```

---

## 8. Scheduling

### Candidates Evaluated

| Tool          | Complexity | Scale         | UI  | Best For                        |
|---------------|-----------|---------------|-----|---------------------------------|
| Cron          | Minimal   | Single server | No  | Simple, time-based triggers     |
| APScheduler   | Low       | Single server | No  | In-process Python scheduling    |
| Huey periodic | Low       | Single server | No  | Integrated with task queue      |
| Prefect       | Medium    | Multi-server  | Yes | Dynamic workflows, observability|
| Airflow       | High      | Multi-server  | Yes | Complex DAGs, enterprise        |
| Dagster       | Medium    | Multi-server  | Yes | Data-aware orchestration        |

### Recommendation: Huey Periodic Tasks (Start) --> Prefect (Scale)

**Phase 1: Huey periodic tasks + simple cron**
- Huey supports `@periodic_task` decorator for recurring jobs.
- Cron as a fallback for system-level scheduling.
- Zero additional infrastructure.
- Sufficient for: "scrape Texas every Monday, Oklahoma every Wednesday."

**Phase 2: Prefect (when orchestration complexity grows)**
- When the project needs: dynamic scheduling per state, dependency chains between scrape/classify/extract, retry policies per state, and a visual monitoring UI.
- Prefect uses standard Python functions (no rigid DAG definitions like Airflow).
- Supports reactive, event-based orchestration (e.g., "run extraction when new documents arrive").
- Better developer experience than Airflow for Python-native teams.
- Prefect 3.x (current) supports hybrid cloud/on-prem execution.

**Why not Airflow:**
- Airflow's static DAG model is a poor fit for dynamic scraping workloads where each state has different schedules and the number of documents per run is unknown.
- Higher operational overhead (separate web server, scheduler, database, worker processes).
- Airflow 3 (2025) improved things, but Prefect remains more developer-friendly.

### Scheduling Pattern

```
SCHEDULE CONFIGURATION (stored in database):

  State: TX  | Frequency: daily    | Time: 02:00 UTC | Priority: 1
  State: OK  | Frequency: daily    | Time: 03:00 UTC | Priority: 2
  State: ND  | Frequency: weekly   | Day: Monday     | Priority: 3
  State: NM  | Frequency: weekly   | Day: Tuesday    | Priority: 4
  ...

SCHEDULER reads config --> enqueues scrape tasks --> workers execute
```

---

## 9. Frontend Options

### Evaluation Criteria

The web dashboard needs to support:
- Scrape run monitoring (status, progress, errors).
- Document search and browsing.
- Data quality review (side-by-side document viewer + extracted data).
- Export configuration and download.

### Recommendation: Next.js with shadcn/ui

**Why Next.js:**
- Server-side rendering for fast initial loads on data-heavy pages.
- API routes can proxy to the FastAPI backend or serve lightweight endpoints directly.
- App Router (stable since Next.js 13+, mature in Next.js 16) provides clean layout composition.
- Strong ecosystem for dashboards: shadcn/ui, TailAdmin, Tremor for charts.
- TypeScript support for type-safe frontend development.
- Excellent developer experience with hot reload.

**Component Stack:**
```
Next.js 16 + TypeScript
  |-- shadcn/ui (component library, Tailwind-based)
  |-- TanStack Table (data tables with sorting, filtering, pagination)
  |-- TanStack Query (server state management, caching)
  |-- Recharts or Tremor (charts for monitoring dashboards)
  |-- react-pdf (document viewer for PDFs in Data Quality Review)
```

**Alternatives considered:**
- **Plain React SPA**: Viable, but loses SSR benefits for data-heavy pages.
- **Streamlit / Gradio**: Quick to build, but limited customization and poor UX for production dashboards.
- **Retool / Appsmith**: Low-code internal tools -- fast to prototype but limited for custom workflows like document review.

### Dashboard Pages

```
/dashboard              -- Overview: recent scrape runs, system health
/dashboard/scrapes      -- Scrape run history with status, metrics
/dashboard/scrapes/:id  -- Detail view of a specific scrape run
/documents              -- Document search and browse
/documents/:id          -- Document detail with extracted data
/review                 -- Data quality review queue
/review/:id             -- Side-by-side document + data review
/exports                -- Configure and download exports
/settings/states        -- State site registry management
/settings/scrapers      -- Scraper health and configuration
```

---

## 10. API Design

### Recommendation: FastAPI

FastAPI is the clear choice for the Python backend API:
- Async support via Starlette (handles concurrent requests efficiently).
- Automatic data validation via Pydantic models.
- Auto-generated OpenAPI docs at `/docs` and `/redoc`.
- Native async database access via asyncpg.
- Dependency injection for shared resources (DB sessions, auth, etc.).

### API Endpoints Design

```
BASE URL: /api/v1

# Documents
GET    /documents                  -- Search/list documents (with filters)
GET    /documents/:id              -- Get document detail + extracted data
GET    /documents/:id/file         -- Download original document file
GET    /documents/:id/extracted    -- Get extracted data for document
PATCH  /documents/:id/extracted    -- Correct extracted data (Flow 3)

# Search
GET    /search?q=...&state=...&type=...&operator=...
       -- Full-text search across documents with faceted filters

# Wells
GET    /wells                      -- List/search wells
GET    /wells/:api_number          -- Get well by API number
GET    /wells/:api_number/documents -- Get all documents for a well

# Operators
GET    /operators                  -- List/search operators
GET    /operators/:id/documents    -- Get all documents for an operator

# Scrape Runs
GET    /scrapes                    -- List scrape runs
POST   /scrapes                    -- Trigger a new scrape run
GET    /scrapes/:id                -- Get scrape run status and metrics
DELETE /scrapes/:id                -- Cancel a running scrape

# Exports
POST   /exports                    -- Create an export job
GET    /exports/:id                -- Get export status
GET    /exports/:id/download       -- Download export file

# State Registry
GET    /states                     -- List all states with scraper status
GET    /states/:code               -- Get state detail and config
GET    /states/:code/health        -- Get scraper health for a state

# System Health
GET    /health                     -- System health check
GET    /metrics                    -- Prometheus-compatible metrics
```

### Query Parameter Patterns

```
# Filtering
GET /documents?state=TX&doc_type=production_report&operator=Devon+Energy

# Date Range
GET /documents?scraped_after=2026-01-01&scraped_before=2026-03-27

# Pagination
GET /documents?page=1&per_page=50

# Sorting
GET /documents?sort_by=scraped_at&sort_order=desc

# Full-text Search
GET /search?q=permian+basin+production&state=TX,NM

# Field Selection (for performance)
GET /documents?fields=id,doc_type,state,operator,scraped_at
```

### Authentication

For an internal tool, start simple:
- API key authentication for programmatic access.
- Session-based auth for the web dashboard.
- Consider OAuth2/OIDC integration if connecting to existing corporate identity systems.

---

## 11. Export Formats

### Supported Formats

| Format | Library        | Use Case                                    |
|--------|---------------|---------------------------------------------|
| CSV    | pandas/csv     | Universal compatibility, spreadsheet import |
| JSON   | stdlib json    | API consumers, programmatic access          |
| JSONL  | stdlib json    | Streaming, large datasets, line-by-line     |
| Excel  | openpyxl       | Business users, formatted reports           |
| Parquet| pyarrow        | Analytics tools, DuckDB, data science       |

### Implementation Approach

```python
# Export pipeline powered by DuckDB for performance
class ExportService:
    """Generate exports from PostgreSQL data via DuckDB for speed."""

    def export_csv(self, query_params, output_path):
        # DuckDB reads from PostgreSQL, writes CSV directly
        ...

    def export_excel(self, query_params, output_path):
        # openpyxl for formatted Excel with multiple sheets
        # Sheet 1: Summary statistics
        # Sheet 2: Document listing
        # Sheet 3: Extracted data
        ...

    def export_json(self, query_params, output_path):
        # Streaming JSON for large datasets
        ...

    def export_parquet(self, query_params, output_path):
        # DuckDB native Parquet export for analytics
        ...
```

### Library Recommendations

- **pandas**: Best general-purpose library for data manipulation and export. Use `df.to_csv()`, `df.to_json()`, `df.to_excel()`.
- **openpyxl**: For Excel files requiring formatting, multiple sheets, or styled headers. Used by pandas as the Excel engine.
- **XlsxWriter**: If Excel export performance is critical (faster than openpyxl for large files).
- **pyarrow**: For Parquet export -- columnar format ideal for analytics consumption.
- **DuckDB**: Can export query results directly to CSV, JSON, and Parquet with excellent performance, eliminating the need to load data into pandas first for large exports.

### Export Job Pattern

Exports are asynchronous (large datasets may take minutes):
```
User requests export --> API creates export job --> Task queue processes
                                                         |
                                                         v
                                                   Export file stored
                                                         |
                                                         v
                                                   User downloads file
```

---

## 12. Deployment Options

### Deployment Tiers

```
TIER 1: LOCAL DEVELOPMENT
  Developer laptop
  - Docker Compose: PostgreSQL + Redis + MinIO
  - Python venv or uv for application code
  - SQLite option for zero-dependency testing

TIER 2: SINGLE SERVER (Recommended Starting Point)
  VPS ($20-50/month) or dedicated server
  - Docker Compose orchestration
  - All services on one machine
  - Suitable for: initial deployment, small-medium scale
  - Providers: Hetzner ($5-20/mo), DigitalOcean ($12-48/mo), Linode

TIER 3: MULTI-SERVICE DEPLOYMENT
  Multiple containers/services
  - Docker Compose or Docker Swarm
  - Separate containers for: web, workers, scheduler, database
  - Suitable for: medium scale, better isolation

TIER 4: CLOUD/KUBERNETES
  Cloud-native deployment
  - AWS ECS/Fargate, GCP Cloud Run, or Kubernetes
  - Managed database (RDS PostgreSQL)
  - S3 for file storage
  - Suitable for: enterprise scale, high availability
```

### Recommended: Docker Compose (Tier 2)

```yaml
# docker-compose.yml (simplified)
services:
  db:
    image: postgres:18
    volumes:
      - pgdata:/var/lib/postgresql/data

  redis:
    image: redis:7-alpine

  minio:
    image: minio/minio
    command: server /data

  api:
    build: ./packages/api
    depends_on: [db, redis]

  worker:
    build: ./packages/worker
    depends_on: [db, redis, minio]

  scheduler:
    build: ./packages/scheduler
    depends_on: [db, redis]

  dashboard:
    build: ./packages/dashboard
    depends_on: [api]
```

### Docker Optimization for Scraping

- Use **multi-stage builds** to keep images small (Alpine Linux base reduces image size significantly).
- Install Playwright browsers in a separate layer (cached across builds).
- Use **connection pooling** for database connections.
- Implement **async I/O** throughout for better resource utilization.
- Benchmark from the field: optimized Docker scraping containers achieved 40% reduction in scraping time and ~$5,000/month savings on cloud infrastructure.

### Cost-Effective Hosting Options

| Provider        | Specs                    | Cost/Month | Notes                          |
|----------------|--------------------------|------------|--------------------------------|
| Hetzner CX32   | 4 vCPU, 8GB RAM, 80GB   | ~$7        | Best value, EU datacenter      |
| Hetzner CX42   | 8 vCPU, 16GB RAM, 160GB | ~$14       | Good for production             |
| DigitalOcean    | 4 vCPU, 8GB RAM         | ~$48       | Better US presence              |
| AWS Lightsail   | 4 vCPU, 16GB RAM        | ~$80       | Easy AWS integration            |
| GitHub Actions  | Free tier CI/CD          | $0         | Good for scheduled batch jobs   |

### Serverless Considerations

Serverless (AWS Lambda, Cloud Functions) is generally NOT recommended for web scraping because:
- Browser automation (Playwright) requires persistent browser instances.
- Cold starts add latency that breaks scraping workflows.
- Execution time limits (15 min on Lambda) conflict with long-running scrape jobs.
- However, serverless CAN work for: API endpoints, export generation, notification sending, and lightweight scheduled checks.

---

## 13. Monitoring & Alerting

### What to Monitor

```
SCRAPER HEALTH METRICS:
  - Pages scraped per minute (by state)
  - HTTP status code distribution (2xx, 3xx, 4xx, 5xx)
  - Request success rate (target: >95%)
  - Response latency (P50, P95, P99)
  - Documents downloaded per run
  - Documents classified per run
  - Items extracted per run
  - Null/empty field rate per extractor
  - Error rate by scraper/state

SYSTEM METRICS:
  - CPU, memory, disk usage
  - Database connection pool utilization
  - Task queue depth and processing rate
  - File storage usage

DATA QUALITY METRICS:
  - Average confidence score per document type
  - Documents flagged for review
  - Extraction failure rate
  - Data correction rate (how often humans fix extracted data)
```

### Alert Conditions

```
CRITICAL ALERTS (immediate notification):
  - Scraper success rate drops below 80% over 15 minutes
  - Database connection failures
  - File storage write failures
  - Task queue depth exceeds 10,000 (processing stalled)

WARNING ALERTS (daily digest):
  - State site returns different HTML structure (possible layout change)
  - Null/empty field rate exceeds 20% for an extractor
  - No new documents found for a state in 7+ days
  - Average confidence score drops below threshold
  - Scraper returns >5% 403/429 responses (rate limiting/blocking)

INFORMATIONAL (weekly report):
  - Summary of documents scraped per state
  - New data available notifications
  - System resource utilization trends
```

### Monitoring Stack Recommendation

**Phase 1 (Minimal -- built into the app):**
- Log all scrape metrics to PostgreSQL (scrape_runs table with JSONB metrics).
- ScrapeOps integration for Scrapy-specific monitoring (free tier available).
- Simple email/Slack alerts via the application.

**Phase 2 (Observability stack):**
- **Prometheus** for metrics collection (expose `/metrics` endpoint from FastAPI).
- **Grafana** for dashboards and alerting.
- **Loki** for log aggregation (or simpler: structured JSON logging to files).
- All three run as Docker containers alongside the application.

### Broken Scraper Detection

The most critical monitoring need for this project is detecting when a state site changes its layout, breaking the scraper. Detection strategies:

1. **Output volume monitoring**: If a scraper that normally finds 50+ documents suddenly finds 0, the site probably changed.
2. **HTML structure fingerprinting**: Hash the DOM structure of key pages; alert when the hash changes.
3. **Null field rate tracking**: A spike in null values for previously-reliable fields indicates parser breakage.
4. **Visual regression**: Screenshot comparison of state site pages across runs (using Playwright's screenshot capability).
5. **Canary documents**: Maintain a list of known documents per state; verify they are still findable after each run.

---

## 14. Cost Optimization

### Compute Optimization

1. **Delta scraping**: Only download new/changed documents. Track `Last-Modified` headers and ETags. Compute URL fingerprints to detect already-scraped pages. This alone can reduce compute by 60-80% on recurring runs.

2. **Headless browser pooling**: Reuse Playwright browser contexts across pages instead of launching new browsers. Share browser instances across multiple spider requests.

3. **Async everything**: Use asyncio throughout the pipeline. A single worker with async I/O can handle 10x the throughput of synchronous code for I/O-bound operations.

4. **Right-size workers**: Most scraping is I/O-bound, not CPU-bound. A 4-vCPU server with good network is sufficient for substantial scraping volume.

### Storage Optimization

1. **Deduplication**: SHA256 hashing prevents storing the same document twice.
2. **Compression**: Compress stored documents (gzip for text-based formats, skip for already-compressed PDFs).
3. **Tiered storage**: Keep recent documents on fast storage; archive older documents to cheaper storage.
4. **Cleanup policy**: Define retention periods for raw scrape artifacts vs. processed data.

### API Call Optimization

1. **Avoid third-party scraping APIs for government sites**: Government sites generally do not have aggressive anti-bot measures. Direct scraping with Scrapy+Playwright is cheaper than paying per-request to scraping API services.

2. **Cache responses**: Cache unchanged pages to avoid re-fetching.

3. **OCR cost management**: Use free/self-hosted Tesseract for OCR instead of paid cloud OCR services. Reserve paid OCR (Google Document AI, AWS Textract) for documents where Tesseract fails.

4. **LLM cost management**: If using LLMs for classification or extraction, batch requests and use smaller models (Claude Haiku, GPT-4o-mini) for routine classification; reserve larger models for ambiguous cases.

### Estimated Monthly Costs (Single Server Deployment)

```
COMPONENT                          COST/MONTH
Hetzner CX42 (8 vCPU, 16GB)      $14
PostgreSQL (on same server)        $0 (included)
Redis (on same server)             $0 (included)
MinIO (on same server)             $0 (included)
Domain + SSL (Let's Encrypt)       ~$1
Backups (Hetzner snapshots)        ~$3
Optional: OCR API overflow         $0-50
Optional: LLM API for classify     $0-100
                                   -----------
TOTAL                              $18-168/month
```

This compares very favorably to commercial data services that charge $10,000-$100,000+/year for O&G regulatory data.

---

## 15. Language Choice: Python vs Node.js

### Recommendation: Python (Primary) with Node.js (Frontend Only)

**Why Python for the backend/scraping/pipeline:**

| Factor                  | Python                              | Node.js                          |
|-------------------------|--------------------------------------|----------------------------------|
| Scraping ecosystem      | Scrapy, BeautifulSoup, lxml (mature)| Puppeteer, Cheerio (good)        |
| PDF parsing             | PyMuPDF, pdfplumber, Camelot        | pdf-parse (limited)              |
| OCR                     | Tesseract bindings, PaddleOCR       | Limited options                  |
| Data processing         | pandas, numpy, DuckDB               | No equivalent ecosystem          |
| ML/Classification       | scikit-learn, transformers, spaCy   | Limited ML ecosystem             |
| Browser automation      | Playwright (excellent support)       | Playwright (native, excellent)   |
| Task queues             | Celery, Dramatiq, Huey              | Bull, BullMQ                     |
| API framework           | FastAPI (excellent)                  | Express, Fastify (excellent)     |
| Database ORM            | SQLAlchemy (mature, powerful)        | Prisma, TypeORM (good)           |
| Community for scraping  | Largest and most active              | Growing but smaller              |

**Key deciding factors for Python:**
1. **PDF parsing and OCR** are critical for this project (scanned regulatory documents). Python's ecosystem here is unmatched.
2. **Data processing** with pandas and DuckDB is essential for normalization across states.
3. **Scrapy** is the most mature, battle-tested scraping framework available in any language.
4. **ML/NLP** libraries for document classification are Python-first.
5. The team likely has Python data engineering skills (O&G industry standard).

**Why Node.js/TypeScript for the frontend:**
- Next.js is the best option for the dashboard.
- TypeScript provides type safety for the UI layer.
- React ecosystem has the best component libraries for dashboards.

### Hybrid Architecture

```
PYTHON (Backend + Pipeline):
  - FastAPI (REST API)
  - Scrapy + Playwright (scraping engine)
  - Document classification and extraction
  - Task queue workers
  - Data processing and export
  - CLI tool

NODE.JS/TYPESCRIPT (Frontend Only):
  - Next.js dashboard
  - Communicates with Python backend via REST API
```

---

## 16. Monorepo Structure

### Recommendation: UV Workspaces Monorepo

UV (by Astral, the Ruff creators) has become the standard Python package manager in 2025-2026. Its workspace feature enables clean monorepo organization.

### Proposed Project Structure

```
og-doc-scraper/
|-- pyproject.toml                    # Root workspace configuration
|-- uv.lock                          # Single lockfile for all packages
|-- .python-version                  # Pin Python version
|-- docker-compose.yml               # Development environment
|-- Dockerfile                       # Multi-stage build
|
|-- packages/
|   |-- core/                        # Shared core library
|   |   |-- pyproject.toml
|   |   |-- src/og_scraper_core/
|   |   |   |-- models/             # SQLAlchemy models
|   |   |   |-- db/                 # Database connection, queries
|   |   |   |-- storage/            # File storage abstraction
|   |   |   |-- schemas/            # Pydantic schemas
|   |   |   |-- config.py           # Settings management
|   |   |   |-- constants.py        # Shared constants
|   |
|   |-- scraper/                     # Scraping engine
|   |   |-- pyproject.toml
|   |   |-- src/og_scraper/
|   |   |   |-- spiders/            # Scrapy spiders (one per state)
|   |   |   |   |-- base.py         # Base state spider
|   |   |   |   |-- texas.py
|   |   |   |   |-- oklahoma.py
|   |   |   |   |-- north_dakota.py
|   |   |   |-- pipelines/          # Scrapy item pipelines
|   |   |   |-- middlewares/         # Scrapy middlewares
|   |   |   |-- adapters/           # State-specific site adapters
|   |   |   |-- settings.py         # Scrapy settings
|   |
|   |-- classifier/                  # Document classification
|   |   |-- pyproject.toml
|   |   |-- src/og_classifier/
|   |   |   |-- classifiers/        # Per-doc-type classifiers
|   |   |   |-- models/             # ML model files
|   |   |   |-- rules/              # Rule-based classification
|   |
|   |-- extractor/                   # Data extraction
|   |   |-- pyproject.toml
|   |   |-- src/og_extractor/
|   |   |   |-- extractors/         # Per-format extractors
|   |   |   |   |-- pdf.py
|   |   |   |   |-- xlsx.py
|   |   |   |   |-- csv_ext.py
|   |   |   |   |-- html.py
|   |   |   |-- ocr/                # OCR utilities
|   |   |   |-- normalizers/        # State-specific normalizers
|   |
|   |-- api/                         # FastAPI REST API
|   |   |-- pyproject.toml
|   |   |-- src/og_api/
|   |   |   |-- routes/             # API route handlers
|   |   |   |-- middleware/         # Auth, CORS, etc.
|   |   |   |-- dependencies/      # FastAPI dependencies
|   |   |   |-- main.py            # FastAPI app entry
|   |
|   |-- worker/                      # Task queue workers
|   |   |-- pyproject.toml
|   |   |-- src/og_worker/
|   |   |   |-- tasks/             # Task definitions
|   |   |   |-- main.py            # Worker entry point
|   |
|   |-- cli/                         # CLI tool
|   |   |-- pyproject.toml
|   |   |-- src/og_cli/
|   |   |   |-- commands/          # CLI command groups
|   |   |   |-- main.py            # Typer app entry
|   |
|   |-- dashboard/                   # Next.js frontend (not a UV package)
|       |-- package.json
|       |-- src/
|       |   |-- app/               # Next.js App Router
|       |   |-- components/        # React components
|       |   |-- lib/               # API client, utilities
|
|-- migrations/                      # Alembic migrations
|   |-- alembic.ini
|   |-- versions/
|
|-- tests/                           # Integration tests
|   |-- conftest.py
|   |-- test_pipeline/
|   |-- test_api/
|
|-- data/                            # Local data storage (gitignored)
|   |-- documents/
|   |-- exports/
|
|-- config/                          # Configuration files
|   |-- states/                    # Per-state scraper configs (YAML)
|   |   |-- TX.yaml
|   |   |-- OK.yaml
|   |-- logging.yaml
```

### UV Workspace Configuration

```toml
# Root pyproject.toml
[project]
name = "og-doc-scraper"
version = "0.1.0"
requires-python = ">=3.12"

[tool.uv.workspace]
members = [
    "packages/core",
    "packages/scraper",
    "packages/classifier",
    "packages/extractor",
    "packages/api",
    "packages/worker",
    "packages/cli",
]

[tool.uv.sources]
og-scraper-core = { workspace = true }
```

### Benefits of UV Workspaces

- **Single lockfile**: All packages share one `uv.lock`, ensuring consistent dependency versions.
- **Shared virtual environment**: One `.venv` at the workspace root.
- **Editable installations**: Changes to `core` are immediately available to `scraper`, `api`, etc.
- **Independent versioning**: Each package has its own `pyproject.toml` and can be versioned separately.
- **Build isolation**: Each package can have its own dependencies without affecting others.

---

## 17. Domain-Specific Considerations

### Oil & Gas Regulatory Data Challenges

1. **Texas Railroad Commission (RRC)**: Provides bulk data downloads and a Production Data Query system. However, automated scraping is explicitly discouraged and detected. Strategy: Use bulk data downloads where available; targeted scraping only for documents not available in bulk.

2. **State site variability**: Each state has a completely different web interface. The adapter pattern (one spider class per state inheriting from a base) is essential.

3. **API number formats**: Different states use different API number formats. The API number (a 14-digit well identifier assigned by the American Petroleum Institute) should be normalized to a consistent format in the `wells` table.

4. **Rate limiting**: Government sites often have strict rate limits. Build rate limiting into each state adapter's configuration, stored in the database so it can be adjusted without code changes.

5. **Anti-scraping on government sites**: Generally minimal compared to commercial sites. Most government sites do not use CAPTCHAs or aggressive bot detection. The main risks are: IP-based rate limiting, session timeout, and structural changes to the site.

6. **Document format diversity**: PDFs (both text and scanned), Excel spreadsheets, CSV files, HTML pages, and occasionally Word documents. The extractor package needs a handler for each format.

### Data Integrity

The PRD emphasizes that "the source of truth is fuzzy and data quality is poor across the industry." The system design addresses this through:
- Per-field confidence scores on all extracted data.
- Provenance tracking (source URL, scrape timestamp, extraction version).
- Correction tracking (what was changed, by whom, when).
- Multiple extraction versions (re-extract with improved models without losing old data).

---

## 18. Recommendations Summary

### Technology Stack

```
LAYER              TECHNOLOGY           RATIONALE
---------------------------------------------------------------------------
Language           Python 3.12+         Best ecosystem for scraping, PDF, OCR, ML
Package Manager    uv                   Modern, fast, workspace support
Database           PostgreSQL 18        Relational + JSONB hybrid, FTS built-in
Cache/Broker       Redis                Task queue broker, caching, rate limiting
File Storage       Local -> MinIO -> S3 Progressive, S3-compatible throughout
Scraping           Scrapy + Playwright  Mature framework + JS rendering
Task Queue         Huey (start)         Lightweight, fast, built-in scheduling
                   Dramatiq (scale)     Modern, reliable, better middleware
Scheduling         Huey periodic (start) Integrated with task queue
                   Prefect (scale)       Dynamic workflows, observability
API Framework      FastAPI              Async, auto-docs, Pydantic validation
ORM                SQLAlchemy 2.0       Async support, mature, Alembic migrations
Search             PostgreSQL FTS (start) Zero infrastructure
                   Meilisearch (scale)   Typo-tolerant, faceted, lightweight
Analytics          DuckDB               Embedded OLAP for exports and analysis
CLI Framework      Typer                Based on Click, modern Python CLI
Frontend           Next.js 16 + shadcn  SSR dashboard, TypeScript, component libs
Monitoring         ScrapeOps + Grafana  Scraper-specific + general observability
Deployment         Docker Compose       Single-server, reproducible, scalable
Hosting            Hetzner VPS          Best price/performance for EU/US
```

### Architecture Principles

1. **CLI-first, web-second**: Build the core pipeline as a CLI tool; add the dashboard after the pipeline is solid.
2. **Progressive complexity**: Start simple (single server, PostgreSQL FTS, Huey, local files) and add complexity only when needed (Meilisearch, Prefect, MinIO).
3. **Adapter pattern**: One scraper adapter per state, inheriting from a common base. Configuration in YAML files and database.
4. **Decoupled pipeline stages**: Each stage (scrape, download, classify, extract, normalize, store) is independently retriable and scalable.
5. **Confidence-first data**: Every extracted value carries a confidence score. The system never pretends data is cleaner than it is.
6. **Full provenance**: Every piece of data traces back to a source URL, scrape timestamp, and extraction version.

### Implementation Priority

```
PHASE 1 (MVP - 4-6 weeks):
  - PostgreSQL schema + Alembic migrations
  - Core library (models, storage, config)
  - Scrapy framework with Playwright integration
  - First state adapter (Texas - highest volume)
  - Basic document download and storage
  - CLI tool for running scrapers and querying data
  - CSV/JSON export

PHASE 2 (Classification + Extraction - 4-6 weeks):
  - Document classification engine (rule-based first)
  - PDF text extraction + basic OCR
  - Spreadsheet parsing
  - Data extraction and normalization
  - Confidence scoring
  - Task queue (Huey) for async processing
  - 2-3 more state adapters

PHASE 3 (Web Dashboard - 3-4 weeks):
  - FastAPI REST API
  - Next.js dashboard (monitoring, search, browse)
  - Data quality review interface (Flow 3)
  - Export builder UI

PHASE 4 (Scale + Polish - ongoing):
  - Remaining state adapters
  - Meilisearch for better search UX
  - Prefect for workflow orchestration
  - Grafana monitoring dashboard
  - ML-based classification improvements
  - Incremental/delta scraping optimization
```

---

## Sources

### Database Selection
- [PostgreSQL vs MongoDB for Web Scraping](https://data-ox.com/comparison-postgresql-vs-mysql-vs-mongodb-for-web-scraping)
- [MySQL vs PostgreSQL vs MongoDB: Which Database to Choose 2026](https://www.hyaking.com/mysql-vs-postgresql-vs-mongodb-which-database-to-choose-2026/)
- [PostgreSQL vs MongoDB vs SQLite Comparison](https://db-engines.com/en/system/MongoDB%3BPostgreSQL%3BSQLite)
- [Building a Document Store with PostgreSQL JSONB](https://www.cloudthat.com/resources/blog/building-a-document-store-with-postgresql-jsonb)
- [7 Postgres JSONB Patterns for Semi-Structured Speed](https://medium.com/@connect.hashblock/7-postgres-jsonb-patterns-for-semi-structured-speed-69f02f727ce5)
- [PostgreSQL JSONB - Powerful Storage for Semi-Structured Data](https://www.architecture-weekly.com/p/postgresql-jsonb-powerful-storage)
- [Why DuckDB](https://duckdb.org/why_duckdb)
- [Embedded Databases and 2025 Trends](https://kestra.io/blogs/embedded-databases)

### Full-Text Search
- [Postgres Full Text Search vs Meilisearch vs Elasticsearch](https://medium.com/@simbatmotsi/postgres-full-text-search-vs-meilisearch-vs-elasticsearch-choosing-a-search-stack-that-scales-fcf17ef40a1b)
- [Full Text Search over Postgres: Elasticsearch vs Alternatives (ParadeDB)](https://www.paradedb.com/blog/elasticsearch-vs-postgres)
- [Postgres Full Text Search vs the Rest (Supabase)](https://supabase.com/blog/postgres-full-text-search-vs-the-rest)
- [When Does Postgres Stop Being Good Enough for Full Text Search (Meilisearch)](https://www.meilisearch.com/blog/postgres-full-text-search-limitations)

### Scraping Architecture
- [Scrapy Architecture Overview](https://docs.scrapy.org/en/latest/topics/architecture.html)
- [Scrapy Item Pipeline Documentation](https://docs.scrapy.org/en/latest/topics/item-pipeline.html)
- [Scrapy Playwright Tutorial (Apify)](https://blog.apify.com/scrapy-playwright/)
- [How to Build a Web Scraper with Scrapy and Playwright](https://oneuptime.com/blog/post/2026-01-21-web-scraper-scrapy-playwright/view)
- [Optimal Web Scraping Tech Stack for 2025](https://www.buzzybrains.com/blog/crafting-optimal-web-scraping-tech-stack-2025/)

### Task Queues
- [Choosing The Right Python Task Queue](https://judoscale.com/blog/choose-python-task-queue)
- [Python Background Tasks 2025: Celery vs RQ vs Dramatiq](https://devproportal.com/languages/python/python-background-tasks-celery-rq-dramatiq-comparison-2025/)
- [Exploring Python Task Queue Libraries with Load Test](https://stevenyue.com/blogs/exploring-python-task-queue-libraries-with-load-test)
- [Dramatiq Motivation](https://dramatiq.io/motivation.html)

### Scheduling
- [Python Data Pipeline Tools 2026: Airflow vs Prefect vs Dagster](https://ukdataservices.co.uk/blog/articles/python-data-pipeline-tools-2025)
- [Apache Airflow vs Prefect: 2025 Comparison](https://www.sql-datatools.com/2025/10/apache-airflow-vs-prefect-2025.html)
- [Prefect vs Airflow](https://www.prefect.io/prefect-vs-airflow)
- [Advanced Task Scheduling with Python in 2025](https://dev.to/srijan-xi/advanced-task-scheduling-and-orchestration-with-python-in-2025-4cb5)

### File Storage
- [MinIO: High-Performance S3 Compatible Object Store](https://github.com/minio/minio)
- [MinIO as a Local S3 Service](https://dev.to/stefanalfbo/minio-as-a-local-s3-service-5bp8)

### Language Choice
- [JavaScript vs Python for Web Scraping 2025 (Oxylabs)](https://oxylabs.io/blog/javascript-vs-python)
- [Python vs Node.js for Web Scraping (Scrape.do)](https://scrape.do/blog/web-scraping-python-vs-nodejs/)

### Monorepo / UV Workspaces
- [UV Workspaces Documentation](https://docs.astral.sh/uv/concepts/projects/workspaces/)
- [How to Set Up a Python Monorepo with UV Workspaces](https://pydevtools.com/handbook/how-to/how-to-set-up-a-python-monorepo-with-uv-workspaces/)
- [Python Workspaces (Monorepos)](https://tomasrepcik.dev/blog/2025/2025-10-26-python-workspaces/)
- [FOSDEM 2026 - Modern Python Monorepo with UV](https://fosdem.org/2026/schedule/event/WE7NHM-modern-python-monorepo-apache-airflow/)

### Deployment & Cost
- [5 Cheap Ways to Deploy Docker Containers (2025)](https://sliplane.io/blog/5-cheap-ways-to-deploy-docker-containers-in-2025)
- [How to Set Up a Docker-Based Web Scraping Environment](https://oneuptime.com/blog/post/2026-02-08-how-to-set-up-a-docker-based-web-scraping-environment/view)
- [How Much Does Web Scraping Cost? 2026 Pricing Guide](https://tendem.ai/blog/web-scraping-cost-pricing-guide)
- [Reduce Web Scraping Costs with Smart Infrastructure](https://soax.com/blog/reducing-scraping-costs)

### Monitoring
- [ScrapeOps - Job Monitoring & Scheduling for Web Scrapers](https://scrapeops.io/monitoring-scheduling/)
- [10 Web Scraping Best Practices 2025](https://www.scrapeunblocker.com/post/10-web-scraping-best-practices-for-developers-in-2025)

### API Design
- [FastAPI Best Practices](https://github.com/zhanymkanov/fastapi-best-practices)
- [FastAPI Documentation](https://fastapi.tiangolo.com/)

### Migrations
- [Best Practices for Alembic Schema Migration](https://www.pingcap.com/article/best-practices-alembic-schema-migration/)
- [Alembic Auto Generating Migrations](https://alembic.sqlalchemy.org/en/latest/autogenerate.html)

### Domain-Specific
- [Texas RRC Data Sets Available for Download](https://www.rrc.texas.gov/resource-center/research/data-sets-available-for-download/)
- [Texas RRC Production Data Query](https://webapps2.rrc.texas.gov/EWA/ewaPdqMain.do)
- [TXRRC Data Harvest (GitHub)](https://github.com/mlbelobraydi/TXRRC_data_harvest)
