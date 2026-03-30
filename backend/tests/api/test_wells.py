"""Tests for well API endpoints."""

from collections import namedtuple
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from og_scraper.api.deps import get_db

from .conftest import (
    STATE_TX,
)

# Named tuple to simulate Row-like objects from query results
WellRow = namedtuple(
    "WellRow",
    [
        "id",
        "api_number",
        "well_name",
        "operator_name",
        "state_code",
        "county",
        "well_status",
        "well_type",
        "latitude",
        "longitude",
        "document_count",
    ],
)


def make_well_row(well, operator_name=None, document_count=0):
    """Create a WellRow from a mock well object."""
    return WellRow(
        id=well.id,
        api_number=well.api_number,
        well_name=well.well_name,
        operator_name=operator_name,
        state_code=well.state_code,
        county=well.county,
        well_status=well.well_status,
        well_type=well.well_type,
        latitude=well.latitude,
        longitude=well.longitude,
        document_count=document_count,
    )


@pytest.mark.asyncio
async def test_list_wells_returns_200(app, seed_data):
    """GET /api/v1/wells returns 200 with paginated response structure."""
    wells = seed_data["wells"]
    operators = seed_data["operators"]

    mock_db = AsyncMock()

    # Mock paginate to return well rows
    well_rows = [
        make_well_row(wells[0], operators[0].name, 2),
        make_well_row(wells[1], operators[0].name, 1),
        make_well_row(wells[2], operators[1].name, 1),
    ]

    async def mock_get_db():
        yield mock_db

    app.dependency_overrides[get_db] = mock_get_db

    with patch("og_scraper.api.routes.wells.paginate") as mock_paginate:
        mock_paginate.return_value = {
            "items": well_rows,
            "total": 3,
            "page": 1,
            "page_size": 50,
            "total_pages": 1,
        }

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test", follow_redirects=True) as client:
            response = await client.get("/api/v1/wells")

        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert "total" in data
        assert "page" in data
        assert "page_size" in data
        assert "total_pages" in data
        assert data["total"] == 3
        assert data["page"] == 1
        assert len(data["items"]) == 3

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_list_wells_filter_by_state(app, seed_data):
    """GET /api/v1/wells?state=TX returns only Texas wells."""
    wells = seed_data["wells"]
    operators = seed_data["operators"]

    tx_wells = [w for w in wells if w.state_code == STATE_TX]
    well_rows = [make_well_row(w, operators[0].name, len(w.documents)) for w in tx_wells]

    mock_db = AsyncMock()

    async def mock_get_db():
        yield mock_db

    app.dependency_overrides[get_db] = mock_get_db

    with patch("og_scraper.api.routes.wells.paginate") as mock_paginate:
        mock_paginate.return_value = {
            "items": well_rows,
            "total": len(well_rows),
            "page": 1,
            "page_size": 50,
            "total_pages": 1,
        }

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test", follow_redirects=True) as client:
            response = await client.get("/api/v1/wells?state=TX")

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == len(tx_wells)
        for item in data["items"]:
            assert item["state_code"] == "TX"

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_list_wells_filter_by_operator(app, seed_data):
    """GET /api/v1/wells?operator=Devon returns wells with matching operator."""
    wells = seed_data["wells"]
    op1 = seed_data["operators"][0]

    devon_wells = [w for w in wells if w.operator and w.operator.id == op1.id]
    well_rows = [make_well_row(w, op1.name, len(w.documents)) for w in devon_wells]

    mock_db = AsyncMock()

    async def mock_get_db():
        yield mock_db

    app.dependency_overrides[get_db] = mock_get_db

    with patch("og_scraper.api.routes.wells.paginate") as mock_paginate:
        mock_paginate.return_value = {
            "items": well_rows,
            "total": len(well_rows),
            "page": 1,
            "page_size": 50,
            "total_pages": 1,
        }

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test", follow_redirects=True) as client:
            response = await client.get("/api/v1/wells?operator=Devon")

        assert response.status_code == 200
        data = response.json()
        for item in data["items"]:
            assert item["operator_name"] == "Devon Energy Corporation"

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_list_wells_pagination(app, seed_data):
    """GET /api/v1/wells?page=2&page_size=2 returns correct page."""
    wells = seed_data["wells"]
    operators = seed_data["operators"]

    # Page 2 with page_size=2 should return wells 3-4
    page2_wells = wells[2:4]
    well_rows = [make_well_row(w, operators[1].name, len(w.documents)) for w in page2_wells]

    mock_db = AsyncMock()

    async def mock_get_db():
        yield mock_db

    app.dependency_overrides[get_db] = mock_get_db

    with patch("og_scraper.api.routes.wells.paginate") as mock_paginate:
        mock_paginate.return_value = {
            "items": well_rows,
            "total": 5,
            "page": 2,
            "page_size": 2,
            "total_pages": 3,
        }

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test", follow_redirects=True) as client:
            response = await client.get("/api/v1/wells?page=2&page_size=2")

        assert response.status_code == 200
        data = response.json()
        assert data["page"] == 2
        assert data["page_size"] == 2
        assert data["total"] == 5
        assert data["total_pages"] == 3
        assert len(data["items"]) == 2

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_list_wells_full_text_search(app, seed_data):
    """GET /api/v1/wells?q=permian returns wells matching full-text search."""
    wells = seed_data["wells"][:2]
    well_rows = [make_well_row(w, "Devon Energy Corporation", 2) for w in wells]

    mock_db = AsyncMock()

    async def mock_get_db():
        yield mock_db

    app.dependency_overrides[get_db] = mock_get_db

    with patch("og_scraper.api.routes.wells.paginate") as mock_paginate:
        mock_paginate.return_value = {
            "items": well_rows,
            "total": 2,
            "page": 1,
            "page_size": 50,
            "total_pages": 1,
        }

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test", follow_redirects=True) as client:
            response = await client.get("/api/v1/wells?q=permian")

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 2

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_list_wells_api_number_filter(app, seed_data):
    """GET /api/v1/wells?api_number=42-501-20130 normalizes and finds the well."""
    wells = seed_data["wells"]
    well_rows = [make_well_row(wells[0], "Devon Energy Corporation", 2)]

    mock_db = AsyncMock()

    async def mock_get_db():
        yield mock_db

    app.dependency_overrides[get_db] = mock_get_db

    with patch("og_scraper.api.routes.wells.paginate") as mock_paginate:
        mock_paginate.return_value = {
            "items": well_rows,
            "total": 1,
            "page": 1,
            "page_size": 50,
            "total_pages": 1,
        }

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test", follow_redirects=True) as client:
            response = await client.get("/api/v1/wells?api_number=42-501-20130")

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_get_well_detail(app, seed_data):
    """GET /api/v1/wells/{api_number} returns well detail with documents."""
    well = seed_data["wells"][0]
    operator = seed_data["operators"][0]

    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = well
    mock_db.execute.return_value = mock_result

    async def mock_get_db():
        yield mock_db

    app.dependency_overrides[get_db] = mock_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(f"/api/v1/wells/{well.api_number}")

    assert response.status_code == 200
    data = response.json()
    assert data["api_number"] == well.api_number
    assert data["operator_name"] == operator.name
    assert data["state_code"] == "TX"
    assert "documents" in data

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_get_well_detail_with_dashes(app, seed_data):
    """GET /api/v1/wells/42-501-20130-03-00 normalizes and finds the well."""
    well = seed_data["wells"][0]

    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = well
    mock_db.execute.return_value = mock_result

    async def mock_get_db():
        yield mock_db

    app.dependency_overrides[get_db] = mock_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/wells/42-501-20130-03-00")

    assert response.status_code == 200
    data = response.json()
    assert data["api_number"] == well.api_number

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_get_well_not_found(app):
    """GET /api/v1/wells/99999999999 returns 404."""
    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_db.execute.return_value = mock_result

    async def mock_get_db():
        yield mock_db

    app.dependency_overrides[get_db] = mock_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/wells/99999999999")

    assert response.status_code == 404

    app.dependency_overrides.clear()
