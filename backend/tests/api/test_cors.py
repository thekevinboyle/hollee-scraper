"""Tests for CORS configuration."""

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
async def test_cors_allows_frontend_origin(client):
    """CORS headers allow the frontend origin."""
    response = await client.options(
        "/health",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert response.headers.get("access-control-allow-origin") == "http://localhost:3000"


@pytest.mark.asyncio
async def test_cors_allows_127_origin(client):
    """CORS headers allow the 127.0.0.1:3000 origin."""
    response = await client.options(
        "/health",
        headers={
            "Origin": "http://127.0.0.1:3000",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert response.headers.get("access-control-allow-origin") == "http://127.0.0.1:3000"


@pytest.mark.asyncio
async def test_cors_blocks_unknown_origin(client):
    """CORS does not allow unknown origins."""
    response = await client.options(
        "/health",
        headers={
            "Origin": "http://evil.com",
            "Access-Control-Request-Method": "GET",
        },
    )
    # FastAPI CORS middleware doesn't set the header for disallowed origins
    allow_origin = response.headers.get("access-control-allow-origin")
    assert allow_origin != "http://evil.com"


@pytest.mark.asyncio
async def test_cors_allows_all_methods(client):
    """CORS allows all HTTP methods for allowed origins."""
    for method in ["GET", "POST", "PUT", "DELETE", "PATCH"]:
        response = await client.options(
            "/health",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": method,
            },
        )
        assert response.headers.get("access-control-allow-origin") == "http://localhost:3000"


@pytest.mark.asyncio
async def test_cors_allows_credentials(client):
    """CORS allows credentials for allowed origins."""
    response = await client.options(
        "/health",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert response.headers.get("access-control-allow-credentials") == "true"
