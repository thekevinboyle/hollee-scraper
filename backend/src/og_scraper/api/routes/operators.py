"""Operators API endpoints.

GET /api/v1/operators -- List/search operators with well counts
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import asc, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from og_scraper.api.deps import get_db
from og_scraper.api.schemas.enums import SortDirection
from og_scraper.api.schemas.operator import OperatorSummary
from og_scraper.api.schemas.pagination import PaginatedResponse
from og_scraper.api.utils.pagination import paginate
from og_scraper.models.operator import Operator
from og_scraper.models.well import Well

router = APIRouter()

DbSession = Annotated[AsyncSession, Depends(get_db)]


@router.get("/", response_model=PaginatedResponse[OperatorSummary])
async def list_operators(
    db: DbSession,
    q: str | None = None,
    state: str | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    sort_dir: SortDirection = SortDirection.ASC,
):
    """List/search operators with well counts and state codes.

    When q is provided, uses trigram similarity matching for fuzzy search.
    """
    query = (
        select(
            Operator.id,
            Operator.name,
            Operator.normalized_name,
            func.count(Well.id).label("well_count"),
            func.array_agg(func.distinct(Well.state_code)).label("state_codes"),
        )
        .outerjoin(Well, Well.operator_id == Operator.id)
        .group_by(Operator.id, Operator.name, Operator.normalized_name)
    )

    # Trigram similarity search
    if q:
        similarity = func.similarity(Operator.name, q)
        query = query.where(similarity > 0.3)
        query = query.order_by(similarity.desc())
    else:
        order_func = desc if sort_dir == SortDirection.DESC else asc
        query = query.order_by(order_func(Operator.name))

    # Filter by state
    if state:
        query = query.having(func.bool_or(Well.state_code == state.upper()))

    result = await paginate(db, query, page, page_size)

    # Convert Row objects to OperatorSummary
    result["items"] = [
        OperatorSummary(
            id=row.id,
            name=row.name,
            normalized_name=row.normalized_name,
            well_count=row.well_count,
            # Filter out None values from array_agg (from operators with no wells)
            state_codes=[s for s in (row.state_codes or []) if s is not None],
        )
        for row in result["items"]
    ]

    return result
