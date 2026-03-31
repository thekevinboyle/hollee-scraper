"""Task 7.1: API integration tests.

Tests API endpoints with seeded database data via httpx AsyncClient.
Requires Docker for testcontainers PostgreSQL+PostGIS.
"""

import pytest

from tests.e2e.conftest import requires_docker


@requires_docker
class TestStatesEndpoint:
    """Test /api/v1/states/ endpoint."""

    @pytest.mark.asyncio
    async def test_states_returns_10(self, client):
        response = await client.get("/api/v1/states/")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 10

    @pytest.mark.asyncio
    async def test_states_have_required_fields(self, client):
        response = await client.get("/api/v1/states/")
        data = response.json()
        for state in data:
            assert "code" in state
            assert "name" in state
            assert len(state["code"]) == 2


@requires_docker
class TestWellsEndpoint:
    """Test /api/v1/wells/ endpoint."""

    @pytest.mark.asyncio
    async def test_wells_list_empty(self, client):
        """No wells seeded — should return empty list."""
        response = await client.get("/api/v1/wells/")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 0
        assert data["items"] == []

    @pytest.mark.asyncio
    async def test_wells_list_with_data(self, client_with_wells, seeded_wells):
        """Wells seeded — should return well records."""
        response = await client_with_wells.get("/api/v1/wells/")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 5
        assert len(data["items"]) == 5

    @pytest.mark.asyncio
    async def test_wells_filter_by_state(self, client_with_wells):
        """Filter wells by state should narrow results."""
        response = await client_with_wells.get("/api/v1/wells/", params={"state": "TX"})
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 2
        for item in data["items"]:
            assert item["state_code"] == "TX"

    @pytest.mark.asyncio
    async def test_wells_pagination(self, client_with_wells):
        """Pagination should limit results per page."""
        response = await client_with_wells.get("/api/v1/wells/", params={"page_size": 2, "page": 1})
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 2
        assert data["total"] == 5

    @pytest.mark.asyncio
    async def test_well_detail_by_api_number(self, client_with_wells, seeded_wells):
        """Get well detail by API number."""
        first_well = list(seeded_wells["wells"].values())[0]
        response = await client_with_wells.get(f"/api/v1/wells/{first_well.api_number}")
        assert response.status_code == 200
        data = response.json()
        assert data["api_number"] == first_well.api_number

    @pytest.mark.asyncio
    async def test_well_not_found(self, client_with_wells):
        """Non-existent API number returns 404."""
        response = await client_with_wells.get("/api/v1/wells/99999999999999")
        assert response.status_code == 404


@requires_docker
class TestDocumentsEndpoint:
    """Test /api/v1/documents/ endpoint."""

    @pytest.mark.asyncio
    async def test_documents_list(self, client_with_documents, seeded_documents):
        response = await client_with_documents.get("/api/v1/documents/")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 5

    @pytest.mark.asyncio
    async def test_documents_filter_by_state(self, client_with_documents):
        response = await client_with_documents.get("/api/v1/documents/", params={"state": "TX"})
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 2


@requires_docker
class TestMapEndpoint:
    """Test /api/v1/map/wells endpoint."""

    @pytest.mark.asyncio
    async def test_map_wells_bounding_box(self, client_with_wells):
        """Wells within bounding box should be returned."""
        response = await client_with_wells.get(
            "/api/v1/map/wells",
            params={
                "min_lat": 31.0,
                "max_lat": 33.0,
                "min_lng": -103.0,
                "max_lng": -101.0,
            },
        )
        assert response.status_code == 200
        wells = response.json()
        assert len(wells) >= 1
        for well in wells:
            assert 31.0 <= well["latitude"] <= 33.0
            assert -103.0 <= well["longitude"] <= -101.0

    @pytest.mark.asyncio
    async def test_map_wells_outside_box_excluded(self, client_with_wells):
        """Wells outside bounding box should not be returned."""
        # Tiny box in the middle of the ocean
        response = await client_with_wells.get(
            "/api/v1/map/wells",
            params={
                "min_lat": 0.0,
                "max_lat": 0.1,
                "min_lng": 0.0,
                "max_lng": 0.1,
            },
        )
        assert response.status_code == 200
        wells = response.json()
        assert len(wells) == 0

    @pytest.mark.asyncio
    async def test_map_invalid_bounds(self, client_with_wells):
        """Invalid bounds should return 400."""
        response = await client_with_wells.get(
            "/api/v1/map/wells",
            params={"min_lat": 40, "max_lat": 30, "min_lng": -100, "max_lng": -90},
        )
        assert response.status_code == 400


@requires_docker
class TestStatsEndpoint:
    """Test /api/v1/stats/ endpoint."""

    @pytest.mark.asyncio
    async def test_stats_response(self, client_with_documents):
        response = await client_with_documents.get("/api/v1/stats/")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, dict)


@requires_docker
class TestScrapeEndpoint:
    """Test /api/v1/scrape/ endpoint."""

    @pytest.mark.asyncio
    async def test_create_scrape_job(self, client):
        """Creating a scrape job should return 202."""
        response = await client.post(
            "/api/v1/scrape/",
            json={"state_code": "TX", "job_type": "full"},
        )
        assert response.status_code == 202
        data = response.json()
        assert data["state_code"] == "TX"
        assert data["status"] == "pending"
        assert "id" in data

    @pytest.mark.asyncio
    async def test_create_scrape_invalid_state(self, client):
        """Invalid state code should return 400."""
        response = await client.post(
            "/api/v1/scrape/",
            json={"state_code": "ZZ", "job_type": "full"},
        )
        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_list_scrape_jobs(self, client):
        """Listing scrape jobs should return paginated results."""
        response = await client.get("/api/v1/scrape/jobs")
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert "total" in data
