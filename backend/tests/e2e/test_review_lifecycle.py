"""Task 7.1: Review queue lifecycle tests.

Tests the complete review queue workflow: listing pending items, approving,
correcting with field edits, rejecting, and verifying error cases.
"""

import pytest

from tests.e2e.conftest import requires_docker


@requires_docker
class TestReviewQueueLifecycle:
    """Full lifecycle tests for the review queue."""

    @pytest.mark.asyncio
    async def test_list_pending_review_items(self, client_with_reviews, seeded_review_items):
        """Pending review items should be listed."""
        response = await client_with_reviews.get("/api/v1/review/")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 2
        for item in data["items"]:
            assert item["status"] == "pending"

    @pytest.mark.asyncio
    async def test_get_review_item_detail(self, client_with_reviews, seeded_review_items):
        """Getting a review item by ID returns full detail."""
        reviews = seeded_review_items["reviews"]
        review_id = list(reviews.values())[0].id
        response = await client_with_reviews.get(f"/api/v1/review/{review_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == str(review_id)
        assert data["status"] == "pending"
        assert data["document_confidence"] is not None

    @pytest.mark.asyncio
    async def test_approve_review_item(self, client_with_reviews, seeded_review_items):
        """Approving a review item should change its status."""
        reviews = seeded_review_items["reviews"]
        review_id = list(reviews.values())[0].id

        response = await client_with_reviews.patch(
            f"/api/v1/review/{review_id}",
            json={"status": "approved", "reviewed_by": "test_reviewer"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "approved"
        assert data["reviewed_by"] == "test_reviewer"

    @pytest.mark.asyncio
    async def test_approved_item_not_in_pending_queue(self, client_with_reviews, seeded_review_items):
        """After approval, item should no longer appear in pending queue."""
        reviews = seeded_review_items["reviews"]
        review_id = list(reviews.values())[0].id

        # Approve it
        await client_with_reviews.patch(
            f"/api/v1/review/{review_id}",
            json={"status": "approved", "reviewed_by": "tester"},
        )

        # Check pending queue
        response = await client_with_reviews.get("/api/v1/review/", params={"status": "pending"})
        data = response.json()
        item_ids = [item["id"] for item in data["items"]]
        assert str(review_id) not in item_ids

    @pytest.mark.asyncio
    async def test_correct_review_item_with_field_edits(self, client_with_reviews, seeded_review_items):
        """Correcting a review item should update extracted data."""
        reviews = seeded_review_items["reviews"]
        review_id = list(reviews.values())[0].id

        response = await client_with_reviews.patch(
            f"/api/v1/review/{review_id}",
            json={
                "status": "corrected",
                "reviewed_by": "data_analyst",
                "corrections": {"operator_name": "CORRECTED OIL CO"},
                "notes": "Fixed operator name typo",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "corrected"

    @pytest.mark.asyncio
    async def test_reject_review_item(self, client_with_reviews, seeded_review_items):
        """Rejecting a review item should set status to rejected."""
        reviews = seeded_review_items["reviews"]
        review_id = list(reviews.values())[1].id

        response = await client_with_reviews.patch(
            f"/api/v1/review/{review_id}",
            json={"status": "rejected", "reviewed_by": "reviewer", "notes": "Unreadable document"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "rejected"

    @pytest.mark.asyncio
    async def test_double_action_returns_400(self, client_with_reviews, seeded_review_items):
        """Acting on an already-resolved item should return 400."""
        reviews = seeded_review_items["reviews"]
        review_id = list(reviews.values())[0].id

        # First action: approve
        await client_with_reviews.patch(
            f"/api/v1/review/{review_id}",
            json={"status": "approved", "reviewed_by": "tester"},
        )

        # Second action: try to reject
        response = await client_with_reviews.patch(
            f"/api/v1/review/{review_id}",
            json={"status": "rejected", "reviewed_by": "tester"},
        )
        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_correction_without_corrections_field(self, client_with_reviews, seeded_review_items):
        """Correcting without providing corrections should return 400."""
        reviews = seeded_review_items["reviews"]
        review_id = list(reviews.values())[0].id

        response = await client_with_reviews.patch(
            f"/api/v1/review/{review_id}",
            json={"status": "corrected", "reviewed_by": "tester"},
        )
        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_review_not_found(self, client_with_reviews):
        """Non-existent review ID returns 404."""
        import uuid

        fake_id = str(uuid.uuid4())
        response = await client_with_reviews.get(f"/api/v1/review/{fake_id}")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_review_stats(self, client_with_reviews):
        """Review stats endpoint should return counts."""
        response = await client_with_reviews.get("/api/v1/review/stats")
        assert response.status_code == 200
        data = response.json()
        assert "pending_count" in data
        assert data["pending_count"] >= 0
