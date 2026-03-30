"""Tests for operator API endpoints."""

from collections import namedtuple
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from og_scraper.api.deps import get_db

OperatorRow = namedtuple(
    "OperatorRow",
    ["id", "name", "normalized_name", "well_count", "state_codes"],
)


@pytest.mark.asyncio
async def test_list_operators_returns_200(app, seed_data):
    """GET /api/v1/operators returns paginated operator list."""
    operators = seed_data["operators"]

    op_rows = [
        OperatorRow(
            id=operators[0].id,
            name=operators[0].name,
            normalized_name=operators[0].normalized_name,
            well_count=3,
            state_codes=["TX"],
        ),
        OperatorRow(
            id=operators[1].id,
            name=operators[1].name,
            normalized_name=operators[1].normalized_name,
            well_count=2,
            state_codes=["NM", "ND"],
        ),
    ]

    mock_db = AsyncMock()

    async def mock_get_db():
        yield mock_db

    app.dependency_overrides[get_db] = mock_get_db

    with patch("og_scraper.api.routes.operators.paginate") as mock_paginate:
        mock_paginate.return_value = {
            "items": op_rows,
            "total": 2,
            "page": 1,
            "page_size": 50,
            "total_pages": 1,
        }

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test", follow_redirects=True) as client:
            response = await client.get("/api/v1/operators")

        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert "total" in data
        assert data["total"] == 2
        assert len(data["items"]) == 2

        # Check operator fields
        item = data["items"][0]
        assert "id" in item
        assert "name" in item
        assert "normalized_name" in item
        assert "well_count" in item
        assert "state_codes" in item

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_list_operators_search(app, seed_data):
    """GET /api/v1/operators?q=Devon returns matching operators."""
    operators = seed_data["operators"]

    op_rows = [
        OperatorRow(
            id=operators[0].id,
            name=operators[0].name,
            normalized_name=operators[0].normalized_name,
            well_count=3,
            state_codes=["TX"],
        ),
    ]

    mock_db = AsyncMock()

    async def mock_get_db():
        yield mock_db

    app.dependency_overrides[get_db] = mock_get_db

    with patch("og_scraper.api.routes.operators.paginate") as mock_paginate:
        mock_paginate.return_value = {
            "items": op_rows,
            "total": 1,
            "page": 1,
            "page_size": 50,
            "total_pages": 1,
        }

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test", follow_redirects=True) as client:
            response = await client.get("/api/v1/operators?q=Devon")

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert data["items"][0]["name"] == "Devon Energy Corporation"

    app.dependency_overrides.clear()
