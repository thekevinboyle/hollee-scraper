"""States API endpoints.

GET /api/v1/states -- List all states with well/document counts
"""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from og_scraper.api.deps import get_db
from og_scraper.api.schemas.state import StateSummary
from og_scraper.models.document import Document
from og_scraper.models.state import State
from og_scraper.models.well import Well

router = APIRouter()

DbSession = Annotated[AsyncSession, Depends(get_db)]


@router.get("/", response_model=list[StateSummary])
async def list_states(
    db: DbSession,
):
    """List all states with well and document counts."""
    # Subquery for well counts per state
    well_count_subq = (
        select(
            Well.state_code,
            func.count(Well.id).label("well_count"),
        )
        .group_by(Well.state_code)
        .subquery()
    )

    # Subquery for document counts per state
    doc_count_subq = (
        select(
            Document.state_code,
            func.count(Document.id).label("document_count"),
        )
        .group_by(Document.state_code)
        .subquery()
    )

    query = (
        select(
            State.code,
            State.name,
            State.api_state_code,
            State.tier,
            State.last_scraped_at,
            func.coalesce(well_count_subq.c.well_count, 0).label("well_count"),
            func.coalesce(doc_count_subq.c.document_count, 0).label("document_count"),
        )
        .outerjoin(well_count_subq, State.code == well_count_subq.c.state_code)
        .outerjoin(doc_count_subq, State.code == doc_count_subq.c.state_code)
        .order_by(State.name)
    )

    result = await db.execute(query)
    rows = result.all()

    return [
        StateSummary(
            code=row.code,
            name=row.name,
            api_state_code=row.api_state_code,
            tier=row.tier,
            last_scraped_at=row.last_scraped_at,
            well_count=row.well_count,
            document_count=row.document_count,
        )
        for row in rows
    ]
