"""Central v1 API router aggregating all modular sub-routers."""

from fastapi import APIRouter
from backend.app.api.v1.health import router as health_router

api_router = APIRouter()

# Register modular sub-routers
api_router.include_router(health_router, tags=["Health"])
