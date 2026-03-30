"""Huey tasks for scrape job execution and document processing.

Tasks run in the Huey worker process using SYNCHRONOUS SQLAlchemy
(not async) because Huey workers are not async-aware.
"""

import logging
from datetime import UTC, datetime

from og_scraper.config import get_settings
from og_scraper.scrapers.state_registry import STATE_REGISTRY
from og_scraper.tasks import huey

logger = logging.getLogger(__name__)

# Lazy sync engine -- created on first use to avoid import-time errors
# when psycopg2 is not installed (e.g., in test environments).
_sync_engine = None


def _get_sync_engine():
    global _sync_engine
    if _sync_engine is None:
        from sqlalchemy import create_engine

        settings = get_settings()
        _sync_engine = create_engine(settings.sync_database_url)
    return _sync_engine


def _get_session():
    from sqlalchemy.orm import Session

    return Session(_get_sync_engine())


@huey.task(retries=2, retry_delay=60)
def run_scrape_job(job_id: str, state_code: str | None, parameters: dict):
    """Execute a scrape job. Enqueued from the FastAPI POST /scrape endpoint.

    This runs in the Huey worker process (synchronous context).
    Updates the scrape_jobs row with progress as it goes.
    """
    from og_scraper.models.scrape_job import ScrapeJob

    with _get_session() as db:
        job = db.get(ScrapeJob, job_id)
        if not job:
            logger.error("Scrape job %s not found", job_id)
            return

        # Mark as running
        job.status = "running"
        job.started_at = datetime.now(UTC)
        db.commit()

        try:
            # Determine which states to scrape
            state_codes = [state_code.upper()] if state_code else list(STATE_REGISTRY.keys())

            for sc in state_codes:
                logger.info("Scrape job %s: processing state %s", job_id, sc)
                # Get spider class from state registry
                config = STATE_REGISTRY.get(sc)
                if not config or not config.spider_class:
                    logger.warning(
                        "Scrape job %s: no spider implemented for state %s, skipping",
                        job_id,
                        sc,
                    )
                    continue

                # Spider execution will be wired here once state spiders
                # are implemented in Phase 4 / Phase 6.
                # For each document yielded by the spider:
                #   1. Update documents_found
                #   2. Download -> update documents_downloaded
                #   3. Process through pipeline -> update documents_processed
                #   4. On failure -> update documents_failed, append to errors
                #   5. db.commit() after each document (so SSE picks up changes)

            job.status = "completed"
            job.finished_at = datetime.now(UTC)
            db.commit()
            logger.info("Scrape job %s completed", job_id)

        except Exception as e:
            logger.exception("Scrape job %s failed: %s", job_id, e)
            job.status = "failed"
            job.finished_at = datetime.now(UTC)
            job.errors = job.errors + [
                {"error": str(e), "timestamp": datetime.now(UTC).isoformat()}
            ]
            db.commit()
            raise  # Re-raise so Huey's retry mechanism can catch it


@huey.task(retries=3, retry_delay=30)
def process_document(document_id: str):
    """Process a single document through classify -> extract -> normalize -> store."""
    with _get_session() as db:  # noqa: F841
        # Load document, run through pipeline stages,
        # update document status and confidence scores.
        # If low confidence, call flag_for_review.
        logger.info("Processing document %s", document_id)


@huey.task()
def flag_for_review(document_id: str, reason: str, details: dict):
    """Create a review queue entry for a low-confidence document."""
    with _get_session() as db:  # noqa: F841
        logger.info("Flagging document %s for review: %s", document_id, reason)
