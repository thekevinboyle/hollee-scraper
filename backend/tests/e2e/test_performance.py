"""Task 7.4: Performance & benchmark tests.

Verifies API response times, pipeline processing speed, database query
performance, and map rendering with large datasets.
"""

import time

import pytest

from og_scraper.models.operator import Operator
from og_scraper.models.state import State
from og_scraper.models.well import Well
from og_scraper.pipeline.classifier import DocumentClassifier
from og_scraper.pipeline.confidence import ConfidenceScorer
from og_scraper.pipeline.extractor import DataExtractor, FieldValue
from og_scraper.pipeline.normalizer import DataNormalizer


def _docker_available():
    try:
        import docker

        client = docker.from_env()
        client.ping()
        return True
    except Exception:
        return False


requires_docker = pytest.mark.skipif(
    not _docker_available(),
    reason="Docker daemon not available",
)


# ============================================================
# Pipeline Performance
# ============================================================


class TestPipelinePerformance:
    """Benchmark pipeline component performance."""

    def test_classifier_speed(self):
        """Classification should complete in under 100ms for a typical document."""
        classifier = DocumentClassifier()
        text = (
            """
        MONTHLY PRODUCTION REPORT
        Texas Railroad Commission
        API Number: 42-461-12345-00-00
        Operator: Devon Energy Corporation
        Lease Name: State #1
        Oil Production: 1,500 BBL
        Gas Production: 5,000 MCF
        Water Production: 200 BBL
        Reporting Period: January 2025
        """
            * 5
        )  # Simulate multi-page document

        start = time.perf_counter()
        for _ in range(100):
            classifier.classify(text)
        elapsed = time.perf_counter() - start

        avg_ms = (elapsed / 100) * 1000
        assert avg_ms < 100, f"Classification too slow: {avg_ms:.1f}ms avg (limit: 100ms)"

    def test_extractor_speed(self):
        """Field extraction should complete in under 200ms for a typical document."""
        extractor = DataExtractor()
        text = """
        API Number: 42-461-12345-00-00
        Operator: Devon Energy Corporation
        Well Name: State #1
        County: Harris
        Latitude: 29.7604
        Longitude: -95.3698
        Oil Production: 1,500 BBL
        Gas Production: 5,000 MCF
        Water Production: 200 BBL
        Days Produced: 30
        Reporting Period: January 2025
        Permit Number: 12345
        Spud Date: 01/15/2025
        Completion Date: 03/01/2025
        Well Depth: 8,500 ft
        """

        start = time.perf_counter()
        for _ in range(50):
            extractor.extract(text, "production_report", "TX")
        elapsed = time.perf_counter() - start

        avg_ms = (elapsed / 50) * 1000
        assert avg_ms < 200, f"Extraction too slow: {avg_ms:.1f}ms avg (limit: 200ms)"

    def test_scorer_speed(self):
        """Confidence scoring should complete in under 50ms."""
        scorer = ConfidenceScorer()
        fields = {
            "api_number": FieldValue(
                value="42461123450000",
                confidence=0.95,
                source_text="42-461-12345",
                pattern_used="api_14",
                extraction_method="regex",
                pattern_specificity=1.0,
            ),
            "operator_name": FieldValue(
                value="Devon Energy",
                confidence=0.90,
                source_text="Devon Energy",
                pattern_used="operator",
                extraction_method="regex",
                pattern_specificity=0.90,
            ),
            "production_oil_bbl": FieldValue(
                value="1500",
                confidence=0.92,
                source_text="1,500 BBL",
                pattern_used="oil",
                extraction_method="regex",
                pattern_specificity=0.90,
            ),
        }

        start = time.perf_counter()
        for _ in range(1000):
            scorer.score(
                ocr_confidence=0.95,
                classification_confidence=0.90,
                fields=fields,
                expected_fields=["api_number", "operator_name", "production_oil_bbl"],
            )
        elapsed = time.perf_counter() - start

        avg_ms = (elapsed / 1000) * 1000
        assert avg_ms < 50, f"Scoring too slow: {avg_ms:.1f}ms avg (limit: 50ms)"

    def test_normalizer_speed(self):
        """Normalization should complete in under 50ms."""
        normalizer = DataNormalizer()
        from og_scraper.pipeline.extractor import FieldExtractionResult

        fields = {
            "api_number": FieldValue(
                value="42-461-12345",
                confidence=0.95,
                source_text="42-461-12345",
                pattern_used="api",
                extraction_method="regex",
                pattern_specificity=1.0,
            ),
            "operator_name": FieldValue(
                value="  DEVON ENERGY CORP  ",
                confidence=0.90,
                source_text="DEVON ENERGY CORP",
                pattern_used="op",
                extraction_method="regex",
                pattern_specificity=0.90,
            ),
        }
        extraction = FieldExtractionResult(
            fields=fields,
            raw_text="test",
            doc_type="production_report",
            state="TX",
        )

        start = time.perf_counter()
        for _ in range(1000):
            normalizer.normalize(extraction)
        elapsed = time.perf_counter() - start

        avg_ms = (elapsed / 1000) * 1000
        assert avg_ms < 50, f"Normalization too slow: {avg_ms:.1f}ms avg (limit: 50ms)"


# ============================================================
# Database Query Performance
# ============================================================


@requires_docker
class TestDatabasePerformance:
    """Benchmark database query performance with larger datasets."""

    @pytest.mark.asyncio
    async def test_wells_query_with_100_records(self, db_session):
        """Querying 100 wells should complete quickly."""
        state = State(code="TX", name="Texas", agency_name="RRC")
        db_session.add(state)
        await db_session.flush()

        operator = Operator(name="Test Operator", normalized_name="test operator", state_code="TX")
        db_session.add(operator)
        await db_session.flush()

        # Insert 100 wells
        for i in range(100):
            well = Well(
                api_number=f"42461{i:05d}0000",
                well_name=f"Test Well {i}",
                operator_id=operator.id,
                state_code="TX",
                county="Harris",
                latitude=29.7604 + (i * 0.001),
                longitude=-95.3698 + (i * 0.001),
                well_status="active",
            )
            db_session.add(well)
        await db_session.flush()

        # Benchmark the query
        from httpx import ASGITransport, AsyncClient

        from og_scraper.api.app import create_app
        from og_scraper.api.deps import get_db

        app = create_app()

        async def override_get_db():
            yield db_session

        app.dependency_overrides[get_db] = override_get_db
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            start = time.perf_counter()
            response = await client.get("/api/v1/wells/", params={"page_size": 50, "state": "TX"})
            elapsed_ms = (time.perf_counter() - start) * 1000

            assert response.status_code == 200
            data = response.json()
            assert data["total"] == 100
            assert len(data["items"]) == 50
            assert elapsed_ms < 500, f"Wells query too slow: {elapsed_ms:.0f}ms (limit: 500ms)"

        app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_map_query_with_100_wells(self, db_session):
        """Map bounding box query with 100 wells should be fast."""
        state = State(code="TX", name="Texas", agency_name="RRC")
        db_session.add(state)
        await db_session.flush()

        # Insert 100 wells in a small area
        for i in range(100):
            well = Well(
                api_number=f"42461{i:05d}0000",
                well_name=f"Map Well {i}",
                state_code="TX",
                latitude=31.0 + (i * 0.01),
                longitude=-103.0 + (i * 0.01),
                well_status="active",
            )
            db_session.add(well)
        await db_session.flush()

        from httpx import ASGITransport, AsyncClient

        from og_scraper.api.app import create_app
        from og_scraper.api.deps import get_db

        app = create_app()

        async def override_get_db():
            yield db_session

        app.dependency_overrides[get_db] = override_get_db
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            start = time.perf_counter()
            response = await client.get(
                "/api/v1/map/wells",
                params={
                    "min_lat": 30.0,
                    "max_lat": 33.0,
                    "min_lng": -104.0,
                    "max_lng": -101.0,
                    "limit": 1000,
                },
            )
            elapsed_ms = (time.perf_counter() - start) * 1000

            assert response.status_code == 200
            wells = response.json()
            assert len(wells) > 0
            assert elapsed_ms < 500, f"Map query too slow: {elapsed_ms:.0f}ms (limit: 500ms)"

        app.dependency_overrides.clear()


# ============================================================
# API Response Time Benchmarks
# ============================================================


@requires_docker
class TestAPIResponseTimes:
    """Verify API endpoints respond within acceptable time limits."""

    @pytest.fixture
    async def seeded_client(self, db_session):
        """Client with seeded data for benchmarking."""
        # Seed states
        for code, name in [
            ("TX", "Texas"),
            ("OK", "Oklahoma"),
            ("CO", "Colorado"),
            ("PA", "Pennsylvania"),
            ("NM", "New Mexico"),
            ("ND", "North Dakota"),
            ("WY", "Wyoming"),
            ("LA", "Louisiana"),
            ("CA", "California"),
            ("AK", "Alaska"),
        ]:
            db_session.add(State(code=code, name=name, agency_name=f"{name} Agency"))
        await db_session.flush()

        # Seed some wells
        op = Operator(name="Test Corp", normalized_name="test corp", state_code="TX")
        db_session.add(op)
        await db_session.flush()

        for i in range(20):
            well = Well(
                api_number=f"42461{i:05d}0000",
                well_name=f"Benchmark Well {i}",
                operator_id=op.id,
                state_code="TX",
                county="Harris",
                latitude=29.76 + (i * 0.01),
                longitude=-95.37 + (i * 0.01),
                well_status="active",
            )
            db_session.add(well)
        await db_session.flush()

        from httpx import ASGITransport, AsyncClient

        from og_scraper.api.app import create_app
        from og_scraper.api.deps import get_db

        app = create_app()

        async def override_get_db():
            yield db_session

        app.dependency_overrides[get_db] = override_get_db
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield client

        app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_health_under_100ms(self, seeded_client):
        start = time.perf_counter()
        response = await seeded_client.get("/health")
        elapsed_ms = (time.perf_counter() - start) * 1000
        assert response.status_code == 200
        assert elapsed_ms < 100, f"Health too slow: {elapsed_ms:.0f}ms"

    @pytest.mark.asyncio
    async def test_states_under_200ms(self, seeded_client):
        start = time.perf_counter()
        response = await seeded_client.get("/api/v1/states/")
        elapsed_ms = (time.perf_counter() - start) * 1000
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 10
        assert elapsed_ms < 200, f"States too slow: {elapsed_ms:.0f}ms"

    @pytest.mark.asyncio
    async def test_wells_list_under_500ms(self, seeded_client):
        start = time.perf_counter()
        response = await seeded_client.get("/api/v1/wells/", params={"page_size": 50})
        elapsed_ms = (time.perf_counter() - start) * 1000
        assert response.status_code == 200
        assert elapsed_ms < 500, f"Wells list too slow: {elapsed_ms:.0f}ms"

    @pytest.mark.asyncio
    async def test_stats_under_500ms(self, seeded_client):
        start = time.perf_counter()
        response = await seeded_client.get("/api/v1/stats/")
        elapsed_ms = (time.perf_counter() - start) * 1000
        assert response.status_code == 200
        assert elapsed_ms < 500, f"Stats too slow: {elapsed_ms:.0f}ms"
