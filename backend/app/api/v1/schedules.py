"""FastAPI router endpoints for social media post scheduling and automation.

Phase 12: All endpoints require authentication. Schedules are owned by users via
the workflow relationship. Returns 404 for resources belonging to other users.
"""

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.api.v1.dependencies import get_current_active_user
from backend.app.db.models.user import User
from backend.app.db.repositories.workflow_repo import WorkflowRepository
from backend.app.db.session import get_db_session
from backend.app.scheduling.manager import get_schedule_manager
from backend.app.scheduling.schemas import (
    CreateScheduleRequestSchema,
    ScheduleListResponseSchema,
    ScheduleResponseSchema,
    UpdateScheduleRequestSchema,
)
from backend.app.scheduling.service import SchedulingService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/schedules", tags=["Schedules"])


def _get_scheduling_service(request: Request) -> SchedulingService:
    """Instantiate SchedulingService with the manager attached to app state or singleton."""
    manager = getattr(request.app.state, "schedule_manager", None) or get_schedule_manager()
    return SchedulingService(schedule_manager=manager)


def _format_schedule_response(sched: Any) -> ScheduleResponseSchema:
    """Convert ORM Schedule to response schema."""
    return ScheduleResponseSchema(
        id=sched.id,
        workflow_run_id=sched.workflow_run_id,
        post_id=sched.post_id,
        platform=sched.platform,
        scheduled_at=sched.scheduled_at,
        timezone=sched.timezone,
        status=sched.status,
        job_id=sched.job_id,
        attempt_count=sched.attempt_count,
        last_error=sched.last_error,
        executed_at=sched.executed_at,
        created_at=sched.created_at,
        updated_at=sched.updated_at,
    )


async def _check_schedule_ownership(
    workflow_id: str,
    current_user: User,
    session: AsyncSession,
) -> None:
    """Verify ownership of a schedule's parent workflow. Raises 404 for mismatches."""
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
            detail=f"Schedule resource not found.",
        )


@router.post(
    "",
    response_model=ScheduleResponseSchema,
    status_code=status.HTTP_201_CREATED,
    summary="Schedule an approved workflow post for future publication",
)
async def create_schedule(
    payload: CreateScheduleRequestSchema,
    request: Request,
    current_user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_db_session),
) -> ScheduleResponseSchema:
    """Register a new future publication schedule for an approved workflow."""
    await _check_schedule_ownership(payload.workflow_id, current_user, session)
    service = _get_scheduling_service(request)
    try:
        schedule = await service.create_schedule(
            request=payload,
            session=session,
        )
        return _format_schedule_response(schedule)
    except ValueError as val_err:
        err_msg = str(val_err)
        err_lower = err_msg.lower()
        if "not found" in err_lower:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=err_msg)
        if "not approved" in err_lower or "expected 'approved'" in err_lower:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=err_msg)
        if "already" in err_lower or "conflict" in err_lower:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=err_msg)
        if "past" in err_lower or "timezone" in err_lower:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=err_msg)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=err_msg)
    except Exception as err:
        logger.exception("Failed to create schedule for workflow '%s': %s", payload.workflow_id, err)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Scheduling execution error: {err}",
        )


@router.get(
    "",
    response_model=ScheduleListResponseSchema,
    summary="List all schedules with optional filters (scoped to authenticated user)",
)
async def list_schedules(
    request: Request,
    workflow_id: str | None = Query(default=None, description="Filter by workflow run ID"),
    status_filter: str | None = Query(default=None, alias="status", description="Filter by status (SCHEDULED, RUNNING, COMPLETED, FAILED, CANCELLED)"),
    platform: str | None = Query(default=None, description="Filter by platform"),
    current_user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_db_session),
) -> ScheduleListResponseSchema:
    """Retrieve all schedules filtered by workflow ID, status, or platform.

    Phase 12: Returns only schedules for workflows owned by the authenticated user
    (or legacy workflows with no owner).
    """
    if workflow_id:
        await _check_schedule_ownership(workflow_id, current_user, session)
        service = _get_scheduling_service(request)
        schedules = await service.get_schedules_for_workflow(workflow_id, session)
        if status_filter:
            schedules = [s for s in schedules if s.status.upper() == status_filter.strip().upper()]
        if platform:
            schedules = [s for s in schedules if s.platform.lower() == platform.strip().lower()]
    else:
        # Scope to current user's workflows only
        from sqlalchemy import or_, select
        from backend.app.db.models.schedule import Schedule
        from backend.app.db.models.workflow import WorkflowRun

        stmt = (
            select(Schedule)
            .join(WorkflowRun, Schedule.workflow_run_id == WorkflowRun.id)
            .where(
                or_(
                    WorkflowRun.user_id == current_user.id,
                    WorkflowRun.user_id == None,  # noqa: E711
                )
            )
            .order_by(Schedule.created_at.desc())
        )
        if status_filter:
            stmt = stmt.where(Schedule.status == status_filter.strip().upper())
        if platform:
            stmt = stmt.where(Schedule.platform == platform.strip().lower())

        result = await session.execute(stmt)
        schedules = list(result.scalars().all())

    formatted = [_format_schedule_response(s) for s in schedules]
    return ScheduleListResponseSchema(
        schedules=formatted,
        total=len(formatted),
    )


@router.get(
    "/{schedule_id}",
    response_model=ScheduleResponseSchema,
    summary="Retrieve details of a specific schedule",
)
async def get_schedule(
    schedule_id: str,
    request: Request,
    current_user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_db_session),
) -> ScheduleResponseSchema:
    """Fetch details of an individual schedule by its ID."""
    service = _get_scheduling_service(request)
    sched = await service.get_schedule(schedule_id, session)
    if not sched:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Schedule '{schedule_id}' not found.",
        )
    await _check_schedule_ownership(sched.workflow_run_id, current_user, session)
    return _format_schedule_response(sched)


@router.patch(
    "/{schedule_id}",
    response_model=ScheduleResponseSchema,
    summary="Update or reschedule an existing schedule",
)
async def update_schedule(
    schedule_id: str,
    payload: UpdateScheduleRequestSchema,
    request: Request,
    current_user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_db_session),
) -> ScheduleResponseSchema:
    """Update the target execution timestamp or timezone of an existing schedule."""
    service = _get_scheduling_service(request)
    # Ownership check
    sched = await service.get_schedule(schedule_id, session)
    if not sched:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Schedule '{schedule_id}' not found.",
        )
    await _check_schedule_ownership(sched.workflow_run_id, current_user, session)

    try:
        updated = await service.update_schedule(
            schedule_id=schedule_id,
            request=payload,
            session=session,
        )
        return _format_schedule_response(updated)
    except ValueError as val_err:
        err_msg = str(val_err)
        err_lower = err_msg.lower()
        if "not found" in err_lower:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=err_msg)
        if "completed" in err_lower or "running" in err_lower:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=err_msg)
        if "past" in err_lower or "timezone" in err_lower or "cannot" in err_lower:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=err_msg)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=err_msg)
    except Exception as err:
        logger.exception("Failed to update schedule '%s': %s", schedule_id, err)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error updating schedule: {err}",
        )


@router.delete(
    "/{schedule_id}",
    response_model=ScheduleResponseSchema,
    summary="Cancel an active schedule",
)
async def cancel_schedule(
    schedule_id: str,
    request: Request,
    current_user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_db_session),
) -> ScheduleResponseSchema:
    """Cancel an active schedule prior to its execution."""
    service = _get_scheduling_service(request)
    sched = await service.get_schedule(schedule_id, session)
    if not sched:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Schedule '{schedule_id}' not found.",
        )
    await _check_schedule_ownership(sched.workflow_run_id, current_user, session)

    try:
        cancelled = await service.cancel_schedule(schedule_id, session)
        return _format_schedule_response(cancelled)
    except ValueError as val_err:
        err_msg = str(val_err)
        err_lower = err_msg.lower()
        if "not found" in err_lower:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=err_msg)
        if "completed" in err_lower or "running" in err_lower:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=err_msg)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=err_msg)
    except Exception as err:
        logger.exception("Failed to cancel schedule '%s': %s", schedule_id, err)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error cancelling schedule: {err}",
        )


@router.post(
    "/{schedule_id}/run",
    response_model=ScheduleResponseSchema,
    summary="Manually trigger immediate execution of a schedule",
)
async def run_schedule_now(
    schedule_id: str,
    request: Request,
    current_user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_db_session),
) -> ScheduleResponseSchema:
    """Trigger immediate publishing execution for a scheduled post."""
    service = _get_scheduling_service(request)
    sched = await service.get_schedule(schedule_id, session)
    if not sched:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Schedule '{schedule_id}' not found.",
        )
    await _check_schedule_ownership(sched.workflow_run_id, current_user, session)

    try:
        executed = await service.run_schedule_now(schedule_id, session)
        return _format_schedule_response(executed)
    except ValueError as val_err:
        err_msg = str(val_err)
        err_lower = err_msg.lower()
        if "not found" in err_lower:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=err_msg)
        if "already" in err_lower or "running" in err_lower or "completed" in err_lower:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=err_msg)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=err_msg)
    except Exception as err:
        logger.exception("Failed to run schedule '%s' immediately: %s", schedule_id, err)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error executing schedule: {err}",
        )
