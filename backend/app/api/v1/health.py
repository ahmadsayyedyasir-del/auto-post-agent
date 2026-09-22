"""Health check endpoint router."""

from fastapi import APIRouter

router = APIRouter()


@router.get("/health", summary="Health Check", tags=["Health"])
async def health_check() -> dict[str, str]:
    """Return application health status."""
    return {"status": "healthy"}
