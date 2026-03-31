"""Huey tasks for scrape job execution and document processing.

Tasks run in the Huey worker process using SYNCHRONOUS SQLAlchemy
(not async) because Huey workers are not async-aware.
"""

import logging
from datetime import UTC, datetime

from og_scraper.config import get_settings
from og_scraper.scrapers.state_registry import STATE_REGISTRY
from og_scraper.worker import huey_app as huey

logger = logging.getLogger(__name__)

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


def _persist_items(db, wells, docs, job, state_code):
    """Save scraped WellItems and DocumentItems to the database."""
    from og_scraper.models.document import Document
    from og_scraper.models.operator import Operator
    from og_scraper.models.well import Well

    operator_cache: dict[str, Operator] = {}

    def get_or_create_operator(name: str) -> Operator:
        key = name.lower().strip()
        if key in operator_cache:
            return operator_cache[key]
        existing = db.query(Operator).filter(
            Operator.normalized_name == key,
        ).first()
        if existing:
            operator_cache[key] = existing
            return existing
        op = Operator(
            name=name.strip(),
            normalized_name=key,
        )
        db.add(op)
        db.flush()
        operator_cache[key] = op
        return op

    well_cache: dict[str, Well] = {}

    # Save wells
    for wi in wells:
        if not wi.api_number:
            continue
        if wi.api_number in well_cache:
            continue

        existing = db.query(Well).filter(Well.api_number == wi.api_number).first()
        if existing:
            well_cache[wi.api_number] = existing
            continue

        operator = None
        if wi.operator_name:
            operator = get_or_create_operator(wi.operator_name)

        # Normalize well_status to match DB enum values
        raw_status = (wi.well_status or "unknown").lower().strip()
        valid_statuses = {"active", "inactive", "plugged", "permitted", "drilling", "completed", "shut_in", "temporarily_abandoned", "unknown"}
        well_status = raw_status if raw_status in valid_statuses else "unknown"

        well = Well(
            api_number=wi.api_number,
            well_name=wi.well_name,
            well_number=wi.well_number,
            operator_id=operator.id if operator else None,
            state_code=wi.state_code,
            county=wi.county,
            basin=wi.basin,
            field_name=wi.field_name,
            lease_name=wi.lease_name,
            latitude=wi.latitude,
            longitude=wi.longitude,
            well_status=well_status,
            well_type=wi.well_type,
            spud_date=wi.spud_date,
            completion_date=wi.completion_date,
            total_depth=wi.total_depth,
            metadata_=wi.metadata or {},
            alternate_ids=wi.alternate_ids or {},
        )
        db.add(well)
        try:
            db.flush()
            well_cache[wi.api_number] = well
            job.documents_found = (job.documents_found or 0) + 1
        except Exception as e:
            db.rollback()
            logger.warning("Failed to insert well %s: %s", wi.api_number, e)

    db.commit()

    # Save documents
    for di in docs:
        # Find linked well
        well = None
        if di.api_number and di.api_number in well_cache:
            well = well_cache[di.api_number]

        operator = None
        if di.operator_name:
            operator = get_or_create_operator(di.operator_name)

        doc = Document(
            well_id=well.id if well else None,
            state_code=di.state_code,
            scrape_job_id=job.id,
            doc_type=di.doc_type or "unknown",
            status="stored",
            source_url=di.source_url,
            file_path=di.file_path,
            file_hash=di.file_hash,
            file_format=di.file_format,
            file_size_bytes=di.file_size_bytes,
        )
        db.add(doc)
        try:
            db.flush()
            job.documents_processed = (job.documents_processed or 0) + 1
        except Exception as e:
            db.rollback()
            logger.warning("Failed to insert document: %s", e)
            job.documents_failed = (job.documents_failed or 0) + 1

    db.commit()


@huey.task(retries=2, retry_delay=60)
def run_scrape_job(job_id: str, state_code: str | None, parameters: dict):
    """Execute a scrape job: run spider, persist items, update progress."""
    from og_scraper.models.scrape_job import ScrapeJob
    from og_scraper.tasks.scrape_runner import run_spider_sync

    with _get_session() as db:
        job = db.get(ScrapeJob, job_id)
        if not job:
            logger.error("Scrape job %s not found", job_id)
            return

        job.status = "running"
        job.started_at = datetime.now(UTC)
        db.commit()

        try:
            state_codes = [state_code.upper()] if state_code else list(STATE_REGISTRY.keys())

            for sc in state_codes:
                config = STATE_REGISTRY.get(sc)
                if not config or not config.spider_class:
                    logger.warning("No spider for state %s, skipping", sc)
                    continue

                logger.info("Scrape job %s: running spider for %s", job_id, sc)

                limit = parameters.get("limit", 50)
                wells, docs = run_spider_sync(config.spider_class, limit=limit)

                logger.info(
                    "Scrape job %s: %s yielded %d wells, %d docs",
                    job_id, sc, len(wells), len(docs),
                )

                _persist_items(db, wells, docs, job, sc)
                db.commit()

            job.status = "completed"
            job.finished_at = datetime.now(UTC)
            db.commit()
            logger.info("Scrape job %s completed", job_id)

        except Exception as e:
            logger.exception("Scrape job %s failed: %s", job_id, e)
            job.status = "failed"
            job.finished_at = datetime.now(UTC)
            job.errors = (job.errors or []) + [
                {"error": str(e), "timestamp": datetime.now(UTC).isoformat()}
            ]
            db.commit()
            raise


@huey.task(retries=3, retry_delay=30)
def process_document(document_id: str):
    """Process a single document through the pipeline."""
    logger.info("Processing document %s", document_id)


@huey.task()
def flag_for_review(document_id: str, reason: str, details: dict):
    """Create a review queue entry for a low-confidence document."""
    logger.info("Flagging document %s for review: %s", document_id, reason)
