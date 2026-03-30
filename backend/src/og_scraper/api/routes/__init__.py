"""API route aggregation.

Collects all routers and provides a single router for the app to include.
"""

from fastapi import APIRouter

from .health import router as health_router

# API v1 router -- all versioned endpoints go here
api_v1_router = APIRouter(prefix="/api/v1")

# Health is at root level (not versioned)
# API endpoints will be added to api_v1_router in Phase 3

__all__ = ["api_v1_router", "health_router"]
