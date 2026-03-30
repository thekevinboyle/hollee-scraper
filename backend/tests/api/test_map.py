"""Tests for map API endpoints."""

from collections import namedtuple
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from og_scraper.api.deps import get_db
from og_scraper.models.enums import WellStatus

from .conftest import (
    WELL_1_ID,
    WELL_2_ID,
    WELL_3_ID,
)

# Named tuple to simulate Row-like objects returned by the map query
MapWellRow = namedtuple(
    "MapWellRow",
    ["id", "api_number", "well_name", "operator_name", "latitude", "longitude", "well_status", "well_type"],
)


def _make_map_rows():
    """Create test map well rows with known coordinates.

    Well 1: West Texas (31.5, -103.5) -- inside TX bounding box
    Well 2: West Texas (31.7, -103.2) -- inside TX bounding box
    Well 3: North Dakota (48.1, -103.8) -- outside TX bounding box
    """
    return [
        MapWellRow(
            id=WELL_1_ID,
            api_number="42501201300300",
            well_name="TX Well 1",
            operator_name="Devon Energy Corporation",
            latitude=31.5,
            longitude=-103.5,
            well_status=WellStatus.ACTIVE,
            well_type="oil",
        ),
        MapWellRow(
            id=WELL_2_ID,
            api_number="42501201300400",
            well_name="TX Well 2",
            operator_name="Devon Energy Corporation",
            latitude=31.7,
            longitude=-103.2,
            well_status=WellStatus.ACTIVE,
            well_type="oil",
        ),
        MapWellRow(
            id=WELL_3_ID,
            api_number="33105678900000",
            well_name="ND Well 1",
            operator_name="Continental Resources",
            latitude=48.1,
            longitude=-103.8,
            well_status=WellStatus.PLUGGED,
            well_type="gas",
        ),
    ]


@pytest.mark.asyncio
async def test_map_wells_bounding_box(app):
    """GET /api/v1/map/wells returns wells within bounding box."""
    all_rows = _make_map_rows()
    # Only TX wells are within the bounding box (lat 31-32, lng -104 to -103)
    tx_rows = [r for r in all_rows if r.latitude >= 31.0 and r.latitude <= 32.0]

    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.all.return_value = tx_rows
    mock_db.execute.return_value = mock_result

    async def mock_get_db():
        yield mock_db

    app.dependency_overrides[get_db] = mock_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test", follow_redirects=True) as client:
        response = await client.get(
            "/api/v1/map/wells",
            params={
                "min_lat": 31.0,
                "max_lat": 32.0,
                "min_lng": -104.0,
                "max_lng": -103.0,
            },
        )

    assert response.status_code == 200
    wells = response.json()
    assert len(wells) == 2
    assert all(w["latitude"] >= 31.0 and w["latitude"] <= 32.0 for w in wells)
    assert all("id" in w and "api_number" in w for w in wells)

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_map_wells_with_status_filter(app):
    """GET /api/v1/map/wells with well_status filter returns filtered results."""
    all_rows = _make_map_rows()
    # Mock returns only active wells
    active_rows = [r for r in all_rows if r.well_status == WellStatus.ACTIVE]

    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.all.return_value = active_rows
    mock_db.execute.return_value = mock_result

    async def mock_get_db():
        yield mock_db

    app.dependency_overrides[get_db] = mock_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test", follow_redirects=True) as client:
        response = await client.get(
            "/api/v1/map/wells",
            params={
                "min_lat": 30.0,
                "max_lat": 50.0,
                "min_lng": -110.0,
                "max_lng": -100.0,
                "well_status": "active",
            },
        )

    assert response.status_code == 200
    wells = response.json()
    assert len(wells) == 2
    assert all(w["well_status"] == "active" for w in wells)

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_map_wells_with_type_filter(app):
    """GET /api/v1/map/wells with well_type filter returns filtered results."""
    gas_rows = [r for r in _make_map_rows() if r.well_type == "gas"]

    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.all.return_value = gas_rows
    mock_db.execute.return_value = mock_result

    async def mock_get_db():
        yield mock_db

    app.dependency_overrides[get_db] = mock_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test", follow_redirects=True) as client:
        response = await client.get(
            "/api/v1/map/wells",
            params={
                "min_lat": 30.0,
                "max_lat": 50.0,
                "min_lng": -110.0,
                "max_lng": -100.0,
                "well_type": "gas",
            },
        )

    assert response.status_code == 200
    wells = response.json()
    assert len(wells) == 1
    assert wells[0]["well_type"] == "gas"

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_map_wells_invalid_bounds_lat(app):
    """GET /api/v1/map/wells with inverted latitude returns 400."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test", follow_redirects=True) as client:
        response = await client.get(
            "/api/v1/map/wells",
            params={
                "min_lat": 40.0,
                "max_lat": 30.0,  # inverted
                "min_lng": -110.0,
                "max_lng": -100.0,
            },
        )

    assert response.status_code == 400
    assert "min_lat" in response.json()["detail"]


@pytest.mark.asyncio
async def test_map_wells_invalid_bounds_lng(app):
    """GET /api/v1/map/wells with inverted longitude returns 400."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test", follow_redirects=True) as client:
        response = await client.get(
            "/api/v1/map/wells",
            params={
                "min_lat": 30.0,
                "max_lat": 40.0,
                "min_lng": -100.0,
                "max_lng": -110.0,  # inverted
            },
        )

    assert response.status_code == 400
    assert "min_lng" in response.json()["detail"]


@pytest.mark.asyncio
async def test_map_wells_empty_area(app):
    """GET /api/v1/map/wells in ocean returns empty list."""
    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.all.return_value = []
    mock_db.execute.return_value = mock_result

    async def mock_get_db():
        yield mock_db

    app.dependency_overrides[get_db] = mock_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test", follow_redirects=True) as client:
        response = await client.get(
            "/api/v1/map/wells",
            params={
                "min_lat": 0.0,
                "max_lat": 1.0,
                "min_lng": 0.0,
                "max_lng": 1.0,
            },
        )

    assert response.status_code == 200
    assert len(response.json()) == 0

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_map_wells_limit_parameter(app):
    """GET /api/v1/map/wells respects limit parameter."""
    rows = _make_map_rows()[:1]  # Only return 1 even though more exist

    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.all.return_value = rows
    mock_db.execute.return_value = mock_result

    async def mock_get_db():
        yield mock_db

    app.dependency_overrides[get_db] = mock_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test", follow_redirects=True) as client:
        response = await client.get(
            "/api/v1/map/wells",
            params={
                "min_lat": 30.0,
                "max_lat": 50.0,
                "min_lng": -110.0,
                "max_lng": -100.0,
                "limit": 1,
            },
        )

    assert response.status_code == 200
    wells = response.json()
    assert len(wells) == 1

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_map_wells_missing_required_params(app):
    """GET /api/v1/map/wells without required params returns 422."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test", follow_redirects=True) as client:
        response = await client.get("/api/v1/map/wells")

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_map_wells_response_structure(app):
    """GET /api/v1/map/wells returns correct response fields."""
    rows = _make_map_rows()[:1]

    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.all.return_value = rows
    mock_db.execute.return_value = mock_result

    async def mock_get_db():
        yield mock_db

    app.dependency_overrides[get_db] = mock_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test", follow_redirects=True) as client:
        response = await client.get(
            "/api/v1/map/wells",
            params={
                "min_lat": 31.0,
                "max_lat": 32.0,
                "min_lng": -104.0,
                "max_lng": -103.0,
            },
        )

    assert response.status_code == 200
    well = response.json()[0]
    assert "id" in well
    assert "api_number" in well
    assert "well_name" in well
    assert "operator_name" in well
    assert "latitude" in well
    assert "longitude" in well
    assert "well_status" in well
    assert "well_type" in well

    app.dependency_overrides.clear()
