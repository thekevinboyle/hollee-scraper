# Synergy Review: Oil & Gas Document Scraper

**Date**: 2026-03-28
**Scope**: All 33 task files (phases 1-7), PHASES.md, DISCOVERY.md
**Status**: Complete

---

## 1. CONTRADICTIONS

### Issue 1.1: API Endpoint Path Prefix Inconsistency (PHASES.md vs Task Files)

**Severity**: HIGH

PHASES.md (lines 418-425) defines endpoint paths WITHOUT the `/v1/` prefix:
```
GET /api/wells?state=TX
GET /api/documents?state=...
GET /api/map/wells?bbox=...
```

Task 3.1 and all other Phase 3 task files define endpoints WITH the `/v1/` prefix:
```
GET /api/v1/wells
GET /api/v1/documents
GET /api/v1/map/wells
```

Task 1.4 explicitly creates an `api_v1_router` with `prefix="/api/v1"`.

The PHASES.md contracts in Phase 4.R also omit the prefix:
```
GET /api/wells?state=PA
GET /api/documents?state=CO&type=PRODUCTION_REPORT
```

Meanwhile, the frontend code in Tasks 5.2-5.5 correctly uses `/api/v1/...` paths through the API proxy.

**Fix**: Edit `PHASES.md` -- change all endpoint references from `/api/wells`, `/api/documents`, `/api/map/wells`, `/api/scrape`, `/api/review`, `/api/states`, `/api/operators`, `/api/export` to their `/api/v1/` prefixed versions. Specifically update lines in Phase 3 contracts section, Phase 4.R testing section, Phase 5 contracts sections, and Phase 6.R testing section.

---

### Issue 1.2: SSE Endpoint Path Inconsistency Across Documents

**Severity**: MEDIUM

The SSE endpoint path varies across documents:

- PHASES.md (line 452): `GET /api/scrape/{job_id}/progress`
- PHASES.md (line 734): `GET /api/scrape/{job_id}/progress`
- Task 3.2 (implementation): `GET /api/v1/scrape/jobs/{id}/events`
- Task 5.4 contracts: `GET /api/v1/scrape/jobs/{id}/events`
- Task 5.4 hook code: `${sseBaseUrl}/api/v1/scrape/jobs/${jobId}/events`

PHASES.md uses `/progress` while the actual task implementation uses `/events`. Also, PHASES.md omits the `jobs/` path segment.

**Fix**: Edit PHASES.md lines 452 and 734 to use `GET /api/v1/scrape/jobs/{job_id}/events` to match the Task 3.2 implementation.

---

### Issue 1.3: Review Queue Action Endpoint Path Contradiction

**Severity**: MEDIUM

PHASES.md (lines 478-480) defines three separate action endpoints:
```
POST /api/review/{id}/approve
POST /api/review/{id}/correct
POST /api/review/{id}/reject
```

Task 3.3 implements a single unified endpoint:
```
PATCH /api/v1/review/{id}
```
with the action specified in the request body `{ status: "approved" | "rejected" | "corrected" }`.

Task 5.5 contracts (PHASES.md lines 766-769) revert to the three-endpoint pattern:
```
POST /api/review/{id}/approve
POST /api/review/{id}/correct
POST /api/review/{id}/reject
```

**Fix**: Update PHASES.md Phase 3.3 and Phase 5.5 contracts to use `PATCH /api/v1/review/{id}` with action in body, matching Task 3.3's actual implementation.

---

### Issue 1.4: Confidence Column Precision Mismatch

**Severity**: MEDIUM

PHASES.md (line 170) specifies: `Confidence: DECIMAL(4,3) (0.000 to 1.000)`

Task 1.2 (line 323-324 in document model) uses: `NUMERIC(5, 4)` -- which gives range 0.0000 to 9.9999.

Task 1.R (line 374) references: `NUMERIC(5,4)`

The `DECIMAL(4,3)` from PHASES.md would only support 0.000 to 9.000, while `NUMERIC(5,4)` in the actual schema supports 0.0000 to 9.9999. Both are technically wrong for a 0.0-1.0 confidence score (neither constrains the upper bound). But the precision differs: 3 vs 4 decimal places.

**Fix**: Standardize on `NUMERIC(5, 4)` as used in Task 1.2 (higher precision is better for confidence scoring). Update PHASES.md line 170 to read `NUMERIC(5,4) (0.0000 to 1.0000)`.

---

### Issue 1.5: DocumentType Enum Value Mismatch

**Severity**: MEDIUM

PHASES.md Task 2.2 (line 306) defines a `DocumentType` enum with values including `UNKNOWN`.

Task 1.2's `DocType` enum (line 111) has `OTHER = "other"` but no `UNKNOWN`.

Task 2.2's ClassificationResult (line 46) uses `doc_type: str` with values like `"unknown"`.

The pipeline classifier will emit `"unknown"` for unclassifiable documents, but the database enum (`DocType`) only has `OTHER`, not `UNKNOWN`. This will cause a database insertion error if the pipeline tries to store a document classified as `"unknown"` with the enum.

Also, PHASES.md lists `SPACING_ORDER` as a single type, but Task 1.2 splits it into `SPACING_ORDER` and `POOLING_ORDER` (separate values). PHASES.md Task 2.2 only mentions `SPACING_ORDER` in the enum.

**Fix**:
1. Add `UNKNOWN = "unknown"` to the `DocType` enum in Task 1.2 (`backend/src/og_scraper/models/enums.py`), OR map `"unknown"` to `DocType.OTHER` in the pipeline's storage stage.
2. Task 2.2's `ClassificationResult.doc_type` should use the `DocType` enum type or string values that match the database enum exactly.

---

### Issue 1.6: Database Credentials Mismatch

**Severity**: LOW

PHASES.md (line 133) specifies:
```
DATABASE_URL: postgresql+asyncpg://postgres:postgres@db:5432/ogdocs
```

Task 1.1 Docker Compose uses:
```
POSTGRES_USER=${POSTGRES_USER:-ogdocs}
POSTGRES_PASSWORD=${POSTGRES_PASSWORD:-ogdocs_dev}
```

So the actual default URL is `postgresql+asyncpg://ogdocs:ogdocs_dev@db:5432/ogdocs`, not `postgres:postgres`.

**Fix**: Update PHASES.md line 133-134 to use `ogdocs:ogdocs_dev` credentials matching Task 1.1.

---

### Issue 1.7: Pagination Response Field Name Inconsistency

**Severity**: LOW

PHASES.md (line 426): `{items: [], total: int, page: int, per_page: int, pages: int}`

Task 3.1 PaginatedResponse (line 122-123): `{items, total, page, page_size, total_pages}`

The field names differ: `per_page` vs `page_size`, `pages` vs `total_pages`.

**Fix**: Update PHASES.md to use `page_size` and `total_pages` matching Task 3.1.

---

## 2. DATA CONTRACTS ALIGNMENT

### Issue 2.1: Scrape POST Body Structure Inconsistency

**Severity**: HIGH

PHASES.md (line 450):
```
POST /api/scrape body: {state: str|"all", search_params?: {operator?, api_number?, county?}}
```

Task 3.2 ScrapeJobCreate schema (lines 49-63):
```python
class ScrapeJobCreate(BaseModel):
    state_code: Optional[str]  # None = all states
    job_type: str = "full"
    parameters: dict = {}
```

Key differences:
- Field name: `state` vs `state_code`
- "All states" representation: `"all"` string vs `None`
- Search params: `search_params` nested object vs `parameters` flat dict

The frontend (Task 5.4 line 174) hardcodes `state_code` in the request body, which matches Task 3.2 but not PHASES.md.

**Fix**: Update PHASES.md line 450 to match Task 3.2: `{state_code: str|null, job_type?: str, parameters?: dict}`.

---

### Issue 2.2: Huey Instance Duplication

**Severity**: HIGH

Task 1.4 creates `og_scraper.worker.huey_app` as the Huey SqliteHuey instance.

Task 3.2 Step 2 creates a SEPARATE Huey instance in `og_scraper.tasks.__init__`:
```python
from huey import SqliteHuey
huey = SqliteHuey("og-scraper", filename="data/huey.db")
```

This means there are TWO separate Huey instances. The worker process (docker-compose `entrypoint`) references `og_scraper.worker.huey_app`, but Task 3.2's scrape tasks are decorated with `@huey.task()` from `og_scraper.tasks`. These are different objects, so tasks enqueued via `og_scraper.tasks.huey` will NOT be picked up by the worker running `og_scraper.worker.huey_app`.

**Fix**: Task 3.2 should import and use the existing `huey_app` from `og_scraper.worker` instead of creating a new instance:
```python
# backend/src/og_scraper/tasks/__init__.py
from og_scraper.worker import huey_app as huey
```
OR the worker entrypoint in docker-compose.yml should reference `og_scraper.tasks.huey` instead. One canonical Huey instance must be used everywhere.

---

### Issue 2.3: Sync Database URL Access Pattern in Huey Tasks

**Severity**: MEDIUM

Task 3.2 (line 124) references `settings.SYNC_DATABASE_URL` (uppercase attribute).

Task 1.4 Settings class (line 63) defines it as `sync_database_url` (lowercase).

Pydantic settings uses lowercase attribute names. `settings.SYNC_DATABASE_URL` will raise `AttributeError`.

**Fix**: Change Task 3.2 line 124 to `settings.sync_database_url`.

---

### Issue 2.4: Spider Output (DocumentItem) vs Pipeline Input Mismatch

**Severity**: MEDIUM

Task 1.3 defines `DocumentItem` (a dataclass in `scrapers/items.py`) with fields like `file_content`, `file_path`, `file_hash`.

Task 2.4 defines `DocumentPipeline.process(file_path: Path, state: str) -> ProcessingResult` which takes a file path on disk.

The spider yields `DocumentItem` objects through Scrapy pipelines, which save the file to disk. But the document processing pipeline (Phase 2) expects a file path, not a `DocumentItem`.

The bridge between these is missing. The Huey task in Task 3.2 needs to:
1. Take the `file_path` from the `DocumentItem` (after Scrapy storage pipeline writes to disk)
2. Call `DocumentPipeline.process(file_path, state)`
3. Store the `ProcessingResult` in the database

This bridge logic is not explicitly defined in any task. Task 3.2 has placeholder `pass` statements where this integration should happen.

**Fix**: Add explicit bridge logic to Task 3.2's `run_scrape_job` or `process_document` tasks that maps `DocumentItem.file_path` to `DocumentPipeline.process()` input. Alternatively, add a note to Task 3.2 implementation plan specifying this integration clearly.

---

### Issue 2.5: ProcessingResult to Database Storage Mapping Undefined

**Severity**: MEDIUM

Task 2.4 produces `ProcessingResult` with fields: `disposition`, `doc_type`, `score` (DocumentScore), `field_extraction`, `classification`, `text_extraction`, `normalized_fields`, `raw_text`.

None of the task files explicitly define HOW `ProcessingResult` maps to the database tables (`documents`, `extracted_data`, `review_queue`). The mapping is assumed but never documented:

- `ProcessingResult.doc_type` -> `documents.doc_type`
- `ProcessingResult.score.document_confidence` -> `documents.confidence_score`
- `ProcessingResult.score.ocr_confidence` -> `documents.ocr_confidence`
- `ProcessingResult.normalized_fields` -> `extracted_data.data` (JSONB)
- `ProcessingResult.score.field_confidences` -> `extracted_data.field_confidence` (JSONB)
- `ProcessingResult.disposition == "review"` -> create `review_queue` entry

**Fix**: Add a "Database Storage Mapping" section to Task 2.4 or Task 3.2 that explicitly maps `ProcessingResult` fields to database columns.

---

### Issue 2.6: Well Lookup Endpoint Inconsistency

**Severity**: LOW

PHASES.md Task 3.1 (line 419): `GET /api/wells/{id}` -- retrieves by UUID `id`
Task 3.1 Step 5 implementation: `GET /api/v1/wells` with filters, `GET /api/v1/wells/{api_number}` -- retrieves by API number

Task 5.2 (line 85): `useWellDetail(apiNumber)` fetches `/api/v1/wells/${apiNumber}` -- by API number

These are inconsistent. PHASES.md says `{id}` (UUID), but the implementation uses `{api_number}`. The frontend expects API number lookup.

**Fix**: Standardize on API number lookup as primary (matching frontend needs). Update PHASES.md to `GET /api/v1/wells/{api_number}`. Optionally add a separate `GET /api/v1/wells/by-id/{id}` for internal use.

---

## 3. DEPENDENCY CORRECTNESS

### Issue 3.1: Task 3.2 Missing Dependency on Task 2.4

**Severity**: HIGH

Task 3.2 (Scrape Job Endpoints & Huey Integration) processes documents through the pipeline inside its Huey task. It needs to call `DocumentPipeline.process()` from Phase 2.

PHASES.md declares Task 3.2 as blocked by 3.1 and 1.3. Task 3.2's own "Blocked By" section says "Task 3.1, Task 1.3".

But Task 3.2 actually needs Task 2.4 (the complete pipeline). Without it, the scrape task cannot process downloaded documents.

**Fix**: Add Task 2.4 to Task 3.2's "Blocked By" list. This is already partially implied (Task 3.2 mentions "pipeline" in its context), but the explicit dependency is missing.

---

### Issue 3.2: Task 5.5 Missing File Serving Endpoint Dependency

**Severity**: HIGH

Task 5.5 (Review Queue & Document Viewer) renders PDFs using `react-pdf` with a `fileUrl` prop set to `/api/v1/documents/{id}/file`.

Task 3.3 (line 212) constructs this URL: `file_url = f"/api/v1/documents/{review.document_id}/file"`.

But **no task explicitly creates the `GET /api/v1/documents/{id}/file` endpoint**. Task 3.1 creates document list/detail endpoints but does not mention a file serving endpoint. Task 3.3 assumes it exists. Task 5.5 depends on it.

PHASES.md Task 3.1 mentions `GET /documents/{id}` for detail but not `GET /documents/{id}/file`.

The research findings for Task 3.1 (line 29) mention: "Section 3.5: File serving pattern using FileResponse with MIME type detection" -- but this is never assigned to any task.

**Fix**: Add a file-serving endpoint `GET /api/v1/documents/{id}/file` to Task 3.1's implementation plan. It should use FastAPI's `FileResponse` to serve the document from the file path stored in `documents.file_path`. Add this to Task 3.1's endpoint list and test plan.

---

### Issue 3.3: Task 2.3 Lists Incorrect Dependency

**Severity**: LOW

Task 2.3 "Blocked By" says "Task 2.1, Task 1.2". But looking at what it actually uses:
- It needs text from Task 2.1 (correct)
- It needs document type from Task 2.2 (the classifier) -- `doc_type: DocumentType, state: str` as parameters
- Task 1.2 is listed for "database schema defines target fields" but Task 2.3 does not write to the database

Task 2.3's `DataExtractor.extract()` takes `doc_type` as a parameter, which comes from Task 2.2's classifier output. So Task 2.2 should be in the dependency chain (and PHASES.md correctly shows 2.3 blocked by 2.1, but also 1.2 for target field names).

**Fix**: Add Task 2.2 to Task 2.3's "Blocked By" section (or at minimum to Dependencies). The extraction patterns depend on knowing the document type from classification.

---

## 4. TESTING ALIGNMENT

### Issue 4.1: Test File Path Inconsistency

**Severity**: MEDIUM

Task 1.R expects tests at `backend/tests/test_scrapers/test_base_spider.py` (with `test_scrapers/` prefix).

Task 1.3 creates tests at `backend/tests/test_scrapers/test_base_spider.py`.

But Task 4.1 expects scraper tests at `backend/tests/scrapers/test_pa_spider.py` (no `test_` prefix on directory).

VCR cassettes are at `backend/tests/scrapers/cassettes/pa/` (no `test_` prefix).

Both patterns are used inconsistently:
- `backend/tests/test_scrapers/` (Phase 1 tasks)
- `backend/tests/scrapers/` (Phase 4+ tasks)
- `backend/tests/test_api/` (Phase 1)
- `backend/tests/api/` (Phase 3)
- `backend/tests/pipeline/` (Phase 2)

**Fix**: Standardize all test directories. Recommend using `backend/tests/` with subdirectories matching source layout (no `test_` prefix on directories since they're already inside `tests/`):
- `backend/tests/api/` (not `test_api/`)
- `backend/tests/scrapers/` (not `test_scrapers/`)
- `backend/tests/pipeline/`
- `backend/tests/utils/` (not `test_utils/`)
- `backend/tests/e2e/`
- `backend/tests/regression/`

Update Task 1.3, Task 1.4, and Task 1.R to use the consistent non-prefixed convention.

---

### Issue 4.2: Phase 2 Test Fixtures Location Unclear

**Severity**: MEDIUM

Task 2.1 lists fixture files at `backend/tests/fixtures/sample_text.pdf` and `backend/tests/fixtures/sample_scan.pdf`.

Task 2.R generates fixtures programmatically in `backend/tests/pipeline/conftest.py` using `tmp_path`.

These are two different approaches. Task 2.1 implies static fixtures checked into the repo. Task 2.R generates them at test time. If Task 2.1's tests depend on static fixture files at `backend/tests/fixtures/`, those files need to be created (either committed to git or generated in conftest).

**Fix**: Task 2.1 should generate test PDFs programmatically (like Task 2.R does) rather than expecting pre-existing static fixtures. Update Task 2.1 to include a conftest.py that generates `sample_text.pdf` and `sample_scan.pdf` using PyMuPDF. Alternatively, add a step to Task 2.1 to create these static fixtures.

---

### Issue 4.3: Phase 5.R Health Endpoint Path Wrong

**Severity**: LOW

Task 5.R (line 48) checks:
```bash
curl http://localhost:8000/api/v1/health
```

But the health endpoint is at root level (not under `/api/v1`):
- Task 1.4 mounts health at `GET /health`
- Task 1.4 routes/__init__.py: "Health is at root level (not versioned)"

**Fix**: Change Task 5.R line 48 to `curl http://localhost:8000/health`.

---

## 5. GAPS

### Issue 5.1: Alembic Migration Not Auto-Run on Docker Startup

**Severity**: CRITICAL

No task or Docker Compose configuration runs `alembic upgrade head` automatically when the backend container starts. The backend Dockerfile CMD is:
```
CMD ["uv", "run", "uvicorn", "og_scraper.api.app:create_app", "--factory", ...]
```

Task 1.R Step 3 explicitly says `# Run migrations (if not auto-run)` and manually runs:
```bash
docker compose exec backend uv run alembic upgrade head
```

This means every fresh `docker compose up` requires a manual migration step. For a tool targeting a non-technical coworker (DISCOVERY D16), this is a significant usability gap.

**Fix**: Add a startup script to the backend Dockerfile or an entrypoint that runs `alembic upgrade head` before starting uvicorn. Example:
```dockerfile
# backend/Dockerfile.dev
COPY scripts/start.sh /app/start.sh
CMD ["/app/start.sh"]
```
```bash
# backend/scripts/start.sh
#!/bin/bash
uv run alembic upgrade head
uv run uvicorn og_scraper.api.app:create_app --factory --host 0.0.0.0 --port 8000 --reload
```
Add this to Task 1.1's implementation plan (Docker Compose section) or Task 1.2 (Alembic section).

---

### Issue 5.2: State Seed Data Creation Location Unclear

**Severity**: HIGH

Task 1.2 mentions seeding 10 states. Task 1.R Step 3 verifies:
```bash
docker compose exec db psql -U ogdocs -d ogdocs -c "SELECT code, name, tier FROM states ORDER BY code;"
# Expected: AK, CA, CO, LA, ND, NM, OK, PA, TX, WY
```

But Task 1.2's implementation plan does NOT include a data seeding step. The Alembic migration file (`001_initial_schema.py`) is defined as creating tables, but no INSERT statements for states are shown.

Where are the 10 states seeded? Options:
- In the Alembic migration (data migration)
- In a separate seed script
- In the FastAPI lifespan startup

None of these are explicitly implemented in any task.

**Fix**: Add explicit state seeding to Task 1.2. The recommended approach is to add INSERT statements for the 10 states at the end of the `001_initial_schema.py` Alembic migration:
```python
op.execute("""
INSERT INTO states (code, name, api_state_code, tier) VALUES
('AK', 'Alaska', '02', 2),
('CA', 'California', '04', 2),
('CO', 'Colorado', '05', 1),
('LA', 'Louisiana', '17', 2),
('ND', 'North Dakota', '35', 1),
('NM', 'New Mexico', '32', 1),
('OK', 'Oklahoma', '37', 1),
('PA', 'Pennsylvania', '39', 2),
('TX', 'Texas', '42', 1),
('WY', 'Wyoming', '49', 2);
""")
```

---

### Issue 5.3: Document File Serving Endpoint Never Defined

**Severity**: HIGH

(Same as Issue 3.2, restated as a gap)

The `GET /api/v1/documents/{id}/file` endpoint is referenced by:
- Task 3.3 (review detail constructs `file_url`)
- Task 5.5 (DocumentViewer component `fileUrl` prop)
- PHASES.md Task 5.5 contracts

But no task creates this endpoint. It is a gap in Task 3.1 or should be a separate sub-task.

**Fix**: Add to Task 3.1 implementation plan:
```python
@router.get("/{document_id}/file")
async def get_document_file(document_id: UUID, db: AsyncSession = Depends(get_db)):
    doc = await db.get(Document, document_id)
    if not doc or not doc.file_path:
        raise HTTPException(404)
    file_path = Path(settings.documents_dir) / doc.file_path
    if not file_path.exists():
        raise HTTPException(404)
    return FileResponse(file_path, media_type="application/pdf")
```

---

### Issue 5.4: Test PDF Fixtures Never Created

**Severity**: MEDIUM

Task 2.1 lists test fixtures: `backend/tests/fixtures/sample_text.pdf` and `backend/tests/fixtures/sample_scan.pdf`. These are not generated by any task. Task 2.R generates fixtures programmatically, but only for its own regression tests using `tmp_path`.

The Phase 2 unit tests (test_text_extractor.py, etc.) need persistent fixtures.

**Fix**: Either:
1. Add a conftest.py to `backend/tests/pipeline/` that generates all needed PDFs (recommended, as done in Task 2.R), or
2. Add a step to Task 2.1 to create static test PDFs committed to the repo.

---

### Issue 5.5: DATA_DIR vs DOCUMENTS_DIR Inconsistency

**Severity**: MEDIUM

Docker Compose defines two separate environment variables:
- `DATA_DIR=/app/data`
- `DOCUMENTS_DIR=/data/documents`

These use different base paths (`/app/data` vs `/data/documents`). The storage pipeline in Task 1.3 uses `DOCUMENTS_DIR` for saving files. The Huey DB uses `DATA_DIR` for its SQLite file.

The `documents` volume in docker-compose.yml mounts to `/data/documents`, but the backend source mount is to `/app/src`. So documents are stored at `/data/documents` (a Docker volume), while `DATA_DIR` is `/app/data` (inside the backend container image).

This is not necessarily wrong but is confusing. The `FileStoragePipeline` in Task 1.3 uses `DOCUMENTS_DIR` correctly, but `data_dir` in the Settings class points to `/app/data`.

**Fix**: Add a comment to Task 1.1's Docker Compose section clarifying the two paths. Optionally simplify by making DOCUMENTS_DIR a subdirectory of DATA_DIR: `DOCUMENTS_DIR=/app/data/documents` and mounting the volume at `/app/data`.

---

### Issue 5.6: SSE URL Not Configurable for Docker Network

**Severity**: MEDIUM

Task 5.1 sets `NEXT_PUBLIC_SSE_URL=http://localhost:8000` for SSE connections that bypass the Next.js proxy.

When running inside Docker Compose, the frontend container uses `NEXT_PUBLIC_API_URL=http://localhost:${BACKEND_PORT:-8000}` for the rewrite proxy destination. But SSE connections are made from the browser (client-side), so `localhost:8000` is correct since the browser accesses the host machine.

However, if someone changes `BACKEND_PORT` to a non-8000 value, the SSE URL hardcoded to `localhost:8000` will break because `NEXT_PUBLIC_SSE_URL` in `.env.local` is static.

**Fix**: In Task 5.1, ensure `.env.local` and `.env.docker` derive `NEXT_PUBLIC_SSE_URL` from the backend port:
```
NEXT_PUBLIC_SSE_URL=http://localhost:${BACKEND_PORT:-8000}
```
And in the Docker Compose frontend service:
```yaml
- NEXT_PUBLIC_SSE_URL=http://localhost:${BACKEND_PORT:-8000}
```

---

### Issue 5.7: `ebcdic-parser` Not in Python Dependencies

**Severity**: MEDIUM

Task 6.1 references `ebcdic-parser` library and states "(already in project dependencies from Phase 1)". But Task 1.1's `backend/pyproject.toml` does NOT include `ebcdic-parser` in the dependencies list.

Similarly, Task 6.1 references `pyproj` for coordinate transformation (EPSG:3857 to EPSG:4326 for CA spider), and Task 6.3 uses it. Neither `pyproj` nor `ebcdic-parser` are in the dependency list.

Task 4.3 (OK spider) processes XLSX files using openpyxl, which is also not in the dependencies.

**Fix**: Add to Task 1.1's `backend/pyproject.toml`:
```toml
"ebcdic-parser>=0.3.0",
"pyproj>=3.7.0",
"openpyxl>=3.1.0",
```

---

### Issue 5.8: `swr` vs `@tanstack/react-query` Dependency Conflict

**Severity**: MEDIUM

Task 1.1's `frontend/package.json` includes `@tanstack/react-query` as a dependency.

Task 5.1 installs `swr` for data fetching. Tasks 5.2-5.5 all use `swr` (via `useSWR`).

Having both `@tanstack/react-query` and `swr` is redundant. The project uses `swr` throughout Phase 5 but ships `@tanstack/react-query` as an unused dependency.

**Fix**: Either remove `@tanstack/react-query` from Task 1.1's `frontend/package.json`, or switch Phase 5 tasks to use `@tanstack/react-query` instead of `swr`. Since all Phase 5 code already uses `swr`, removing `@tanstack/react-query` is the simpler fix.

---

### Issue 5.9: No Export Endpoint Defined for Dashboard Statistics

**Severity**: LOW

PHASES.md mentions a stats endpoint for the dashboard. Task 3.4 defines `DashboardStats` and `StateStats` schemas but the router implementation is not fully shown. Task 5.1 mentions stat cards on the dashboard home page.

The stats endpoint paths are not explicitly declared in the API contracts. Is it `GET /api/v1/stats`? `GET /api/v1/dashboard`?

**Fix**: Add explicit stats endpoint paths to Task 3.4: `GET /api/v1/stats` (dashboard-level) and `GET /api/v1/stats/{state_code}` (per-state). Ensure Task 5.1 references these paths in its API client.

---

## 6. CROSS-PHASE BUILD-ON ISSUES

### Issue 6.1: Phase 5 Frontend Types Not Derived from Backend Schemas

**Severity**: MEDIUM

Task 5.1 mentions creating TypeScript types in `frontend/src/lib/types.ts`. Task 5.2 imports `Well`, `PaginatedResponse` from `@/lib/types`.

But no task describes HOW these frontend types are generated or kept in sync with the backend Pydantic schemas. If someone changes a Pydantic schema in Phase 3, the frontend types won't update.

**Fix**: Add a step to Task 5.1 to manually define TypeScript interfaces that mirror the Pydantic schemas from Task 3.1. Add a comment noting these must be kept in sync. Alternatively, add an OpenAPI TypeScript code generation step using the `/openapi.json` endpoint.

---

### Issue 6.2: Phase 4 Scrapers Reference Pipeline Differently Than Phase 6

**Severity**: LOW

Phase 4 tasks (4.1-4.3) describe spiders yielding `DocumentItem` through Scrapy pipelines and then separately processing through `DocumentPipeline`.

Phase 6 tasks (6.1-6.3) describe the same pattern but also mention yielding `WellItem` objects. The Scrapy pipelines (validation, dedup, storage from Task 1.3) only handle `DocumentItem`, not `WellItem`. If Phase 6 spiders yield `WellItem`, the pipelines will pass them through without validation.

**Fix**: Either extend the Scrapy pipeline classes (Task 1.3) to handle both `DocumentItem` and `WellItem`, or add a `WellStoragePipeline` to Task 1.3's implementation plan.

---

### Issue 6.3: Phase 7.1 E2E Test Uses `Base.metadata.create_all` Instead of Alembic

**Severity**: LOW

Task 7.1 conftest.py (line 76) uses:
```python
await conn.run_sync(Base.metadata.create_all)
```

But the project uses Alembic migrations (Task 1.2), which include triggers, functions, and seed data that `create_all` won't reproduce. Specifically:
- PostGIS auto-sync trigger (location column)
- Full-text search triggers (tsvector)
- State seed data
- Generated columns (api_10)

**Fix**: Update Task 7.1 conftest to run Alembic migrations instead of `create_all`:
```python
from alembic.config import Config
from alembic import command

alembic_cfg = Config("backend/alembic.ini")
alembic_cfg.set_main_option("sqlalchemy.url", sync_database_url)
command.upgrade(alembic_cfg, "head")
```

---

### Issue 6.4: API State Code Mapping Inconsistency

**Severity**: LOW

Task 1.2 State model has `api_state_code` field (the FIPS code used in API numbers).

Task 2.3 patterns.py `VALID_API_STATE_CODES` maps FIPS codes to state abbreviations:
```python
"02": "AK", "04": "CA", "05": "CO", "17": "LA", "32": "NM",
"35": "ND", "37": "OK", "39": "PA", "42": "TX", "49": "WY"
```

Task 4.3 (OK spider research) says "OK state code `35`" and Task 4.R says "OK state code `35`" for API numbers. But the standard FIPS code for Oklahoma is `35` for ND, not OK.

Wait -- checking: the actual FIPS state codes are:
- AK=02, CA=06 (not 04), CO=08 (not 05), LA=22 (not 17), ND=38 (not 35), NM=35 (not 32), OK=37, PA=42 (not 39), TX=42, WY=56 (not 49)

But the API number system uses **API state codes**, which are different from FIPS codes. The API numbering system from AAPG has: AK=50, CA=04, CO=05, LA=17, ND=33, NM=30, OK=35, PA=37, TX=42, WY=49.

Task 2.3 patterns.py has some of these wrong. For example:
- `"02": "AK"` -- should be `"50": "AK"` (API code) or correct if using FIPS
- `"35": "ND"` -- API code for ND is 33, for OK is 35
- `"39": "PA"` -- API code for PA is 37

The mapping in patterns.py conflates FIPS codes with API state codes. This will cause API number validation failures for most states.

**Fix**: Verify and correct the `VALID_API_STATE_CODES` mapping in Task 2.3. The API numbering system uses its own codes (not FIPS). Cross-reference with AAPG API number standard. Also ensure the `api_state_code` values in the State seed data (Issue 5.2) match the same standard.

---

## SUMMARY OF CRITICAL/HIGH ISSUES

| # | Issue | Severity | Files to Fix |
|---|-------|----------|-------------|
| 5.1 | Alembic not auto-run on Docker startup | CRITICAL | Task 1.1 (docker-compose.yml, Dockerfile) |
| 2.2 | Duplicate Huey instances | HIGH | Task 3.2 (tasks/__init__.py) |
| 3.2/5.3 | Document file serving endpoint missing | HIGH | Task 3.1 (routes/documents.py) |
| 5.2 | State seed data not defined | HIGH | Task 1.2 (Alembic migration) |
| 1.1 | API path prefix inconsistency | HIGH | PHASES.md |
| 2.1 | Scrape POST body field name mismatch | HIGH | PHASES.md |
| 3.1 | Task 3.2 missing dependency on 2.4 | HIGH | Task 3.2 |
| 6.4 | API state code mapping wrong | HIGH | Task 2.3 (patterns.py), Task 1.2 (seed data) |
| 1.5 | UNKNOWN missing from DocType enum | MEDIUM | Task 1.2 (enums.py) |
| 5.7 | Missing Python dependencies | MEDIUM | Task 1.1 (pyproject.toml) |
| 5.8 | Redundant react-query + swr | MEDIUM | Task 1.1 (package.json) |
| 2.3 | Settings attribute case mismatch | MEDIUM | Task 3.2 |
| 4.1 | Test directory naming inconsistent | MEDIUM | Tasks 1.3, 1.4, 1.R |
| 1.2 | SSE endpoint path mismatch | MEDIUM | PHASES.md |
| 1.3 | Review action endpoint style mismatch | MEDIUM | PHASES.md |
| 2.4/2.5 | Pipeline-to-DB mapping undefined | MEDIUM | Task 3.2 or Task 2.4 |
