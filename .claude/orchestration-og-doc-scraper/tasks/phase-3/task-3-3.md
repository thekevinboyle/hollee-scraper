# Task 3.3: Review Queue & Data Correction Endpoints

## Objective

Implement the review queue API endpoints that enable users to list, inspect, approve, correct, and reject low-confidence documents. This includes the full data correction workflow: when a user corrects extracted data, the original values are preserved in a `data_corrections` audit trail, the `extracted_data` record is updated, and the review item status is set to `corrected`. This is the human-in-the-loop quality control layer per DISCOVERY D10 (strict rejection policy) and D15 (review queue in dashboard).

## Context

Phase 2 (Task 2.4) built the confidence scoring pipeline that routes documents with scores below 0.85 into the `review_queue` table. This task builds the API that the frontend's "Needs Review" tab consumes. Users see flagged documents with their extracted data side-by-side with the original document, then approve (data is correct), correct (fix specific fields), or reject (discard extracted data entirely).

The review queue is a core differentiator of this tool -- without it, ~10-15% of documents with mediocre OCR quality would either be silently stored with errors or silently discarded. The review queue captures that middle ground.

## Dependencies

- Task 3.1 - Core API structure (Pydantic schemas, pagination, router patterns, document/well schemas)
- Task 2.4 - Confidence scoring pipeline that populates the review_queue table
- Task 1.2 - Database models (review_queue, data_corrections, extracted_data, documents tables)

## Blocked By

- Task 3.1 (base API patterns must exist)
- Task 2.4 (pipeline must be able to populate the review_queue table)

## Research Findings

Key findings from research files relevant to this task:

- From `confidence-scoring` skill: Three dispositions: auto-accept (>= 0.85), review queue (0.50-0.84), reject (< 0.50). Review queue shows documents ordered by confidence (highest first -- easiest to review)
- From `confidence-scoring` skill: User actions are Approve, Correct, Reject. Corrections are logged in `data_corrections` table with `field_path`, `old_value`, `new_value`, `corrected_by`
- From `confidence-scoring` skill: Critical field override -- even if overall confidence >= 0.85, a single critical field (API number, production values) below its reject threshold forces the document into review
- From `backend-schema-implementation.md` Section 3.1: Review endpoints are `GET /review` (list), `GET /review/{id}` (detail), `PATCH /review/{id}` (action with status, corrections, notes, reviewed_by)
- From `postgresql-postgis-schema` skill: `review_queue` table has columns for status, reason, flag_details, document_confidence, field_confidences, corrections, reviewed_by, reviewed_at, notes
- From `postgresql-postgis-schema` skill: `data_corrections` table has columns for extracted_data_id, review_queue_id, field_path, old_value, new_value, corrected_by, corrected_at

## Implementation Plan

### Step 1: Create Review Queue Pydantic Schemas

**File: `backend/src/og_scraper/api/schemas/review.py`**

```python
from datetime import datetime
from typing import Optional
from uuid import UUID
from pydantic import BaseModel, Field, ConfigDict
from .enums import ReviewStatus, DocType

class ReviewQueueItem(BaseModel):
    """List view of a review queue item."""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    document_id: UUID
    extracted_data_id: Optional[UUID]
    status: ReviewStatus
    reason: str
    document_confidence: Optional[float]
    # Joined fields for display
    well_api_number: Optional[str] = None
    state_code: Optional[str] = None
    doc_type: Optional[DocType] = None
    well_name: Optional[str] = None
    operator_name: Optional[str] = None
    created_at: datetime

class ReviewItemDetail(ReviewQueueItem):
    """Full detail view including document, extracted data, and file URL."""
    flag_details: dict = {}
    field_confidences: dict = {}
    corrections: dict = {}
    notes: Optional[str] = None
    reviewed_by: Optional[str] = None
    reviewed_at: Optional[datetime] = None
    # Nested objects
    document: Optional["DocumentDetail"] = None
    extracted_data: Optional["ExtractedDataSummary"] = None
    # Computed field for frontend to display original file
    file_url: Optional[str] = None

class ReviewAction(BaseModel):
    """Request body for PATCH /review/{id}."""
    status: ReviewStatus = Field(
        ...,
        description="New status: 'approved', 'rejected', or 'corrected'",
    )
    corrections: Optional[dict] = Field(
        None,
        description='Field corrections: {"field_name": {"old": "...", "new": "..."}}',
    )
    notes: Optional[str] = Field(
        None,
        description="Optional reviewer notes",
    )
    reviewed_by: Optional[str] = Field(
        None,
        description="Name of the reviewer (no auth, just a freeform name)",
    )

class ReviewStats(BaseModel):
    """Summary stats for the review queue."""
    pending_count: int
    approved_count: int
    rejected_count: int
    corrected_count: int
    avg_confidence: Optional[float]
```

Import `DocumentDetail` and `ExtractedDataSummary` from `schemas/document.py` (created in Task 3.1).

### Step 2: Implement Review Router

**File: `backend/src/og_scraper/api/routes/review.py`**

Three endpoints:

**`GET /api/v1/review`** -- List review queue items

Query parameters:
- `status` (ReviewStatus, default="pending"): filter by review status
- `state` (str): filter by state code (joined through document)
- `doc_type` (DocType): filter by document type (joined through document)
- `min_confidence` (float): filter by minimum document confidence
- `max_confidence` (float): filter by maximum document confidence
- `sort_by` (str, default="document_confidence"): sort field
- `sort_dir` (SortDirection, default="desc"): sort direction (highest confidence first = easiest to review)
- `page`, `page_size`: pagination

Response: `PaginatedResponse[ReviewQueueItem]`

Query pattern -- join review_queue to documents and wells for display fields:

```python
@router.get("/", response_model=PaginatedResponse[ReviewQueueItem])
async def list_review_items(
    status: ReviewStatus = ReviewStatus.PENDING,
    state: str | None = None,
    doc_type: DocType | None = None,
    min_confidence: float | None = None,
    max_confidence: float | None = None,
    sort_by: str = "document_confidence",
    sort_dir: SortDirection = SortDirection.DESC,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    query = (
        select(
            ReviewQueue,
            Document.state_code.label("state_code"),
            Document.doc_type.label("doc_type"),
            Well.api_number.label("well_api_number"),
            Well.well_name.label("well_name"),
            Operator.name.label("operator_name"),
        )
        .join(Document, ReviewQueue.document_id == Document.id)
        .outerjoin(Well, Document.well_id == Well.id)
        .outerjoin(Operator, Well.operator_id == Operator.id)
    )

    # Filters
    query = query.where(ReviewQueue.status == status.value)
    if state:
        query = query.where(Document.state_code == state.upper())
    if doc_type:
        query = query.where(Document.doc_type == doc_type.value)
    if min_confidence is not None:
        query = query.where(ReviewQueue.document_confidence >= min_confidence)
    if max_confidence is not None:
        query = query.where(ReviewQueue.document_confidence <= max_confidence)

    # Sort -- default: highest confidence first (easiest to review)
    if sort_by == "document_confidence":
        sort_col = ReviewQueue.document_confidence
    elif sort_by == "created_at":
        sort_col = ReviewQueue.created_at
    else:
        sort_col = ReviewQueue.document_confidence

    order = desc(sort_col) if sort_dir == SortDirection.DESC else asc(sort_col)
    query = query.order_by(order)

    return await paginate(db, query, page, page_size)
```

**`GET /api/v1/review/{id}`** -- Review item detail

Returns the full `ReviewItemDetail` including:
- The review queue record itself (status, reason, flag_details, field_confidences)
- The nested `document` with all its metadata
- The nested `extracted_data` record with field values and per-field confidence
- A computed `file_url` pointing to `/api/v1/documents/{doc_id}/file`

```python
@router.get("/{review_id}", response_model=ReviewItemDetail)
async def get_review_item(
    review_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    review = await db.get(ReviewQueue, review_id)
    if not review:
        raise HTTPException(status_code=404, detail="Review item not found")

    # Load document with well info
    document = await db.get(Document, review.document_id)

    # Load extracted data if present
    extracted = None
    if review.extracted_data_id:
        extracted = await db.get(ExtractedData, review.extracted_data_id)

    # Build file URL
    file_url = f"/api/v1/documents/{review.document_id}/file" if document and document.file_path else None

    return ReviewItemDetail(
        **review.__dict__,
        document=document,
        extracted_data=extracted,
        file_url=file_url,
        # joined fields
        state_code=document.state_code if document else None,
        doc_type=document.doc_type if document else None,
    )
```

**`PATCH /api/v1/review/{id}`** -- Approve, reject, or correct

This is the most complex endpoint. It handles three actions:

1. **Approve** (`status: "approved"`): Mark the document as accepted. Update document status from `flagged_for_review` to `stored`.
2. **Reject** (`status: "rejected"`): Mark the document as rejected. Keep original file for reference but mark extracted data as rejected.
3. **Correct** (`status: "corrected"`): Update specific fields in `extracted_data.data`, log each correction in `data_corrections` table, then accept.

```python
@router.patch("/{review_id}", response_model=ReviewItemDetail)
async def update_review_item(
    review_id: UUID,
    action: ReviewAction,
    db: AsyncSession = Depends(get_db),
):
    review = await db.get(ReviewQueue, review_id)
    if not review:
        raise HTTPException(status_code=404, detail="Review item not found")
    if review.status != "pending":
        raise HTTPException(
            status_code=400,
            detail=f"Review item already resolved with status: {review.status}",
        )

    now = datetime.utcnow()

    # Update review record
    review.status = action.status.value
    review.reviewed_by = action.reviewed_by
    review.reviewed_at = now
    review.notes = action.notes

    if action.status == ReviewStatus.CORRECTED:
        if not action.corrections:
            raise HTTPException(
                status_code=400,
                detail="Corrections are required when status is 'corrected'",
            )

        # Load extracted data
        extracted = await db.get(ExtractedData, review.extracted_data_id)
        if not extracted:
            raise HTTPException(status_code=404, detail="Extracted data not found")

        # Apply each correction
        updated_data = dict(extracted.data)  # Copy JSONB dict
        for field_path, correction in action.corrections.items():
            old_value = updated_data.get(field_path)
            new_value = correction.get("new") if isinstance(correction, dict) else correction

            # Update the extracted data
            updated_data[field_path] = new_value

            # Create audit trail record
            data_correction = DataCorrection(
                extracted_data_id=extracted.id,
                review_queue_id=review.id,
                field_path=field_path,
                old_value=json.dumps(old_value) if old_value is not None else None,
                new_value=json.dumps(new_value),
                corrected_by=action.reviewed_by,
                corrected_at=now,
            )
            db.add(data_correction)

        # Save updated data back to extracted_data
        extracted.data = updated_data
        review.corrections = action.corrections

    # Update document status
    document = await db.get(Document, review.document_id)
    if document:
        if action.status in (ReviewStatus.APPROVED, ReviewStatus.CORRECTED):
            document.status = "stored"
        elif action.status == ReviewStatus.REJECTED:
            document.status = "extraction_failed"  # or a dedicated rejected status

    await db.commit()
    await db.refresh(review)

    return review  # Will be serialized via ReviewItemDetail
```

Key business rules:
- Can only act on `pending` items. Return 400 if already resolved.
- `corrected` status requires `corrections` dict. Return 400 if missing.
- Each correction creates a `data_corrections` record (audit trail).
- Corrections store JSONB values for `old_value` and `new_value` (not strings).
- Approved/corrected items update document status to `stored`.
- Rejected items update document status to `extraction_failed`.

### Step 3: Register Review Router

Update `backend/src/og_scraper/api/routes/__init__.py`:

```python
from .review import router as review_router
api_router.include_router(review_router, prefix="/review", tags=["review"])
```

### Step 4: Write Tests

**File: `backend/tests/api/test_review.py`**

Set up test fixtures that create a review queue item with associated document, extracted_data, and well:

```python
@pytest.fixture
async def review_fixture(db: AsyncSession):
    """Create a complete review chain: operator -> well -> document -> extracted_data -> review_queue."""
    operator = Operator(name="Test Operator", normalized_name="test operator")
    db.add(operator)
    await db.flush()

    well = Well(
        api_number="42501201300300",
        state_code="TX",
        well_name="Test Well #1",
        operator_id=operator.id,
    )
    db.add(well)
    await db.flush()

    document = Document(
        well_id=well.id,
        state_code="TX",
        doc_type="production_report",
        status="flagged_for_review",
        source_url="https://example.com/doc.pdf",
        confidence_score=0.72,
        ocr_confidence=0.80,
    )
    db.add(document)
    await db.flush()

    extracted = ExtractedData(
        document_id=document.id,
        well_id=well.id,
        data_type="production",
        data={"oil_bbl": 1250, "gas_mcf": 3400, "operator_name": "Tset Opertaor"},
        field_confidence={"oil_bbl": 0.95, "gas_mcf": 0.92, "operator_name": 0.55},
        confidence_score=0.72,
    )
    db.add(extracted)
    await db.flush()

    review = ReviewQueue(
        document_id=document.id,
        extracted_data_id=extracted.id,
        status="pending",
        reason="low_field_confidence: operator_name",
        flag_details={"low_fields": ["operator_name"]},
        document_confidence=0.72,
        field_confidences={"oil_bbl": 0.95, "gas_mcf": 0.92, "operator_name": 0.55},
    )
    db.add(review)
    await db.commit()

    return {
        "review": review,
        "document": document,
        "extracted": extracted,
        "well": well,
        "operator": operator,
    }
```

Test cases:

```python
@pytest.mark.asyncio
async def test_list_review_items(client, review_fixture):
    response = await client.get("/api/v1/review")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] >= 1
    item = data["items"][0]
    assert item["status"] == "pending"
    assert item["reason"] == "low_field_confidence: operator_name"

@pytest.mark.asyncio
async def test_list_review_items_filter_by_state(client, review_fixture):
    response = await client.get("/api/v1/review?state=TX")
    assert response.status_code == 200
    assert response.json()["total"] >= 1

    response = await client.get("/api/v1/review?state=OK")
    assert response.json()["total"] == 0

@pytest.mark.asyncio
async def test_get_review_detail(client, review_fixture):
    review_id = str(review_fixture["review"].id)
    response = await client.get(f"/api/v1/review/{review_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["document"] is not None
    assert data["extracted_data"] is not None
    assert data["file_url"] is not None or data["file_url"] is None  # depends on file_path

@pytest.mark.asyncio
async def test_approve_review(client, review_fixture):
    review_id = str(review_fixture["review"].id)
    response = await client.patch(f"/api/v1/review/{review_id}", json={
        "status": "approved",
        "reviewed_by": "John",
    })
    assert response.status_code == 200
    assert response.json()["status"] == "approved"
    assert response.json()["reviewed_by"] == "John"

@pytest.mark.asyncio
async def test_correct_review(client, review_fixture):
    review_id = str(review_fixture["review"].id)
    response = await client.patch(f"/api/v1/review/{review_id}", json={
        "status": "corrected",
        "corrections": {
            "operator_name": {"old": "Tset Opertaor", "new": "Test Operator"},
        },
        "reviewed_by": "John",
        "notes": "Fixed typo in operator name",
    })
    assert response.status_code == 200
    assert response.json()["status"] == "corrected"
    # Verify the correction was logged in data_corrections table

@pytest.mark.asyncio
async def test_reject_review(client, review_fixture):
    review_id = str(review_fixture["review"].id)
    response = await client.patch(f"/api/v1/review/{review_id}", json={
        "status": "rejected",
        "reviewed_by": "John",
        "notes": "Document is unreadable",
    })
    assert response.status_code == 200
    assert response.json()["status"] == "rejected"

@pytest.mark.asyncio
async def test_cannot_act_on_resolved_review(client, review_fixture):
    review_id = str(review_fixture["review"].id)
    # Approve first
    await client.patch(f"/api/v1/review/{review_id}", json={"status": "approved"})
    # Try to reject -- should fail
    response = await client.patch(f"/api/v1/review/{review_id}", json={"status": "rejected"})
    assert response.status_code == 400

@pytest.mark.asyncio
async def test_correct_without_corrections_fails(client, review_fixture):
    review_id = str(review_fixture["review"].id)
    response = await client.patch(f"/api/v1/review/{review_id}", json={
        "status": "corrected",
    })
    assert response.status_code == 400
```

## Files to Create

- `backend/src/og_scraper/api/schemas/review.py` - ReviewQueueItem, ReviewItemDetail, ReviewAction, ReviewStats
- `backend/src/og_scraper/api/routes/review.py` - GET /review, GET /review/{id}, PATCH /review/{id}
- `backend/tests/api/test_review.py` - All review endpoint tests with fixtures

## Files to Modify

- `backend/src/og_scraper/api/routes/__init__.py` - Register review router
- `backend/src/og_scraper/api/schemas/__init__.py` - Export review schemas

## Contracts

### Provides (for downstream tasks)

- **Endpoint**: `GET /api/v1/review` - List review queue items
  - Request: Query params (status=pending, state, doc_type, min_confidence, max_confidence, sort_by=document_confidence, sort_dir=desc, page, page_size)
  - Response: `PaginatedResponse[ReviewQueueItem]` sorted by confidence desc (highest first)
- **Endpoint**: `GET /api/v1/review/{id}` - Review item detail
  - Response: `ReviewItemDetail` with nested document, extracted_data, and file_url
  - Error 404: Review item not found
- **Endpoint**: `PATCH /api/v1/review/{id}` - Take action on review item
  - Request: `ReviewAction` body: `{"status": "approved"|"rejected"|"corrected", "corrections?": {...}, "notes?": "...", "reviewed_by?": "..."}`
  - Response: Updated `ReviewItemDetail`
  - Error 404: Review item not found
  - Error 400: Already resolved, or corrected without corrections
- **Schemas**: `ReviewQueueItem`, `ReviewItemDetail`, `ReviewAction`, `ReviewStats`

### Consumes (from upstream tasks)

- From Task 3.1: `PaginatedResponse`, `paginate()`, `DocumentDetail`, `ExtractedDataSummary`, enums, router registration
- From Task 2.4: Confidence scoring pipeline that creates `review_queue` records when confidence < 0.85
- From Task 1.2: `ReviewQueue`, `DataCorrection`, `ExtractedData`, `Document`, `Well`, `Operator` models

## Acceptance Criteria

- [ ] `GET /api/v1/review` returns paginated review items (default: pending status, sorted by confidence desc)
- [ ] `GET /api/v1/review` filters by state, doc_type, and confidence range
- [ ] `GET /api/v1/review/{id}` returns full detail with nested document and extracted data
- [ ] `GET /api/v1/review/{id}` returns computed file_url for the original document
- [ ] `PATCH /api/v1/review/{id}` with `approved` updates review and document status
- [ ] `PATCH /api/v1/review/{id}` with `corrected` updates extracted_data.data, creates data_corrections records, updates statuses
- [ ] `PATCH /api/v1/review/{id}` with `rejected` marks document as rejected
- [ ] `PATCH /api/v1/review/{id}` returns 400 when acting on already-resolved items
- [ ] `PATCH /api/v1/review/{id}` with `corrected` returns 400 when corrections dict is missing
- [ ] Data corrections audit trail records field_path, old_value, new_value, corrected_by, corrected_at
- [ ] Review items show joined data: well_api_number, state_code, doc_type, well_name, operator_name
- [ ] All tests pass
- [ ] Build succeeds

## Testing Protocol

### Unit/Integration Tests

- Test file: `backend/tests/api/test_review.py`
- Test cases:
  - [ ] List pending review items returns correct count and structure
  - [ ] List filters by state correctly (TX returns items, OK returns empty)
  - [ ] List filters by doc_type correctly
  - [ ] List sorts by confidence descending by default
  - [ ] Detail endpoint returns nested document and extracted_data
  - [ ] Detail endpoint returns 404 for nonexistent ID
  - [ ] Approve updates review status to approved and document status to stored
  - [ ] Correct updates extracted_data.data with new values
  - [ ] Correct creates data_corrections audit records (one per corrected field)
  - [ ] Correct preserves old_value in data_corrections
  - [ ] Reject updates review status and document status
  - [ ] Cannot act on already-resolved review (returns 400)
  - [ ] Correct without corrections dict returns 400
  - [ ] Corrections with multiple fields creates multiple data_corrections records

### API/Script Testing

- Seed database with a low-confidence document that appears in review queue
- `curl http://localhost:8000/api/v1/review` returns the pending item
- `curl http://localhost:8000/api/v1/review/{id}` returns detail with document
- `curl -X PATCH http://localhost:8000/api/v1/review/{id} -H "Content-Type: application/json" -d '{"status": "approved", "reviewed_by": "Kevin"}'`

### Build/Lint/Type Checks

- [ ] `uv run pytest backend/tests/api/test_review.py` succeeds
- [ ] `uv run ruff check backend/src/og_scraper/api/routes/review.py` passes
- [ ] `uv run ruff check backend/src/og_scraper/api/schemas/review.py` passes

## Skills to Read

- `fastapi-backend` - API patterns, PATCH endpoint, Pydantic validation
- `confidence-scoring` - Review queue workflow, user actions (approve/correct/reject), corrections tracking, threshold logic
- `postgresql-postgis-schema` - review_queue and data_corrections table schemas

## Research Files to Read

- `.claude/orchestration-og-doc-scraper/research/backend-schema-implementation.md` - Section 3.1 (review endpoint signatures), Section 3.2 (ReviewQueueItem, ReviewItemDetail, ReviewAction schemas)
- `.claude/orchestration-og-doc-scraper/research/document-pipeline-implementation.md` - Section 5 (confidence scoring, review queue routing logic)

## Git

- Branch: `phase-3/task-3-3-review-queue-endpoints`
- Commit message prefix: `Task 3.3:`
