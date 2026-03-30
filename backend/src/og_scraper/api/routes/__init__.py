"""API route aggregation.

Collects all routers and provides a single router for the app to include.
"""

from fastapi import APIRouter

from .documents import router as documents_router
from .health import router as health_router
from .operators import router as operators_router
from .review import router as review_router
from .scrape import router as scrape_router
from .states import router as states_router
from .wells import router as wells_router

# API v1 router -- all versioned endpoints go here
api_v1_router = APIRouter(prefix="/api/v1")

# Register CRUD routers
api_v1_router.include_router(wells_router, prefix="/wells", tags=["wells"])
api_v1_router.include_router(documents_router, prefix="/documents", tags=["documents"])
api_v1_router.include_router(operators_router, prefix="/operators", tags=["operators"])
api_v1_router.include_router(states_router, prefix="/states", tags=["states"])
api_v1_router.include_router(review_router, prefix="/review", tags=["review"])
api_v1_router.include_router(scrape_router, prefix="/scrape", tags=["scraping"])

# Health is at root level (not versioned)

__all__ = ["api_v1_router", "health_router"]
