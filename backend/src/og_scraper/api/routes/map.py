"""Map API endpoints.

GET /api/v1/map/wells -- Wells within a geographic bounding box
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from og_scraper.api.deps import get_db
from og_scraper.api.schemas.map import WellMapPoint
from og_scraper.models.operator import Operator
from og_scraper.models.well import Well

router = APIRouter()

DbSession = Annotated[AsyncSession, Depends(get_db)]


@router.get("/wells", response_model=list[WellMapPoint])
async def get_map_wells(
    db: DbSession,
    min_lat: float = Query(..., description="South boundary latitude"),
    max_lat: float = Query(..., description="North boundary latitude"),
    min_lng: float = Query(..., description="West boundary longitude"),
    max_lng: float = Query(..., description="East boundary longitude"),
    well_status: str | None = Query(None, description="Filter by well status"),
    well_type: str | None = Query(None, description="Filter by well type"),
    limit: int = Query(default=1000, ge=1, le=5000, description="Max wells to return"),
):
    """Return wells within the given map viewport bounding box.

    Uses PostGIS spatial index (GiST) with the && operator for
    sub-10ms query performance on large datasets.

    IMPORTANT: ST_MakeEnvelope takes (min_lng, min_lat, max_lng, max_lat, srid)
    -- longitude first, latitude second.
    """
    # Validate bounds
    if min_lat >= max_lat:
        raise HTTPException(status_code=400, detail="min_lat must be less than max_lat")
    if min_lng >= max_lng:
        raise HTTPException(status_code=400, detail="min_lng must be less than max_lng")

    # Build the bounding box envelope -- longitude first, latitude second
    envelope = func.ST_MakeEnvelope(min_lng, min_lat, max_lng, max_lat, 4326)

    query = (
        select(
            Well.id,
            Well.api_number,
            Well.well_name,
            Operator.name.label("operator_name"),
            Well.latitude,
            Well.longitude,
            Well.well_status,
            Well.well_type,
        )
        .outerjoin(Operator, Well.operator_id == Operator.id)
        .where(Well.location.op("&&")(envelope))  # Bounding box check using GiST index
        .where(Well.latitude.is_not(None))
        .where(Well.longitude.is_not(None))
    )

    if well_status:
        query = query.where(Well.well_status == well_status)
    if well_type:
        query = query.where(Well.well_type == well_type)

    query = query.order_by(Well.api_number).limit(limit)

    result = await db.execute(query)
    rows = result.all()

    return [
        WellMapPoint(
            id=row.id,
            api_number=row.api_number,
            well_name=row.well_name,
            operator_name=row.operator_name,
            latitude=row.latitude,
            longitude=row.longitude,
            well_status=row.well_status,
            well_type=row.well_type,
        )
        for row in rows
    ]
