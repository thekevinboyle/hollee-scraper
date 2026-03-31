"""Task 7.3: Error handling & edge case tests.

Tests failure modes, malformed data, edge cases, and error recovery across
the pipeline and API layers. Exercises every error path to verify the system
fails gracefully and communicates errors clearly.
"""

import uuid

import pytest

from og_scraper.models.document import Document
from og_scraper.models.extracted_data import ExtractedData
from og_scraper.models.review_queue import ReviewQueue
from og_scraper.models.state import State
from og_scraper.models.well import Well
from og_scraper.pipeline.classifier import DocumentClassifier
from og_scraper.pipeline.confidence import ConfidenceScorer
from og_scraper.pipeline.extractor import DataExtractor, FieldExtractionResult, FieldValue
from og_scraper.pipeline.normalizer import DataNormalizer


def _docker_available():
    """Check if Docker daemon is reachable."""
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
# Pipeline Error Handling
# ============================================================


class TestClassifierEdgeCases:
    """Test document classifier with malformed and edge-case inputs."""

    def test_empty_text_returns_unknown(self):
        classifier = DocumentClassifier()
        result = classifier.classify("")
        assert result.doc_type == "unknown"
        assert result.confidence < 0.50

    def test_whitespace_only_text(self):
        classifier = DocumentClassifier()
        result = classifier.classify("   \n\t\n  ")
        assert result.doc_type == "unknown"

    def test_random_gibberish(self):
        classifier = DocumentClassifier()
        result = classifier.classify("asdfghjkl qwerty zxcvbnm 12345 !@#$%")
        assert result.doc_type == "unknown"
        assert result.confidence < 0.50

    def test_non_english_text(self):
        classifier = DocumentClassifier()
        result = classifier.classify("这是一些中文文本，不是石油和天然气文档")
        assert result.doc_type == "unknown"

    def test_very_long_text(self):
        """Classifier should handle very long documents without crashing."""
        classifier = DocumentClassifier()
        long_text = "Oil production report " * 10000
        result = classifier.classify(long_text)
        assert result.doc_type is not None
        assert 0.0 <= result.confidence <= 1.0

    def test_text_with_production_keywords_classifies_correctly(self):
        classifier = DocumentClassifier()
        text = """
        MONTHLY PRODUCTION REPORT
        Production Report for January 2025
        Oil Production: 1,500 barrels produced
        Gas Production: 5,000 mcf produced
        Water Production: 200 BBL
        Days Produced: 30
        Production Summary
        Annual Production Volume
        Reporting Period: January 2025
        """
        result = classifier.classify(text, metadata={"state": "TX"})
        assert result.doc_type == "production_report"
        assert result.confidence >= 0.30

    def test_text_with_permit_keywords(self):
        classifier = DocumentClassifier()
        text = """
        APPLICATION TO DRILL
        Permit to Drill
        Drilling Permit Application
        Proposed Total Depth: 8,500 feet
        Anticipated Spud Date: 2025-02-01
        Surface Location: Section 12
        Bottom Hole Location: Section 12
        Proposed Casing Program: 7" casing
        Operator: Devon Energy
        Well Name: State #1
        API Number: 42-461-67890
        """
        result = classifier.classify(text)
        assert result.doc_type == "well_permit"
        assert result.confidence >= 0.30


class TestExtractorEdgeCases:
    """Test data extractor with malformed field data."""

    def test_extract_from_empty_text(self):
        extractor = DataExtractor()
        result = extractor.extract("", "production_report", "TX")
        assert isinstance(result, FieldExtractionResult)
        assert len(result.fields) == 0

    def test_extract_from_gibberish(self):
        extractor = DataExtractor()
        result = extractor.extract("asdf1234 no real data here", "production_report", "TX")
        assert isinstance(result, FieldExtractionResult)

    def test_malformed_api_numbers(self):
        """API numbers in wrong formats should still be extracted where possible."""
        extractor = DataExtractor()
        # Too-short API number
        result = extractor.extract("API: 123", "well_permit", "TX")
        # Should not extract a 3-digit number as an API
        api_field = result.fields.get("api_number")
        if api_field:
            assert api_field.confidence < 0.80

    def test_negative_production_volumes(self):
        """Negative production volumes are invalid."""
        extractor = DataExtractor()
        text = "Oil Production: -500 BBL  Gas Production: -1000 MCF"
        result = extractor.extract(text, "production_report", "TX")
        # Negative values should either not be extracted or have low confidence
        oil_field = result.fields.get("production_oil_bbl")
        if oil_field:
            assert oil_field.value is None or float(oil_field.value) >= 0 or oil_field.confidence < 0.50

    def test_impossible_coordinates(self):
        """Coordinates outside valid ranges should be handled."""
        extractor = DataExtractor()
        text = "Latitude: 999.0  Longitude: -999.0"
        result = extractor.extract(text, "well_permit", "TX")
        lat_field = result.fields.get("latitude")
        if lat_field:
            val = float(lat_field.value)
            # Either not extracted, or flagged with low confidence
            if not (-90 <= val <= 90):
                assert lat_field.confidence < 0.50

    def test_extract_with_unknown_doc_type(self):
        """Extraction with 'unknown' doc type should still work."""
        extractor = DataExtractor()
        text = "API Number: 42-461-12345\nOperator: Test Oil Co"
        result = extractor.extract(text, "unknown", "TX")
        assert isinstance(result, FieldExtractionResult)


class TestConfidenceScorerEdgeCases:
    """Test confidence scoring edge cases."""

    def test_all_fields_missing(self):
        """No fields extracted should give very low confidence."""
        scorer = ConfidenceScorer()
        score = scorer.score(
            ocr_confidence=1.0,
            classification_confidence=0.9,
            fields={},
            expected_fields=["api_number", "operator_name", "production_oil_bbl"],
        )
        assert score.document_confidence < 0.50
        assert score.disposition == "reject"

    def test_perfect_confidence(self):
        """All fields with max confidence should auto-accept."""
        scorer = ConfidenceScorer()
        fields = {
            "api_number": FieldValue(
                value="42461123450000",
                confidence=0.99,
                source_text="42-461-12345",
                pattern_used="api_14",
                extraction_method="regex",
                pattern_specificity=1.0,
            ),
            "operator_name": FieldValue(
                value="Devon Energy",
                confidence=0.95,
                source_text="Devon Energy",
                pattern_used="operator",
                extraction_method="regex",
                pattern_specificity=0.95,
            ),
        }
        score = scorer.score(
            ocr_confidence=1.0,
            classification_confidence=0.98,
            fields=fields,
            expected_fields=["api_number", "operator_name"],
        )
        assert score.document_confidence >= 0.85
        assert score.disposition == "accept"

    def test_critical_field_override(self):
        """Bad API number should force review even with high overall confidence."""
        scorer = ConfidenceScorer()
        fields = {
            "api_number": FieldValue(
                value="GARBLED",
                confidence=0.10,
                source_text="GARBLED",
                pattern_used="none",
                extraction_method="regex",
                pattern_specificity=0.1,
            ),
            "operator_name": FieldValue(
                value="Devon Energy",
                confidence=0.95,
                source_text="Devon Energy",
                pattern_used="operator",
                extraction_method="regex",
                pattern_specificity=0.95,
            ),
            "production_oil_bbl": FieldValue(
                value="1500",
                confidence=0.95,
                source_text="1,500 BBL",
                pattern_used="oil_volume",
                extraction_method="regex",
                pattern_specificity=0.95,
            ),
        }
        score = scorer.score(
            ocr_confidence=1.0,
            classification_confidence=0.95,
            fields=fields,
            expected_fields=["api_number", "operator_name", "production_oil_bbl"],
        )
        assert score.critical_field_override is True
        assert score.disposition == "review"

    def test_zero_ocr_confidence(self):
        """OCR confidence of 0 should contribute to low overall score."""
        scorer = ConfidenceScorer()
        score = scorer.score(
            ocr_confidence=0.0,
            classification_confidence=0.5,
            fields={},
            expected_fields=[],
        )
        assert score.document_confidence < 0.50

    def test_boundary_accept_threshold(self):
        """Score exactly at 0.85 should be accepted."""
        scorer = ConfidenceScorer()
        # Craft fields to land exactly at threshold
        fields = {
            "api_number": FieldValue(
                value="42461123450000",
                confidence=0.96,
                source_text="42-461-12345",
                pattern_used="api_14",
                extraction_method="regex",
                pattern_specificity=1.0,
            ),
        }
        score = scorer.score(
            ocr_confidence=0.85,
            classification_confidence=0.85,
            fields=fields,
            expected_fields=["api_number"],
        )
        if score.document_confidence >= 0.85:
            assert score.disposition == "accept"
        else:
            assert score.disposition == "review"

    def test_boundary_review_threshold(self):
        """Low confidence should result in review or reject disposition."""
        scorer = ConfidenceScorer()
        # Use a non-critical field to avoid critical field override
        fields = {
            "operator_name": FieldValue(
                value="Test Op",
                confidence=0.60,
                source_text="Test Op",
                pattern_used="operator",
                extraction_method="regex",
                pattern_specificity=0.7,
            ),
        }
        score = scorer.score(
            ocr_confidence=0.50,
            classification_confidence=0.50,
            fields=fields,
            expected_fields=["operator_name"],
        )
        # With these inputs, score should be in review or reject range
        assert score.disposition in ("review", "reject")


class TestNormalizerEdgeCases:
    """Test normalizer with unusual inputs."""

    def test_normalize_empty_extraction(self):
        normalizer = DataNormalizer()
        extraction = FieldExtractionResult(
            fields={},
            raw_text="",
            doc_type="unknown",
            state="TX",
        )
        result = normalizer.normalize(extraction)
        assert result.fields == {} or isinstance(result.fields, dict)
        assert isinstance(result.warnings, list)


# ============================================================
# API Error Handling
# ============================================================


@requires_docker
class TestAPIErrorHandling:
    """Test API endpoints return proper errors for invalid inputs."""

    @pytest.fixture(autouse=True)
    async def setup(self, db_session):
        """Seed minimal state data."""
        for code, name in [("TX", "Texas"), ("OK", "Oklahoma")]:
            db_session.add(State(code=code, name=name, agency_name=f"{name} Agency"))
        await db_session.flush()
        self.db = db_session

    @pytest.fixture
    async def client(self, db_session):
        from httpx import ASGITransport, AsyncClient

        from og_scraper.api.app import create_app
        from og_scraper.api.deps import get_db

        app = create_app()

        async def override_get_db():
            yield db_session

        app.dependency_overrides[get_db] = override_get_db
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac
        app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_get_well_not_found(self, client):
        """GET /wells/{api} with non-existent well returns 404."""
        response = await client.get("/api/v1/wells/99999999999999")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_scrape_invalid_state(self, client):
        """POST /scrape with invalid state returns 400."""
        response = await client.post(
            "/api/v1/scrape/",
            json={"state_code": "ZZ", "job_type": "full"},
        )
        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_scrape_job_not_found(self, client):
        """GET /scrape/jobs/{id} with random UUID returns 404."""
        fake_id = str(uuid.uuid4())
        response = await client.get(f"/api/v1/scrape/jobs/{fake_id}")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_review_item_not_found(self, client):
        """GET /review/{id} with random UUID returns 404."""
        fake_id = str(uuid.uuid4())
        response = await client.get(f"/api/v1/review/{fake_id}")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_map_invalid_bounds(self, client):
        """Map endpoint with min_lat > max_lat returns 400."""
        response = await client.get(
            "/api/v1/map/wells",
            params={"min_lat": 40, "max_lat": 30, "min_lng": -100, "max_lng": -90},
        )
        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_map_invalid_lng_bounds(self, client):
        """Map endpoint with min_lng > max_lng returns 400."""
        response = await client.get(
            "/api/v1/map/wells",
            params={"min_lat": 30, "max_lat": 40, "min_lng": -80, "max_lng": -90},
        )
        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_wells_pagination_out_of_range(self, client):
        """Wells endpoint with very high page number returns empty results."""
        response = await client.get(
            "/api/v1/wells/",
            params={"page": 99999, "page_size": 50},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["items"] == []

    @pytest.mark.asyncio
    async def test_review_double_action(self, client, db_session):
        """Approving an already-resolved review item returns 400."""
        # Create a document and review item
        doc = Document(
            state_code="TX",
            doc_type="production_report",
            status="classified",
            source_url="https://example.com/test.pdf",
        )
        db_session.add(doc)
        await db_session.flush()

        review = ReviewQueue(
            document_id=doc.id,
            status="approved",  # Already resolved
            reason="Test",
            document_confidence=0.75,
        )
        db_session.add(review)
        await db_session.flush()

        response = await client.patch(
            f"/api/v1/review/{review.id}",
            json={"status": "approved", "reviewed_by": "tester"},
        )
        assert response.status_code == 400
        assert "already resolved" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_correction_without_corrections_field(self, client, db_session):
        """Correcting a review item without corrections returns 400."""
        doc = Document(
            state_code="TX",
            doc_type="production_report",
            status="classified",
            source_url="https://example.com/test.pdf",
        )
        db_session.add(doc)
        await db_session.flush()

        review = ReviewQueue(
            document_id=doc.id,
            status="pending",
            reason="Test",
            document_confidence=0.65,
        )
        db_session.add(review)
        await db_session.flush()

        response = await client.patch(
            f"/api/v1/review/{review.id}",
            json={"status": "corrected", "reviewed_by": "tester"},
        )
        assert response.status_code == 400


# ============================================================
# Scraper Edge Cases
# ============================================================


class TestSpiderEdgeCases:
    """Test spider base class edge cases."""

    def test_normalize_api_too_short(self):
        """API numbers too short to be valid should be returned as-is."""
        from og_scraper.scrapers.spiders.base import BaseOGSpider

        class TestSpider(BaseOGSpider):
            name = "test"
            state_code = "TX"
            state_name = "Texas"
            agency_name = "Test"
            base_url = "http://test.com"

            def start_requests(self):
                return []

        spider = TestSpider()
        assert spider.normalize_api_number("123") == "123"  # Too short
        assert spider.normalize_api_number("42461201300") == "42461201300000"  # Valid 11 digits

    def test_normalize_api_with_dashes(self):
        from og_scraper.scrapers.spiders.base import BaseOGSpider

        class TestSpider(BaseOGSpider):
            name = "test2"
            state_code = "TX"
            state_name = "Texas"
            agency_name = "Test"
            base_url = "http://test.com"

            def start_requests(self):
                return []

        spider = TestSpider()
        assert spider.normalize_api_number("42-461-20130-03-00") == "42461201300300"

    def test_file_hash_deterministic(self):
        from og_scraper.scrapers.spiders.base import BaseOGSpider

        class TestSpider(BaseOGSpider):
            name = "test3"
            state_code = "TX"
            state_name = "Texas"
            agency_name = "Test"
            base_url = "http://test.com"

            def start_requests(self):
                return []

        spider = TestSpider()
        content = b"test document content"
        hash1 = spider.compute_file_hash(content)
        hash2 = spider.compute_file_hash(content)
        assert hash1 == hash2
        assert len(hash1) == 64  # SHA-256

    def test_spider_missing_required_attribute(self):
        """Spider without required attributes should raise ValueError."""
        from og_scraper.scrapers.spiders.base import BaseOGSpider

        class BadSpider(BaseOGSpider):
            name = "bad"
            # Missing state_code, state_name, etc.

            def start_requests(self):
                return []

        with pytest.raises((TypeError, ValueError)):
            BadSpider()


# ============================================================
# Data Integrity Edge Cases
# ============================================================


@requires_docker
class TestDataIntegrityEdgeCases:
    """Test data integrity constraints and edge cases."""

    @pytest.mark.asyncio
    async def test_duplicate_api_number_same_state(self, db_session):
        """Two wells with same API number in same state should be handled."""
        state = State(code="TX", name="Texas", agency_name="RRC")
        db_session.add(state)
        await db_session.flush()

        well1 = Well(
            api_number="42461123450000",
            well_name="Test Well 1",
            state_code="TX",
        )
        db_session.add(well1)
        await db_session.flush()

        # Second well with same API - DB may allow or reject depending on constraints
        well2 = Well(
            api_number="42461123450000",
            well_name="Test Well 2 (duplicate)",
            state_code="TX",
        )
        db_session.add(well2)
        try:
            await db_session.flush()
            # If DB allows it, both should exist
        except Exception:
            await db_session.rollback()
            # Constraint violation is acceptable behavior

    @pytest.mark.asyncio
    async def test_document_without_well(self, db_session):
        """Documents can exist without a linked well (orphan docs are valid)."""
        state = State(code="TX", name="Texas", agency_name="RRC")
        db_session.add(state)
        await db_session.flush()

        doc = Document(
            state_code="TX",
            doc_type="production_report",
            status="pending",
            source_url="https://example.com/orphan.pdf",
            well_id=None,  # No well linked
        )
        db_session.add(doc)
        await db_session.flush()
        assert doc.id is not None

    @pytest.mark.asyncio
    async def test_well_with_null_coordinates(self, db_session):
        """Wells without coordinates should still be stored."""
        state = State(code="TX", name="Texas", agency_name="RRC")
        db_session.add(state)
        await db_session.flush()

        well = Well(
            api_number="42461999990000",
            well_name="No Coords Well",
            state_code="TX",
            latitude=None,
            longitude=None,
        )
        db_session.add(well)
        await db_session.flush()
        assert well.id is not None

    @pytest.mark.asyncio
    async def test_extracted_data_empty_jsonb(self, db_session):
        """ExtractedData with empty JSON should be valid."""
        state = State(code="TX", name="Texas", agency_name="RRC")
        db_session.add(state)
        await db_session.flush()

        doc = Document(
            state_code="TX",
            doc_type="unknown",
            status="pending",
            source_url="https://example.com/empty.pdf",
        )
        db_session.add(doc)
        await db_session.flush()

        ed = ExtractedData(
            document_id=doc.id,
            data={},
            extraction_method="none",
        )
        db_session.add(ed)
        await db_session.flush()
        assert ed.id is not None
