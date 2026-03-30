"""Wells API endpoints.

GET /api/v1/wells -- Search/filter/paginate wells
GET /api/v1/wells/{api_number} -- Well detail with documents
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from og_scraper.api.deps import get_db
from og_scraper.api.schemas.enums import SortDirection, WellStatus
from og_scraper.api.schemas.pagination import PaginatedResponse
from og_scraper.api.schemas.well import WellDetail, WellSummary
from og_scraper.api.utils.api_number import normalize_api_number
from og_scraper.api.utils.pagination import paginate
from og_scraper.api.utils.query_builder import build_wells_query
from og_scraper.models.well import Well

router = APIRouter()

DbSession = Annotated[AsyncSession, Depends(get_db)]


@router.get("/", response_model=PaginatedResponse[WellSummary])
async def list_wells(
    db: DbSession,
    q: str | None = None,
    api_number: str | None = None,
    state: str | None = None,
    county: str | None = None,
    operator: str | None = None,
    lease_name: str | None = None,
    well_status: WellStatus | None = None,
    well_type: str | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    sort_by: str = "api_number",
    sort_dir: SortDirection = SortDirection.ASC,
):
    """Search, filter, and paginate wells."""
    query = build_wells_query(
        q=q,
        api_number=api_number,
        state=state,
        county=county,
        operator=operator,
        lease_name=lease_name,
        well_status=well_status.value if well_status else None,
        well_type=well_type,
        sort_by=sort_by,
        sort_dir=sort_dir.value,
    )
    result = await paginate(db, query, page, page_size)

    # Convert Row objects to WellSummary dicts
    result["items"] = [
        WellSummary(
            id=row.id,
            api_number=row.api_number,
            well_name=row.well_name,
            operator_name=row.operator_name,
            state_code=row.state_code,
            county=row.county,
            well_status=row.well_status,
            well_type=row.well_type,
            latitude=row.latitude,
            longitude=row.longitude,
            document_count=row.document_count,
        )
        for row in result["items"]
    ]

    return result


@router.get("/{api_number}", response_model=WellDetail)
async def get_well(
    api_number: str,
    db: DbSession,
):
    """Get well detail by API number (accepts dashes)."""
    normalized = normalize_api_number(api_number)
    query = (
        select(Well)
        .options(selectinload(Well.documents), selectinload(Well.operator))
        .where(
            or_(
                Well.api_number == normalized,
                Well.api_10 == normalized[:10],
            )
        )
    )
    result = await db.execute(query)
    well = result.scalar_one_or_none()
    if not well:
        raise HTTPException(status_code=404, detail=f"Well not found: {api_number}")

    # Build response with operator_name and metadata
    return WellDetail(
        id=well.id,
        api_number=well.api_number,
        api_10=well.api_10,
        well_name=well.well_name,
        well_number=well.well_number,
        operator_id=well.operator_id,
        operator_name=well.operator.name if well.operator else None,
        state_code=well.state_code,
        county=well.county,
        basin=well.basin,
        field_name=well.field_name,
        lease_name=well.lease_name,
        latitude=well.latitude,
        longitude=well.longitude,
        well_status=well.well_status,
        well_type=well.well_type,
        spud_date=well.spud_date,
        completion_date=well.completion_date,
        total_depth=well.total_depth,
        true_vertical_depth=well.true_vertical_depth,
        lateral_length=well.lateral_length,
        metadata=well.metadata_,
        alternate_ids=well.alternate_ids,
        documents=well.documents,
        created_at=well.created_at,
        updated_at=well.updated_at,
    )
