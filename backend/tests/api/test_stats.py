"""Tests for stats API endpoints."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from og_scraper.api.deps import get_db
from og_scraper.models.state import State

from .conftest import NOW


def _make_mock_state(code, name, api_state_code, tier=1, last_scraped_at=None):
    """Create a mock State object."""
    state = MagicMock(spec=State)
    state.code = code
    state.name = name
    state.api_state_code = api_state_code
    state.tier = tier
    state.last_scraped_at = last_scraped_at
    state.config = {}
    return state


def _setup_stats_mock_db():
    """Create a mock db session that returns realistic stats query results.

    Returns the mock_db and a dict of expected values for assertions.
    """
    mock_db = AsyncMock()

    # Track call count to return different results for different queries
    call_count = [0]

    async def execute_side_effect(query):
        call_count[0] += 1
        result = MagicMock()
        idx = call_count[0]

        if idx == 1:
            # total_wells
            result.scalar_one.return_value = 5
        elif idx == 2:
            # total_documents
            result.scalar_one.return_value = 5
        elif idx == 3:
            # total_extracted
            result.scalar_one.return_value = 2
        elif idx == 4:
            # documents_by_state
            result.all.return_value = [("TX", 3), ("NM", 1), ("ND", 1)]
        elif idx == 5:
            # documents_by_type
            result.all.return_value = [("production_report", 1), ("well_permit", 2), ("completion_report", 1), ("plugging_report", 1)]
        elif idx == 6:
            # wells_by_status
            result.all.return_value = [("active", 2), ("drilling", 1), ("plugged", 1), ("completed", 1)]
        elif idx == 7:
            # wells_by_state
            result.all.return_value = [("TX", 3), ("NM", 1), ("ND", 1)]
        elif idx == 8:
            # review_queue_pending
            result.scalar_one.return_value = 0
        elif idx == 9:
            # avg_confidence
            result.scalar_one.return_value = 0.9040
        elif idx == 10:
            # recent_scrape_jobs
            mock_scalars = MagicMock()
            mock_scalars.all.return_value = []
            result.scalars.return_value = mock_scalars
        else:
            result.scalar_one.return_value = 0
            result.all.return_value = []

        return result

    mock_db.execute = AsyncMock(side_effect=execute_side_effect)

    return mock_db


@pytest.mark.asyncio
async def test_dashboard_stats_returns_200(app):
    """GET /api/v1/stats returns 200 with all expected fields."""
    mock_db = _setup_stats_mock_db()

    async def mock_get_db():
        yield mock_db

    app.dependency_overrides[get_db] = mock_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test", follow_redirects=True) as client:
        response = await client.get("/api/v1/stats")

    assert response.status_code == 200
    data = response.json()
    assert "total_wells" in data
    assert "total_documents" in data
    assert "total_extracted" in data
    assert "documents_by_state" in data
    assert "documents_by_type" in data
    assert "wells_by_status" in data
    assert "wells_by_state" in data
    assert "review_queue_pending" in data
    assert "avg_confidence" in data
    assert "recent_scrape_jobs" in data

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_dashboard_stats_values(app):
    """GET /api/v1/stats returns correct aggregate values."""
    mock_db = _setup_stats_mock_db()

    async def mock_get_db():
        yield mock_db

    app.dependency_overrides[get_db] = mock_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test", follow_redirects=True) as client:
        response = await client.get("/api/v1/stats")

    data = response.json()
    assert data["total_wells"] == 5
    assert data["total_documents"] == 5
    assert data["total_extracted"] == 2
    assert isinstance(data["documents_by_state"], dict)
    assert data["documents_by_state"]["TX"] == 3
    assert isinstance(data["documents_by_type"], dict)
    assert isinstance(data["wells_by_status"], dict)
    assert isinstance(data["wells_by_state"], dict)
    assert data["review_queue_pending"] == 0
    assert data["avg_confidence"] == 0.904
    assert isinstance(data["recent_scrape_jobs"], list)

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_state_stats_returns_200(app):
    """GET /api/v1/stats/state/TX returns 200 with state-specific stats."""
    mock_db = AsyncMock()
    mock_state = _make_mock_state("TX", "Texas", "42", last_scraped_at=NOW)

    call_count = [0]

    async def execute_side_effect(query):
        call_count[0] += 1
        result = MagicMock()
        idx = call_count[0]

        if idx == 1:
            # total_wells
            result.scalar_one.return_value = 3
        elif idx == 2:
            # total_documents
            result.scalar_one.return_value = 3
        elif idx == 3:
            # docs_by_type
            result.all.return_value = [("production_report", 1), ("well_permit", 1), ("completion_report", 1)]
        elif idx == 4:
            # wells_by_status
            result.all.return_value = [("active", 2), ("completed", 1)]
        elif idx == 5:
            # avg_confidence
            result.scalar_one.return_value = 0.9167
        elif idx == 6:
            # review_pending
            result.scalar_one.return_value = 0
        else:
            result.scalar_one.return_value = 0

        return result

    mock_db.execute = AsyncMock(side_effect=execute_side_effect)
    mock_db.get = AsyncMock(return_value=mock_state)

    async def mock_get_db():
        yield mock_db

    app.dependency_overrides[get_db] = mock_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test", follow_redirects=True) as client:
        response = await client.get("/api/v1/stats/state/TX")

    assert response.status_code == 200
    data = response.json()
    assert data["state_code"] == "TX"
    assert data["state_name"] == "Texas"
    assert data["total_wells"] == 3
    assert data["total_documents"] == 3
    assert isinstance(data["documents_by_type"], dict)
    assert isinstance(data["wells_by_status"], dict)
    assert data["review_queue_pending"] == 0
    assert data["last_scraped_at"] is not None

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_state_stats_case_insensitive(app):
    """GET /api/v1/stats/state/tx (lowercase) works correctly."""
    mock_db = AsyncMock()
    mock_state = _make_mock_state("TX", "Texas", "42")

    call_count = [0]

    async def execute_side_effect(query):
        call_count[0] += 1
        result = MagicMock()
        idx = call_count[0]

        if idx == 1:
            # total_wells
            result.scalar_one.return_value = 0
        elif idx == 2:
            # total_documents
            result.scalar_one.return_value = 0
        elif idx == 3:
            # docs_by_type
            result.all.return_value = []
        elif idx == 4:
            # wells_by_status
            result.all.return_value = []
        elif idx == 5:
            # avg_confidence
            result.scalar_one.return_value = None
        elif idx == 6:
            # review_pending
            result.scalar_one.return_value = 0
        else:
            result.scalar_one.return_value = 0

        return result

    mock_db.execute = AsyncMock(side_effect=execute_side_effect)
    mock_db.get = AsyncMock(return_value=mock_state)

    async def mock_get_db():
        yield mock_db

    app.dependency_overrides[get_db] = mock_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test", follow_redirects=True) as client:
        response = await client.get("/api/v1/stats/state/tx")

    assert response.status_code == 200
    data = response.json()
    assert data["state_code"] == "TX"

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_state_stats_not_found(app):
    """GET /api/v1/stats/state/ZZ returns 404 for unknown state."""
    mock_db = AsyncMock()
    mock_db.get = AsyncMock(return_value=None)

    async def mock_get_db():
        yield mock_db

    app.dependency_overrides[get_db] = mock_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test", follow_redirects=True) as client:
        response = await client.get("/api/v1/stats/state/ZZ")

    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_dashboard_stats_null_confidence(app):
    """GET /api/v1/stats handles null avg_confidence gracefully."""
    mock_db = AsyncMock()

    call_count = [0]

    async def execute_side_effect(query):
        call_count[0] += 1
        result = MagicMock()
        idx = call_count[0]

        if idx <= 3:
            result.scalar_one.return_value = 0
        elif idx <= 7:
            result.all.return_value = []
        elif idx == 8:
            # review_queue_pending
            result.scalar_one.return_value = 0
        elif idx == 9:
            # avg_confidence -- None when no documents with confidence
            result.scalar_one.return_value = None
        elif idx == 10:
            # recent_scrape_jobs
            mock_scalars = MagicMock()
            mock_scalars.all.return_value = []
            result.scalars.return_value = mock_scalars
        else:
            result.scalar_one.return_value = 0

        return result

    mock_db.execute = AsyncMock(side_effect=execute_side_effect)

    async def mock_get_db():
        yield mock_db

    app.dependency_overrides[get_db] = mock_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test", follow_redirects=True) as client:
        response = await client.get("/api/v1/stats")

    assert response.status_code == 200
    data = response.json()
    assert data["avg_confidence"] is None

    app.dependency_overrides.clear()
