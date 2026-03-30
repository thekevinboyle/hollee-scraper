"""Reusable pagination utility for SQLAlchemy async queries."""

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession


async def paginate(
    db: AsyncSession,
    query,
    page: int = 1,
    page_size: int = 50,
) -> dict:
    """Apply pagination to a SQLAlchemy query and return paginated result.

    Args:
        db: Async database session.
        query: SQLAlchemy select statement.
        page: Page number (1-based).
        page_size: Number of items per page.

    Returns:
        Dict with items, total, page, page_size, total_pages.
    """
    # Count total matching rows
    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar_one()

    # Apply offset/limit
    offset = (page - 1) * page_size
    items_query = query.offset(offset).limit(page_size)
    result = await db.execute(items_query)
    items = result.all()

    total_pages = max(1, (total + page_size - 1) // page_size)

    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": total_pages,
    }
