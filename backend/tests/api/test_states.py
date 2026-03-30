"""Tests for state API endpoints."""

from collections import namedtuple
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from og_scraper.api.deps import get_db

StateRow = namedtuple(
    "StateRow",
    ["code", "name", "api_state_code", "tier", "last_scraped_at", "well_count", "document_count"],
)


@pytest.mark.asyncio
async def test_list_states_returns_200(app, seed_data):
    """GET /api/v1/states returns all seeded states with counts."""
    states_data = seed_data["states"]

    state_rows = [
        StateRow(
            code=s["code"],
            name=s["name"],
            api_state_code=s["api_state_code"],
            tier=s["tier"],
            last_scraped_at=None,
            well_count=3 if s["code"] == "TX" else 1,
            document_count=3 if s["code"] == "TX" else 1,
        )
        for s in states_data
    ]

    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.all.return_value = state_rows
    mock_db.execute.return_value = mock_result

    async def mock_get_db():
        yield mock_db

    app.dependency_overrides[get_db] = mock_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test", follow_redirects=True) as client:
        response = await client.get("/api/v1/states")

    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) == 3

    # Check state fields
    for item in data:
        assert "code" in item
        assert "name" in item
        assert "api_state_code" in item
        assert "tier" in item
        assert "well_count" in item
        assert "document_count" in item

    # Check TX has higher counts
    tx = next(s for s in data if s["code"] == "TX")
    assert tx["well_count"] == 3
    assert tx["document_count"] == 3
    assert tx["name"] == "Texas"

    app.dependency_overrides.clear()
