---
name: postgresql-postgis-schema
description: PostgreSQL+PostGIS schema with 8 tables, full-text search, spatial queries, and Alembic migrations. Use when working with database schema, queries, or migrations.
---

# PostgreSQL + PostGIS Database Schema

## What It Is

PostgreSQL 16 with PostGIS 3.4 powering an 8-table relational schema for an oil and gas document scraper. The database stores well data with geographic coordinates, scraped regulatory documents, structured extracted data (JSONB), and confidence-scored review workflows. It supports full-text search via tsvector columns, spatial queries via PostGIS GEOMETRY columns, and flexible per-document-type data via JSONB.

## When to Use This Skill

- Writing or modifying SQL queries against the schema
- Creating or editing Alembic migration scripts
- Adding new columns, tables, or indexes
- Working with PostGIS spatial queries (map viewport, distance, nearest-neighbor)
- Building or modifying SQLAlchemy 2.0 async models
- Debugging full-text search or JSONB query issues
- Writing test fixtures that touch the database

---

## Schema Overview (8 Tables)

### 1. `states`

Reference table for the 10 supported US states. Primary key is the 2-letter state code.

| Column | Type | Notes |
|--------|------|-------|
| `code` | VARCHAR(2) PK | e.g. `TX`, `NM` |
| `name` | VARCHAR(100) | e.g. `Texas` |
| `api_state_code` | VARCHAR(2) UNIQUE | API numeric code, e.g. `42` for TX |
| `tier` | SMALLINT | 1 = Tier 1 (TX, NM, ND, OK, CO), 2 = Tier 2 (WY, LA, PA, CA, AK) |
| `last_scraped_at` | TIMESTAMPTZ | Last completed scrape timestamp |
| `config` | JSONB | State-specific scraper configuration |
| `created_at` / `updated_at` | TIMESTAMPTZ | Auto-set timestamps |

### 2. `operators`

Normalized oil and gas operator/company entities. Operators may appear under different names across states.

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID PK | uuid_generate_v4() |
| `name` | VARCHAR(500) | Canonical display name |
| `normalized_name` | VARCHAR(500) | Lowercase, stripped for matching |
| `aliases` | JSONB | Array of name variations: `["DEVON ENERGY CORP", "DEVON ENERGY CORPORATION"]` |
| `state_operator_ids` | JSONB | Per-state operator numbers: `{"TX": "123456", "OK": "789012"}` |
| `metadata` | JSONB | Extra info |
| `search_vector` | TSVECTOR | Full-text search on name + aliases |

### 3. `wells`

One row per physical well. The central table -- most queries start here.

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID PK | uuid_generate_v4() |
| `api_number` | VARCHAR(14) | Stored without dashes, zero-padded. e.g. `42501201300300` |
| `api_10` | VARCHAR(10) | **GENERATED ALWAYS** as `LEFT(api_number, 10)` -- first 10 digits for cross-referencing |
| `well_name` | VARCHAR(500) | |
| `well_number` | VARCHAR(100) | |
| `operator_id` | UUID FK | References `operators(id)` |
| `state_code` | VARCHAR(2) FK | References `states(code)` |
| `county` | VARCHAR(255) | |
| `basin` | VARCHAR(255) | |
| `field_name` | VARCHAR(255) | |
| `lease_name` | VARCHAR(500) | |
| `latitude` | DOUBLE PRECISION | Human-readable, used for CSV export |
| `longitude` | DOUBLE PRECISION | Human-readable, used for CSV export |
| `location` | GEOMETRY(Point, 4326) | PostGIS point, auto-synced from lat/long via trigger |
| `well_status` | well_status_enum | `active`, `inactive`, `plugged`, `permitted`, `drilling`, `completed`, `shut_in`, `temporarily_abandoned`, `unknown` |
| `well_type` | VARCHAR(50) | `oil`, `gas`, `injection`, `disposal`, etc. |
| `spud_date` | DATE | |
| `completion_date` | DATE | |
| `total_depth` | INTEGER | Feet |
| `true_vertical_depth` | INTEGER | Feet |
| `lateral_length` | INTEGER | Feet (horizontal wells) |
| `metadata` | JSONB | State-specific fields: `{"formation": "Wolfcamp", "pool": "Spraberry"}` |
| `alternate_ids` | JSONB | Non-API identifiers: `{"permit_number": "DP-2024-001"}` |
| `search_vector` | TSVECTOR | Full-text on api_number, well_name, lease_name, county, basin, field_name |

**Unique constraint**: `(api_number, state_code)`

### 4. `documents`

Every scraped document (PDF, XLSX, CSV, HTML) with full provenance tracking.

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID PK | |
| `well_id` | UUID FK | References `wells(id)` |
| `state_code` | VARCHAR(2) FK | References `states(code)` |
| `scrape_job_id` | UUID FK | References `scrape_jobs(id)` |
| `doc_type` | doc_type_enum | `well_permit`, `completion_report`, `production_report`, `spacing_order`, `pooling_order`, `plugging_report`, `inspection_record`, `incident_report`, `other` |
| `status` | document_status_enum | `discovered` through `stored`, plus failure states |
| `source_url` | TEXT | Original scrape URL |
| `file_path` | TEXT | Local path: `data/{state}/{operator}/{doc_type}/{filename}` |
| `file_hash` | VARCHAR(64) UNIQUE | SHA-256 for deduplication |
| `file_format` | VARCHAR(20) | `pdf`, `xlsx`, `csv`, `html` |
| `file_size_bytes` | BIGINT | |
| `confidence_score` | NUMERIC(5,4) | Document-level confidence 0.0000-1.0000 |
| `ocr_confidence` | NUMERIC(5,4) | OCR-specific confidence from PaddleOCR |
| `classification_method` | VARCHAR(50) | `rule_based`, `ocr_keyword`, `manual` |
| `document_date` | DATE | Date on the document itself |
| `scraped_at` | TIMESTAMPTZ | When downloaded |
| `processed_at` | TIMESTAMPTZ | When extraction completed |
| `raw_metadata` | JSONB | Original scrape metadata |
| `search_vector` | TSVECTOR | Full-text on doc_type, state_code, raw_metadata fields |

### 5. `extracted_data`

Structured data extracted from documents. One document may produce multiple rows (e.g., one per month in a production report). The `data` JSONB column holds fields that vary by document type.

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID PK | |
| `document_id` | UUID FK | References `documents(id)` ON DELETE CASCADE |
| `well_id` | UUID FK | References `wells(id)` |
| `data_type` | VARCHAR(50) | `production`, `permit`, `completion`, etc. |
| `data` | JSONB | The extracted fields -- varies by data_type (see JSONB examples below) |
| `field_confidence` | JSONB | Per-field scores: `{"oil_bbl": 0.97, "gas_mcf": 0.92}` |
| `confidence_score` | NUMERIC(5,4) | Overall extraction confidence |
| `extractor_used` | VARCHAR(100) | `paddleocr`, `tabula`, `regex`, `manual` |
| `extraction_version` | VARCHAR(20) | Version of extraction logic |
| `reporting_period_start` | DATE | For production data |
| `reporting_period_end` | DATE | For production data |
| `extracted_at` | TIMESTAMPTZ | |

**JSONB `data` column examples by data_type**:

```json
// data_type = 'production'
{"reporting_month": "2025-06", "oil_bbl": 1250, "gas_mcf": 3400, "water_bbl": 890, "days_produced": 30}

// data_type = 'permit'
{"permit_number": "DP-2025-00456", "permit_date": "2025-03-15", "permit_type": "new_drill", "proposed_depth": 12000, "target_formation": "Wolfcamp A"}

// data_type = 'completion'
{"completion_date": "2025-06-01", "total_depth_md": 22500, "lateral_length": 10000, "frac_stages": 45, "ip_oil_bbl": 1200}
```

### 6. `review_queue`

Low-confidence documents flagged for manual review. Addresses the strict data quality policy.

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID PK | |
| `document_id` | UUID FK | References `documents(id)` ON DELETE CASCADE |
| `extracted_data_id` | UUID FK | References `extracted_data(id)` ON DELETE CASCADE |
| `status` | review_status_enum | `pending`, `approved`, `rejected`, `corrected` |
| `reason` | TEXT | Why flagged: `low_confidence`, `ocr_quality`, `anomaly` |
| `flag_details` | JSONB | Specific fields/values that triggered the flag |
| `document_confidence` | NUMERIC(5,4) | Confidence at time of flagging |
| `field_confidences` | JSONB | Snapshot of per-field confidence |
| `reviewed_by` | VARCHAR(100) | Who reviewed (no auth -- just a name) |
| `reviewed_at` | TIMESTAMPTZ | |
| `corrections` | JSONB | `{"field_name": {"old": "...", "new": "..."}}` |
| `notes` | TEXT | |

### 7. `scrape_jobs`

Tracks on-demand scrape jobs triggered from the dashboard.

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID PK | |
| `state_code` | VARCHAR(2) FK | NULL means all states |
| `status` | scrape_job_status_enum | `pending`, `running`, `completed`, `failed`, `cancelled` |
| `job_type` | VARCHAR(50) | `full`, `incremental`, `targeted` |
| `parameters` | JSONB | Filters, date range, etc. |
| `total_documents` | INTEGER | |
| `documents_found` | INTEGER | Progress counters |
| `documents_downloaded` | INTEGER | |
| `documents_processed` | INTEGER | |
| `documents_failed` | INTEGER | |
| `started_at` | TIMESTAMPTZ | |
| `finished_at` | TIMESTAMPTZ | |
| `errors` | JSONB | Array of `{url, error, timestamp}` objects |

### 8. `data_corrections`

Audit trail for manual corrections made via the review queue.

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID PK | |
| `extracted_data_id` | UUID FK | References `extracted_data(id)` ON DELETE CASCADE |
| `review_queue_id` | UUID FK | References `review_queue(id)` |
| `field_path` | VARCHAR(255) | JSON path to the corrected field |
| `old_value` | JSONB | |
| `new_value` | JSONB | |
| `corrected_by` | VARCHAR(100) | |
| `corrected_at` | TIMESTAMPTZ | |

---

## Key Patterns

### API Number Storage

- **Format**: VARCHAR(14), stored without dashes, zero-padded. e.g. `42501201300300`
- **Generated column**: `api_10 VARCHAR(10) GENERATED ALWAYS AS (LEFT(api_number, 10)) STORED` -- first 10 digits for cross-referencing between systems that use different API lengths
- **Why VARCHAR not INTEGER**: Leading zeros (state code `02` = Alaska), some states have non-numeric suffixes
- **Normalization on insert**: Strip dashes/spaces, zero-pad to at least 10 digits
- **Unique constraint**: `(api_number, state_code)` -- some states reuse short API numbers with different sidetrack codes

### Dual Location Storage

Three forms for different use cases:

| Column | Type | Used For |
|--------|------|----------|
| `latitude` | DOUBLE PRECISION | Display, CSV export, human-readable |
| `longitude` | DOUBLE PRECISION | Display, CSV export, human-readable |
| `location` | GEOMETRY(Point, 4326) | Spatial indexing, bounding box queries, distance calculations |

Auto-sync trigger populates `location` from lat/long:

```sql
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
```

### Full-Text Search

Tsvector columns with weighted triggers on `wells`, `documents`, and `operators`:

- **wells.search_vector**: api_number (A), well_name (A), lease_name (B), county (C), basin (C), field_name (C)
- **operators.search_vector**: name (A), normalized_name (A), aliases (B)
- **documents.search_vector**: doc_type (A), state_code (B), raw_metadata fields (B/C)

Query pattern:

```sql
SELECT * FROM wells
WHERE search_vector @@ plainto_tsquery('english', :query)
ORDER BY ts_rank(search_vector, plainto_tsquery('english', :query)) DESC;
```

Trigram indexes (`pg_trgm`) on `api_number`, `lease_name`, and `operator.name` enable fuzzy/typo-tolerant search via `%` and `similarity()`.

### JSONB for Flexible Extracted Data

Different document types produce different extracted fields. The `extracted_data.data` JSONB column stores these without schema rigidity. GIN indexes enable efficient queries into JSONB:

```sql
-- Find all extracted data where oil production exceeded 1000 bbl
SELECT * FROM extracted_data
WHERE data @> '{"oil_bbl": 1000}'::jsonb;

-- Query nested JSONB with path operators
SELECT * FROM extracted_data
WHERE data->>'target_formation' = 'Wolfcamp A';
```

### Confidence Scores

Three-level confidence scoring system:

1. **OCR Confidence** (`documents.ocr_confidence` NUMERIC(5,4)): Set by PaddleOCR during text extraction
2. **Field Confidence** (`extracted_data.field_confidence` JSONB): Per-field scores, e.g. `{"oil_bbl": 0.97, "operator_name": 0.65}`
3. **Document Confidence** (`documents.confidence_score` NUMERIC(5,4)): Aggregate of OCR + average field confidence

**Threshold**: 0.80 (configurable). Documents or fields below threshold are flagged to `review_queue`.

### Enum Types

```sql
doc_type_enum:         well_permit | completion_report | production_report | spacing_order |
                       pooling_order | plugging_report | inspection_record | incident_report | other
document_status_enum:  discovered | downloading | downloaded | classifying | classified |
                       extracting | extracted | normalized | stored | flagged_for_review |
                       download_failed | classification_failed | extraction_failed
scrape_job_status_enum: pending | running | completed | failed | cancelled
review_status_enum:     pending | approved | rejected | corrected
well_status_enum:       active | inactive | plugged | permitted | drilling | completed |
                       shut_in | temporarily_abandoned | unknown
```

---

## Key Indexes

### Wells (most heavily indexed table)

```sql
idx_wells_api_number       -- B-tree on api_number (primary search pattern)
idx_wells_api_10           -- B-tree on api_10 (cross-reference lookups)
idx_wells_api_trgm         -- GIN trigram on api_number (fuzzy/partial search)
idx_wells_operator         -- B-tree on operator_id
idx_wells_state_county     -- B-tree on (state_code, county)
idx_wells_status           -- B-tree on well_status
idx_wells_lease_trgm       -- GIN trigram on lease_name (fuzzy search)
idx_wells_location_gist    -- GiST on location (spatial/map queries)
idx_wells_search           -- GIN on search_vector (full-text)
idx_wells_metadata_gin     -- GIN on metadata (JSONB path queries)
idx_wells_alt_ids_gin      -- GIN on alternate_ids (JSONB path queries)
```

### Documents

```sql
idx_documents_state_type   -- B-tree on (state_code, doc_type)
idx_documents_well         -- B-tree on well_id
idx_documents_scrape_job   -- B-tree on scrape_job_id
idx_documents_date         -- B-tree on document_date
idx_documents_status       -- B-tree on status
idx_documents_source_url   -- HASH on source_url
idx_documents_search       -- GIN on search_vector
idx_documents_metadata_gin -- GIN on raw_metadata
```

### Extracted Data

```sql
idx_extracted_document       -- B-tree on document_id
idx_extracted_well           -- B-tree on well_id
idx_extracted_data_type      -- B-tree on data_type
idx_extracted_period         -- B-tree on (reporting_period_start, reporting_period_end)
idx_extracted_data_gin       -- GIN on data (JSONB path queries)
idx_extracted_confidence_gin -- GIN on field_confidence
```

---

## PostGIS Specifics

### Extension Setup

The initial Alembic migration enables PostGIS before any spatial columns are created:

```sql
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS pg_trgm;
```

### SRID 4326 (WGS84)

All spatial data uses SRID 4326 (WGS84 -- standard GPS coordinate system). Always specify SRID when creating points:

```sql
ST_SetSRID(ST_MakePoint(longitude, latitude), 4326)
```

Note the parameter order: **longitude first, latitude second** (x, y).

### Map Viewport Query (Bounding Box)

The primary map query, called on every pan/zoom:

```sql
SELECT w.id, w.api_number, w.well_name, w.latitude, w.longitude, w.well_status
FROM wells w
WHERE w.location && ST_MakeEnvelope(:min_lng, :min_lat, :max_lng, :max_lat, 4326)
ORDER BY w.api_number
LIMIT :limit;
```

The `&&` operator uses the GiST index for a bounding-box-only check (no full geometry computation). Returns in <10ms for ~500K wells.

### Distance Query

```sql
-- Wells within 5 miles of a point
SELECT w.id, w.api_number,
    ST_Distance(w.location::geography, ST_SetSRID(ST_MakePoint(:lng, :lat), 4326)::geography) AS distance_meters
FROM wells w
WHERE ST_DWithin(
    w.location::geography,
    ST_SetSRID(ST_MakePoint(:lng, :lat), 4326)::geography,
    8046.72  -- 5 miles in meters
)
ORDER BY distance_meters;
```

### Nearest Neighbor (KNN)

```sql
SELECT w.id, w.api_number,
    w.location <-> ST_SetSRID(ST_MakePoint(:lng, :lat), 4326) AS distance
FROM wells w
WHERE w.location IS NOT NULL
ORDER BY w.location <-> ST_SetSRID(ST_MakePoint(:lng, :lat), 4326)
LIMIT 10;
```

### Docker Image

Use `postgis/postgis:16-3.4` for the database container. PostGIS extension is enabled in the initial migration, not in Docker config.

---

## Alembic Migrations

### Source of Truth

SQLAlchemy 2.0 async models (in `app/models/`) are the source of truth. The schema DDL is derived from these models via Alembic autogeneration.

### Creating a New Migration

```bash
# Generate migration from model changes
alembic revision --autogenerate -m "description of change"

# Apply migrations
alembic upgrade head

# Rollback one step
alembic downgrade -1
```

### Async Configuration

Alembic is configured for async SQLAlchemy with `asyncpg` driver:

- Connection string: `postgresql+asyncpg://og_user:og_password@localhost:5432/og_scraper`
- `alembic/env.py` uses `async_engine_from_config` and `asyncio.run()` to run migrations
- All models are imported in `env.py` so autogenerate detects them

### Migration Runs on Startup

In Docker, migrations run automatically on backend container startup before the FastAPI app begins serving requests.

### Initial Migration Structure

The initial migration (`001_initial_schema.py`):
1. Creates PostGIS, uuid-ossp, and pg_trgm extensions
2. Creates all enum types
3. Creates all 8 tables with columns, constraints, and defaults
4. Creates all indexes
5. Creates trigger functions and triggers (search vectors, location sync)
6. Seeds the `states` table with the 10 supported states

### Naming Convention

Alembic uses a consistent naming convention for constraints:

```python
naming_convention = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}
```

---

## Common Pitfalls

1. **PostGIS extension must be enabled before creating spatial columns**. If a migration adds a GEOMETRY column, ensure a prior migration (or the same one, earlier) runs `CREATE EXTENSION IF NOT EXISTS postgis`.

2. **Always use SRID 4326 (WGS84)** for lat/long coordinates. Mixing SRIDs causes silent incorrect results in spatial queries.

3. **ST_MakePoint takes longitude first, latitude second** (`ST_MakePoint(lng, lat)`). This is the opposite of how most people say "lat/long".

4. **API number format varies by state** but always store as a 14-digit zero-padded string without dashes. Strip and normalize on input. The generated `api_10` column handles cross-referencing between systems using different lengths.

5. **JSONB queries need proper indexing**. Always use GIN indexes with `jsonb_path_ops` for `@>` containment queries. Without the index, JSONB queries do full table scans.

6. **Cast to `::geography` for distance in meters**. Without the cast, `ST_Distance` and `ST_DWithin` operate in degrees (SRID 4326 units), not meters. Always cast both geometries to geography for real-world distance calculations.

7. **Confidence scores are NUMERIC(5,4)**, range 0.0000 to 1.0000. Do not store percentages (0-100) -- always use the 0-1 decimal scale.

8. **Tsvector triggers must be updated** when adding new searchable columns. If you add a column that should be searchable, update the corresponding trigger function.

9. **The `documents.scrape_job_id` FK is added via ALTER TABLE** because `scrape_jobs` is defined after `documents`. Keep this ordering in mind for migrations.

10. **UUID primary keys** use `uuid_generate_v4()` from the `uuid-ossp` extension. Ensure the extension is created before any table with UUID defaults.

---

## Testing

Use **testcontainers** with the `postgis/postgis:16-3.4` Docker image for integration tests. This spins up a real PostgreSQL+PostGIS instance per test session, ensuring spatial queries and triggers work identically to production.

```python
# pytest fixture pattern
import pytest
from testcontainers.postgres import PostgresContainer

@pytest.fixture(scope="session")
def postgres_container():
    with PostgresContainer("postgis/postgis:16-3.4") as pg:
        yield pg
```

Test dependencies: `pytest`, `pytest-asyncio`, `testcontainers`.

---

## References

- **Full schema DDL, indexes, triggers, and FastAPI backend**: [backend-schema-implementation.md](../../orchestration-og-doc-scraper/research/backend-schema-implementation.md)
- **Oil and gas data models, API number format, domain knowledge**: [og-data-models.md](../../orchestration-og-doc-scraper/research/og-data-models.md)
- **Project discovery and requirements**: [DISCOVERY.md](../../orchestration-og-doc-scraper/DISCOVERY.md)
