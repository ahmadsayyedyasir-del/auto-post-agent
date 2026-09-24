"""Central v1 API router aggregating all modular sub-routers."""

from fastapi import APIRouter
from backend.app.api.v1.auth import router as auth_router
from backend.app.api.v1.credentials import router as credentials_router
from backend.app.api.v1.health import router as health_router
from backend.app.api.v1.publishing import router as publishing_router
from backend.app.api.v1.schedules import router as schedules_router
from backend.app.api.v1.workflows import router as workflows_router

api_router = APIRouter()

# Register modular sub-routers
api_router.include_router(health_router, tags=["Health"])
api_router.include_router(auth_router)          # Phase 12: /auth/*
api_router.include_router(credentials_router)   # Phase 12: /credentials/*
api_router.include_router(workflows_router)
api_router.include_router(publishing_router)
api_router.include_router(schedules_router)
