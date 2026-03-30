"""Statistics API endpoints.

GET /api/v1/stats -- Dashboard aggregate statistics
GET /api/v1/stats/state/{state_code} -- Per-state statistics
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from og_scraper.api.deps import get_db
from og_scraper.api.schemas.stats import DashboardStats, StateStats
from og_scraper.models.document import Document
from og_scraper.models.extracted_data import ExtractedData
from og_scraper.models.review_queue import ReviewQueue
from og_scraper.models.scrape_job import ScrapeJob
from og_scraper.models.state import State
from og_scraper.models.well import Well

router = APIRouter()

DbSession = Annotated[AsyncSession, Depends(get_db)]


@router.get("/", response_model=DashboardStats)
async def get_dashboard_stats(db: DbSession):
    """Aggregate dashboard statistics.

    Returns totals, breakdowns by state/type/status, review queue count,
    average confidence, and recent scrape jobs.
    """
    # Total counts
    total_wells = (await db.execute(select(func.count(Well.id)))).scalar_one()
    total_documents = (await db.execute(select(func.count(Document.id)))).scalar_one()
    total_extracted = (await db.execute(select(func.count(ExtractedData.id)))).scalar_one()

    # Documents by state
    docs_by_state_result = await db.execute(
        select(Document.state_code, func.count(Document.id)).group_by(Document.state_code)
    )
    documents_by_state = {row[0]: row[1] for row in docs_by_state_result.all() if row[0]}

    # Documents by type
    docs_by_type_result = await db.execute(
        select(Document.doc_type, func.count(Document.id)).group_by(Document.doc_type)
    )
    documents_by_type = {str(row[0]): row[1] for row in docs_by_type_result.all() if row[0]}

    # Wells by status
    wells_by_status_result = await db.execute(
        select(Well.well_status, func.count(Well.id)).group_by(Well.well_status)
    )
    wells_by_status = {str(row[0]): row[1] for row in wells_by_status_result.all() if row[0]}

    # Wells by state
    wells_by_state_result = await db.execute(
        select(Well.state_code, func.count(Well.id)).group_by(Well.state_code)
    )
    wells_by_state = {row[0]: row[1] for row in wells_by_state_result.all() if row[0]}

    # Review queue pending count
    review_pending = (
        await db.execute(select(func.count(ReviewQueue.id)).where(ReviewQueue.status == "pending"))
    ).scalar_one()

    # Average document confidence
    avg_conf = (
        await db.execute(
            select(func.avg(Document.confidence_score)).where(Document.confidence_score.is_not(None))
        )
    ).scalar_one()

    # Recent scrape jobs (last 5)
    recent_jobs_result = await db.execute(
        select(ScrapeJob).order_by(ScrapeJob.created_at.desc()).limit(5)
    )
    recent_jobs = [
        {
            "id": str(j.id),
            "state_code": j.state_code,
            "status": str(j.status),
            "job_type": j.job_type,
            "documents_found": j.documents_found or 0,
            "documents_processed": j.documents_processed or 0,
            "created_at": j.created_at.isoformat() if j.created_at else None,
        }
        for j in recent_jobs_result.scalars().all()
    ]

    return DashboardStats(
        total_wells=total_wells,
        total_documents=total_documents,
        total_extracted=total_extracted,
        documents_by_state=documents_by_state,
        documents_by_type=documents_by_type,
        wells_by_status=wells_by_status,
        wells_by_state=wells_by_state,
        review_queue_pending=review_pending,
        avg_confidence=round(float(avg_conf), 4) if avg_conf else None,
        recent_scrape_jobs=recent_jobs,
    )


@router.get("/state/{state_code}", response_model=StateStats)
async def get_state_stats(state_code: str, db: DbSession):
    """Per-state statistics.

    Returns totals, breakdowns, and metadata for a specific state.
    """
    state_code = state_code.upper()

    # Check state exists
    state = await db.get(State, state_code)
    if not state:
        raise HTTPException(status_code=404, detail=f"State not found: {state_code}")

    # Total wells in state
    total_wells = (
        await db.execute(select(func.count(Well.id)).where(Well.state_code == state_code))
    ).scalar_one()

    # Total documents in state
    total_documents = (
        await db.execute(select(func.count(Document.id)).where(Document.state_code == state_code))
    ).scalar_one()

    # Documents by type in state
    docs_by_type_result = await db.execute(
        select(Document.doc_type, func.count(Document.id))
        .where(Document.state_code == state_code)
        .group_by(Document.doc_type)
    )
    documents_by_type = {str(row[0]): row[1] for row in docs_by_type_result.all() if row[0]}

    # Wells by status in state
    wells_by_status_result = await db.execute(
        select(Well.well_status, func.count(Well.id))
        .where(Well.state_code == state_code)
        .group_by(Well.well_status)
    )
    wells_by_status = {str(row[0]): row[1] for row in wells_by_status_result.all() if row[0]}

    # Average confidence for documents in state
    avg_conf = (
        await db.execute(
            select(func.avg(Document.confidence_score))
            .where(Document.state_code == state_code)
            .where(Document.confidence_score.is_not(None))
        )
    ).scalar_one()

    # Review queue pending for documents in this state
    review_pending = (
        await db.execute(
            select(func.count(ReviewQueue.id))
            .join(Document, ReviewQueue.document_id == Document.id)
            .where(Document.state_code == state_code)
            .where(ReviewQueue.status == "pending")
        )
    ).scalar_one()

    return StateStats(
        state_code=state_code,
        state_name=state.name,
        total_wells=total_wells,
        total_documents=total_documents,
        documents_by_type=documents_by_type,
        wells_by_status=wells_by_status,
        avg_confidence=round(float(avg_conf), 4) if avg_conf else None,
        last_scraped_at=state.last_scraped_at.isoformat() if state.last_scraped_at else None,
        review_queue_pending=review_pending,
    )
