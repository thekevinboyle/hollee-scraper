"""Tests for export API endpoints."""

import json
from collections import namedtuple
from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient

from og_scraper.api.deps import get_db
from og_scraper.models.enums import WellStatus

# Named tuple to simulate well export query rows
WellExportRow = namedtuple(
    "WellExportRow",
    [
        "api_number",
        "well_name",
        "well_number",
        "operator_name",
        "state_code",
        "county",
        "basin",
        "field_name",
        "lease_name",
        "latitude",
        "longitude",
        "well_status",
        "well_type",
        "spud_date",
        "completion_date",
        "total_depth",
    ],
)

# Named tuple for production export query rows
ProductionExportRow = namedtuple(
    "ProductionExportRow",
    [
        "api_number",
        "well_name",
        "operator_name",
        "state_code",
        "county",
        "data",
        "reporting_period_start",
        "reporting_period_end",
        "confidence_score",
    ],
)


def _make_well_export_rows():
    """Create test well export rows."""
    return [
        WellExportRow(
            api_number="42501201300300",
            well_name="Test Well 1",
            well_number="1",
            operator_name="Devon Energy Corporation",
            state_code="TX",
            county="Reeves",
            basin="Permian",
            field_name="Wolfcamp",
            lease_name="Test Lease A",
            latitude=31.5,
            longitude=-103.5,
            well_status=WellStatus.ACTIVE,
            well_type="oil",
            spud_date=date(2024, 1, 15),
            completion_date=date(2024, 6, 1),
            total_depth=12000,
        ),
        WellExportRow(
            api_number="42501201300400",
            well_name="Test Well 2",
            well_number="2",
            operator_name="Devon Energy Corporation",
            state_code="TX",
            county="Loving",
            basin="Permian",
            field_name=None,
            lease_name=None,
            latitude=31.7,
            longitude=-103.2,
            well_status=WellStatus.ACTIVE,
            well_type="oil",
            spud_date=None,
            completion_date=None,
            total_depth=None,
        ),
        WellExportRow(
            api_number="30015123450000",
            well_name="NM Well 1",
            well_number="1",
            operator_name="Continental Resources",
            state_code="NM",
            county="Lea",
            basin="Permian",
            field_name=None,
            lease_name=None,
            latitude=32.5,
            longitude=-103.8,
            well_status=WellStatus.DRILLING,
            well_type="gas",
            spud_date=date(2025, 1, 10),
            completion_date=None,
            total_depth=None,
        ),
    ]


def _make_production_export_rows():
    """Create test production export rows."""
    return [
        ProductionExportRow(
            api_number="42501201300300",
            well_name="Test Well 1",
            operator_name="Devon Energy Corporation",
            state_code="TX",
            county="Reeves",
            data={"oil_bbl": 1250, "gas_mcf": 3400, "water_bbl": 890, "days_produced": 30},
            reporting_period_start=date(2025, 1, 1),
            reporting_period_end=date(2025, 1, 31),
            confidence_score=Decimal("0.9400"),
        ),
        ProductionExportRow(
            api_number="42501201300300",
            well_name="Test Well 1",
            operator_name="Devon Energy Corporation",
            state_code="TX",
            county="Reeves",
            data={"oil_bbl": 1100, "gas_mcf": 3200, "water_bbl": 920, "days_produced": 28},
            reporting_period_start=date(2025, 2, 1),
            reporting_period_end=date(2025, 2, 28),
            confidence_score=Decimal("0.9200"),
        ),
    ]


class MockAsyncStream:
    """Mock for db.stream() that yields rows asynchronously."""

    def __init__(self, rows):
        self._rows = rows

    def __aiter__(self):
        return self._iter()

    async def _iter(self):
        for row in self._rows:
            yield row


@pytest.mark.asyncio
async def test_export_wells_csv(app):
    """GET /api/v1/export/wells?format=csv returns valid CSV with headers."""
    rows = _make_well_export_rows()

    mock_db = AsyncMock()
    mock_db.stream = AsyncMock(return_value=MockAsyncStream(rows))

    async def mock_get_db():
        yield mock_db

    app.dependency_overrides[get_db] = mock_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test", follow_redirects=True) as client:
        response = await client.get("/api/v1/export/wells?format=csv")

    assert response.status_code == 200
    assert "text/csv" in response.headers["content-type"]
    assert "Content-Disposition" in response.headers
    assert "wells_export.csv" in response.headers["Content-Disposition"]

    lines = response.text.strip().split("\n")
    assert len(lines) == 4  # header + 3 data rows
    header = lines[0]
    assert "api_number" in header
    assert "well_name" in header
    assert "operator" in header
    assert "latitude" in header
    assert "longitude" in header

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_export_wells_json(app):
    """GET /api/v1/export/wells?format=json returns valid JSON array."""
    rows = _make_well_export_rows()

    mock_db = AsyncMock()
    mock_db.stream = AsyncMock(return_value=MockAsyncStream(rows))

    async def mock_get_db():
        yield mock_db

    app.dependency_overrides[get_db] = mock_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test", follow_redirects=True) as client:
        response = await client.get("/api/v1/export/wells?format=json")

    assert response.status_code == 200
    assert "application/json" in response.headers["content-type"]
    assert "wells_export.json" in response.headers["Content-Disposition"]

    data = json.loads(response.text)
    assert isinstance(data, list)
    assert len(data) == 3
    assert "api_number" in data[0]
    assert "well_name" in data[0]
    assert data[0]["api_number"] == "42501201300300"

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_export_wells_csv_state_filter(app):
    """GET /api/v1/export/wells?format=csv&state=TX returns only TX rows."""
    # Only TX rows
    tx_rows = [r for r in _make_well_export_rows() if r.state_code == "TX"]

    mock_db = AsyncMock()
    mock_db.stream = AsyncMock(return_value=MockAsyncStream(tx_rows))

    async def mock_get_db():
        yield mock_db

    app.dependency_overrides[get_db] = mock_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test", follow_redirects=True) as client:
        response = await client.get("/api/v1/export/wells?format=csv&state=TX")

    assert response.status_code == 200
    lines = response.text.strip().split("\n")
    assert len(lines) == 3  # header + 2 TX rows
    for line in lines[1:]:
        assert "TX" in line

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_export_wells_json_state_filter(app):
    """GET /api/v1/export/wells?format=json&state=TX returns only TX entries."""
    tx_rows = [r for r in _make_well_export_rows() if r.state_code == "TX"]

    mock_db = AsyncMock()
    mock_db.stream = AsyncMock(return_value=MockAsyncStream(tx_rows))

    async def mock_get_db():
        yield mock_db

    app.dependency_overrides[get_db] = mock_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test", follow_redirects=True) as client:
        response = await client.get("/api/v1/export/wells?format=json&state=TX")

    assert response.status_code == 200
    data = json.loads(response.text)
    assert len(data) == 2
    assert all(d["state"] == "TX" for d in data)

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_export_wells_empty(app):
    """GET /api/v1/export/wells with no data returns headers-only CSV or empty JSON array."""
    mock_db = AsyncMock()
    mock_db.stream = AsyncMock(return_value=MockAsyncStream([]))

    async def mock_get_db():
        yield mock_db

    app.dependency_overrides[get_db] = mock_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test", follow_redirects=True) as client:
        # CSV -- should have header only
        response_csv = await client.get("/api/v1/export/wells?format=csv")
        assert response_csv.status_code == 200
        lines = response_csv.text.strip().split("\n")
        assert len(lines) == 1  # header only
        assert "api_number" in lines[0]

        # JSON -- should be empty array
        mock_db.stream = AsyncMock(return_value=MockAsyncStream([]))
        response_json = await client.get("/api/v1/export/wells?format=json")
        assert response_json.status_code == 200
        data = json.loads(response_json.text)
        assert data == []

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_export_production_csv(app):
    """GET /api/v1/export/production?format=csv returns valid CSV with production columns."""
    rows = _make_production_export_rows()

    mock_db = AsyncMock()
    mock_db.stream = AsyncMock(return_value=MockAsyncStream(rows))

    async def mock_get_db():
        yield mock_db

    app.dependency_overrides[get_db] = mock_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test", follow_redirects=True) as client:
        response = await client.get("/api/v1/export/production?format=csv")

    assert response.status_code == 200
    assert "text/csv" in response.headers["content-type"]
    assert "production_export.csv" in response.headers["Content-Disposition"]

    lines = response.text.strip().split("\n")
    assert len(lines) == 3  # header + 2 data rows
    header = lines[0]
    assert "api_number" in header
    assert "oil_bbl" in header
    assert "gas_mcf" in header
    assert "water_bbl" in header
    assert "days_produced" in header
    assert "confidence_score" in header

    # Verify data values in first data row
    assert "1250" in lines[1]
    assert "3400" in lines[1]

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_export_production_json(app):
    """GET /api/v1/export/production?format=json returns valid JSON with production data."""
    rows = _make_production_export_rows()

    mock_db = AsyncMock()
    mock_db.stream = AsyncMock(return_value=MockAsyncStream(rows))

    async def mock_get_db():
        yield mock_db

    app.dependency_overrides[get_db] = mock_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test", follow_redirects=True) as client:
        response = await client.get("/api/v1/export/production?format=json")

    assert response.status_code == 200
    data = json.loads(response.text)
    assert isinstance(data, list)
    assert len(data) == 2
    assert data[0]["oil_bbl"] == 1250
    assert data[0]["gas_mcf"] == 3400
    assert data[0]["water_bbl"] == 890
    assert data[0]["days_produced"] == 30
    assert data[0]["reporting_period_start"] == "2025-01-01"
    assert data[0]["reporting_period_end"] == "2025-01-31"

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_export_production_empty(app):
    """GET /api/v1/export/production with no data returns headers-only CSV or empty JSON."""
    mock_db = AsyncMock()
    mock_db.stream = AsyncMock(return_value=MockAsyncStream([]))

    async def mock_get_db():
        yield mock_db

    app.dependency_overrides[get_db] = mock_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test", follow_redirects=True) as client:
        # CSV
        response = await client.get("/api/v1/export/production?format=csv")
        assert response.status_code == 200
        lines = response.text.strip().split("\n")
        assert len(lines) == 1  # header only

        # JSON
        mock_db.stream = AsyncMock(return_value=MockAsyncStream([]))
        response = await client.get("/api/v1/export/production?format=json")
        assert response.status_code == 200
        assert json.loads(response.text) == []

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_export_production_date_filter(app):
    """GET /api/v1/export/production with date filters works correctly."""
    rows = _make_production_export_rows()[:1]  # Only January data

    mock_db = AsyncMock()
    mock_db.stream = AsyncMock(return_value=MockAsyncStream(rows))

    async def mock_get_db():
        yield mock_db

    app.dependency_overrides[get_db] = mock_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test", follow_redirects=True) as client:
        response = await client.get(
            "/api/v1/export/production",
            params={"format": "csv", "date_from": "2025-01-01", "date_to": "2025-01-31"},
        )

    assert response.status_code == 200
    lines = response.text.strip().split("\n")
    assert len(lines) == 2  # header + 1 row

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_export_wells_default_format_is_csv(app):
    """GET /api/v1/export/wells without format param defaults to CSV."""
    mock_db = AsyncMock()
    mock_db.stream = AsyncMock(return_value=MockAsyncStream([]))

    async def mock_get_db():
        yield mock_db

    app.dependency_overrides[get_db] = mock_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test", follow_redirects=True) as client:
        response = await client.get("/api/v1/export/wells")

    assert response.status_code == 200
    assert "text/csv" in response.headers["content-type"]

    app.dependency_overrides.clear()
