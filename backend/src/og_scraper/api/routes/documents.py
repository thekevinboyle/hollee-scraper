"""Documents API endpoints.

GET /api/v1/documents -- Search/filter/paginate documents
GET /api/v1/documents/{id} -- Document detail with extracted data
GET /api/v1/documents/{id}/file -- Serve the original document file
"""

import uuid
from datetime import date
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from og_scraper.api.deps import get_db
from og_scraper.api.schemas.document import DocumentDetail, DocumentSummary
from og_scraper.api.schemas.enums import DocType, DocumentStatus, SortDirection
from og_scraper.api.schemas.pagination import PaginatedResponse
from og_scraper.api.utils.pagination import paginate
from og_scraper.api.utils.query_builder import build_documents_query
from og_scraper.models.document import Document

router = APIRouter()

DbSession = Annotated[AsyncSession, Depends(get_db)]

# MIME type mapping for file serving
MIME_TYPES = {
    "pdf": "application/pdf",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "xls": "application/vnd.ms-excel",
    "csv": "text/csv",
    "html": "text/html",
    "tif": "image/tiff",
    "tiff": "image/tiff",
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
}


@router.get("/", response_model=PaginatedResponse[DocumentSummary])
async def list_documents(
    db: DbSession,
    q: str | None = None,
    well_id: uuid.UUID | None = None,
    state: str | None = None,
    doc_type: DocType | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    min_confidence: float | None = None,
    status: DocumentStatus | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    sort_by: str = "scraped_at",
    sort_dir: SortDirection = SortDirection.DESC,
):
    """Search, filter, and paginate documents."""
    query = build_documents_query(
        q=q,
        well_id=str(well_id) if well_id else None,
        state=state,
        doc_type=doc_type.value if doc_type else None,
        date_from=date_from,
        date_to=date_to,
        min_confidence=min_confidence,
        status=status.value if status else None,
        sort_by=sort_by,
        sort_dir=sort_dir.value,
    )
    result = await paginate(db, query, page, page_size)

    # Convert Row objects to DocumentSummary dicts
    result["items"] = [
        DocumentSummary(
            id=row.id,
            well_id=row.well_id,
            state_code=row.state_code,
            doc_type=row.doc_type,
            document_date=row.document_date,
            confidence_score=float(row.confidence_score) if row.confidence_score is not None else None,
            file_format=row.file_format,
            source_url=row.source_url,
            scraped_at=row.scraped_at,
        )
        for row in result["items"]
    ]

    return result


@router.get("/{document_id}", response_model=DocumentDetail)
async def get_document(
    document_id: uuid.UUID,
    db: DbSession,
):
    """Get document detail with extracted data."""
    query = (
        select(Document)
        .options(
            selectinload(Document.extracted_data),
            selectinload(Document.well),
        )
        .where(Document.id == document_id)
    )
    result = await db.execute(query)
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail=f"Document not found: {document_id}")

    return DocumentDetail(
        id=doc.id,
        well_id=doc.well_id,
        well_api_number=doc.well.api_number if doc.well else None,
        state_code=doc.state_code,
        doc_type=doc.doc_type,
        status=doc.status,
        source_url=doc.source_url,
        file_path=doc.file_path,
        file_format=doc.file_format,
        file_size_bytes=doc.file_size_bytes,
        file_hash=doc.file_hash,
        confidence_score=float(doc.confidence_score) if doc.confidence_score is not None else None,
        ocr_confidence=float(doc.ocr_confidence) if doc.ocr_confidence is not None else None,
        classification_method=doc.classification_method,
        document_date=doc.document_date,
        scraped_at=doc.scraped_at,
        processed_at=doc.processed_at,
        raw_metadata=doc.raw_metadata,
        extracted_data=doc.extracted_data,
        created_at=doc.created_at,
        updated_at=doc.updated_at,
    )


@router.get("/{document_id}/file")
async def get_document_file(
    document_id: uuid.UUID,
    db: DbSession,
):
    """Serve the original document file.

    PDF files are served inline (viewable in browser).
    Other file types are served as attachments (download).
    """
    query = select(Document).where(Document.id == document_id)
    result = await db.execute(query)
    doc = result.scalar_one_or_none()

    if not doc:
        raise HTTPException(status_code=404, detail=f"Document not found: {document_id}")

    if not doc.file_path:
        raise HTTPException(status_code=404, detail="Document has no associated file")

    file_path = Path(doc.file_path)
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Document file not found on disk")

    # Determine MIME type
    extension = file_path.suffix.lstrip(".").lower()
    media_type = MIME_TYPES.get(extension, "application/octet-stream")

    # PDF: inline viewing; others: attachment (download)
    filename = file_path.name
    if extension == "pdf":
        content_disposition = f'inline; filename="{filename}"'
    else:
        content_disposition = f'attachment; filename="{filename}"'

    return FileResponse(
        path=str(file_path),
        media_type=media_type,
        headers={"Content-Disposition": content_disposition},
    )
