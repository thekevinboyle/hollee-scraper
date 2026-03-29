# PostgreSQL Schema & FastAPI Backend Implementation
## Oil & Gas Document Scraper

**Research Date**: 2026-03-27
**Scope**: Complete PostgreSQL schema, PostGIS spatial queries, FastAPI API design, SQLAlchemy 2.0 async models, Alembic migrations, Docker Compose configuration
**Depends On**: [Architecture & Storage Research](./architecture-storage.md), [O&G Data Models](./og-data-models.md), [DISCOVERY.md](../DISCOVERY.md)

---

## Table of Contents

1. [PostgreSQL Schema Design](#1-postgresql-schema-design)
2. [PostGIS for Geographic Queries](#2-postgis-for-geographic-queries)
3. [FastAPI Backend Design](#3-fastapi-backend-design)
4. [SQLAlchemy 2.0 Async Models](#4-sqlalchemy-20-async-models)
5. [Alembic Migrations](#5-alembic-migrations)
6. [Docker Compose Configuration](#6-docker-compose-configuration)

---

## 1. PostgreSQL Schema Design

### 1.1 Complete Schema DDL

The schema follows a relational core with JSONB extensions for variable/state-specific data. Every entity that users search by gets its own indexed column; flexible fields live in JSONB.

```sql
-- ============================================================
-- EXTENSIONS
-- ============================================================
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "postgis";       -- spatial queries
CREATE EXTENSION IF NOT EXISTS "pg_trgm";       -- fuzzy/typo-tolerant search

-- ============================================================
-- ENUM TYPES
-- ============================================================
CREATE TYPE doc_type_enum AS ENUM (
    'well_permit',
    'completion_report',
    'production_report',
    'spacing_order',
    'pooling_order',
    'plugging_report',
    'inspection_record',
    'incident_report',
    'other'
);

CREATE TYPE document_status_enum AS ENUM (
    'discovered',
    'downloading',
    'downloaded',
    'classifying',
    'classified',
    'extracting',
    'extracted',
    'normalized',
    'stored',
    'flagged_for_review',
    'download_failed',
    'classification_failed',
    'extraction_failed'
);

CREATE TYPE scrape_job_status_enum AS ENUM (
    'pending',
    'running',
    'completed',
    'failed',
    'cancelled'
);

CREATE TYPE review_status_enum AS ENUM (
    'pending',
    'approved',
    'rejected',
    'corrected'
);

CREATE TYPE well_status_enum AS ENUM (
    'active',
    'inactive',
    'plugged',
    'permitted',
    'drilling',
    'completed',
    'shut_in',
    'temporarily_abandoned',
    'unknown'
);

-- ============================================================
-- TABLE: states
-- ============================================================
-- Reference table for the 10 supported states.
-- Tier determines scraping priority.
CREATE TABLE states (
    code            VARCHAR(2)   PRIMARY KEY,          -- e.g. 'TX', 'NM'
    name            VARCHAR(100) NOT NULL,              -- e.g. 'Texas'
    api_state_code  VARCHAR(2)   NOT NULL UNIQUE,       -- API numeric code, e.g. '42' for TX
    tier            SMALLINT     NOT NULL DEFAULT 1,    -- 1 = Tier 1, 2 = Tier 2
    last_scraped_at TIMESTAMPTZ,
    config          JSONB        NOT NULL DEFAULT '{}', -- state-specific scraper config
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

-- ============================================================
-- TABLE: operators
-- ============================================================
-- Normalized operator entities. An operator may appear under
-- different names/spellings across states and documents.
CREATE TABLE operators (
    id              UUID         PRIMARY KEY DEFAULT uuid_generate_v4(),
    name            VARCHAR(500) NOT NULL,              -- canonical/display name
    normalized_name VARCHAR(500) NOT NULL,              -- lowercase, stripped for matching
    aliases         JSONB        NOT NULL DEFAULT '[]', -- ["DEVON ENERGY CORP", "DEVON ENERGY CORPORATION"]
    state_operator_ids JSONB     NOT NULL DEFAULT '{}', -- {"TX": "123456", "OK": "789012"}
    metadata        JSONB        NOT NULL DEFAULT '{}', -- any extra info
    search_vector   TSVECTOR,                           -- full-text search
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

-- ============================================================
-- TABLE: wells
-- ============================================================
-- One row per physical well. API number is the primary business
-- identifier. Supports 10-14 digit variations stored as a
-- VARCHAR(14) with leading zeros preserved. A separate column
-- holds the normalized 14-digit form for consistent lookups.
CREATE TABLE wells (
    id              UUID         PRIMARY KEY DEFAULT uuid_generate_v4(),
    api_number      VARCHAR(14)  NOT NULL,              -- stored without dashes, e.g. '42501201300300'
    api_10          VARCHAR(10)  GENERATED ALWAYS AS (LEFT(api_number, 10)) STORED,  -- first 10 digits
    well_name       VARCHAR(500),
    well_number     VARCHAR(100),
    operator_id     UUID         REFERENCES operators(id) ON DELETE SET NULL,
    state_code      VARCHAR(2)   NOT NULL REFERENCES states(code),
    county          VARCHAR(255),
    basin           VARCHAR(255),
    field_name      VARCHAR(255),
    lease_name      VARCHAR(500),
    -- Location: both simple floats AND PostGIS geometry for flexibility
    latitude        DOUBLE PRECISION,
    longitude       DOUBLE PRECISION,
    location        GEOMETRY(Point, 4326),              -- PostGIS point, SRID 4326 = WGS84
    -- Well details
    well_status     well_status_enum DEFAULT 'unknown',
    well_type       VARCHAR(50),                        -- 'oil', 'gas', 'injection', 'disposal', etc.
    spud_date       DATE,
    completion_date DATE,
    total_depth     INTEGER,                            -- feet
    true_vertical_depth INTEGER,                        -- feet
    lateral_length  INTEGER,                            -- feet (horizontal wells)
    -- Flexible/state-specific data
    metadata        JSONB        NOT NULL DEFAULT '{}', -- state-specific fields, permit numbers, etc.
    alternate_ids   JSONB        NOT NULL DEFAULT '{}', -- {"permit_number": "...", "rrc_lease_id": "..."}
    -- Search
    search_vector   TSVECTOR,
    -- Timestamps
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),

    -- Unique constraint: API number should be unique, but some states
    -- reuse short API numbers with different sidetrack/event codes.
    -- Use the full api_number + state_code as the uniqueness key.
    CONSTRAINT uq_wells_api_state UNIQUE (api_number, state_code)
);

-- ============================================================
-- TABLE: documents
-- ============================================================
-- Every scraped document (PDF, XLSX, CSV, HTML).
-- Provenance tracked via source_url, scrape_job_id, scraped_at.
CREATE TABLE documents (
    id              UUID            PRIMARY KEY DEFAULT uuid_generate_v4(),
    well_id         UUID            REFERENCES wells(id) ON DELETE SET NULL,
    state_code      VARCHAR(2)      NOT NULL REFERENCES states(code),
    scrape_job_id   UUID,           -- FK added after scrape_jobs table created
    doc_type        doc_type_enum   NOT NULL DEFAULT 'other',
    status          document_status_enum NOT NULL DEFAULT 'discovered',
    -- Provenance
    source_url      TEXT            NOT NULL,
    file_path       TEXT,                                -- local filesystem path
    file_hash       VARCHAR(64)     UNIQUE,              -- SHA-256 for deduplication
    file_format     VARCHAR(20),                         -- 'pdf', 'xlsx', 'csv', 'html'
    file_size_bytes BIGINT,
    -- Confidence
    confidence_score NUMERIC(5,4),                       -- 0.0000 to 1.0000 document-level
    ocr_confidence   NUMERIC(5,4),                       -- OCR-specific confidence
    -- Classification
    classification_method VARCHAR(50),                   -- 'rule_based', 'ocr_keyword', 'manual'
    -- Dates
    document_date   DATE,                                -- date ON the document (permit date, report period, etc.)
    scraped_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    processed_at    TIMESTAMPTZ,
    -- Flexible metadata
    raw_metadata    JSONB           NOT NULL DEFAULT '{}', -- original scrape metadata
    -- Search
    search_vector   TSVECTOR,
    -- Timestamps
    created_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);

-- ============================================================
-- TABLE: extracted_data
-- ============================================================
-- Structured data extracted from documents. One document may have
-- multiple extracted_data rows (e.g., a production report yields
-- one row per month of production data). The `data` JSONB column
-- holds the actual fields, which vary by doc_type.
CREATE TABLE extracted_data (
    id              UUID         PRIMARY KEY DEFAULT uuid_generate_v4(),
    document_id     UUID         NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    well_id         UUID         REFERENCES wells(id) ON DELETE SET NULL,
    data_type       VARCHAR(50)  NOT NULL,              -- 'production', 'permit', 'completion', etc.
    -- The actual extracted data — flexible per doc_type
    data            JSONB        NOT NULL DEFAULT '{}',
    -- Per-field confidence scores
    -- e.g. {"oil_production": 0.95, "gas_production": 0.87, "operator_name": 0.99}
    field_confidence JSONB       NOT NULL DEFAULT '{}',
    -- Overall extraction confidence for this record
    confidence_score NUMERIC(5,4),
    -- Extraction provenance
    extractor_used  VARCHAR(100),                       -- 'paddleocr', 'tabula', 'regex', 'manual'
    extraction_version VARCHAR(20),                     -- version of the extraction logic
    -- Dates
    reporting_period_start DATE,                        -- for production data: start of period
    reporting_period_end   DATE,                        -- for production data: end of period
    extracted_at    TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    -- Timestamps
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

-- ============================================================
-- TABLE: review_queue
-- ============================================================
-- Items flagged for human review due to low confidence scores
-- or extraction anomalies. Addresses D10 (strict rejection)
-- and D15 (review queue in dashboard).
CREATE TABLE review_queue (
    id              UUID             PRIMARY KEY DEFAULT uuid_generate_v4(),
    document_id     UUID             NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    extracted_data_id UUID           REFERENCES extracted_data(id) ON DELETE CASCADE,
    -- Review details
    status          review_status_enum NOT NULL DEFAULT 'pending',
    reason          TEXT             NOT NULL,           -- why flagged: 'low_confidence', 'ocr_quality', 'anomaly', etc.
    flag_details    JSONB            NOT NULL DEFAULT '{}', -- specific fields/values that triggered the flag
    -- Confidence info at time of flagging
    document_confidence NUMERIC(5,4),
    field_confidences   JSONB        DEFAULT '{}',      -- snapshot of per-field confidence
    -- Resolution
    reviewed_by     VARCHAR(100),                        -- who reviewed (no auth, just a name)
    reviewed_at     TIMESTAMPTZ,
    corrections     JSONB            DEFAULT '{}',       -- {"field_name": {"old": "...", "new": "..."}}
    notes           TEXT,
    -- Timestamps
    created_at      TIMESTAMPTZ      NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ      NOT NULL DEFAULT NOW()
);

-- ============================================================
-- TABLE: scrape_jobs
-- ============================================================
-- Tracks on-demand scrape jobs triggered from the dashboard.
-- One job per scrape invocation (could be one state or all states).
CREATE TABLE scrape_jobs (
    id              UUID                PRIMARY KEY DEFAULT uuid_generate_v4(),
    state_code      VARCHAR(2)          REFERENCES states(code),  -- NULL = all states
    -- Job metadata
    status          scrape_job_status_enum NOT NULL DEFAULT 'pending',
    job_type        VARCHAR(50)         NOT NULL DEFAULT 'full', -- 'full', 'incremental', 'targeted'
    parameters      JSONB               NOT NULL DEFAULT '{}',   -- filters, date range, etc.
    -- Progress tracking
    total_documents     INTEGER         DEFAULT 0,
    documents_found     INTEGER         DEFAULT 0,
    documents_downloaded INTEGER        DEFAULT 0,
    documents_processed INTEGER         DEFAULT 0,
    documents_failed    INTEGER         DEFAULT 0,
    -- Timing
    started_at      TIMESTAMPTZ,
    finished_at     TIMESTAMPTZ,
    -- Error tracking
    errors          JSONB               NOT NULL DEFAULT '[]',   -- [{url, error, timestamp}, ...]
    -- Timestamps
    created_at      TIMESTAMPTZ         NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ         NOT NULL DEFAULT NOW()
);

-- Add the FK from documents to scrape_jobs now that both tables exist
ALTER TABLE documents
    ADD CONSTRAINT fk_documents_scrape_job
    FOREIGN KEY (scrape_job_id) REFERENCES scrape_jobs(id) ON DELETE SET NULL;

-- ============================================================
-- TABLE: data_corrections
-- ============================================================
-- Audit trail for manual corrections made via the review queue.
-- Supports learning from corrections over time.
CREATE TABLE data_corrections (
    id                UUID        PRIMARY KEY DEFAULT uuid_generate_v4(),
    extracted_data_id UUID        NOT NULL REFERENCES extracted_data(id) ON DELETE CASCADE,
    review_queue_id   UUID        REFERENCES review_queue(id) ON DELETE SET NULL,
    field_path        VARCHAR(255) NOT NULL,             -- JSON path to the corrected field
    old_value         JSONB,
    new_value         JSONB        NOT NULL,
    corrected_by      VARCHAR(100),
    corrected_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    created_at        TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);
```

### 1.2 API Number Storage Strategy

API numbers present unique challenges because they appear in 10, 12, and 14-digit formats across different state systems. The schema handles this as follows:

```
Storage Strategy:
  - api_number VARCHAR(14): stores the longest known form, zero-padded, no dashes
  - api_10 VARCHAR(10) GENERATED ALWAYS: auto-computed first 10 digits for cross-referencing
  - All searches match against BOTH api_number (exact) and api_10 (prefix match)
  - Dashes are stripped on input; display formatting is handled in the API layer
```

**Why VARCHAR, not INTEGER**: API numbers have leading zeros (state code '02' = Alaska), and some states have non-numeric suffixes. VARCHAR preserves the original format and avoids silent data loss.

**Normalization on insert**: The application layer normalizes API numbers before storage:
- Strip all dashes and spaces
- Zero-pad to at least 10 digits
- If fewer than 14 digits, right-pad with zeros only when the sidetrack/event code is truly unknown (otherwise leave as-is)

### 1.3 Location Storage Strategy

The schema stores location data in three forms to balance simplicity and capability:

| Column | Type | Purpose |
|--------|------|---------|
| `latitude` | DOUBLE PRECISION | Simple queries, CSV export, human-readable |
| `longitude` | DOUBLE PRECISION | Simple queries, CSV export, human-readable |
| `location` | GEOMETRY(Point, 4326) | Spatial indexing, bounding box queries, distance calculations |

The `location` column is populated from lat/long on insert via a trigger (see section 1.6). This dual storage means simple queries can skip PostGIS entirely while map/spatial queries get full index support.

### 1.4 JSONB Column Patterns

Each JSONB column serves a specific purpose:

| Table.Column | Contains | Example |
|-------------|----------|---------|
| `wells.metadata` | State-specific well attributes | `{"formation": "Wolfcamp", "pool": "Spraberry", "abstract": "A-1234"}` |
| `wells.alternate_ids` | Non-API identifiers | `{"permit_number": "DP-2024-001", "rrc_lease_id": "12345", "state_well_id": "W-789"}` |
| `operators.aliases` | Name variations | `["DEVON ENERGY CORP", "DEVON ENERGY CORPORATION", "DEVON ENERGY PRODUCTION CO"]` |
| `operators.state_operator_ids` | Per-state operator numbers | `{"TX": "123456", "OK": "789012", "NM": "445566"}` |
| `documents.raw_metadata` | Original scrape metadata | `{"page_count": 3, "form_number": "W-1", "scraper_version": "1.2.0"}` |
| `extracted_data.data` | Extracted fields (varies by doc_type) | See examples below |
| `extracted_data.field_confidence` | Per-field confidence | `{"oil_bbl": 0.97, "gas_mcf": 0.92, "operator": 0.85}` |
| `review_queue.flag_details` | Why flagged | `{"low_fields": ["operator", "api_number"], "ocr_quality": "poor"}` |
| `scrape_jobs.parameters` | Job configuration | `{"date_range": ["2025-01-01", "2025-12-31"], "doc_types": ["production_report"]}` |

**Extracted data JSONB examples by doc_type**:

```json
// data_type = 'production'
{
    "reporting_month": "2025-06",
    "oil_bbl": 1250,
    "gas_mcf": 3400,
    "water_bbl": 890,
    "days_produced": 30,
    "well_status": "producing",
    "disposition": {"sold": 1200, "used_on_lease": 50},
    "casinghead_gas_mcf": 150
}

// data_type = 'permit'
{
    "permit_number": "DP-2025-00456",
    "permit_date": "2025-03-15",
    "permit_type": "new_drill",
    "proposed_depth": 12000,
    "target_formation": "Wolfcamp A",
    "surface_location": {
        "section": 8,
        "township": "2N",
        "range": "1E",
        "meridian": "6th PM",
        "quarter_quarter": "NW/4 of NE/4"
    },
    "casing_program": [
        {"type": "surface", "size": "13-3/8", "depth": 500},
        {"type": "intermediate", "size": "9-5/8", "depth": 8000},
        {"type": "production", "size": "5-1/2", "depth": 12000}
    ]
}

// data_type = 'completion'
{
    "completion_date": "2025-06-01",
    "total_depth_md": 22500,
    "total_depth_tvd": 10200,
    "lateral_length": 10000,
    "formation_completed": "Wolfcamp A",
    "frac_stages": 45,
    "proppant_lbs": 12000000,
    "fluid_bbl": 350000,
    "ip_oil_bbl": 1200,
    "ip_gas_mcf": 2500,
    "ip_water_bbl": 3000,
    "perforations": [
        {"top": 12500, "bottom": 22500, "shots_per_foot": 6}
    ]
}
```

### 1.5 Indexing Strategy

```sql
-- ============================================================
-- INDEXES: wells
-- ============================================================
-- API number lookups (the #1 search pattern in O&G)
CREATE INDEX idx_wells_api_number ON wells(api_number);
CREATE INDEX idx_wells_api_10 ON wells(api_10);
-- Trigram index for fuzzy API number search (handles partial input)
CREATE INDEX idx_wells_api_trgm ON wells USING GIN (api_number gin_trgm_ops);
-- Operator lookups
CREATE INDEX idx_wells_operator ON wells(operator_id);
-- State + county (common filter combination)
CREATE INDEX idx_wells_state_county ON wells(state_code, county);
-- Well status filter
CREATE INDEX idx_wells_status ON wells(well_status);
-- Lease name search (trigram for fuzzy matching)
CREATE INDEX idx_wells_lease_trgm ON wells USING GIN (lease_name gin_trgm_ops);
-- PostGIS spatial index (for map bounding box queries)
CREATE INDEX idx_wells_location_gist ON wells USING GIST (location);
-- Full-text search
CREATE INDEX idx_wells_search ON wells USING GIN (search_vector);
-- JSONB GIN index for metadata queries
CREATE INDEX idx_wells_metadata_gin ON wells USING GIN (metadata jsonb_path_ops);
CREATE INDEX idx_wells_alt_ids_gin ON wells USING GIN (alternate_ids jsonb_path_ops);

-- ============================================================
-- INDEXES: documents
-- ============================================================
-- State + doc_type (common filter combination)
CREATE INDEX idx_documents_state_type ON documents(state_code, doc_type);
-- Well association
CREATE INDEX idx_documents_well ON documents(well_id);
-- Deduplication by file hash
-- (already UNIQUE constraint, which creates an index)
-- Scrape job tracking
CREATE INDEX idx_documents_scrape_job ON documents(scrape_job_id);
-- Date range queries
CREATE INDEX idx_documents_date ON documents(document_date);
CREATE INDEX idx_documents_scraped_at ON documents(scraped_at);
-- Status filtering
CREATE INDEX idx_documents_status ON documents(status);
-- Source URL for provenance lookups
CREATE INDEX idx_documents_source_url ON documents USING HASH (source_url);
-- Full-text search
CREATE INDEX idx_documents_search ON documents USING GIN (search_vector);
-- JSONB metadata
CREATE INDEX idx_documents_metadata_gin ON documents USING GIN (raw_metadata jsonb_path_ops);

-- ============================================================
-- INDEXES: extracted_data
-- ============================================================
-- Document association
CREATE INDEX idx_extracted_document ON extracted_data(document_id);
-- Well association (for well-centric queries)
CREATE INDEX idx_extracted_well ON extracted_data(well_id);
-- Data type filtering
CREATE INDEX idx_extracted_data_type ON extracted_data(data_type);
-- Reporting period range queries (production data)
CREATE INDEX idx_extracted_period ON extracted_data(reporting_period_start, reporting_period_end);
-- JSONB GIN on the data column (enables queries into extracted fields)
CREATE INDEX idx_extracted_data_gin ON extracted_data USING GIN (data jsonb_path_ops);
-- JSONB GIN on field_confidence (find low-confidence fields)
CREATE INDEX idx_extracted_confidence_gin ON extracted_data USING GIN (field_confidence jsonb_path_ops);

-- ============================================================
-- INDEXES: review_queue
-- ============================================================
-- Status filtering (primary query: "show me pending reviews")
CREATE INDEX idx_review_status ON review_queue(status);
-- Document association
CREATE INDEX idx_review_document ON review_queue(document_id);
-- Date ordering
CREATE INDEX idx_review_created ON review_queue(created_at);

-- ============================================================
-- INDEXES: scrape_jobs
-- ============================================================
-- Status filtering
CREATE INDEX idx_scrape_jobs_status ON scrape_jobs(status);
-- State filtering
CREATE INDEX idx_scrape_jobs_state ON scrape_jobs(state_code);

-- ============================================================
-- INDEXES: operators
-- ============================================================
-- Normalized name for matching
CREATE INDEX idx_operators_normalized ON operators(normalized_name);
-- Trigram for fuzzy operator name search
CREATE INDEX idx_operators_name_trgm ON operators USING GIN (name gin_trgm_ops);
-- Full-text search
CREATE INDEX idx_operators_search ON operators USING GIN (search_vector);
-- JSONB GIN on aliases (find operator by any known name)
CREATE INDEX idx_operators_aliases_gin ON operators USING GIN (aliases jsonb_path_ops);
```

### 1.6 Full-Text Search Setup

```sql
-- ============================================================
-- FULL-TEXT SEARCH: tsvector triggers
-- ============================================================

-- Wells: search by well name, lease name, county, basin, operator name, API number
CREATE OR REPLACE FUNCTION wells_search_update() RETURNS trigger AS $$
BEGIN
    NEW.search_vector :=
        setweight(to_tsvector('english', COALESCE(NEW.api_number, '')), 'A') ||
        setweight(to_tsvector('english', COALESCE(NEW.well_name, '')), 'A') ||
        setweight(to_tsvector('english', COALESCE(NEW.lease_name, '')), 'B') ||
        setweight(to_tsvector('english', COALESCE(NEW.county, '')), 'C') ||
        setweight(to_tsvector('english', COALESCE(NEW.basin, '')), 'C') ||
        setweight(to_tsvector('english', COALESCE(NEW.field_name, '')), 'C');
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_wells_search_update
    BEFORE INSERT OR UPDATE OF api_number, well_name, lease_name, county, basin, field_name
    ON wells
    FOR EACH ROW EXECUTE FUNCTION wells_search_update();

-- Wells: auto-populate PostGIS location from lat/long
CREATE OR REPLACE FUNCTION wells_location_update() RETURNS trigger AS $$
BEGIN
    IF NEW.latitude IS NOT NULL AND NEW.longitude IS NOT NULL THEN
        NEW.location := ST_SetSRID(ST_MakePoint(NEW.longitude, NEW.latitude), 4326);
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_wells_location_update
    BEFORE INSERT OR UPDATE OF latitude, longitude
    ON wells
    FOR EACH ROW EXECUTE FUNCTION wells_location_update();

-- Operators: search by name and aliases
CREATE OR REPLACE FUNCTION operators_search_update() RETURNS trigger AS $$
DECLARE
    alias_text TEXT := '';
    alias_val JSONB;
BEGIN
    -- Concatenate all aliases into a searchable string
    IF NEW.aliases IS NOT NULL AND jsonb_array_length(NEW.aliases) > 0 THEN
        SELECT string_agg(elem::TEXT, ' ')
        INTO alias_text
        FROM jsonb_array_elements_text(NEW.aliases) AS elem;
    END IF;

    NEW.search_vector :=
        setweight(to_tsvector('english', COALESCE(NEW.name, '')), 'A') ||
        setweight(to_tsvector('english', COALESCE(NEW.normalized_name, '')), 'A') ||
        setweight(to_tsvector('english', COALESCE(alias_text, '')), 'B');
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_operators_search_update
    BEFORE INSERT OR UPDATE OF name, normalized_name, aliases
    ON operators
    FOR EACH ROW EXECUTE FUNCTION operators_search_update();

-- Documents: search by metadata, doc type, state
CREATE OR REPLACE FUNCTION documents_search_update() RETURNS trigger AS $$
BEGIN
    NEW.search_vector :=
        setweight(to_tsvector('english', COALESCE(NEW.doc_type::TEXT, '')), 'A') ||
        setweight(to_tsvector('english', COALESCE(NEW.state_code, '')), 'B') ||
        setweight(to_tsvector('english', COALESCE(NEW.raw_metadata->>'operator', '')), 'B') ||
        setweight(to_tsvector('english', COALESCE(NEW.raw_metadata->>'well_name', '')), 'B') ||
        setweight(to_tsvector('english', COALESCE(NEW.raw_metadata->>'lease_name', '')), 'C') ||
        setweight(to_tsvector('english', COALESCE(NEW.raw_metadata->>'county', '')), 'C');
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_documents_search_update
    BEFORE INSERT OR UPDATE OF doc_type, state_code, raw_metadata
    ON documents
    FOR EACH ROW EXECUTE FUNCTION documents_search_update();
```

### 1.7 Confidence Score Design

Three-level confidence scoring per D23:

```
Level 1 — OCR Confidence:
  documents.ocr_confidence  (NUMERIC 0-1)
  Set by PaddleOCR during text extraction.
  Represents how confident OCR is in the raw text output.

Level 2 — Field Confidence:
  extracted_data.field_confidence  (JSONB)
  Per-field scores set by the extraction engine.
  Each extracted value gets its own confidence.
  Example: {"oil_bbl": 0.97, "operator_name": 0.65}

Level 3 — Document Confidence:
  documents.confidence_score  (NUMERIC 0-1)
  Aggregate score computed from OCR confidence + average field confidence.
  Used for the review queue threshold.
```

**Threshold logic** (implemented in application layer):

```python
CONFIDENCE_THRESHOLD = 0.80  # configurable

def should_flag_for_review(document_confidence: float, field_confidences: dict) -> tuple[bool, str]:
    """Determine if a document should be sent to the review queue."""
    # Flag if document-level confidence is below threshold
    if document_confidence < CONFIDENCE_THRESHOLD:
        return True, "low_document_confidence"

    # Flag if ANY field has confidence below a stricter threshold
    low_fields = [
        field for field, conf in field_confidences.items()
        if conf < CONFIDENCE_THRESHOLD
    ]
    if low_fields:
        return True, f"low_field_confidence: {', '.join(low_fields)}"

    return False, ""
```

### 1.8 Document Provenance Tracking

Every document has a complete provenance chain:

```
documents.source_url     — the URL the document was scraped from
documents.file_hash      — SHA-256 hash for deduplication and integrity
documents.file_path      — local filesystem path (data/{state}/{operator}/{doc_type}/{filename})
documents.scraped_at     — when the document was downloaded
documents.scrape_job_id  — which scrape job found it
documents.raw_metadata   — any metadata from the scrape (HTTP headers, page context, etc.)

extracted_data.extractor_used        — which tool extracted the data
extracted_data.extraction_version    — version of the extraction logic
extracted_data.extracted_at          — when extraction happened

data_corrections.*       — full audit trail of any manual corrections
```

---

## 2. PostGIS for Geographic Queries

### 2.1 When to Use PostGIS vs Simple Lat/Long

| Query Type | Use Simple Float | Use PostGIS |
|-----------|------------------|-------------|
| Display lat/long values | Yes | No |
| CSV/JSON export | Yes | No |
| Filter by state/county | Yes (use text columns) | No |
| "Show wells near coordinates" | No | Yes (ST_DWithin) |
| "Wells within map viewport" | No | Yes (ST_MakeEnvelope + &&) |
| "Find nearest 10 wells" | No | Yes (ORDER BY geom <-> point) |
| "Wells within 5 miles of a point" | No | Yes (ST_DWithin with distance) |
| "Calculate acreage of a lease" | No | Yes (ST_Area) |

**For this project**: The map feature (D13) requires bounding box queries for the viewport, making PostGIS essential. However, simple lat/long columns are kept for easy export and human readability.

### 2.2 Spatial Indexing for Map Queries

The GiST index on `wells.location` enables efficient bounding box queries used when the map viewport changes:

```sql
-- Bounding box query: wells visible in the current map viewport
-- This is the primary map query, called on every pan/zoom
SELECT
    w.id,
    w.api_number,
    w.well_name,
    w.operator_id,
    o.name AS operator_name,
    w.latitude,
    w.longitude,
    w.well_status,
    w.well_type
FROM wells w
LEFT JOIN operators o ON w.operator_id = o.id
WHERE w.location && ST_MakeEnvelope(
    :min_lng,   -- west boundary
    :min_lat,   -- south boundary
    :max_lng,   -- east boundary
    :max_lat,   -- north boundary
    4326        -- SRID = WGS84
)
ORDER BY w.api_number
LIMIT :limit;
```

**Performance notes**:
- The `&&` operator uses the GiST index for a bounding-box-only check (no full geometry computation), making it extremely fast.
- For a dataset of ~500K wells, this query returns in <10ms with a GiST index.
- ST_MakeEnvelope constructs the rectangle from the map viewport coordinates.
- LIMIT prevents returning too many results when zoomed out; the frontend should cluster wells at low zoom levels.

### 2.3 Distance Queries and Geo-Filtering

```sql
-- Find wells within 5 miles of a point
-- ST_DWithin uses the spatial index and is much faster than ST_Distance < X
SELECT
    w.id,
    w.api_number,
    w.well_name,
    ST_Distance(
        w.location::geography,
        ST_SetSRID(ST_MakePoint(:lng, :lat), 4326)::geography
    ) AS distance_meters
FROM wells w
WHERE ST_DWithin(
    w.location::geography,
    ST_SetSRID(ST_MakePoint(:lng, :lat), 4326)::geography,
    8046.72  -- 5 miles in meters
)
ORDER BY distance_meters
LIMIT 50;

-- Find the 10 nearest wells to a point (KNN search)
-- The <-> operator uses the GiST index for efficient nearest-neighbor
SELECT
    w.id,
    w.api_number,
    w.well_name,
    w.location <-> ST_SetSRID(ST_MakePoint(:lng, :lat), 4326) AS distance
FROM wells w
WHERE w.location IS NOT NULL
ORDER BY w.location <-> ST_SetSRID(ST_MakePoint(:lng, :lat), 4326)
LIMIT 10;
```

### 2.4 PostGIS Docker Setup

See Section 6 for the complete Docker Compose configuration. The key points:

- Use the official `postgis/postgis:17-3.5` Docker image (PostGIS 3.5 on PostgreSQL 17).
- PostGIS extension is enabled in the initial migration (`CREATE EXTENSION IF NOT EXISTS postgis`).
- No additional configuration is needed beyond the standard PostgreSQL setup.
- SRID 4326 (WGS84) is the standard for GPS coordinates and is used throughout.

---

## 3. FastAPI Backend Design

### 3.1 API Endpoint Structure

```
BASE URL: http://localhost:8000/api/v1

============================================================
WELLS
============================================================
GET  /wells                     Search/filter/paginate wells
     Query params:
       q           (str)    — full-text search across all well fields
       api_number  (str)    — exact or prefix match on API number
       state       (str)    — state code filter (e.g., TX)
       county      (str)    — county name filter
       operator    (str)    — operator name (fuzzy match)
       lease_name  (str)    — lease name (fuzzy match)
       well_status (str)    — filter by status enum
       well_type   (str)    — filter by type
       page        (int)    — page number (default 1)
       page_size   (int)    — results per page (default 50, max 200)
       sort_by     (str)    — field to sort by (default: api_number)
       sort_dir    (str)    — asc or desc
     Response: Paginated list of WellSummary objects

GET  /wells/{api_number}        Well detail with associated documents
     Path params:
       api_number  (str)    — 10-14 digit API number (dashes optional)
     Response: WellDetail with nested documents and extracted_data

============================================================
DOCUMENTS
============================================================
GET  /documents                 Search/filter/paginate documents
     Query params:
       q           (str)    — full-text search
       well_id     (uuid)   — filter by well
       state       (str)    — state code filter
       doc_type    (str)    — document type enum filter
       date_from   (date)   — document date range start
       date_to     (date)   — document date range end
       min_confidence (float) — minimum confidence score
       status      (str)    — document status filter
       page, page_size, sort_by, sort_dir — pagination/sorting
     Response: Paginated list of DocumentSummary objects

GET  /documents/{id}            Document detail with extracted data
     Response: DocumentDetail with nested extracted_data records

GET  /documents/{id}/file       Serve the original document file
     Response: FileResponse (PDF, XLSX, etc.) with appropriate Content-Type

============================================================
SCRAPING
============================================================
POST /scrape                    Trigger a new scrape job
     Body: { state_code?: str, job_type: str, parameters?: object }
     Response: ScrapeJob with job ID

GET  /scrape/jobs               List scrape jobs with status
     Query params:
       status      (str)    — filter by job status
       state       (str)    — filter by state
       page, page_size
     Response: Paginated list of ScrapeJobSummary

GET  /scrape/jobs/{id}          Detailed job status with progress
     Response: ScrapeJobDetail with progress counters and error list

GET  /scrape/jobs/{id}/events   SSE stream for real-time progress
     Response: text/event-stream with progress events
     Events: { type: "progress"|"document"|"error"|"complete", data: ... }

============================================================
REVIEW QUEUE
============================================================
GET  /review                    List items needing review
     Query params:
       status      (str)    — filter by review status (default: 'pending')
       state       (str)    — filter by state
       doc_type    (str)    — filter by document type
       page, page_size
     Response: Paginated list of ReviewQueueItem

GET  /review/{id}               Review item detail with document + extracted data
     Response: ReviewItemDetail with document, extracted_data, and original file URL

PATCH /review/{id}              Approve, reject, or correct a review item
     Body: {
       status: "approved"|"rejected"|"corrected",
       corrections?: { field_name: { old: any, new: any } },
       notes?: str,
       reviewed_by?: str
     }
     Response: Updated ReviewItemDetail

============================================================
MAP
============================================================
GET  /map/wells                 Wells within a bounding box (for map viewport)
     Query params:
       min_lat     (float)  — south boundary
       max_lat     (float)  — north boundary
       min_lng     (float)  — west boundary
       max_lng     (float)  — east boundary
       well_status (str)    — optional status filter
       well_type   (str)    — optional type filter
       limit       (int)    — max results (default 1000)
     Response: List of WellMapPoint (minimal fields for pin rendering)

============================================================
STATISTICS / DASHBOARD
============================================================
GET  /stats                     Dashboard statistics
     Response: {
       total_wells, total_documents, total_extracted,
       documents_by_state, documents_by_type,
       wells_by_status, recent_scrape_jobs,
       review_queue_pending_count, avg_confidence
     }

GET  /stats/state/{state_code}  Per-state statistics
     Response: State-specific breakdown

============================================================
EXPORT
============================================================
GET  /export/wells              Export wells data
     Query params:
       format      (str)    — 'csv' or 'json'
       (all well filter params from GET /wells)
     Response: StreamingResponse with Content-Disposition attachment

GET  /export/production         Export production data
     Query params:
       format      (str)    — 'csv' or 'json'
       well_id, state, date_from, date_to, etc.
     Response: StreamingResponse with Content-Disposition attachment
```

### 3.2 Pydantic Models for Request/Response Validation

```python
# ============================================================
# schemas.py — Pydantic models for API request/response
# ============================================================
from datetime import date, datetime
from enum import Enum
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, Field, ConfigDict


# ---- Enums ----

class DocType(str, Enum):
    WELL_PERMIT = "well_permit"
    COMPLETION_REPORT = "completion_report"
    PRODUCTION_REPORT = "production_report"
    SPACING_ORDER = "spacing_order"
    POOLING_ORDER = "pooling_order"
    PLUGGING_REPORT = "plugging_report"
    INSPECTION_RECORD = "inspection_record"
    INCIDENT_REPORT = "incident_report"
    OTHER = "other"

class WellStatus(str, Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    PLUGGED = "plugged"
    PERMITTED = "permitted"
    DRILLING = "drilling"
    COMPLETED = "completed"
    SHUT_IN = "shut_in"
    TEMPORARILY_ABANDONED = "temporarily_abandoned"
    UNKNOWN = "unknown"

class ReviewStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    CORRECTED = "corrected"

class ScrapeJobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

class SortDirection(str, Enum):
    ASC = "asc"
    DESC = "desc"


# ---- Pagination ----

class PaginationParams(BaseModel):
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=50, ge=1, le=200)

class PaginatedResponse(BaseModel):
    """Generic paginated response wrapper."""
    items: list[Any]
    total: int
    page: int
    page_size: int
    total_pages: int


# ---- Wells ----

class WellSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    api_number: str
    well_name: Optional[str]
    operator_name: Optional[str]        # joined from operators table
    state_code: str
    county: Optional[str]
    well_status: Optional[WellStatus]
    well_type: Optional[str]
    latitude: Optional[float]
    longitude: Optional[float]
    document_count: Optional[int] = 0   # computed

class WellDetail(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    api_number: str
    api_10: Optional[str]
    well_name: Optional[str]
    well_number: Optional[str]
    operator_id: Optional[UUID]
    operator_name: Optional[str]
    state_code: str
    county: Optional[str]
    basin: Optional[str]
    field_name: Optional[str]
    lease_name: Optional[str]
    latitude: Optional[float]
    longitude: Optional[float]
    well_status: Optional[WellStatus]
    well_type: Optional[str]
    spud_date: Optional[date]
    completion_date: Optional[date]
    total_depth: Optional[int]
    true_vertical_depth: Optional[int]
    lateral_length: Optional[int]
    metadata: dict = {}
    alternate_ids: dict = {}
    documents: list["DocumentSummary"] = []
    created_at: datetime
    updated_at: datetime


# ---- Documents ----

class DocumentSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    well_id: Optional[UUID]
    state_code: str
    doc_type: DocType
    document_date: Optional[date]
    confidence_score: Optional[float]
    file_format: Optional[str]
    source_url: str
    scraped_at: datetime

class DocumentDetail(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    well_id: Optional[UUID]
    well_api_number: Optional[str]       # joined from wells table
    state_code: str
    doc_type: DocType
    status: str
    source_url: str
    file_path: Optional[str]
    file_format: Optional[str]
    file_size_bytes: Optional[int]
    file_hash: Optional[str]
    confidence_score: Optional[float]
    ocr_confidence: Optional[float]
    classification_method: Optional[str]
    document_date: Optional[date]
    scraped_at: datetime
    processed_at: Optional[datetime]
    raw_metadata: dict = {}
    extracted_data: list["ExtractedDataSummary"] = []
    created_at: datetime
    updated_at: datetime


# ---- Extracted Data ----

class ExtractedDataSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    document_id: UUID
    data_type: str
    data: dict
    field_confidence: dict = {}
    confidence_score: Optional[float]
    extractor_used: Optional[str]
    reporting_period_start: Optional[date]
    reporting_period_end: Optional[date]
    extracted_at: datetime


# ---- Scrape Jobs ----

class ScrapeJobCreate(BaseModel):
    state_code: Optional[str] = None     # None = all states
    job_type: str = "full"
    parameters: dict = {}

class ScrapeJobSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    state_code: Optional[str]
    status: ScrapeJobStatus
    job_type: str
    documents_found: int = 0
    documents_downloaded: int = 0
    documents_processed: int = 0
    documents_failed: int = 0
    started_at: Optional[datetime]
    finished_at: Optional[datetime]
    created_at: datetime

class ScrapeJobDetail(ScrapeJobSummary):
    parameters: dict = {}
    errors: list[dict] = []
    total_documents: int = 0


# ---- Review Queue ----

class ReviewQueueItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    document_id: UUID
    extracted_data_id: Optional[UUID]
    status: ReviewStatus
    reason: str
    document_confidence: Optional[float]
    well_api_number: Optional[str]       # joined
    state_code: Optional[str]            # joined
    doc_type: Optional[DocType]          # joined
    created_at: datetime

class ReviewItemDetail(ReviewQueueItem):
    flag_details: dict = {}
    field_confidences: dict = {}
    corrections: dict = {}
    notes: Optional[str]
    reviewed_by: Optional[str]
    reviewed_at: Optional[datetime]
    document: Optional[DocumentDetail]
    extracted_data: Optional[ExtractedDataSummary]

class ReviewAction(BaseModel):
    status: ReviewStatus
    corrections: Optional[dict] = None
    notes: Optional[str] = None
    reviewed_by: Optional[str] = None


# ---- Map ----

class WellMapPoint(BaseModel):
    """Minimal well data for map pin rendering. Keep this small."""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    api_number: str
    well_name: Optional[str]
    operator_name: Optional[str]
    latitude: float
    longitude: float
    well_status: Optional[WellStatus]
    well_type: Optional[str]


# ---- Stats ----

class DashboardStats(BaseModel):
    total_wells: int
    total_documents: int
    total_extracted: int
    documents_by_state: dict[str, int]
    documents_by_type: dict[str, int]
    wells_by_status: dict[str, int]
    review_queue_pending: int
    avg_confidence: Optional[float]
    recent_scrape_jobs: list[ScrapeJobSummary]
```

### 3.3 Background Task Handling: Huey over FastAPI BackgroundTasks

**Decision: Huey task queue for scrape jobs. FastAPI BackgroundTasks for trivial async work only.**

Rationale:

| Feature | FastAPI BackgroundTasks | Huey |
|---------|----------------------|------|
| Survives server restart | No | Yes (Redis-backed) |
| Retry on failure | No | Yes (configurable) |
| Progress tracking | Manual | Built-in result storage |
| Concurrency control | None | Worker pool |
| Scheduled tasks | No | Yes (cron-like) |
| Complexity | Zero | Low (Redis required) |

Scrape jobs are long-running (minutes to hours), must survive restarts, need progress tracking, and benefit from retry logic. Huey provides all of this with minimal overhead. Redis is already in the stack for Huey's broker.

**Huey integration pattern**:

```python
# tasks.py
from huey import RedisHuey

huey = RedisHuey("og-scraper", host="localhost", port=6379)

@huey.task(retries=2, retry_delay=60)
def run_scrape_job(job_id: str, state_code: str | None, parameters: dict):
    """Execute a scrape job. Called from FastAPI endpoint."""
    # Update job status to 'running'
    # Initialize appropriate state adapter(s)
    # Run scraping pipeline
    # Update progress counters in the database as documents are processed
    # Update job status to 'completed' or 'failed'
    pass

@huey.task(retries=3, retry_delay=30)
def process_document(document_id: str):
    """Process a single document through classify -> extract -> normalize -> store."""
    pass

@huey.task()
def flag_for_review(document_id: str, reason: str, details: dict):
    """Create a review queue entry for a low-confidence document."""
    pass
```

**FastAPI endpoint triggering Huey**:

```python
# api/scrape.py
from fastapi import APIRouter, HTTPException
from app.tasks import run_scrape_job
from app.schemas import ScrapeJobCreate, ScrapeJobDetail

router = APIRouter(prefix="/api/v1/scrape", tags=["scraping"])

@router.post("/", response_model=ScrapeJobDetail)
async def create_scrape_job(job_in: ScrapeJobCreate, db: AsyncSession = Depends(get_db)):
    """Trigger a new scrape job. Returns immediately with job ID."""
    # Create job record in database
    job = ScrapeJob(
        state_code=job_in.state_code,
        job_type=job_in.job_type,
        parameters=job_in.parameters,
        status="pending",
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)

    # Enqueue the actual work to Huey
    run_scrape_job(str(job.id), job_in.state_code, job_in.parameters)

    return job
```

### 3.4 Real-Time Scrape Progress via SSE

Server-Sent Events (SSE) are used for real-time scrape progress. SSE is preferable to WebSockets for this use case because the communication is one-directional (server pushes updates to client) and SSE works over standard HTTP with automatic reconnection built into the browser's EventSource API.

```python
# api/scrape.py
import asyncio
import json
from fastapi import APIRouter
from fastapi.responses import StreamingResponse

router = APIRouter(prefix="/api/v1/scrape", tags=["scraping"])

@router.get("/jobs/{job_id}/events")
async def scrape_job_events(job_id: UUID, db: AsyncSession = Depends(get_db)):
    """SSE endpoint for real-time scrape job progress."""

    async def event_generator():
        last_state = None
        while True:
            # Poll the job status from the database
            job = await db.get(ScrapeJob, job_id)
            if job is None:
                yield f"event: error\ndata: {json.dumps({'message': 'Job not found'})}\n\n"
                break

            current_state = {
                "status": job.status,
                "documents_found": job.documents_found,
                "documents_downloaded": job.documents_downloaded,
                "documents_processed": job.documents_processed,
                "documents_failed": job.documents_failed,
            }

            # Only send if state changed
            if current_state != last_state:
                yield f"event: progress\ndata: {json.dumps(current_state)}\n\n"
                last_state = current_state

            # Stop streaming when job is done
            if job.status in ("completed", "failed", "cancelled"):
                yield f"event: complete\ndata: {json.dumps(current_state)}\n\n"
                break

            await asyncio.sleep(1)  # poll interval

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # disable nginx buffering
        },
    )
```

**Frontend consumption**:

```javascript
const eventSource = new EventSource(`/api/v1/scrape/jobs/${jobId}/events`);
eventSource.addEventListener("progress", (e) => {
    const data = JSON.parse(e.data);
    updateProgressBar(data);
});
eventSource.addEventListener("complete", (e) => {
    const data = JSON.parse(e.data);
    showCompletionMessage(data);
    eventSource.close();
});
eventSource.addEventListener("error", (e) => {
    // EventSource auto-reconnects by default
    console.error("SSE error:", e);
});
```

### 3.5 File Serving for Original Documents

```python
# api/documents.py
import os
from pathlib import Path
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

router = APIRouter(prefix="/api/v1/documents", tags=["documents"])

# Base directory for stored documents (from config)
DOCUMENTS_BASE_DIR = Path("data/documents")

MIME_TYPES = {
    "pdf": "application/pdf",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "xls": "application/vnd.ms-excel",
    "csv": "text/csv",
    "html": "text/html",
    "tif": "image/tiff",
    "tiff": "image/tiff",
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
}

@router.get("/{document_id}/file")
async def serve_document_file(
    document_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """Serve the original document file for viewing/download."""
    document = await db.get(Document, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")

    if not document.file_path:
        raise HTTPException(status_code=404, detail="File not available for this document")

    file_path = Path(document.file_path)
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found on disk")

    # Determine MIME type
    ext = file_path.suffix.lstrip(".").lower()
    media_type = MIME_TYPES.get(ext, "application/octet-stream")

    # Use FileResponse for efficient file serving
    # FileResponse handles async streaming and does not block the event loop
    return FileResponse(
        path=str(file_path),
        media_type=media_type,
        filename=file_path.name,
        # Set Content-Disposition to inline for PDFs (view in browser)
        # and attachment for other types (download)
        headers={
            "Content-Disposition": f"{'inline' if ext == 'pdf' else 'attachment'}; filename=\"{file_path.name}\""
        },
    )
```

### 3.6 Export Endpoints

```python
# api/export.py
import csv
import io
import json
from fastapi import APIRouter
from fastapi.responses import StreamingResponse

router = APIRouter(prefix="/api/v1/export", tags=["export"])

@router.get("/wells")
async def export_wells(
    format: str = "csv",  # 'csv' or 'json'
    state: str | None = None,
    county: str | None = None,
    well_status: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    """Export wells data as CSV or JSON. Streams results for large datasets."""

    # Build query with filters (reuse well query builder)
    query = build_wells_query(state=state, county=county, well_status=well_status)

    if format == "csv":
        async def csv_generator():
            output = io.StringIO()
            writer = csv.writer(output)
            # Header row
            writer.writerow([
                "api_number", "well_name", "operator", "state",
                "county", "latitude", "longitude", "well_status",
                "well_type", "spud_date", "completion_date",
            ])
            yield output.getvalue()
            output.seek(0)
            output.truncate(0)

            # Stream rows
            result = await db.stream(query)
            async for row in result:
                writer.writerow([
                    row.api_number, row.well_name, row.operator_name,
                    row.state_code, row.county, row.latitude, row.longitude,
                    row.well_status, row.well_type, row.spud_date,
                    row.completion_date,
                ])
                yield output.getvalue()
                output.seek(0)
                output.truncate(0)

        return StreamingResponse(
            csv_generator(),
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=wells_export.csv"},
        )

    elif format == "json":
        async def json_generator():
            yield "["
            first = True
            result = await db.stream(query)
            async for row in result:
                if not first:
                    yield ","
                first = False
                yield json.dumps({
                    "api_number": row.api_number,
                    "well_name": row.well_name,
                    "operator": row.operator_name,
                    "state": row.state_code,
                    "county": row.county,
                    "latitude": row.latitude,
                    "longitude": row.longitude,
                    "well_status": row.well_status,
                    "well_type": row.well_type,
                })
            yield "]"

        return StreamingResponse(
            json_generator(),
            media_type="application/json",
            headers={"Content-Disposition": "attachment; filename=wells_export.json"},
        )
```

### 3.7 Application Structure

```
backend/
├── alembic/                        # Database migrations
│   ├── versions/
│   ├── env.py
│   └── alembic.ini
├── app/
│   ├── __init__.py
│   ├── main.py                     # FastAPI application factory
│   ├── config.py                   # Settings (pydantic-settings)
│   ├── database.py                 # Async engine, session factory
│   ├── models/                     # SQLAlchemy ORM models
│   │   ├── __init__.py
│   │   ├── base.py                 # Declarative base, common mixins
│   │   ├── state.py
│   │   ├── operator.py
│   │   ├── well.py
│   │   ├── document.py
│   │   ├── extracted_data.py
│   │   ├── review_queue.py
│   │   ├── scrape_job.py
│   │   └── data_correction.py
│   ├── schemas/                    # Pydantic request/response models
│   │   ├── __init__.py
│   │   ├── well.py
│   │   ├── document.py
│   │   ├── scrape.py
│   │   ├── review.py
│   │   ├── map.py
│   │   ├── stats.py
│   │   └── export.py
│   ├── api/                        # FastAPI routers
│   │   ├── __init__.py
│   │   ├── wells.py
│   │   ├── documents.py
│   │   ├── scrape.py
│   │   ├── review.py
│   │   ├── map.py
│   │   ├── stats.py
│   │   └── export.py
│   ├── services/                   # Business logic layer
│   │   ├── __init__.py
│   │   ├── well_service.py
│   │   ├── document_service.py
│   │   ├── search_service.py
│   │   ├── review_service.py
│   │   └── stats_service.py
│   ├── tasks/                      # Huey task definitions
│   │   ├── __init__.py
│   │   ├── scrape_tasks.py
│   │   ├── process_tasks.py
│   │   └── review_tasks.py
│   └── utils/                      # Shared utilities
│       ├── __init__.py
│       ├── api_number.py           # API number normalization
│       ├── pagination.py
│       └── query_builder.py        # Reusable query construction
├── tests/
├── pyproject.toml
├── Dockerfile
└── docker-compose.yml
```

---

## 4. SQLAlchemy 2.0 Async Models

### 4.1 Database Connection Setup

```python
# app/database.py
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import settings

# Create async engine — one per process
engine = create_async_engine(
    settings.database_url,  # postgresql+asyncpg://user:pass@localhost:5432/og_scraper
    echo=settings.debug,
    pool_size=20,
    max_overflow=10,
    pool_pre_ping=True,     # verify connections before use
    pool_recycle=3600,       # recycle connections after 1 hour
)

# Session factory — creates short-lived sessions
async_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,  # prevent lazy-load issues in async
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency that yields an async database session."""
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
```

### 4.2 Base Model and Mixins

```python
# app/models/base.py
from datetime import datetime
from uuid import uuid4

from sqlalchemy import DateTime, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy models."""
    pass


class TimestampMixin:
    """Adds created_at and updated_at columns."""
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class UUIDPrimaryKeyMixin:
    """Adds a UUID primary key column."""
    id: Mapped[uuid4] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
```

### 4.3 Model Definitions

```python
# app/models/state.py
from datetime import datetime
from typing import Optional

from sqlalchemy import String, SmallInteger, DateTime
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class State(Base, TimestampMixin):
    __tablename__ = "states"

    code: Mapped[str] = mapped_column(String(2), primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    api_state_code: Mapped[str] = mapped_column(String(2), unique=True, nullable=False)
    tier: Mapped[int] = mapped_column(SmallInteger, default=1)
    last_scraped_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    config: Mapped[dict] = mapped_column(JSONB, default=dict)

    # Relationships
    wells = relationship("Well", back_populates="state", lazy="selectin")
    documents = relationship("Document", back_populates="state", lazy="selectin")
    scrape_jobs = relationship("ScrapeJob", back_populates="state", lazy="selectin")
```

```python
# app/models/operator.py
from typing import Optional
from uuid import uuid4

from sqlalchemy import String, Index
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Operator(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "operators"

    name: Mapped[str] = mapped_column(String(500), nullable=False)
    normalized_name: Mapped[str] = mapped_column(String(500), nullable=False)
    aliases: Mapped[dict] = mapped_column(JSONB, default=list)
    state_operator_ids: Mapped[dict] = mapped_column(JSONB, default=dict)
    metadata: Mapped[dict] = mapped_column(JSONB, default=dict)
    search_vector: Mapped[Optional[str]] = mapped_column(TSVECTOR)

    # Relationships
    wells = relationship("Well", back_populates="operator", lazy="selectin")

    __table_args__ = (
        Index("idx_operators_normalized", "normalized_name"),
        Index("idx_operators_name_trgm", "name", postgresql_using="gin",
              postgresql_ops={"name": "gin_trgm_ops"}),
        Index("idx_operators_search", "search_vector", postgresql_using="gin"),
        Index("idx_operators_aliases_gin", "aliases", postgresql_using="gin",
              postgresql_ops={"aliases": "jsonb_path_ops"}),
    )
```

```python
# app/models/well.py
from datetime import date, datetime
from typing import Optional
from uuid import uuid4

from geoalchemy2 import Geometry
from sqlalchemy import (
    String, Integer, Float, Date, DateTime, UniqueConstraint, Index,
    Computed, Enum as SAEnum,
)
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Well(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "wells"

    api_number: Mapped[str] = mapped_column(String(14), nullable=False)
    api_10: Mapped[Optional[str]] = mapped_column(
        String(10), Computed("LEFT(api_number, 10)")
    )
    well_name: Mapped[Optional[str]] = mapped_column(String(500))
    well_number: Mapped[Optional[str]] = mapped_column(String(100))
    operator_id: Mapped[Optional[uuid4]] = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey("operators.id", ondelete="SET NULL"),
    )
    state_code: Mapped[str] = mapped_column(
        String(2),
        sa.ForeignKey("states.code"),
        nullable=False,
    )
    county: Mapped[Optional[str]] = mapped_column(String(255))
    basin: Mapped[Optional[str]] = mapped_column(String(255))
    field_name: Mapped[Optional[str]] = mapped_column(String(255))
    lease_name: Mapped[Optional[str]] = mapped_column(String(500))

    # Location
    latitude: Mapped[Optional[float]] = mapped_column(Float(precision=53))
    longitude: Mapped[Optional[float]] = mapped_column(Float(precision=53))
    location: Mapped[Optional[str]] = mapped_column(
        Geometry("POINT", srid=4326)
    )

    # Well details
    well_status: Mapped[Optional[str]] = mapped_column(
        SAEnum(
            "active", "inactive", "plugged", "permitted", "drilling",
            "completed", "shut_in", "temporarily_abandoned", "unknown",
            name="well_status_enum",
        ),
        default="unknown",
    )
    well_type: Mapped[Optional[str]] = mapped_column(String(50))
    spud_date: Mapped[Optional[date]] = mapped_column(Date)
    completion_date: Mapped[Optional[date]] = mapped_column(Date)
    total_depth: Mapped[Optional[int]] = mapped_column(Integer)
    true_vertical_depth: Mapped[Optional[int]] = mapped_column(Integer)
    lateral_length: Mapped[Optional[int]] = mapped_column(Integer)

    # Flexible data
    metadata: Mapped[dict] = mapped_column(JSONB, default=dict)
    alternate_ids: Mapped[dict] = mapped_column(JSONB, default=dict)

    # Search
    search_vector: Mapped[Optional[str]] = mapped_column(TSVECTOR)

    # Relationships
    state = relationship("State", back_populates="wells")
    operator = relationship("Operator", back_populates="wells")
    documents = relationship("Document", back_populates="well", lazy="selectin")
    extracted_data = relationship("ExtractedData", back_populates="well", lazy="selectin")

    __table_args__ = (
        UniqueConstraint("api_number", "state_code", name="uq_wells_api_state"),
        Index("idx_wells_api_number", "api_number"),
        Index("idx_wells_api_10", "api_10"),
        Index("idx_wells_api_trgm", "api_number", postgresql_using="gin",
              postgresql_ops={"api_number": "gin_trgm_ops"}),
        Index("idx_wells_operator", "operator_id"),
        Index("idx_wells_state_county", "state_code", "county"),
        Index("idx_wells_status", "well_status"),
        Index("idx_wells_lease_trgm", "lease_name", postgresql_using="gin",
              postgresql_ops={"lease_name": "gin_trgm_ops"}),
        Index("idx_wells_location_gist", "location", postgresql_using="gist"),
        Index("idx_wells_search", "search_vector", postgresql_using="gin"),
        Index("idx_wells_metadata_gin", "metadata", postgresql_using="gin",
              postgresql_ops={"metadata": "jsonb_path_ops"}),
        Index("idx_wells_alt_ids_gin", "alternate_ids", postgresql_using="gin",
              postgresql_ops={"alternate_ids": "jsonb_path_ops"}),
    )
```

```python
# app/models/document.py
from datetime import date, datetime
from typing import Optional
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import String, BigInteger, Numeric, Date, DateTime, Text, Index
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR, UUID, ENUM
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Document(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "documents"

    well_id: Mapped[Optional[uuid4]] = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey("wells.id", ondelete="SET NULL"),
    )
    state_code: Mapped[str] = mapped_column(
        String(2),
        sa.ForeignKey("states.code"),
        nullable=False,
    )
    scrape_job_id: Mapped[Optional[uuid4]] = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey("scrape_jobs.id", ondelete="SET NULL"),
    )
    doc_type: Mapped[str] = mapped_column(
        ENUM(
            "well_permit", "completion_report", "production_report",
            "spacing_order", "pooling_order", "plugging_report",
            "inspection_record", "incident_report", "other",
            name="doc_type_enum",
        ),
        default="other",
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        ENUM(
            "discovered", "downloading", "downloaded", "classifying",
            "classified", "extracting", "extracted", "normalized",
            "stored", "flagged_for_review", "download_failed",
            "classification_failed", "extraction_failed",
            name="document_status_enum",
        ),
        default="discovered",
        nullable=False,
    )
    # Provenance
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    file_path: Mapped[Optional[str]] = mapped_column(Text)
    file_hash: Mapped[Optional[str]] = mapped_column(String(64), unique=True)
    file_format: Mapped[Optional[str]] = mapped_column(String(20))
    file_size_bytes: Mapped[Optional[int]] = mapped_column(BigInteger)
    # Confidence
    confidence_score: Mapped[Optional[float]] = mapped_column(Numeric(5, 4))
    ocr_confidence: Mapped[Optional[float]] = mapped_column(Numeric(5, 4))
    classification_method: Mapped[Optional[str]] = mapped_column(String(50))
    # Dates
    document_date: Mapped[Optional[date]] = mapped_column(Date)
    scraped_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=sa.func.now()
    )
    processed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    # Flexible
    raw_metadata: Mapped[dict] = mapped_column(JSONB, default=dict)
    # Search
    search_vector: Mapped[Optional[str]] = mapped_column(TSVECTOR)

    # Relationships
    state = relationship("State", back_populates="documents")
    well = relationship("Well", back_populates="documents")
    scrape_job = relationship("ScrapeJob", back_populates="documents")
    extracted_data = relationship(
        "ExtractedData", back_populates="document",
        cascade="all, delete-orphan", lazy="selectin",
    )
    review_items = relationship(
        "ReviewQueueItem", back_populates="document",
        cascade="all, delete-orphan", lazy="selectin",
    )

    __table_args__ = (
        Index("idx_documents_state_type", "state_code", "doc_type"),
        Index("idx_documents_well", "well_id"),
        Index("idx_documents_scrape_job", "scrape_job_id"),
        Index("idx_documents_date", "document_date"),
        Index("idx_documents_scraped_at", "scraped_at"),
        Index("idx_documents_status", "status"),
        Index("idx_documents_search", "search_vector", postgresql_using="gin"),
        Index("idx_documents_metadata_gin", "raw_metadata", postgresql_using="gin",
              postgresql_ops={"raw_metadata": "jsonb_path_ops"}),
    )
```

```python
# app/models/extracted_data.py
from datetime import date, datetime
from typing import Optional
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import String, Numeric, Date, DateTime, Index
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class ExtractedData(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "extracted_data"

    document_id: Mapped[uuid4] = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
    )
    well_id: Mapped[Optional[uuid4]] = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey("wells.id", ondelete="SET NULL"),
    )
    data_type: Mapped[str] = mapped_column(String(50), nullable=False)
    data: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    field_confidence: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    confidence_score: Mapped[Optional[float]] = mapped_column(Numeric(5, 4))
    extractor_used: Mapped[Optional[str]] = mapped_column(String(100))
    extraction_version: Mapped[Optional[str]] = mapped_column(String(20))
    reporting_period_start: Mapped[Optional[date]] = mapped_column(Date)
    reporting_period_end: Mapped[Optional[date]] = mapped_column(Date)
    extracted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=sa.func.now()
    )

    # Relationships
    document = relationship("Document", back_populates="extracted_data")
    well = relationship("Well", back_populates="extracted_data")
    corrections = relationship(
        "DataCorrection", back_populates="extracted_data",
        cascade="all, delete-orphan", lazy="selectin",
    )

    __table_args__ = (
        Index("idx_extracted_document", "document_id"),
        Index("idx_extracted_well", "well_id"),
        Index("idx_extracted_data_type", "data_type"),
        Index("idx_extracted_period", "reporting_period_start", "reporting_period_end"),
        Index("idx_extracted_data_gin", "data", postgresql_using="gin",
              postgresql_ops={"data": "jsonb_path_ops"}),
        Index("idx_extracted_confidence_gin", "field_confidence", postgresql_using="gin",
              postgresql_ops={"field_confidence": "jsonb_path_ops"}),
    )
```

```python
# app/models/review_queue.py
from datetime import datetime
from typing import Optional
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import String, Numeric, Text, DateTime, Index
from sqlalchemy.dialects.postgresql import JSONB, UUID, ENUM
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class ReviewQueueItem(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "review_queue"

    document_id: Mapped[uuid4] = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
    )
    extracted_data_id: Mapped[Optional[uuid4]] = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey("extracted_data.id", ondelete="CASCADE"),
    )
    status: Mapped[str] = mapped_column(
        ENUM("pending", "approved", "rejected", "corrected", name="review_status_enum"),
        default="pending",
        nullable=False,
    )
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    flag_details: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    document_confidence: Mapped[Optional[float]] = mapped_column(Numeric(5, 4))
    field_confidences: Mapped[dict] = mapped_column(JSONB, default=dict)
    reviewed_by: Mapped[Optional[str]] = mapped_column(String(100))
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    corrections: Mapped[dict] = mapped_column(JSONB, default=dict)
    notes: Mapped[Optional[str]] = mapped_column(Text)

    # Relationships
    document = relationship("Document", back_populates="review_items")
    extracted_data = relationship("ExtractedData")

    __table_args__ = (
        Index("idx_review_status", "status"),
        Index("idx_review_document", "document_id"),
        Index("idx_review_created", "created_at"),
    )
```

```python
# app/models/scrape_job.py
from datetime import datetime
from typing import Optional
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import String, Integer, DateTime, Index
from sqlalchemy.dialects.postgresql import JSONB, UUID, ENUM
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class ScrapeJob(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "scrape_jobs"

    state_code: Mapped[Optional[str]] = mapped_column(
        String(2), sa.ForeignKey("states.code")
    )
    status: Mapped[str] = mapped_column(
        ENUM(
            "pending", "running", "completed", "failed", "cancelled",
            name="scrape_job_status_enum",
        ),
        default="pending",
        nullable=False,
    )
    job_type: Mapped[str] = mapped_column(String(50), default="full", nullable=False)
    parameters: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    total_documents: Mapped[int] = mapped_column(Integer, default=0)
    documents_found: Mapped[int] = mapped_column(Integer, default=0)
    documents_downloaded: Mapped[int] = mapped_column(Integer, default=0)
    documents_processed: Mapped[int] = mapped_column(Integer, default=0)
    documents_failed: Mapped[int] = mapped_column(Integer, default=0)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    errors: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)

    # Relationships
    state = relationship("State", back_populates="scrape_jobs")
    documents = relationship("Document", back_populates="scrape_job", lazy="selectin")

    __table_args__ = (
        Index("idx_scrape_jobs_status", "status"),
        Index("idx_scrape_jobs_state", "state_code"),
    )
```

```python
# app/models/data_correction.py
from datetime import datetime
from typing import Optional
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import String, DateTime
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class DataCorrection(Base):
    __tablename__ = "data_corrections"

    id: Mapped[uuid4] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid4
    )
    extracted_data_id: Mapped[uuid4] = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey("extracted_data.id", ondelete="CASCADE"),
        nullable=False,
    )
    review_queue_id: Mapped[Optional[uuid4]] = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey("review_queue.id", ondelete="SET NULL"),
    )
    field_path: Mapped[str] = mapped_column(String(255), nullable=False)
    old_value: Mapped[Optional[dict]] = mapped_column(JSONB)
    new_value: Mapped[dict] = mapped_column(JSONB, nullable=False)
    corrected_by: Mapped[Optional[str]] = mapped_column(String(100))
    corrected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=sa.func.now()
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=sa.func.now()
    )

    # Relationships
    extracted_data = relationship("ExtractedData", back_populates="corrections")
```

### 4.4 Query Patterns for Complex Searches

```python
# app/services/search_service.py
from sqlalchemy import select, func, or_, and_, cast, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import selectinload
from geoalchemy2.functions import ST_MakeEnvelope, ST_DWithin, ST_SetSRID, ST_MakePoint

from app.models.well import Well
from app.models.operator import Operator
from app.models.document import Document


async def search_wells(
    db: AsyncSession,
    *,
    q: str | None = None,
    api_number: str | None = None,
    state: str | None = None,
    county: str | None = None,
    operator: str | None = None,
    lease_name: str | None = None,
    well_status: str | None = None,
    page: int = 1,
    page_size: int = 50,
) -> tuple[list[Well], int]:
    """
    Multi-filter well search with full-text, fuzzy matching, and pagination.
    Returns (results, total_count).
    """
    query = (
        select(Well)
        .outerjoin(Operator, Well.operator_id == Operator.id)
        .options(selectinload(Well.operator))
    )
    count_query = select(func.count()).select_from(Well)

    filters = []

    # Full-text search across tsvector
    if q:
        ts_query = func.plainto_tsquery("english", q)
        filters.append(Well.search_vector.op("@@")(ts_query))
        # Add ranking for relevance-based ordering
        query = query.add_columns(
            func.ts_rank(Well.search_vector, ts_query).label("rank")
        )

    # API number: exact match or prefix match
    if api_number:
        # Strip dashes for matching
        clean_api = api_number.replace("-", "").replace(" ", "")
        if len(clean_api) <= 10:
            filters.append(Well.api_10 == clean_api)
        else:
            filters.append(Well.api_number == clean_api)

    # State filter
    if state:
        filters.append(Well.state_code == state.upper())

    # County filter (case-insensitive)
    if county:
        filters.append(func.lower(Well.county) == county.lower())

    # Operator name (fuzzy match via trigram similarity)
    if operator:
        filters.append(
            func.similarity(Operator.name, operator) > 0.3
        )

    # Lease name (fuzzy match)
    if lease_name:
        filters.append(
            func.similarity(Well.lease_name, lease_name) > 0.3
        )

    # Well status
    if well_status:
        filters.append(Well.well_status == well_status)

    # Apply filters
    if filters:
        query = query.where(and_(*filters))
        count_query = count_query.where(and_(*filters))

    # Get total count
    total = await db.scalar(count_query)

    # Sort and paginate
    if q:
        query = query.order_by(func.ts_rank(Well.search_vector,
                                func.plainto_tsquery("english", q)).desc())
    else:
        query = query.order_by(Well.api_number)

    query = query.offset((page - 1) * page_size).limit(page_size)

    result = await db.execute(query)
    wells = result.scalars().all()

    return wells, total


async def search_wells_in_bbox(
    db: AsyncSession,
    *,
    min_lat: float,
    max_lat: float,
    min_lng: float,
    max_lng: float,
    well_status: str | None = None,
    well_type: str | None = None,
    limit: int = 1000,
) -> list[Well]:
    """Find wells within a geographic bounding box (for map viewport)."""
    envelope = func.ST_MakeEnvelope(min_lng, min_lat, max_lng, max_lat, 4326)

    query = (
        select(Well)
        .outerjoin(Operator, Well.operator_id == Operator.id)
        .where(Well.location.op("&&")(envelope))  # bounding box check via GiST
    )

    if well_status:
        query = query.where(Well.well_status == well_status)
    if well_type:
        query = query.where(Well.well_type == well_type)

    query = query.limit(limit)

    result = await db.execute(query)
    return result.scalars().all()


async def search_documents(
    db: AsyncSession,
    *,
    q: str | None = None,
    well_id: str | None = None,
    state: str | None = None,
    doc_type: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    min_confidence: float | None = None,
    page: int = 1,
    page_size: int = 50,
) -> tuple[list[Document], int]:
    """Multi-filter document search."""
    query = select(Document).options(selectinload(Document.well))
    count_query = select(func.count()).select_from(Document)

    filters = []

    if q:
        ts_query = func.plainto_tsquery("english", q)
        filters.append(Document.search_vector.op("@@")(ts_query))

    if well_id:
        filters.append(Document.well_id == well_id)
    if state:
        filters.append(Document.state_code == state.upper())
    if doc_type:
        filters.append(Document.doc_type == doc_type)
    if date_from:
        filters.append(Document.document_date >= date_from)
    if date_to:
        filters.append(Document.document_date <= date_to)
    if min_confidence is not None:
        filters.append(Document.confidence_score >= min_confidence)

    if filters:
        query = query.where(and_(*filters))
        count_query = count_query.where(and_(*filters))

    total = await db.scalar(count_query)

    query = query.order_by(Document.scraped_at.desc())
    query = query.offset((page - 1) * page_size).limit(page_size)

    result = await db.execute(query)
    documents = result.scalars().all()

    return documents, total
```

---

## 5. Alembic Migrations

### 5.1 Alembic Setup for Async SQLAlchemy

```ini
# alembic.ini
[alembic]
script_location = alembic
sqlalchemy.url = postgresql+asyncpg://og_user:og_password@localhost:5432/og_scraper

[loggers]
keys = root,sqlalchemy,alembic

[handlers]
keys = console

[formatters]
keys = generic

[logger_root]
level = WARN
handlers = console

[logger_sqlalchemy]
level = WARN
handlers =
qualname = sqlalchemy.engine

[logger_alembic]
level = INFO
handlers =
qualname = alembic

[handler_console]
class = StreamHandler
args = (sys.stderr,)
level = NOTSET
formatter = generic

[formatter_generic]
format = %(levelname)-5.5s [%(name)s] %(message)s
datefmt = %H:%M:%S
```

```python
# alembic/env.py
import asyncio
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context

# Import the Base that all models inherit from
from app.models.base import Base

# Import all models so Alembic knows about them
from app.models.state import State
from app.models.operator import Operator
from app.models.well import Well
from app.models.document import Document
from app.models.extracted_data import ExtractedData
from app.models.review_queue import ReviewQueueItem
from app.models.scrape_job import ScrapeJob
from app.models.data_correction import DataCorrection

# Alembic Config object
config = context.config

# Set up logging
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Target metadata for autogeneration
target_metadata = Base.metadata

# Naming convention for constraints — critical for reliable autogeneration
target_metadata.naming_convention = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode (generate SQL without DB connection)."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection):
    """Run migrations with a given connection."""
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,        # detect column type changes
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Run migrations in async mode using asyncpg."""
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
```

### 5.2 Initial Migration

```python
# alembic/versions/001_initial_schema.py
"""Initial schema with all tables, PostGIS, and full-text search.

Revision ID: 001_initial
Revises: (none)
Create Date: 2026-03-27
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID, ENUM, TSVECTOR
import geoalchemy2


# revision identifiers
revision = "001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ---- Extensions ----
    op.execute("CREATE EXTENSION IF NOT EXISTS \"uuid-ossp\"")
    op.execute("CREATE EXTENSION IF NOT EXISTS \"postgis\"")
    op.execute("CREATE EXTENSION IF NOT EXISTS \"pg_trgm\"")

    # ---- Enum types ----
    doc_type_enum = ENUM(
        "well_permit", "completion_report", "production_report",
        "spacing_order", "pooling_order", "plugging_report",
        "inspection_record", "incident_report", "other",
        name="doc_type_enum", create_type=True,
    )
    document_status_enum = ENUM(
        "discovered", "downloading", "downloaded", "classifying",
        "classified", "extracting", "extracted", "normalized",
        "stored", "flagged_for_review", "download_failed",
        "classification_failed", "extraction_failed",
        name="document_status_enum", create_type=True,
    )
    scrape_job_status_enum = ENUM(
        "pending", "running", "completed", "failed", "cancelled",
        name="scrape_job_status_enum", create_type=True,
    )
    review_status_enum = ENUM(
        "pending", "approved", "rejected", "corrected",
        name="review_status_enum", create_type=True,
    )
    well_status_enum = ENUM(
        "active", "inactive", "plugged", "permitted", "drilling",
        "completed", "shut_in", "temporarily_abandoned", "unknown",
        name="well_status_enum", create_type=True,
    )

    # ---- Table: states ----
    op.create_table(
        "states",
        sa.Column("code", sa.String(2), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("api_state_code", sa.String(2), unique=True, nullable=False),
        sa.Column("tier", sa.SmallInteger(), default=1, nullable=False),
        sa.Column("last_scraped_at", sa.DateTime(timezone=True)),
        sa.Column("config", JSONB, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
    )

    # ---- Table: operators ----
    op.create_table(
        "operators",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("name", sa.String(500), nullable=False),
        sa.Column("normalized_name", sa.String(500), nullable=False),
        sa.Column("aliases", JSONB, server_default="'[]'::jsonb"),
        sa.Column("state_operator_ids", JSONB, server_default="'{}'::jsonb"),
        sa.Column("metadata", JSONB, server_default="'{}'::jsonb"),
        sa.Column("search_vector", TSVECTOR),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
    )

    # ---- Table: wells ----
    op.create_table(
        "wells",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("api_number", sa.String(14), nullable=False),
        sa.Column("api_10", sa.String(10), sa.Computed("LEFT(api_number, 10)")),
        sa.Column("well_name", sa.String(500)),
        sa.Column("well_number", sa.String(100)),
        sa.Column("operator_id", UUID(as_uuid=True), sa.ForeignKey("operators.id", ondelete="SET NULL")),
        sa.Column("state_code", sa.String(2), sa.ForeignKey("states.code"), nullable=False),
        sa.Column("county", sa.String(255)),
        sa.Column("basin", sa.String(255)),
        sa.Column("field_name", sa.String(255)),
        sa.Column("lease_name", sa.String(500)),
        sa.Column("latitude", sa.Float(precision=53)),
        sa.Column("longitude", sa.Float(precision=53)),
        sa.Column("location", geoalchemy2.Geometry("POINT", srid=4326)),
        sa.Column("well_status", well_status_enum, default="unknown"),
        sa.Column("well_type", sa.String(50)),
        sa.Column("spud_date", sa.Date()),
        sa.Column("completion_date", sa.Date()),
        sa.Column("total_depth", sa.Integer()),
        sa.Column("true_vertical_depth", sa.Integer()),
        sa.Column("lateral_length", sa.Integer()),
        sa.Column("metadata", JSONB, server_default="'{}'::jsonb"),
        sa.Column("alternate_ids", JSONB, server_default="'{}'::jsonb"),
        sa.Column("search_vector", TSVECTOR),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.UniqueConstraint("api_number", "state_code", name="uq_wells_api_state"),
    )

    # ---- Table: scrape_jobs ----
    op.create_table(
        "scrape_jobs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("state_code", sa.String(2), sa.ForeignKey("states.code")),
        sa.Column("status", scrape_job_status_enum, nullable=False, server_default="pending"),
        sa.Column("job_type", sa.String(50), nullable=False, server_default="full"),
        sa.Column("parameters", JSONB, server_default="'{}'::jsonb"),
        sa.Column("total_documents", sa.Integer(), server_default="0"),
        sa.Column("documents_found", sa.Integer(), server_default="0"),
        sa.Column("documents_downloaded", sa.Integer(), server_default="0"),
        sa.Column("documents_processed", sa.Integer(), server_default="0"),
        sa.Column("documents_failed", sa.Integer(), server_default="0"),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("errors", JSONB, server_default="'[]'::jsonb"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
    )

    # ---- Table: documents ----
    op.create_table(
        "documents",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("well_id", UUID(as_uuid=True), sa.ForeignKey("wells.id", ondelete="SET NULL")),
        sa.Column("state_code", sa.String(2), sa.ForeignKey("states.code"), nullable=False),
        sa.Column("scrape_job_id", UUID(as_uuid=True), sa.ForeignKey("scrape_jobs.id", ondelete="SET NULL")),
        sa.Column("doc_type", doc_type_enum, nullable=False, server_default="other"),
        sa.Column("status", document_status_enum, nullable=False, server_default="discovered"),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("file_path", sa.Text()),
        sa.Column("file_hash", sa.String(64), unique=True),
        sa.Column("file_format", sa.String(20)),
        sa.Column("file_size_bytes", sa.BigInteger()),
        sa.Column("confidence_score", sa.Numeric(5, 4)),
        sa.Column("ocr_confidence", sa.Numeric(5, 4)),
        sa.Column("classification_method", sa.String(50)),
        sa.Column("document_date", sa.Date()),
        sa.Column("scraped_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.Column("processed_at", sa.DateTime(timezone=True)),
        sa.Column("raw_metadata", JSONB, server_default="'{}'::jsonb"),
        sa.Column("search_vector", TSVECTOR),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
    )

    # ---- Table: extracted_data ----
    op.create_table(
        "extracted_data",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("document_id", UUID(as_uuid=True), sa.ForeignKey("documents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("well_id", UUID(as_uuid=True), sa.ForeignKey("wells.id", ondelete="SET NULL")),
        sa.Column("data_type", sa.String(50), nullable=False),
        sa.Column("data", JSONB, server_default="'{}'::jsonb", nullable=False),
        sa.Column("field_confidence", JSONB, server_default="'{}'::jsonb", nullable=False),
        sa.Column("confidence_score", sa.Numeric(5, 4)),
        sa.Column("extractor_used", sa.String(100)),
        sa.Column("extraction_version", sa.String(20)),
        sa.Column("reporting_period_start", sa.Date()),
        sa.Column("reporting_period_end", sa.Date()),
        sa.Column("extracted_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
    )

    # ---- Table: review_queue ----
    op.create_table(
        "review_queue",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("document_id", UUID(as_uuid=True), sa.ForeignKey("documents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("extracted_data_id", UUID(as_uuid=True), sa.ForeignKey("extracted_data.id", ondelete="CASCADE")),
        sa.Column("status", review_status_enum, nullable=False, server_default="pending"),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("flag_details", JSONB, server_default="'{}'::jsonb"),
        sa.Column("document_confidence", sa.Numeric(5, 4)),
        sa.Column("field_confidences", JSONB, server_default="'{}'::jsonb"),
        sa.Column("reviewed_by", sa.String(100)),
        sa.Column("reviewed_at", sa.DateTime(timezone=True)),
        sa.Column("corrections", JSONB, server_default="'{}'::jsonb"),
        sa.Column("notes", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
    )

    # ---- Table: data_corrections ----
    op.create_table(
        "data_corrections",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("extracted_data_id", UUID(as_uuid=True), sa.ForeignKey("extracted_data.id", ondelete="CASCADE"), nullable=False),
        sa.Column("review_queue_id", UUID(as_uuid=True), sa.ForeignKey("review_queue.id", ondelete="SET NULL")),
        sa.Column("field_path", sa.String(255), nullable=False),
        sa.Column("old_value", JSONB),
        sa.Column("new_value", JSONB, nullable=False),
        sa.Column("corrected_by", sa.String(100)),
        sa.Column("corrected_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
    )

    # ---- Indexes (see Section 1.5 for rationale) ----
    # Wells indexes
    op.create_index("idx_wells_api_number", "wells", ["api_number"])
    op.create_index("idx_wells_api_10", "wells", ["api_10"])
    op.execute("CREATE INDEX idx_wells_api_trgm ON wells USING GIN (api_number gin_trgm_ops)")
    op.create_index("idx_wells_operator", "wells", ["operator_id"])
    op.create_index("idx_wells_state_county", "wells", ["state_code", "county"])
    op.create_index("idx_wells_status", "wells", ["well_status"])
    op.execute("CREATE INDEX idx_wells_lease_trgm ON wells USING GIN (lease_name gin_trgm_ops)")
    op.execute("CREATE INDEX idx_wells_location_gist ON wells USING GIST (location)")
    op.execute("CREATE INDEX idx_wells_search ON wells USING GIN (search_vector)")
    op.execute("CREATE INDEX idx_wells_metadata_gin ON wells USING GIN (metadata jsonb_path_ops)")
    op.execute("CREATE INDEX idx_wells_alt_ids_gin ON wells USING GIN (alternate_ids jsonb_path_ops)")

    # Documents indexes
    op.create_index("idx_documents_state_type", "documents", ["state_code", "doc_type"])
    op.create_index("idx_documents_well", "documents", ["well_id"])
    op.create_index("idx_documents_scrape_job", "documents", ["scrape_job_id"])
    op.create_index("idx_documents_date", "documents", ["document_date"])
    op.create_index("idx_documents_scraped_at", "documents", ["scraped_at"])
    op.create_index("idx_documents_status", "documents", ["status"])
    op.execute("CREATE INDEX idx_documents_source_url ON documents USING HASH (source_url)")
    op.execute("CREATE INDEX idx_documents_search ON documents USING GIN (search_vector)")
    op.execute("CREATE INDEX idx_documents_metadata_gin ON documents USING GIN (raw_metadata jsonb_path_ops)")

    # Extracted data indexes
    op.create_index("idx_extracted_document", "extracted_data", ["document_id"])
    op.create_index("idx_extracted_well", "extracted_data", ["well_id"])
    op.create_index("idx_extracted_data_type", "extracted_data", ["data_type"])
    op.create_index("idx_extracted_period", "extracted_data", ["reporting_period_start", "reporting_period_end"])
    op.execute("CREATE INDEX idx_extracted_data_gin ON extracted_data USING GIN (data jsonb_path_ops)")
    op.execute("CREATE INDEX idx_extracted_confidence_gin ON extracted_data USING GIN (field_confidence jsonb_path_ops)")

    # Review queue indexes
    op.create_index("idx_review_status", "review_queue", ["status"])
    op.create_index("idx_review_document", "review_queue", ["document_id"])
    op.create_index("idx_review_created", "review_queue", ["created_at"])

    # Scrape jobs indexes
    op.create_index("idx_scrape_jobs_status", "scrape_jobs", ["status"])
    op.create_index("idx_scrape_jobs_state", "scrape_jobs", ["state_code"])

    # Operators indexes
    op.create_index("idx_operators_normalized", "operators", ["normalized_name"])
    op.execute("CREATE INDEX idx_operators_name_trgm ON operators USING GIN (name gin_trgm_ops)")
    op.execute("CREATE INDEX idx_operators_search ON operators USING GIN (search_vector)")
    op.execute("CREATE INDEX idx_operators_aliases_gin ON operators USING GIN (aliases jsonb_path_ops)")

    # ---- Full-text search triggers ----
    op.execute("""
        CREATE OR REPLACE FUNCTION wells_search_update() RETURNS trigger AS $$
        BEGIN
            NEW.search_vector :=
                setweight(to_tsvector('english', COALESCE(NEW.api_number, '')), 'A') ||
                setweight(to_tsvector('english', COALESCE(NEW.well_name, '')), 'A') ||
                setweight(to_tsvector('english', COALESCE(NEW.lease_name, '')), 'B') ||
                setweight(to_tsvector('english', COALESCE(NEW.county, '')), 'C') ||
                setweight(to_tsvector('english', COALESCE(NEW.basin, '')), 'C') ||
                setweight(to_tsvector('english', COALESCE(NEW.field_name, '')), 'C');
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;

        CREATE TRIGGER trg_wells_search_update
            BEFORE INSERT OR UPDATE OF api_number, well_name, lease_name, county, basin, field_name
            ON wells FOR EACH ROW EXECUTE FUNCTION wells_search_update();
    """)

    op.execute("""
        CREATE OR REPLACE FUNCTION wells_location_update() RETURNS trigger AS $$
        BEGIN
            IF NEW.latitude IS NOT NULL AND NEW.longitude IS NOT NULL THEN
                NEW.location := ST_SetSRID(ST_MakePoint(NEW.longitude, NEW.latitude), 4326);
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;

        CREATE TRIGGER trg_wells_location_update
            BEFORE INSERT OR UPDATE OF latitude, longitude
            ON wells FOR EACH ROW EXECUTE FUNCTION wells_location_update();
    """)

    op.execute("""
        CREATE OR REPLACE FUNCTION operators_search_update() RETURNS trigger AS $$
        DECLARE
            alias_text TEXT := '';
        BEGIN
            IF NEW.aliases IS NOT NULL AND jsonb_array_length(NEW.aliases) > 0 THEN
                SELECT string_agg(elem::TEXT, ' ')
                INTO alias_text
                FROM jsonb_array_elements_text(NEW.aliases) AS elem;
            END IF;

            NEW.search_vector :=
                setweight(to_tsvector('english', COALESCE(NEW.name, '')), 'A') ||
                setweight(to_tsvector('english', COALESCE(NEW.normalized_name, '')), 'A') ||
                setweight(to_tsvector('english', COALESCE(alias_text, '')), 'B');
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;

        CREATE TRIGGER trg_operators_search_update
            BEFORE INSERT OR UPDATE OF name, normalized_name, aliases
            ON operators FOR EACH ROW EXECUTE FUNCTION operators_search_update();
    """)

    op.execute("""
        CREATE OR REPLACE FUNCTION documents_search_update() RETURNS trigger AS $$
        BEGIN
            NEW.search_vector :=
                setweight(to_tsvector('english', COALESCE(NEW.doc_type::TEXT, '')), 'A') ||
                setweight(to_tsvector('english', COALESCE(NEW.state_code, '')), 'B') ||
                setweight(to_tsvector('english', COALESCE(NEW.raw_metadata->>'operator', '')), 'B') ||
                setweight(to_tsvector('english', COALESCE(NEW.raw_metadata->>'well_name', '')), 'B') ||
                setweight(to_tsvector('english', COALESCE(NEW.raw_metadata->>'lease_name', '')), 'C') ||
                setweight(to_tsvector('english', COALESCE(NEW.raw_metadata->>'county', '')), 'C');
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;

        CREATE TRIGGER trg_documents_search_update
            BEFORE INSERT OR UPDATE OF doc_type, state_code, raw_metadata
            ON documents FOR EACH ROW EXECUTE FUNCTION documents_search_update();
    """)

    # ---- Seed: initial state data ----
    op.execute("""
        INSERT INTO states (code, name, api_state_code, tier) VALUES
        ('TX', 'Texas',          '42', 1),
        ('NM', 'New Mexico',     '32', 1),
        ('ND', 'North Dakota',   '35', 1),
        ('OK', 'Oklahoma',       '37', 1),
        ('CO', 'Colorado',       '05', 1),
        ('WY', 'Wyoming',        '49', 2),
        ('LA', 'Louisiana',      '17', 2),
        ('PA', 'Pennsylvania',   '39', 2),
        ('CA', 'California',     '04', 2),
        ('AK', 'Alaska',         '02', 2);
    """)


def downgrade() -> None:
    # Drop tables in reverse order (respect FK dependencies)
    op.drop_table("data_corrections")
    op.drop_table("review_queue")
    op.drop_table("extracted_data")
    op.drop_table("documents")
    op.drop_table("scrape_jobs")
    op.drop_table("wells")
    op.drop_table("operators")
    op.drop_table("states")

    # Drop enum types
    op.execute("DROP TYPE IF EXISTS well_status_enum")
    op.execute("DROP TYPE IF EXISTS review_status_enum")
    op.execute("DROP TYPE IF EXISTS scrape_job_status_enum")
    op.execute("DROP TYPE IF EXISTS document_status_enum")
    op.execute("DROP TYPE IF EXISTS doc_type_enum")

    # Drop functions
    op.execute("DROP FUNCTION IF EXISTS wells_search_update() CASCADE")
    op.execute("DROP FUNCTION IF EXISTS wells_location_update() CASCADE")
    op.execute("DROP FUNCTION IF EXISTS operators_search_update() CASCADE")
    op.execute("DROP FUNCTION IF EXISTS documents_search_update() CASCADE")

    # Drop extensions (optional -- may want to keep them)
    op.execute("DROP EXTENSION IF EXISTS pg_trgm")
    op.execute("DROP EXTENSION IF EXISTS postgis")
    op.execute("DROP EXTENSION IF EXISTS \"uuid-ossp\"")
```

### 5.3 Running Migrations

```bash
# Generate a new migration after model changes
alembic revision --autogenerate -m "description of changes"

# Apply all pending migrations
alembic upgrade head

# Rollback one migration
alembic downgrade -1

# Show migration history
alembic history

# Show current revision
alembic current
```

---

## 6. Docker Compose Configuration

### 6.1 Complete docker-compose.yml

```yaml
# docker-compose.yml
# Oil & Gas Document Scraper — Local Development Stack
version: "3.9"

services:
  # ---- PostgreSQL + PostGIS ----
  postgres:
    image: postgis/postgis:17-3.5
    container_name: og-postgres
    restart: unless-stopped
    environment:
      POSTGRES_DB: og_scraper
      POSTGRES_USER: og_user
      POSTGRES_PASSWORD: og_password
      # Performance tuning for local dev
      POSTGRES_INITDB_ARGS: "--data-checksums"
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data
      # Optional: custom init scripts run on first startup
      # - ./scripts/init-db.sql:/docker-entrypoint-initdb.d/01-init.sql
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U og_user -d og_scraper"]
      interval: 10s
      timeout: 5s
      retries: 5
    # Performance tuning via command-line flags
    command: >
      postgres
        -c shared_buffers=256MB
        -c effective_cache_size=512MB
        -c work_mem=16MB
        -c maintenance_work_mem=128MB
        -c max_connections=100
        -c random_page_cost=1.1
        -c checkpoint_completion_target=0.9
        -c wal_buffers=16MB

  # ---- Redis (Huey task queue broker) ----
  redis:
    image: redis:7-alpine
    container_name: og-redis
    restart: unless-stopped
    ports:
      - "6379:6379"
    volumes:
      - redis_data:/data
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 5s
      retries: 5

  # ---- pgAdmin (optional, for database inspection) ----
  pgadmin:
    image: dpage/pgadmin4:latest
    container_name: og-pgadmin
    restart: unless-stopped
    environment:
      PGADMIN_DEFAULT_EMAIL: admin@localhost.com
      PGADMIN_DEFAULT_PASSWORD: admin
      PGADMIN_CONFIG_SERVER_MODE: "False"   # desktop mode (no login on pgAdmin)
    ports:
      - "5050:80"
    volumes:
      - pgadmin_data:/var/lib/pgadmin
    depends_on:
      postgres:
        condition: service_healthy

  # ---- FastAPI Backend ----
  backend:
    build:
      context: ./backend
      dockerfile: Dockerfile
    container_name: og-backend
    restart: unless-stopped
    environment:
      DATABASE_URL: postgresql+asyncpg://og_user:og_password@postgres:5432/og_scraper
      REDIS_URL: redis://redis:6379/0
      DOCUMENTS_BASE_DIR: /app/data/documents
      DEBUG: "true"
    ports:
      - "8000:8000"
    volumes:
      - ./backend:/app                 # live code reload in development
      - document_storage:/app/data/documents   # persistent document storage
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
    command: uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

  # ---- Huey Worker (background task processing) ----
  worker:
    build:
      context: ./backend
      dockerfile: Dockerfile
    container_name: og-worker
    restart: unless-stopped
    environment:
      DATABASE_URL: postgresql+asyncpg://og_user:og_password@postgres:5432/og_scraper
      REDIS_URL: redis://redis:6379/0
      DOCUMENTS_BASE_DIR: /app/data/documents
    volumes:
      - ./backend:/app
      - document_storage:/app/data/documents
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
    command: huey_consumer app.tasks:huey -w 4 -k process

volumes:
  postgres_data:
    driver: local
  redis_data:
    driver: local
  pgadmin_data:
    driver: local
  document_storage:
    driver: local
```

### 6.2 Backend Dockerfile

```dockerfile
# backend/Dockerfile
FROM python:3.12-slim

WORKDIR /app

# System dependencies for PostGIS, PDF processing, OCR
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev \
    libgdal-dev \
    libgeos-dev \
    libproj-dev \
    poppler-utils \
    tesseract-ocr \
    && rm -rf /var/lib/apt/lists/*

# Python dependencies
COPY pyproject.toml ./
RUN pip install --no-cache-dir -e ".[dev]"

# Application code (mounted as volume in dev, copied in production)
COPY . .

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### 6.3 FastAPI Application Factory

```python
# app/main.py
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import wells, documents, scrape, review, map, stats, export
from app.database import engine


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup and shutdown events."""
    # Startup: verify database connection
    async with engine.begin() as conn:
        await conn.execute(sa.text("SELECT 1"))
    yield
    # Shutdown: dispose engine
    await engine.dispose()


app = FastAPI(
    title="Oil & Gas Document Scraper API",
    version="1.0.0",
    description="API for searching and managing scraped O&G regulatory documents",
    lifespan=lifespan,
)

# CORS — allow Next.js frontend (localhost:3000)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routers
app.include_router(wells.router)
app.include_router(documents.router)
app.include_router(scrape.router)
app.include_router(review.router)
app.include_router(map.router)
app.include_router(stats.router)
app.include_router(export.router)


@app.get("/health")
async def health_check():
    return {"status": "ok"}
```

### 6.4 Configuration

```python
# app/config.py
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Database
    database_url: str = "postgresql+asyncpg://og_user:og_password@localhost:5432/og_scraper"

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # Document storage
    documents_base_dir: str = "data/documents"

    # Confidence thresholds
    confidence_threshold: float = 0.80
    field_confidence_threshold: float = 0.80

    # Pagination defaults
    default_page_size: int = 50
    max_page_size: int = 200

    # Map defaults
    max_map_wells: int = 1000

    # Debug
    debug: bool = False

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
```

### 6.5 Connection Configuration Summary

```
SERVICE         PORT    URL (from host)                                        URL (from containers)
─────────────────────────────────────────────────────────────────────────────────────────────────────
PostgreSQL      5432    postgresql+asyncpg://og_user:og_password@localhost:5432/og_scraper
                        (same, but use 'postgres' as host from containers)
Redis           6379    redis://localhost:6379/0
                        (same, but use 'redis' as host from containers)
FastAPI         8000    http://localhost:8000/api/v1
pgAdmin         5050    http://localhost:5050  (login: admin@localhost.com / admin)
Next.js (FE)    3000    http://localhost:3000
```

### 6.6 Getting Started Commands

```bash
# Start all services
docker compose up -d

# Run database migrations
docker compose exec backend alembic upgrade head

# Check service status
docker compose ps

# View backend logs
docker compose logs -f backend

# View worker logs
docker compose logs -f worker

# Connect to PostgreSQL directly
docker compose exec postgres psql -U og_user -d og_scraper

# Stop all services
docker compose down

# Stop and remove all data (fresh start)
docker compose down -v
```

---

## Key Python Dependencies

```toml
# pyproject.toml (relevant dependencies)
[project]
dependencies = [
    # Web framework
    "fastapi>=0.115.0",
    "uvicorn[standard]>=0.32.0",
    # Database
    "sqlalchemy[asyncio]>=2.0.36",
    "asyncpg>=0.30.0",
    "alembic>=1.14.0",
    "geoalchemy2>=0.15.0",
    # Task queue
    "huey[redis]>=2.5.0",
    # Validation & settings
    "pydantic>=2.10.0",
    "pydantic-settings>=2.6.0",
    # File serving
    "python-multipart>=0.0.18",
    "aiofiles>=24.1.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.24.0",
    "httpx>=0.28.0",        # async test client for FastAPI
    "factory-boy>=3.3.0",   # test data factories
]
```
