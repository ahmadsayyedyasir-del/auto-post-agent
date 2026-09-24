"""FastAPI router endpoints for social media post publishing and publication management.

Phase 12: All endpoints require authentication. Publishing uses the workflow owner's
credentials via AsyncCredentialResolver. Returns 404 for resources of other users.
"""

import logging
from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.api.v1.dependencies import get_current_active_user
from backend.app.db.models.user import User
from backend.app.db.repositories.workflow_repo import WorkflowRepository
from backend.app.db.session import get_db_session
from backend.app.publishing.base import PermanentPlatformError, TransientPlatformError
from backend.app.publishing.schemas import (
    PublicationListResponseSchema,
    PublicationResponseSchema,
    PublishWorkflowRequestSchema,
)
from backend.app.publishing.service import PublishingService

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Publishing"])


def _format_publication_response(pub: Any) -> PublicationResponseSchema:
    """Convert ORM Publication to response schema."""
    return PublicationResponseSchema(
        id=pub.id,
        workflow_run_id=pub.workflow_run_id,
        post_id=pub.post_id,
        platform=pub.platform,
        status=pub.status,
        idempotency_key=pub.idempotency_key,
        external_post_id=pub.external_post_id,
        external_url=pub.external_url,
        attempt_count=pub.attempt_count,
        last_attempt_at=pub.last_attempt_at,
        published_at=pub.published_at,
        error_code=pub.error_code,
        error_message=pub.error_message,
        created_at=pub.created_at,
        updated_at=pub.updated_at,
    )


async def _resolve_workflow_and_check_ownership(
    workflow_id: str,
    current_user: User,
    session: AsyncSession,
) -> str:
    """Fetch workflow and check ownership. Returns the effective user_id for credential resolution.

    Returns 404 for:
    - Workflow not found.
    - Workflow owned by a different user.

    Returns the workflow owner's user_id (may be None for legacy records, falls back to current_user.id).
    """
    repo = WorkflowRepository(session)
    workflow = await repo.get_by_id(workflow_id)
    if not workflow:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Workflow '{workflow_id}' not found.",
        )
    if workflow.user_id is not None and workflow.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Workflow '{workflow_id}' not found.",
        )
    # For legacy (user_id=None) workflows, use the authenticated user's credentials
    return workflow.user_id or current_user.id


@router.post(
    "/workflows/{workflow_id}/publish",
    response_model=PublicationResponseSchema,
    status_code=status.HTTP_200_OK,
    summary="Publish an approved workflow post to a social media platform",
)
async def publish_post(
    workflow_id: str,
    current_user: User = Depends(get_current_active_user),
    payload: PublishWorkflowRequestSchema | None = Body(default=None),
    session: AsyncSession = Depends(get_db_session),
) -> PublicationResponseSchema:
    """Publish the human-approved post for the specified workflow run.

    Phase 12: Uses the workflow owner's platform credentials (per-user DB lookup
    with environment fallback). Credentials never appear in state or responses.
    """
    owner_user_id = await _resolve_workflow_and_check_ownership(workflow_id, current_user, session)
    platform_override = payload.platform_override if payload else None

    service = PublishingService()
    try:
        publication = await service.publish_workflow_post(
            workflow_id=workflow_id,
            session=session,
            platform_override=platform_override,
            user_id=owner_user_id,
        )
        return _format_publication_response(publication)
    except ValueError as val_err:
        err_msg = str(val_err)
        if "not found" in err_msg.lower():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=err_msg,
            )
        if "expected 'approved'" in err_msg.lower() or "in-flight" in err_msg.lower() or "already" in err_msg.lower():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=err_msg,
            )
        if "unsupported" in err_msg.lower():
            raise HTTPException(
                status_code=422,
                detail=err_msg,
            )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=err_msg,
        )
    except PermanentPlatformError as perm_err:
        raise HTTPException(
            status_code=422,
            detail=f"Platform credential or configuration error: {perm_err}",
        )
    except Exception as err:
        logger.exception("Failed to execute publishing for workflow '%s': %s", workflow_id, err)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Publishing execution error: {err}",
        )


@router.get(
    "/workflows/{workflow_id}/publication",
    response_model=PublicationListResponseSchema,
    summary="Retrieve publication history for a workflow",
)
async def get_workflow_publications(
    workflow_id: str,
    current_user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_db_session),
) -> PublicationListResponseSchema:
    """Fetch all publication records for a given workflow run."""
    await _resolve_workflow_and_check_ownership(workflow_id, current_user, session)
    service = PublishingService()
    publications = await service.get_publications_for_workflow(workflow_id, session)
    formatted = [_format_publication_response(p) for p in publications]
    return PublicationListResponseSchema(
        publications=formatted,
        total=len(formatted),
    )


@router.post(
    "/publications/{publication_id}/retry",
    response_model=PublicationResponseSchema,
    summary="Retry a failed social media publication",
)
async def retry_publication(
    publication_id: str,
    current_user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_db_session),
) -> PublicationResponseSchema:
    """Manually retry a publication that previously failed."""
    from backend.app.db.repositories.publication_repo import PublicationRepository

    pub_repo = PublicationRepository(session)
    publication = await pub_repo.get_by_id(publication_id)
    if not publication:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Publication '{publication_id}' not found.",
        )
    # Ownership check via workflow
    owner_user_id = await _resolve_workflow_and_check_ownership(
        publication.workflow_run_id, current_user, session
    )

    service = PublishingService()
    try:
        pub = await service.retry_publication(publication_id, session, user_id=owner_user_id)
        return _format_publication_response(pub)
    except ValueError as val_err:
        err_msg = str(val_err)
        if "not found" in err_msg.lower():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=err_msg,
            )
        if "already" in err_msg.lower() or "approved" in err_msg.lower():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=err_msg,
            )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=err_msg,
        )
    except PermanentPlatformError as perm_err:
        raise HTTPException(
            status_code=422,
            detail=f"Platform configuration error: {perm_err}",
        )
    except Exception as err:
        logger.exception("Failed to retry publication '%s': %s", publication_id, err)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrying publication: {err}",
        )


@router.get(
    "/publications/{publication_id}",
    response_model=PublicationResponseSchema,
    summary="Retrieve a single publication record by ID",
)
async def get_publication(
    publication_id: str,
    current_user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_db_session),
) -> PublicationResponseSchema:
    """Fetch details of a specific publication record."""
    from backend.app.db.repositories.publication_repo import PublicationRepository

    pub_repo = PublicationRepository(session)
    publication = await pub_repo.get_by_id(publication_id)
    if not publication:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Publication '{publication_id}' not found.",
        )
    # Ownership check
    await _resolve_workflow_and_check_ownership(
        publication.workflow_run_id, current_user, session
    )
    service = PublishingService()
    pub = await service.get_publication_by_id(publication_id, session)
    return _format_publication_response(pub)
