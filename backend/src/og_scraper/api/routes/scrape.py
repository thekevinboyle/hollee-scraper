"""Scrape job API endpoints.

POST /api/v1/scrape         -- Trigger a new scrape job
GET  /api/v1/scrape/jobs    -- List scrape jobs (paginated)
GET  /api/v1/scrape/jobs/{id}       -- Job detail with progress
GET  /api/v1/scrape/jobs/{id}/events -- SSE real-time progress stream
"""

import asyncio
import json
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette.sse import EventSourceResponse

from og_scraper.api.deps import get_db
from og_scraper.api.schemas.enums import ScrapeJobStatus
from og_scraper.api.schemas.pagination import PaginatedResponse
from og_scraper.api.schemas.scrape import ScrapeJobCreate, ScrapeJobDetail, ScrapeJobSummary
from og_scraper.api.utils.pagination import paginate
from og_scraper.models.scrape_job import ScrapeJob
from og_scraper.models.state import State
from og_scraper.tasks.scrape_task import run_scrape_job

router = APIRouter()

DbSession = Annotated[AsyncSession, Depends(get_db)]


@router.post("/", response_model=ScrapeJobDetail, status_code=202)
async def create_scrape_job(
    job_in: ScrapeJobCreate,
    db: DbSession,
):
    """Trigger a new scrape job. Returns 202 Accepted with job details immediately."""
    # Validate state_code if provided
    if job_in.state_code:
        state = await db.get(State, job_in.state_code.upper())
        if not state:
            raise HTTPException(
                status_code=400,
                detail=f"Unknown state: {job_in.state_code}",
            )

    # Prevent duplicate running jobs for the same state
    existing_query = select(ScrapeJob).where(
        ScrapeJob.state_code == (job_in.state_code.upper() if job_in.state_code else None),
        ScrapeJob.status.in_(["pending", "running"]),
    )
    existing = await db.execute(existing_query)
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=409,
            detail=f"A scrape job is already running for state: {job_in.state_code or 'all'}",
        )

    # Create job record
    job = ScrapeJob(
        state_code=job_in.state_code.upper() if job_in.state_code else None,
        job_type=job_in.job_type,
        parameters=job_in.parameters,
        status="pending",
    )
    db.add(job)
    await db.flush()
    await db.refresh(job)

    # Enqueue to Huey (fire and forget)
    run_scrape_job(str(job.id), job_in.state_code, job_in.parameters)

    return ScrapeJobDetail(
        id=job.id,
        state_code=job.state_code,
        status=job.status,
        job_type=job.job_type,
        documents_found=job.documents_found,
        documents_downloaded=job.documents_downloaded,
        documents_processed=job.documents_processed,
        documents_failed=job.documents_failed,
        started_at=job.started_at,
        finished_at=job.finished_at,
        created_at=job.created_at,
        parameters=job.parameters,
        errors=job.errors,
        total_documents=job.total_documents,
    )


@router.get("/jobs", response_model=PaginatedResponse[ScrapeJobSummary])
async def list_scrape_jobs(
    db: DbSession,
    status: ScrapeJobStatus | None = None,
    state: str | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
):
    """List scrape jobs, newest first, with optional filters."""
    query = select(ScrapeJob).order_by(ScrapeJob.created_at.desc())
    if status:
        query = query.where(ScrapeJob.status == status.value)
    if state:
        query = query.where(ScrapeJob.state_code == state.upper())
    return await paginate(db, query, page, page_size)


@router.get("/jobs/{job_id}", response_model=ScrapeJobDetail)
async def get_scrape_job(job_id: UUID, db: DbSession):
    """Get detailed scrape job status with progress counters and errors."""
    job = await db.get(ScrapeJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Scrape job not found")
    return ScrapeJobDetail(
        id=job.id,
        state_code=job.state_code,
        status=job.status,
        job_type=job.job_type,
        documents_found=job.documents_found,
        documents_downloaded=job.documents_downloaded,
        documents_processed=job.documents_processed,
        documents_failed=job.documents_failed,
        started_at=job.started_at,
        finished_at=job.finished_at,
        created_at=job.created_at,
        parameters=job.parameters,
        errors=job.errors,
        total_documents=job.total_documents,
    )


@router.get("/jobs/{job_id}/events")
async def scrape_job_events(job_id: UUID, db: DbSession):
    """SSE endpoint for real-time scrape job progress."""
    # Verify job exists before starting the stream
    job = await db.get(ScrapeJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Scrape job not found")

    async def event_generator():
        last_state = None
        while True:
            # Expire cached state so we see the latest DB values
            db.expire_all()
            job = await db.get(ScrapeJob, job_id)

            if job is None:
                yield {
                    "event": "error",
                    "data": json.dumps({"message": "Job not found"}),
                }
                break

            current_state = {
                "status": job.status if isinstance(job.status, str) else job.status.value,
                "documents_found": job.documents_found or 0,
                "documents_downloaded": job.documents_downloaded or 0,
                "documents_processed": job.documents_processed or 0,
                "documents_failed": job.documents_failed or 0,
            }

            # Only emit when state changes
            if current_state != last_state:
                yield {
                    "event": "progress",
                    "data": json.dumps(current_state),
                }
                last_state = current_state.copy()

            # Terminal states -- send complete event and close
            status_val = job.status if isinstance(job.status, str) else job.status.value
            if status_val in ("completed", "failed", "cancelled"):
                final_data = {
                    **current_state,
                    "finished_at": job.finished_at.isoformat() if job.finished_at else None,
                }
                yield {
                    "event": "complete",
                    "data": json.dumps(final_data),
                }
                break

            await asyncio.sleep(1)  # 1-second poll interval

    return EventSourceResponse(
        event_generator(),
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
