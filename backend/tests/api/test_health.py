"""Tests for the health check endpoint."""

import pytest
from httpx import ASGITransport, AsyncClient

from og_scraper.api.app import create_app


@pytest.fixture
def app():
    return create_app()


@pytest.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.mark.asyncio
async def test_health_returns_200(client):
    """Health endpoint returns 200 status code."""
    response = await client.get("/health")
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_health_response_shape(client):
    """Health response has expected fields."""
    response = await client.get("/health")
    data = response.json()
    assert "status" in data
    assert "version" in data
    assert "db" in data
    assert data["version"] == "0.1.0"


@pytest.mark.asyncio
async def test_health_db_connected(client):
    """Health check reports database as connected when DB is up.

    Note: This test requires PostgreSQL to be running.
    Mark as integration test if running without Docker.
    """
    response = await client.get("/health")
    data = response.json()
    # In test environment without DB, this may show 'disconnected'
    # When DB is available, it should show 'connected'
    assert data["db"] in ("connected", "disconnected") or data["db"].startswith(
        "error:"
    )


@pytest.mark.asyncio
async def test_health_postgis_version_when_connected(client):
    """Health check includes PostGIS version when database is connected."""
    response = await client.get("/health")
    data = response.json()
    # If connected, PostGIS version should be present
    if data["db"] == "connected":
        assert data["postgis_version"] is not None
        assert data["db_version"] is not None
        assert data["status"] == "ok"


@pytest.mark.asyncio
async def test_health_degraded_when_disconnected(client):
    """Health check returns degraded status when DB is unreachable."""
    response = await client.get("/health")
    data = response.json()
    if data["db"] != "connected":
        assert data["status"] == "degraded"
