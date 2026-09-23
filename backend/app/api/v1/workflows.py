"""FastAPI router endpoints for Workflow management, HITL review, and revision history."""

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db.repositories.workflow_repo import WorkflowRepository
from backend.app.db.session import get_db_session
from backend.app.models.research import ResearchRequest
from backend.app.publishing.schemas import PublicationResponseSchema
from backend.app.scheduling.schemas import ScheduleResponseSchema
from backend.app.services.workflow_service import WorkflowService
from backend.app.workflows.state import HumanReviewAction, WorkflowStatus

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/workflows", tags=["Workflows"])


# ------------------------------------------------------------------------------
# Request & Response Schemas
# ------------------------------------------------------------------------------


class HumanReviewPayload(BaseModel):
    """Payload schema submitted by a human reviewer to decide on a paused workflow."""

    action: HumanReviewAction = Field(
        ...,
        description="Review action: APPROVE, REVISE, REJECT, or EDIT",
    )
    feedback: list[str] | str | None = Field(
        default=None,
        description="Actionable feedback instructions for REVISE",
    )
    content: str | None = Field(
        default=None,
        description="Updated post text for direct EDIT",
    )


class RevisionResponseSchema(BaseModel):
    """Schema representing an individual historical revision."""

    id: str
    revision_number: int
    revision_source: str
    content: str
    hashtags: list[str]
    cta: str | None
    source_references: list[str]
    revision_feedback: list[str]


class PostResponseSchema(BaseModel):
    """Schema representing generated post data."""

    id: str
    platform: str
    topic: str
    content: str
    status: str
    content_type: str
    language: str
    hashtags: list[str]
    cta: str | None
    source_references: list[str]
    revisions: list[RevisionResponseSchema] = []


class FeedbackResponseSchema(BaseModel):
    """Schema representing evaluation records."""

    id: str
    feedback_source: str
    decision: str
    issues: list[str]
    feedback_items: list[str]
    reviewer_notes: str | None


class WorkflowDetailResponse(BaseModel):
    """Comprehensive response schema for a workflow execution."""

    id: str
    niche: str
    target_platform: str
    audience: str | None
    language: str
    status: str
    current_stage: str | None
    revision_count: int
    agent_revision_count: int
    human_revision_count: int
    max_revisions: int
    research_data: dict[str, Any] | None
    content_plan: dict[str, Any] | None
    error_message: str | None
    posts: list[PostResponseSchema] = []
    feedbacks: list[FeedbackResponseSchema] = []
    publications: list[PublicationResponseSchema] = []
    schedules: list[ScheduleResponseSchema] = []


def _format_workflow_response(wf: Any) -> WorkflowDetailResponse:
    """Helper to convert ORM WorkflowRun to response schema."""
    posts_data = []
    for p in wf.posts:
        revs = [
            RevisionResponseSchema(
                id=r.id,
                revision_number=r.revision_number,
                revision_source=r.revision_source,
                content=r.content,
                hashtags=r.hashtags or [],
                cta=r.cta,
                source_references=r.source_references or [],
                revision_feedback=r.revision_feedback or [],
            )
            for r in getattr(p, "revisions", [])
        ]
        posts_data.append(
            PostResponseSchema(
                id=p.id,
                platform=p.platform,
                topic=p.topic,
                content=p.content,
                status=p.status,
                content_type=p.content_type,
                language=p.language,
                hashtags=p.hashtags or [],
                cta=p.cta,
                source_references=p.source_references or [],
                revisions=revs,
            )
        )

    feedbacks_data = [
        FeedbackResponseSchema(
            id=f.id,
            feedback_source=f.feedback_source,
            decision=f.decision,
            issues=f.issues or [],
            feedback_items=f.feedback_items or [],
            reviewer_notes=f.reviewer_notes,
        )
        for f in getattr(wf, "feedbacks", [])
    ]

    publications_data = [
        PublicationResponseSchema(
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
        for pub in getattr(wf, "publications", [])
    ]

    schedules_data = [
        ScheduleResponseSchema(
            id=sch.id,
            workflow_run_id=sch.workflow_run_id,
            post_id=sch.post_id,
            platform=sch.platform,
            scheduled_at=sch.scheduled_at,
            timezone=sch.timezone,
            status=sch.status,
            job_id=sch.job_id,
            attempt_count=sch.attempt_count,
            last_error=sch.last_error,
            executed_at=sch.executed_at,
            created_at=sch.created_at,
            updated_at=sch.updated_at,
        )
        for sch in getattr(wf, "schedules", [])
    ]

    return WorkflowDetailResponse(
        id=wf.id,
        niche=wf.niche,
        target_platform=wf.target_platform,
        audience=wf.audience,
        language=wf.language,
        status=wf.status,
        current_stage=wf.current_stage,
        revision_count=wf.revision_count,
        agent_revision_count=wf.agent_revision_count,
        human_revision_count=wf.human_revision_count,
        max_revisions=wf.max_revisions,
        research_data=wf.research_data,
        content_plan=wf.content_plan,
        error_message=wf.error_message,
        posts=posts_data,
        feedbacks=feedbacks_data,
        publications=publications_data,
        schedules=schedules_data,
    )


# ------------------------------------------------------------------------------
# API Endpoints
# ------------------------------------------------------------------------------


@router.post(
    "/start",
    response_model=WorkflowDetailResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Start a new multi-agent social media generation workflow",
)
async def start_workflow(
    request: ResearchRequest,
    session: AsyncSession = Depends(get_db_session),
) -> WorkflowDetailResponse:
    """Start workflow execution pipeline. Runs through Research -> Planning -> Writer -> Critic until Human Review."""
    service = WorkflowService()
    try:
        workflow = await service.start_workflow(request, session)
        return _format_workflow_response(workflow)
    except Exception as err:
        logger.exception("Failed to start workflow: %s", err)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to start workflow: {err}",
        )


@router.get(
    "/{workflow_id}",
    response_model=WorkflowDetailResponse,
    summary="Retrieve workflow execution status and associated draft posts",
)
async def get_workflow(
    workflow_id: str,
    session: AsyncSession = Depends(get_db_session),
) -> WorkflowDetailResponse:
    """Fetch complete workflow record, current status, and generated draft/revisions."""
    service = WorkflowService()
    workflow = await service.get_workflow(workflow_id, session)
    if not workflow:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Workflow '{workflow_id}' not found.",
        )
    return _format_workflow_response(workflow)


@router.post(
    "/{workflow_id}/review",
    response_model=WorkflowDetailResponse,
    summary="Submit a human review decision (APPROVE, REVISE, REJECT, EDIT)",
)
async def submit_review(
    workflow_id: str,
    payload: HumanReviewPayload,
    session: AsyncSession = Depends(get_db_session),
) -> WorkflowDetailResponse:
    """Resume a paused workflow by submitting a human review action.

    - **APPROVE**: Approves content and completes workflow.
    - **REVISE**: Sends actionable feedback back to WriterAgent.
    - **REJECT**: Terminates workflow.
    - **EDIT**: Directly edits text and submits to CriticAgent for quality verification.
    """
    service = WorkflowService()
    try:
        updated_workflow = await service.submit_human_review(
            workflow_id=workflow_id,
            action=payload.action,
            session=session,
            feedback=payload.feedback,
            content=payload.content,
        )
        return _format_workflow_response(updated_workflow)
    except ValueError as val_err:
        err_msg = str(val_err)
        if "not found" in err_msg.lower():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=err_msg)
        if "requires" in err_msg.lower() or "unrecognized" in err_msg.lower():
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=err_msg)
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=err_msg)
    except Exception as err:
        logger.exception("Failed to process review for workflow '%s': %s", workflow_id, err)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error executing review decision: {err}",
        )


@router.get(
    "/{workflow_id}/revisions",
    response_model=list[RevisionResponseSchema],
    summary="Retrieve ordered historical revision snapshots for a workflow",
)
async def get_revisions(
    workflow_id: str,
    session: AsyncSession = Depends(get_db_session),
) -> list[RevisionResponseSchema]:
    """Fetch complete revision timeline for all posts in a workflow."""
    service = WorkflowService()
    workflow = await service.get_workflow(workflow_id, session)
    if not workflow:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Workflow '{workflow_id}' not found.",
        )

    all_revisions: list[RevisionResponseSchema] = []
    for post in workflow.posts:
        for rev in post.revisions:
            all_revisions.append(
                RevisionResponseSchema(
                    id=rev.id,
                    revision_number=rev.revision_number,
                    revision_source=rev.revision_source,
                    content=rev.content,
                    hashtags=rev.hashtags or [],
                    cta=rev.cta,
                    source_references=rev.source_references or [],
                    revision_feedback=rev.revision_feedback or [],
                )
            )

    all_revisions.sort(key=lambda r: r.revision_number)
    return all_revisions


@router.get(
    "",
    response_model=list[WorkflowDetailResponse],
    summary="List workflows filtered by status",
)
async def list_workflows(
    status_filter: str | None = Query(default=None, alias="status"),
    session: AsyncSession = Depends(get_db_session),
) -> list[WorkflowDetailResponse]:
    """List workflow runs with optional status filtering."""
    repo = WorkflowRepository(session)
    if status_filter:
        workflows = await repo.get_by_status(status_filter.upper())
    else:
        workflows = await repo.get_all()

    # Hydrate relationships
    results = []
    for wf in workflows:
        hydrated = await repo.get_with_relations(wf.id)
        if hydrated:
            results.append(_format_workflow_response(hydrated))
    return results
