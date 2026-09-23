"""FastAPI application entry point for the AI Social Media Automation Platform."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI

from backend.app.api.v1.router import api_router
from backend.app.config import get_settings
from backend.app.core.logging import setup_logging
from backend.app.db.session import close_db_engine, get_session_factory
from backend.app.scheduling.manager import get_schedule_manager

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Application lifespan context manager for startup and shutdown events."""
    settings = get_settings()
    setup_logging(log_level=settings.log_level)
    logger.info("Starting %s in [%s] mode", settings.app_name, settings.app_env)

    # 1. Initialize and start ScheduleManager (APScheduler)
    schedule_manager = get_schedule_manager()
    schedule_manager.start()

    # 2. Recover and re-register active schedules from database
    if settings.scheduler_startup_recovery_enabled:
        session_factory = get_session_factory(settings)
        async with session_factory() as session:
            try:
                recovered_count = await schedule_manager.recover_schedules(session)
                logger.info("Scheduler startup recovery completed: %d active jobs restored.", recovered_count)
            except Exception as err:
                logger.warning("Scheduler startup recovery encountered error (e.g. fresh database): %s", err)

    yield

    # 3. Graceful shutdown
    logger.info("Shutting down scheduler...")
    schedule_manager.shutdown(wait=False)
    await close_db_engine()
    logger.info("Shutting down %s", settings.app_name)


def create_app() -> FastAPI:
    """Application factory for creating and configuring the FastAPI app instance."""
    settings = get_settings()

    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description="Backend API for AI Social Media Automation Platform (Phase 1: Project Foundation)",
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )

    # Root-level health check endpoint
    @app.get(
        "/health",
        summary="Root Health Check",
        tags=["Health"],
        response_model=dict[str, str],
    )
    async def root_health() -> dict[str, str]:
        """Root health check endpoint."""
        return {"status": "healthy"}

    # Include modular v1 API router
    app.include_router(api_router, prefix=settings.api_v1_str)

    return app


app = create_app()
