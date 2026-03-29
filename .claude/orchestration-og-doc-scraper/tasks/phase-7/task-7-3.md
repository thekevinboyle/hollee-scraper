# Task 7.3: Error Handling & Edge Cases

## Objective

Test failure modes, edge cases, and error recovery across the full system: scrapers encountering unreachable sites, corrupt/unreadable documents, malformed oil & gas data (bad API numbers, impossible coordinates, absurd production volumes), API validation errors, database connection loss, concurrent scrape attempts, and empty state displays. Every error path must be exercised to verify the system fails gracefully and communicates errors clearly.

## Context

This is the third task in Phase 7 (Comprehensive E2E Testing). Task 7.1 validated the happy-path pipeline, Task 7.2 validated the dashboard UI. This task intentionally breaks things to verify the system handles failures gracefully. Error handling is especially important for this project because oil & gas regulatory data is messy: scanned documents are often unreadable, API numbers arrive in inconsistent formats, coordinates use different datums, and state websites go down without notice. Task 7.4 covers performance testing.

## Dependencies

- All Phase 1-6 tasks must be complete
- Task 7.1 (E2E pipeline infrastructure)
- Task 7.2 (Playwright test infrastructure)
- Docker Compose stack running

## Blocked By

- All Phase 1-6 tasks
- Tasks 7.1 and 7.2

## Research Findings

Key findings from research files relevant to this task:

- From `confidence-scoring` skill: Documents below 0.50 are rejected. Critical field override forces review even with high overall confidence. Missing fields contribute 0.0 confidence at their weight.
- From `og-data-models.md`: API numbers can be 10, 12, or 14 digits. Kern County CA uses two county codes (029/030). Watch for MCF vs MMCF vs BCF unit confusion (1000x errors). NAD27 vs NAD83 datum differences cause 100+ meter coordinate errors.
- From `state-regulatory-sites.md`: State government sites have unpredictable downtime. North Dakota has a paywall. Louisiana SONRIS is an Oracle-backed system prone to timeouts.
- From `og-scraper-architecture` skill: Document status state machine includes failure states: DOWNLOAD_FAILED, CLASSIFICATION_FAILED, EXTRACTION_FAILED, FLAGGED_FOR_REVIEW.

## Implementation Plan

### Step 1: Scraper Error Handling Tests

Create `backend/tests/e2e/test_scraper_errors.py` to test scraper behavior when sites are unreachable or return unexpected content.

```python
# backend/tests/e2e/test_scraper_errors.py
import pytest
from unittest.mock import patch, AsyncMock
import httpx

@pytest.mark.asyncio
async def test_scrape_unreachable_site(client, db_session):
    """Scraping when a state site is completely unreachable should fail gracefully."""
    # Mock the HTTP client to simulate connection timeout
    with patch(
        "og_scraper.scrapers.base.BaseOGSpider._fetch",
        side_effect=httpx.ConnectTimeout("Connection timed out"),
    ):
        response = await client.post("/api/scrape", json={"state": "TX"})
        assert response.status_code == 202
        job_id = response.json()["job_id"]

        # Wait for job to complete
        job_response = await client.get(f"/api/scrape/{job_id}")
        job_data = job_response.json()
        assert job_data["status"] == "failed"
        assert "error" in job_data or "errors" in job_data
        # Errors should contain meaningful message
        errors = job_data.get("errors", [])
        assert len(errors) > 0
        assert any("timeout" in str(e).lower() or "unreachable" in str(e).lower() for e in errors)

@pytest.mark.asyncio
async def test_scrape_site_returns_500(client, db_session):
    """State site returning 500 should be handled gracefully."""
    with patch(
        "og_scraper.scrapers.base.BaseOGSpider._fetch",
        return_value=AsyncMock(status_code=500, text="Internal Server Error"),
    ):
        response = await client.post("/api/scrape", json={"state": "OK"})
        assert response.status_code == 202
        job_id = response.json()["job_id"]

        job_response = await client.get(f"/api/scrape/{job_id}")
        job_data = job_response.json()
        assert job_data["status"] == "failed"

@pytest.mark.asyncio
async def test_scrape_site_returns_403_blocked(client, db_session):
    """Being blocked by a state site (403) should record the error."""
    with patch(
        "og_scraper.scrapers.base.BaseOGSpider._fetch",
        return_value=AsyncMock(status_code=403, text="Forbidden"),
    ):
        response = await client.post("/api/scrape", json={"state": "LA"})
        assert response.status_code == 202
        job_id = response.json()["job_id"]

        job_response = await client.get(f"/api/scrape/{job_id}")
        job_data = job_response.json()
        assert job_data["status"] == "failed"
        errors = job_data.get("errors", [])
        assert any("403" in str(e) or "forbidden" in str(e).lower() or "blocked" in str(e).lower() for e in errors)

@pytest.mark.asyncio
async def test_scrape_site_returns_html_not_expected_format(client, db_session):
    """Site returning unexpected HTML (redesigned page) should fail gracefully."""
    with patch(
        "og_scraper.scrapers.base.BaseOGSpider._fetch",
        return_value=AsyncMock(
            status_code=200,
            text="<html><body>Site redesigned, no data here</body></html>",
        ),
    ):
        response = await client.post("/api/scrape", json={"state": "CO"})
        assert response.status_code == 202
        job_id = response.json()["job_id"]

        job_response = await client.get(f"/api/scrape/{job_id}")
        job_data = job_response.json()
        # Should either fail or complete with 0 documents
        assert job_data["status"] in ("failed", "completed")
        if job_data["status"] == "completed":
            assert job_data.get("documents_found", 0) == 0
```

### Step 2: Document Processing Error Tests

Create `backend/tests/e2e/test_document_errors.py` to test processing of corrupt, empty, and malformed documents.

```python
# backend/tests/e2e/test_document_errors.py
import pytest
from pathlib import Path
import tempfile

@pytest.mark.asyncio
async def test_corrupt_pdf_rejected(pipeline, tmp_path):
    """A corrupt/unreadable PDF should be rejected with low confidence."""
    # Create a corrupt PDF file
    corrupt_pdf = tmp_path / "corrupt.pdf"
    corrupt_pdf.write_bytes(b"%PDF-1.4 CORRUPT DATA \x00\x01\x02\x03")

    result = await pipeline.process(str(corrupt_pdf), state="TX")
    assert result.disposition in ("rejected", "review_queue")
    assert result.confidence.overall < 0.50 or result.status == "extraction_failed"

@pytest.mark.asyncio
async def test_zero_byte_file_handled(pipeline, tmp_path):
    """A zero-byte file should be handled gracefully, not crash."""
    empty_file = tmp_path / "empty.pdf"
    empty_file.write_bytes(b"")

    result = await pipeline.process(str(empty_file), state="TX")
    assert result.status in ("download_failed", "extraction_failed", "rejected")
    # Should not raise an unhandled exception

@pytest.mark.asyncio
async def test_non_pdf_file_handled(pipeline, tmp_path):
    """A file with .pdf extension but non-PDF content should be handled."""
    fake_pdf = tmp_path / "actually_html.pdf"
    fake_pdf.write_text("<html><body>This is HTML not PDF</body></html>")

    result = await pipeline.process(str(fake_pdf), state="TX")
    assert result.status in ("classification_failed", "extraction_failed", "rejected")

@pytest.mark.asyncio
async def test_very_large_document_handled(pipeline, tmp_path):
    """A very large file should be processed or rejected, not hang."""
    # Create a 50MB file of random data with valid PDF header
    large_pdf = tmp_path / "large.pdf"
    with open(large_pdf, "wb") as f:
        f.write(b"%PDF-1.4\n")
        f.write(b"X" * (50 * 1024 * 1024))  # 50MB

    # Should complete within timeout, not hang indefinitely
    result = await pipeline.process(str(large_pdf), state="TX")
    assert result is not None  # Did not crash

@pytest.mark.asyncio
async def test_password_protected_pdf_handled(pipeline):
    """A password-protected PDF should be flagged, not crash."""
    result = await pipeline.process(
        "tests/fixtures/ocr/edge_cases/password_protected.pdf", state="TX"
    )
    assert result.disposition in ("rejected", "review_queue")
    assert result.status in ("extraction_failed", "flagged_for_review")

@pytest.mark.asyncio
async def test_scanned_rotated_page_handled(pipeline):
    """A scanned document with rotated pages should still be processed."""
    result = await pipeline.process(
        "tests/fixtures/ocr/edge_cases/rotated_page.pdf", state="TX"
    )
    # Should process (perhaps with lower confidence) but not crash
    assert result is not None
    assert result.status not in ("download_failed",)

@pytest.mark.asyncio
async def test_multi_column_layout_handled(pipeline):
    """A document with multi-column layout should be processed."""
    result = await pipeline.process(
        "tests/fixtures/ocr/edge_cases/multi_column.pdf", state="TX"
    )
    assert result is not None
    # Multi-column may reduce confidence but should not crash
```

### Step 3: Oil & Gas Data Edge Cases

Create `backend/tests/e2e/test_og_data_edge_cases.py` to test domain-specific data issues unique to oil and gas.

```python
# backend/tests/e2e/test_og_data_edge_cases.py
import pytest
from og_scraper.utils.api_number import normalize_api_number, validate_api_number
from og_scraper.pipeline.validators import (
    validate_coordinates,
    validate_production_volumes,
    validate_date,
)

class TestAPINumberEdgeCases:
    """API numbers are the primary identifier in oil & gas. They must be handled
    correctly in every format variant."""

    def test_standard_14_digit_format(self):
        """Standard 14-digit: 42-461-12345-00-00"""
        result = normalize_api_number("42-461-12345-00-00")
        assert result == "42461123450000"

    def test_10_digit_format_without_sidetrack(self):
        """10-digit format (no sidetrack/event): 42-461-12345"""
        result = normalize_api_number("42-461-12345")
        assert result == "42461123450000"  # Zero-padded to 14

    def test_12_digit_format(self):
        """12-digit format: 42-461-12345-00"""
        result = normalize_api_number("42-461-12345-00")
        assert result == "42461123450000"

    def test_api_number_without_dashes(self):
        """API number provided without dashes: 42461123450000"""
        result = normalize_api_number("42461123450000")
        assert result == "42461123450000"

    def test_api_number_with_spaces(self):
        """OCR often inserts spaces: 42 461 12345 00 00"""
        result = normalize_api_number("42 461 12345 00 00")
        assert result == "42461123450000"

    def test_api_number_with_leading_zeros(self):
        """State code 05 (Colorado) must preserve leading zero."""
        result = normalize_api_number("05-123-06789")
        assert result.startswith("05")

    def test_invalid_state_code_rejected(self):
        """State code 99 does not exist."""
        assert not validate_api_number("99-001-00001-00-00")

    def test_kern_county_ca_dual_codes(self):
        """Kern County, CA uses both 029 and 030 county codes."""
        assert validate_api_number("04-029-12345-00-00")  # Kern County 029
        assert validate_api_number("04-030-12345-00-00")  # Kern County 030

    def test_api_number_with_ocr_artifacts(self):
        """OCR may introduce 'O' for '0' or 'l' for '1'."""
        # Should either normalize or reject with low confidence
        result = normalize_api_number("42-46l-l2345-O0-O0")
        # Implementation should try to correct common OCR mistakes
        # or return None/raise to signal low confidence

    def test_empty_api_number(self):
        """Empty/None API number should not crash."""
        result = normalize_api_number("")
        assert result is None or result == ""
        result2 = normalize_api_number(None)
        assert result2 is None


class TestCoordinateEdgeCases:
    """Well coordinates come from many sources with many problems."""

    def test_valid_texas_coordinates(self):
        """Normal Texas coordinates."""
        assert validate_coordinates(31.9686, -102.0779, state="TX")

    def test_coordinates_outside_state_boundaries(self):
        """Coordinates that claim to be in Texas but are actually in New Mexico."""
        # El Paso area - very west Texas
        assert validate_coordinates(31.7619, -106.4850, state="TX")
        # But coordinates in the middle of New Mexico should fail for TX
        assert not validate_coordinates(35.0844, -106.6504, state="TX")

    def test_alaska_coordinates_positive_longitude(self):
        """Aleutian Islands have positive longitudes (crossing 180th meridian)."""
        assert validate_coordinates(51.8, 176.5, state="AK")

    def test_lat_lng_swapped(self):
        """Common error: latitude and longitude values swapped."""
        # -102.0779, 31.9686 -- longitude is clearly wrong for latitude
        assert not validate_coordinates(-102.0779, 31.9686, state="TX")

    def test_zero_zero_coordinates(self):
        """Coordinates at (0, 0) should be rejected (Gulf of Guinea, not US)."""
        assert not validate_coordinates(0.0, 0.0, state="TX")

    def test_null_island_coordinates(self):
        """Coordinates very close to (0, 0) -- null island."""
        assert not validate_coordinates(0.001, -0.001, state="TX")

    def test_continental_us_boundary(self):
        """Coordinates must be within continental US + Alaska."""
        # Antarctica
        assert not validate_coordinates(-80.0, -60.0, state="TX")
        # Russia
        assert not validate_coordinates(55.7558, 37.6173, state="TX")

    def test_nad27_vs_nad83_tolerance(self):
        """NAD27 vs NAD83 datum shift can cause ~100m difference.
        Coordinates should be accepted with some tolerance."""
        # Slight offset that could be a datum issue
        assert validate_coordinates(31.9690, -102.0775, state="TX")

    def test_plss_description_no_latlong(self):
        """Some wells only have PLSS (Township/Range/Section) descriptions."""
        # This should be flagged as lower confidence, not rejected
        # Test the pipeline handling of missing coordinates
        pass


class TestProductionVolumeEdgeCases:
    """Production volumes have many ways to go wrong."""

    def test_normal_oil_production(self):
        """Normal oil production: 500 bbls/month."""
        assert validate_production_volumes(oil_bbls=500)

    def test_zero_production_shut_in_well(self):
        """Zero production is valid for shut-in wells."""
        assert validate_production_volumes(oil_bbls=0, gas_mcf=0, water_bbls=0)

    def test_extremely_high_oil_flagged(self):
        """Oil > 100,000 bbls/month is suspicious for a single well."""
        result = validate_production_volumes(oil_bbls=150_000)
        assert not result  # Should flag as suspicious

    def test_extremely_high_gas_flagged(self):
        """Gas > 1,000,000 MCF/month is suspicious."""
        result = validate_production_volumes(gas_mcf=5_000_000)
        assert not result

    def test_negative_production_rejected(self):
        """Negative production values should be rejected."""
        assert not validate_production_volumes(oil_bbls=-100)

    def test_mcf_vs_mmcf_confusion(self):
        """MCF vs MMCF: 1 MMCF = 1,000 MCF. A value like 500,000 could be
        either 500,000 MCF (normal) or 500,000 MMCF (impossibly high)."""
        # 500,000 MCF is within normal range
        assert validate_production_volumes(gas_mcf=500_000)
        # 500,000,000 MCF (if someone stored MMCF as MCF) is impossibly high
        assert not validate_production_volumes(gas_mcf=500_000_000)

    def test_oil_reported_but_gas_missing_lowers_confidence(self):
        """Oil wells almost always produce some gas. Missing gas should lower confidence."""
        # This is a confidence concern, not a hard rejection
        pass

    def test_production_values_as_strings(self):
        """OCR sometimes extracts numbers with commas or extra characters."""
        # "1,234" should parse to 1234
        # "1.234.5" is ambiguous (European decimal vs. US)
        pass


class TestDateEdgeCases:
    """Dates in oil & gas documents come in many formats."""

    def test_standard_date_formats(self):
        """Common date formats should all parse correctly."""
        assert validate_date("01/15/2026")       # MM/DD/YYYY
        assert validate_date("2026-01-15")        # ISO format
        assert validate_date("15-Jan-26")         # DD-Mon-YY
        assert validate_date("January 15, 2026")  # Full text

    def test_future_date_rejected(self):
        """Dates in the future should be flagged."""
        assert not validate_date("12/31/2099")

    def test_very_old_date_flagged(self):
        """Dates before 1859 (first commercial US oil well) are suspicious."""
        assert not validate_date("01/01/1800")

    def test_reporting_period_lag(self):
        """Production data typically lags 2-6 months behind actual production."""
        # A reporting period date from this month is suspicious
        # (states need time to compile data)
        pass

    def test_ambiguous_date_format(self):
        """01/02/2026 could be Jan 2 or Feb 1 depending on convention."""
        # The system should have a consistent interpretation
        result = validate_date("01/02/2026")
        assert result  # Should parse, but format depends on convention

    def test_completion_after_permit_date(self):
        """A completion date before the permit date is invalid."""
        pass


class TestOperatorNameEdgeCases:
    """Operator names have many variations and OCR artifacts."""

    @pytest.mark.asyncio
    async def test_operator_name_variations_match(self, db_session):
        """Different name variations should resolve to the same operator."""
        variations = [
            "Devon Energy Corporation",
            "DEVON ENERGY CORP",
            "Devon Energy Production Co LP",
            "Devon",
        ]
        # After fuzzy matching, these should all link to the same operator
        # (or at least flag the similarity)

    @pytest.mark.asyncio
    async def test_operator_name_with_ocr_artifacts(self, db_session):
        """OCR may introduce artifacts: 'Dev0n Energy C0rp'."""
        pass

    @pytest.mark.asyncio
    async def test_completely_unknown_operator_flagged(self, db_session):
        """An operator name that matches nothing should be flagged for review."""
        pass
```

### Step 4: API Error Response Tests

Create `backend/tests/e2e/test_api_errors.py` to test API validation and error responses.

```python
# backend/tests/e2e/test_api_errors.py
import pytest

@pytest.mark.asyncio
async def test_get_nonexistent_well(client):
    """GET /api/wells/{id} with non-existent ID returns 404."""
    response = await client.get("/api/wells/00000000-0000-0000-0000-000000000000")
    assert response.status_code == 404

@pytest.mark.asyncio
async def test_get_well_with_invalid_uuid(client):
    """GET /api/wells/{id} with invalid UUID format returns 422."""
    response = await client.get("/api/wells/not-a-uuid")
    assert response.status_code == 422

@pytest.mark.asyncio
async def test_scrape_invalid_state(client):
    """POST /api/scrape with invalid state code returns 400/422."""
    response = await client.post("/api/scrape", json={"state": "ZZ"})
    assert response.status_code in (400, 422)

@pytest.mark.asyncio
async def test_scrape_missing_state(client):
    """POST /api/scrape without state field returns 422."""
    response = await client.post("/api/scrape", json={})
    assert response.status_code == 422

@pytest.mark.asyncio
async def test_scrape_empty_body(client):
    """POST /api/scrape with empty body returns 422."""
    response = await client.post("/api/scrape")
    assert response.status_code == 422

@pytest.mark.asyncio
async def test_wells_invalid_page_number(client):
    """Pagination with negative page number returns 400/422."""
    response = await client.get("/api/wells", params={"page": -1})
    assert response.status_code in (400, 422)

@pytest.mark.asyncio
async def test_wells_excessive_page_size(client):
    """Pagination with page_size > 200 should be rejected or clamped."""
    response = await client.get("/api/wells", params={"per_page": 10000})
    if response.status_code == 200:
        # Clamped to max 200
        data = response.json()
        assert len(data["items"]) <= 200
    else:
        assert response.status_code in (400, 422)

@pytest.mark.asyncio
async def test_map_endpoint_invalid_bbox(client):
    """Map endpoint with inverted bounding box returns error or empty."""
    response = await client.get("/api/map/wells", params={
        "min_lat": 40.0,
        "max_lat": 30.0,  # min > max is invalid
        "min_lng": -100.0,
        "max_lng": -90.0,
    })
    assert response.status_code in (200, 400, 422)
    if response.status_code == 200:
        assert response.json() == [] or len(response.json()) == 0

@pytest.mark.asyncio
async def test_map_endpoint_bbox_outside_us(client):
    """Map endpoint with bbox entirely outside US returns empty results."""
    response = await client.get("/api/map/wells", params={
        "min_lat": 50.0,
        "max_lat": 60.0,
        "min_lng": 0.0,
        "max_lng": 10.0,
    })
    assert response.status_code == 200
    assert len(response.json()) == 0

@pytest.mark.asyncio
async def test_review_approve_nonexistent_item(client):
    """Approving a non-existent review item returns 404."""
    response = await client.post("/api/review/00000000-0000-0000-0000-000000000000/approve")
    assert response.status_code == 404

@pytest.mark.asyncio
async def test_review_correct_with_empty_corrections(client, seed_review_item):
    """Correcting with empty corrections dict should be handled."""
    item_id = seed_review_item["id"]
    response = await client.post(
        f"/api/review/{item_id}/correct",
        json={"corrections": {}},
    )
    # Empty corrections should either be accepted (no-op) or rejected
    assert response.status_code in (200, 400, 422)

@pytest.mark.asyncio
async def test_documents_filter_invalid_doc_type(client):
    """Filtering by an invalid doc_type returns 400/422 or empty results."""
    response = await client.get("/api/documents", params={"type": "nonexistent_type"})
    assert response.status_code in (200, 400, 422)

@pytest.mark.asyncio
async def test_documents_invalid_date_range(client):
    """Date range where from > to should return error or empty."""
    response = await client.get("/api/documents", params={
        "date_from": "2026-12-31",
        "date_to": "2026-01-01",
    })
    assert response.status_code in (200, 400, 422)

@pytest.mark.asyncio
async def test_export_unsupported_format(client):
    """Export with unsupported format should return 400/422."""
    response = await client.get("/api/export/wells", params={"format": "xml"})
    assert response.status_code in (400, 422)

@pytest.mark.asyncio
async def test_search_with_sql_injection_attempt(client):
    """Search input with SQL injection attempt should be safe."""
    response = await client.get(
        "/api/wells/search",
        params={"q": "'; DROP TABLE wells; --"},
    )
    assert response.status_code == 200
    # Database should not be affected
    wells_response = await client.get("/api/wells")
    assert wells_response.status_code == 200

@pytest.mark.asyncio
async def test_search_with_xss_attempt(client):
    """Search input with XSS attempt should be sanitized."""
    response = await client.get(
        "/api/wells/search",
        params={"q": "<script>alert('xss')</script>"},
    )
    assert response.status_code == 200
    data = response.json()
    # No script tags in response
    response_text = str(data)
    assert "<script>" not in response_text
```

### Step 5: Concurrent Scrape Handling Tests

Create `backend/tests/e2e/test_concurrent_scrapes.py` to test concurrent scrape behavior.

```python
# backend/tests/e2e/test_concurrent_scrapes.py
import pytest

@pytest.mark.asyncio
async def test_scrape_while_another_running(client):
    """Triggering a scrape for the same state while one is running should
    be handled (either queued, rejected, or deduplicated)."""
    # Start first scrape
    response1 = await client.post("/api/scrape", json={"state": "PA"})
    assert response1.status_code == 202
    job_id1 = response1.json()["job_id"]

    # Immediately start second scrape for same state
    response2 = await client.post("/api/scrape", json={"state": "PA"})

    # Should either:
    # - Return 409 Conflict (already running)
    # - Return 202 but queue it
    # - Return 200 with the existing job_id
    assert response2.status_code in (200, 202, 409)

    if response2.status_code == 409:
        # Verify meaningful error message
        error = response2.json()
        assert "already" in str(error).lower() or "running" in str(error).lower()

@pytest.mark.asyncio
async def test_scrape_different_states_simultaneously(client):
    """Scraping different states simultaneously should work."""
    response_tx = await client.post("/api/scrape", json={"state": "TX"})
    response_ok = await client.post("/api/scrape", json={"state": "OK"})
    assert response_tx.status_code == 202
    assert response_ok.status_code == 202

    # Both jobs should have different IDs
    assert response_tx.json()["job_id"] != response_ok.json()["job_id"]
```

### Step 6: Database Connection Loss Tests

Create `backend/tests/e2e/test_infrastructure_failures.py` to test behavior when infrastructure fails.

```python
# backend/tests/e2e/test_infrastructure_failures.py
import pytest
from unittest.mock import patch, AsyncMock
from sqlalchemy.exc import OperationalError

@pytest.mark.asyncio
async def test_health_endpoint_reports_db_unhealthy(client):
    """Health endpoint should report unhealthy when DB is unreachable."""
    with patch(
        "og_scraper.database.engine.connect",
        side_effect=OperationalError("connection", {}, Exception("Connection refused")),
    ):
        response = await client.get("/health")
        # Should return 503 or 200 with unhealthy status
        if response.status_code == 200:
            data = response.json()
            assert data.get("database") == "unhealthy" or data.get("status") == "unhealthy"
        else:
            assert response.status_code == 503

@pytest.mark.asyncio
async def test_api_returns_503_when_db_down(client):
    """API endpoints should return 503 when database is unavailable."""
    with patch(
        "og_scraper.database.get_session",
        side_effect=OperationalError("connection", {}, Exception("Connection refused")),
    ):
        response = await client.get("/api/wells")
        assert response.status_code in (500, 503)

@pytest.mark.asyncio
async def test_scrape_handles_db_failure_mid_job(client):
    """If DB fails during a scrape job, it should fail gracefully."""
    # This is a more complex scenario where DB dies partway through
    # The job should be marked as failed with appropriate error message
    pass
```

### Step 7: Frontend Empty State and Error Display Tests (Playwright)

```typescript
// frontend/e2e/error-states.spec.ts
import { test, expect } from '@playwright/test';
import { takeEvidenceScreenshot } from './helpers';

test.describe('Empty States', () => {
  test('search with no results shows empty state', async ({ page }) => {
    await page.goto('/wells');
    await page.waitForLoadState('networkidle');

    const searchInput = page.locator('input[placeholder*="earch"], input[type="search"]');
    await searchInput.fill('xyznonexistentwellname12345');
    await searchInput.press('Enter');
    await page.waitForResponse(resp => resp.url().includes('/api/wells'));

    // Verify empty state message
    await expect(
      page.locator('text=No results').or(
        page.locator('text=no wells found')
      ).or(
        page.locator('[data-testid="empty-state"]')
      )
    ).toBeVisible({ timeout: 5000 });

    await takeEvidenceScreenshot(page, 'error-01-search-no-results');
  });

  test('review queue when empty shows empty state', async ({ page }) => {
    // This test assumes the review queue may be empty after approvals
    await page.goto('/review');
    await page.waitForLoadState('networkidle');

    // If queue is empty, verify empty state message
    const emptyMessage = page.locator(
      'text=No items', { exact: false }
    ).or(
      page.locator('text=queue is empty', { exact: false })
    ).or(
      page.locator('[data-testid="empty-review-queue"]')
    );

    // Take screenshot regardless of state
    await takeEvidenceScreenshot(page, 'error-02-review-queue-state');
  });

  test('map with no data renders empty map', async ({ page }) => {
    // Navigate to map, possibly with a filter that returns no data
    await page.goto('/map');
    await page.waitForLoadState('networkidle');
    await page.waitForSelector('.leaflet-container', { timeout: 15_000 });

    // Map should render even if no wells are loaded
    const mapContainer = page.locator('.leaflet-container');
    await expect(mapContainer).toBeVisible();

    await takeEvidenceScreenshot(page, 'error-03-map-state');
  });
});

test.describe('Error Handling in UI', () => {
  test('API error shows user-friendly message', async ({ page }) => {
    // Intercept API call and return error
    await page.route('**/api/wells**', (route) => {
      route.fulfill({
        status: 500,
        contentType: 'application/json',
        body: JSON.stringify({ detail: 'Internal Server Error' }),
      });
    });

    await page.goto('/wells');
    await page.waitForLoadState('networkidle');

    // Should show error message, not crash
    await expect(
      page.locator('text=error').or(
        page.locator('text=something went wrong')
      ).or(
        page.locator('[data-testid="error-message"]')
      )
    ).toBeVisible({ timeout: 5000 });

    await takeEvidenceScreenshot(page, 'error-04-api-error-display');
  });

  test('network timeout shows retry option', async ({ page }) => {
    // Simulate very slow response
    await page.route('**/api/wells**', async (route) => {
      await new Promise(resolve => setTimeout(resolve, 30_000));
      route.fulfill({ status: 200, body: '{}' });
    });

    await page.goto('/wells');

    // Should show loading state initially, then timeout message
    await expect(
      page.locator('text=loading').or(
        page.locator('[data-testid="loading-spinner"]')
      )
    ).toBeVisible({ timeout: 5000 });

    await takeEvidenceScreenshot(page, 'error-05-loading-timeout');
  });
});
```

### Step 8: Docker Smoke Test Commands

Verify error scenarios at the Docker level.

Add to `justfile`:
```makefile
# Test: Stop database and verify backend reports unhealthy
test-db-failure:
    docker compose stop db
    sleep 5
    curl -s http://localhost:8000/health | python -m json.tool
    docker compose start db
    sleep 10
    curl -s http://localhost:8000/health | python -m json.tool

# Test: Restart backend with invalid database URL
test-bad-db-url:
    docker compose stop backend
    DATABASE_URL=postgresql+asyncpg://wrong:wrong@localhost:9999/noexist docker compose up backend -d
    sleep 10
    curl -s http://localhost:8000/health | python -m json.tool
    docker compose down backend
    docker compose up backend -d
```

Test commands to run manually:
```bash
# Stop database container and verify health endpoint
docker compose stop db
curl -sf http://localhost:8000/health || echo "Health check failed (expected)"
docker compose start db

# Kill backend mid-scrape and verify recovery
docker compose restart backend
curl http://localhost:8000/api/scrape/jobs  # Should show interrupted jobs

# Check API error responses
curl -s http://localhost:8000/api/wells/not-a-uuid | python -m json.tool
curl -s -X POST http://localhost:8000/api/scrape -H "Content-Type: application/json" -d '{"state":"ZZ"}' | python -m json.tool
curl -s "http://localhost:8000/api/wells?page=-1" | python -m json.tool
curl -s "http://localhost:8000/api/wells/search?q='; DROP TABLE wells; --'" | python -m json.tool
```

## Files to Create

- `backend/tests/e2e/test_scraper_errors.py` - Scraper failure mode tests
- `backend/tests/e2e/test_document_errors.py` - Corrupt/malformed document tests
- `backend/tests/e2e/test_og_data_edge_cases.py` - Oil & gas data validation edge cases
- `backend/tests/e2e/test_api_errors.py` - API validation and error response tests
- `backend/tests/e2e/test_concurrent_scrapes.py` - Concurrent scrape handling tests
- `backend/tests/e2e/test_infrastructure_failures.py` - Database/infrastructure failure tests
- `frontend/e2e/error-states.spec.ts` - Frontend empty states and error display tests

## Files to Modify

- `justfile` - Add error testing commands (`test-db-failure`, `test-bad-db-url`)
- `backend/tests/e2e/conftest.py` - Add fixtures for error scenarios (seed_review_item, etc.)

## Contracts

### Provides (for downstream tasks)

- Error handling validation: Confirmation that every failure mode is handled gracefully
- Edge case test suite: Reusable tests for oil & gas data validation
- API error catalog: Complete map of error responses for each endpoint

### Consumes (from upstream tasks)

- From Task 7.1: E2E test infrastructure (testcontainers, VCR, fixtures)
- From Task 7.2: Playwright test infrastructure and helpers
- From Task 2.4: Confidence scoring and validation pipeline
- From Task 3.1-3.4: All API endpoints for error response testing
- From `confidence-scoring` skill: Threshold values, critical field override rule
- From `og-data-models.md`: API number format, production volume ranges, coordinate ranges

## Acceptance Criteria

- [ ] Scraping an unreachable site results in graceful failure with descriptive error
- [ ] Scraping a site returning 500/403 results in failed job with error details
- [ ] Corrupt/unreadable PDF is rejected or flagged, not crashed on
- [ ] Zero-byte file handled gracefully
- [ ] Non-PDF file with .pdf extension handled gracefully
- [ ] Password-protected PDF flagged for review
- [ ] Malformed API numbers (wrong digits, invalid state code, OCR artifacts) handled
- [ ] Coordinates outside US boundaries rejected
- [ ] Swapped lat/lng detected or rejected
- [ ] Production volumes outside realistic ranges flagged
- [ ] Future dates rejected
- [ ] SQL injection in search input does not affect database
- [ ] All API endpoints return proper 400/404/422 for invalid inputs
- [ ] Non-existent resource requests return 404
- [ ] Concurrent scrapes for same state handled appropriately
- [ ] Health endpoint reports unhealthy when DB is down
- [ ] Frontend shows empty state message when no results
- [ ] Frontend shows error message when API returns error
- [ ] All tests pass without unhandled exceptions

## Testing Protocol

### Unit/Integration Tests

Run Python error handling tests:
```bash
# All error handling tests
uv run pytest backend/tests/e2e/test_scraper_errors.py backend/tests/e2e/test_document_errors.py backend/tests/e2e/test_og_data_edge_cases.py backend/tests/e2e/test_api_errors.py backend/tests/e2e/test_concurrent_scrapes.py backend/tests/e2e/test_infrastructure_failures.py -v --timeout=120

# Just API error tests (fastest)
uv run pytest backend/tests/e2e/test_api_errors.py -v

# Just O&G data edge cases
uv run pytest backend/tests/e2e/test_og_data_edge_cases.py -v
```

### Browser Testing (Playwright MCP)

Run Playwright error state tests:
```bash
cd frontend && npx playwright test e2e/error-states.spec.ts --headed
```

### API/Script Testing

Manual curl commands for error validation:
```bash
# Invalid UUID
curl -s http://localhost:8000/api/wells/not-a-uuid | python -m json.tool

# Non-existent resource
curl -s http://localhost:8000/api/wells/00000000-0000-0000-0000-000000000000 | python -m json.tool

# Invalid state code
curl -s -X POST http://localhost:8000/api/scrape -H "Content-Type: application/json" -d '{"state":"ZZ"}' | python -m json.tool

# Missing required field
curl -s -X POST http://localhost:8000/api/scrape -H "Content-Type: application/json" -d '{}' | python -m json.tool

# SQL injection attempt
curl -s "http://localhost:8000/api/wells/search?q=%27%3B+DROP+TABLE+wells%3B+--" | python -m json.tool

# Invalid pagination
curl -s "http://localhost:8000/api/wells?page=-1&per_page=10000" | python -m json.tool

# Invalid bounding box
curl -s "http://localhost:8000/api/map/wells?min_lat=40&max_lat=30&min_lng=-100&max_lng=-90" | python -m json.tool

# Invalid date range
curl -s "http://localhost:8000/api/documents?date_from=2026-12-31&date_to=2026-01-01" | python -m json.tool

# Health check during DB outage
docker compose stop db && curl -s http://localhost:8000/health | python -m json.tool && docker compose start db
```

### Build/Lint/Type Checks

- [ ] `uv run ruff check backend/tests/e2e/` passes
- [ ] `uv run ruff format --check backend/tests/e2e/` passes
- [ ] `cd frontend && npm run lint` passes
- [ ] All error tests pass without unhandled exceptions

## Skills to Read

- `og-testing-strategies` - Test infrastructure patterns
- `confidence-scoring` - Threshold values, critical field override, scoring formula
- `og-scraper-architecture` - Document status state machine, file storage, API contract
- `state-regulatory-sites` - Known issues per state (paywall, timeouts, site quirks)

## Research Files to Read

- `.claude/orchestration-og-doc-scraper/research/og-data-models.md` - API number formats, production volume ranges, coordinate validation, operator name variations
- `.claude/orchestration-og-doc-scraper/research/testing-deployment-implementation.md` - Error handling patterns, health checks, Docker debugging
- `.claude/orchestration-og-doc-scraper/research/state-regulatory-sites.md` - Per-state site issues and failure modes

## Git

- Branch: `task-7-3/error-handling-edge-cases`
- Commit message prefix: `Task 7.3:`
