"""Export API endpoints with streaming responses.

GET /api/v1/export/wells -- Export wells data as CSV or JSON
GET /api/v1/export/production -- Export production data as CSV or JSON
"""

import csv
import io
import json
from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from og_scraper.api.deps import get_db
from og_scraper.api.schemas.export import ExportFormat
from og_scraper.models.extracted_data import ExtractedData
from og_scraper.models.operator import Operator
from og_scraper.models.well import Well

router = APIRouter()

DbSession = Annotated[AsyncSession, Depends(get_db)]


@router.get("/wells")
async def export_wells(  # noqa: A002
    db: DbSession,
    format: ExportFormat = ExportFormat.CSV,  # noqa: A002
    state: str | None = None,
    county: str | None = None,
    well_status: str | None = None,
    well_type: str | None = None,
    operator: str | None = None,
):
    """Export wells data as CSV or JSON. Uses streaming for large datasets.

    Query params:
    - format: csv or json (default: csv)
    - state: Filter by state code
    - county: Filter by county (partial match)
    - well_status: Filter by well status
    - well_type: Filter by well type
    - operator: Filter by operator name (partial match)
    """
    query = (
        select(
            Well.api_number,
            Well.well_name,
            Well.well_number,
            Operator.name.label("operator_name"),
            Well.state_code,
            Well.county,
            Well.basin,
            Well.field_name,
            Well.lease_name,
            Well.latitude,
            Well.longitude,
            Well.well_status,
            Well.well_type,
            Well.spud_date,
            Well.completion_date,
            Well.total_depth,
        )
        .outerjoin(Operator, Well.operator_id == Operator.id)
        .order_by(Well.api_number)
    )

    if state:
        query = query.where(Well.state_code == state.upper())
    if county:
        query = query.where(Well.county.ilike(f"%{county}%"))
    if well_status:
        query = query.where(Well.well_status == well_status)
    if well_type:
        query = query.where(Well.well_type == well_type)
    if operator:
        query = query.where(Operator.name.ilike(f"%{operator}%"))

    if format == ExportFormat.CSV:
        return StreamingResponse(
            _wells_csv_generator(db, query),
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": "attachment; filename=wells_export.csv"},
        )
    else:
        return StreamingResponse(
            _wells_json_generator(db, query),
            media_type="application/json",
            headers={"Content-Disposition": "attachment; filename=wells_export.json"},
        )


async def _wells_csv_generator(db: AsyncSession, query):
    """Async generator that streams wells as CSV rows."""
    output = io.StringIO()
    writer = csv.writer(output)

    # Header row
    headers = [
        "api_number",
        "well_name",
        "well_number",
        "operator",
        "state",
        "county",
        "basin",
        "field_name",
        "lease_name",
        "latitude",
        "longitude",
        "well_status",
        "well_type",
        "spud_date",
        "completion_date",
        "total_depth",
    ]
    writer.writerow(headers)
    yield output.getvalue()
    output.seek(0)
    output.truncate(0)

    # Stream data rows
    result = await db.stream(query)
    async for row in result:
        writer.writerow([
            row.api_number,
            row.well_name or "",
            row.well_number or "",
            row.operator_name or "",
            row.state_code or "",
            row.county or "",
            row.basin or "",
            row.field_name or "",
            row.lease_name or "",
            row.latitude if row.latitude is not None else "",
            row.longitude if row.longitude is not None else "",
            str(row.well_status) if row.well_status else "",
            row.well_type or "",
            str(row.spud_date) if row.spud_date else "",
            str(row.completion_date) if row.completion_date else "",
            row.total_depth if row.total_depth is not None else "",
        ])
        yield output.getvalue()
        output.seek(0)
        output.truncate(0)


async def _wells_json_generator(db: AsyncSession, query):
    """Async generator that streams wells as a JSON array."""
    yield "["
    first = True
    result = await db.stream(query)
    async for row in result:
        if not first:
            yield ","
        first = False
        yield json.dumps({
            "api_number": row.api_number,
            "well_name": row.well_name,
            "well_number": row.well_number,
            "operator": row.operator_name,
            "state": row.state_code,
            "county": row.county,
            "basin": row.basin,
            "field_name": row.field_name,
            "lease_name": row.lease_name,
            "latitude": row.latitude,
            "longitude": row.longitude,
            "well_status": str(row.well_status) if row.well_status else None,
            "well_type": row.well_type,
            "spud_date": str(row.spud_date) if row.spud_date else None,
            "completion_date": str(row.completion_date) if row.completion_date else None,
            "total_depth": row.total_depth,
        })
    yield "]"


@router.get("/production")
async def export_production(
    db: DbSession,
    format: ExportFormat = ExportFormat.CSV,  # noqa: A002
    state: str | None = None,
    well_id: UUID | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
):
    """Export production data as CSV or JSON.

    Extracts production fields from the extracted_data JSONB column.
    Uses streaming for large datasets.

    Query params:
    - format: csv or json (default: csv)
    - state: Filter by state code
    - well_id: Filter by well ID
    - date_from: Filter by start date (inclusive)
    - date_to: Filter by end date (inclusive)
    """
    query = (
        select(
            Well.api_number,
            Well.well_name,
            Operator.name.label("operator_name"),
            Well.state_code,
            Well.county,
            ExtractedData.data,
            ExtractedData.reporting_period_start,
            ExtractedData.reporting_period_end,
            ExtractedData.confidence_score,
        )
        .join(ExtractedData, ExtractedData.well_id == Well.id)
        .outerjoin(Operator, Well.operator_id == Operator.id)
        .where(ExtractedData.data_type == "production")
        .order_by(Well.api_number, ExtractedData.reporting_period_start)
    )

    if state:
        query = query.where(Well.state_code == state.upper())
    if well_id:
        query = query.where(ExtractedData.well_id == well_id)
    if date_from:
        query = query.where(ExtractedData.reporting_period_start >= date_from)
    if date_to:
        query = query.where(ExtractedData.reporting_period_end <= date_to)

    if format == ExportFormat.CSV:
        return StreamingResponse(
            _production_csv_generator(db, query),
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": "attachment; filename=production_export.csv"},
        )
    else:
        return StreamingResponse(
            _production_json_generator(db, query),
            media_type="application/json",
            headers={"Content-Disposition": "attachment; filename=production_export.json"},
        )


async def _production_csv_generator(db: AsyncSession, query):
    """Async generator that streams production data as CSV rows."""
    output = io.StringIO()
    writer = csv.writer(output)

    headers = [
        "api_number",
        "well_name",
        "operator",
        "state",
        "county",
        "reporting_period_start",
        "reporting_period_end",
        "oil_bbl",
        "gas_mcf",
        "water_bbl",
        "days_produced",
        "confidence_score",
    ]
    writer.writerow(headers)
    yield output.getvalue()
    output.seek(0)
    output.truncate(0)

    result = await db.stream(query)
    async for row in result:
        data = row.data or {}
        writer.writerow([
            row.api_number,
            row.well_name or "",
            row.operator_name or "",
            row.state_code or "",
            row.county or "",
            str(row.reporting_period_start) if row.reporting_period_start else "",
            str(row.reporting_period_end) if row.reporting_period_end else "",
            data.get("oil_bbl", ""),
            data.get("gas_mcf", ""),
            data.get("water_bbl", ""),
            data.get("days_produced", ""),
            row.confidence_score if row.confidence_score is not None else "",
        ])
        yield output.getvalue()
        output.seek(0)
        output.truncate(0)


async def _production_json_generator(db: AsyncSession, query):
    """Async generator that streams production data as a JSON array."""
    yield "["
    first = True
    result = await db.stream(query)
    async for row in result:
        if not first:
            yield ","
        first = False
        data = row.data or {}
        yield json.dumps({
            "api_number": row.api_number,
            "well_name": row.well_name,
            "operator": row.operator_name,
            "state": row.state_code,
            "county": row.county,
            "reporting_period_start": str(row.reporting_period_start) if row.reporting_period_start else None,
            "reporting_period_end": str(row.reporting_period_end) if row.reporting_period_end else None,
            "oil_bbl": data.get("oil_bbl"),
            "gas_mcf": data.get("gas_mcf"),
            "water_bbl": data.get("water_bbl"),
            "days_produced": data.get("days_produced"),
            "confidence_score": float(row.confidence_score) if row.confidence_score is not None else None,
        })
    yield "]"
