"""FastAPI router endpoints for social media post scheduling and automation."""

import logging
from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db.session import get_db_session
from backend.app.scheduling.schemas import (
    CreateScheduleRequestSchema,
    ScheduleListResponseSchema,
    ScheduleResponseSchema,
    UpdateScheduleRequestSchema,
)
from backend.app.scheduling.service import SchedulingService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/schedules", tags=["Schedules"])


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


@router.post(
    "",
    response_model=ScheduleResponseSchema,
    status_code=status.HTTP_201_CREATED,
    summary="Schedule an approved workflow post for future publication",
)
async def create_schedule(
    payload: CreateScheduleRequestSchema,
    session: AsyncSession = Depends(get_db_session),
) -> ScheduleResponseSchema:
    """Register a new future publication schedule for an approved workflow."""
    service = SchedulingService()
    try:
        schedule = await service.create_schedule(
            workflow_id=payload.workflow_id,
            scheduled_at=payload.scheduled_at,
            timezone_name=payload.timezone,
            session=session,
            platform_override=payload.platform_override,
        )
        return _format_schedule_response(schedule)
    except ValueError as val_err:
        err_msg = str(val_err)
        if "not found" in err_msg.lower():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=err_msg)
        if "future" in err_msg.lower() or "timezone" in err_msg.lower():
            raise HTTPException(status_code=422, detail=err_msg)
        if "expected 'approved'" in err_msg.lower() or "already" in err_msg.lower():
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=err_msg)
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
    summary="List all schedules with optional filters",
)
async def list_schedules(
    workflow_id: str | None = Query(default=None, description="Filter by workflow run ID"),
    status_filter: str | None = Query(default=None, alias="status", description="Filter by status (SCHEDULED, RUNNING, COMPLETED, FAILED, CANCELLED)"),
    platform: str | None = Query(default=None, description="Filter by platform"),
    session: AsyncSession = Depends(get_db_session),
) -> ScheduleListResponseSchema:
    """Retrieve all schedules filtered by workflow ID, status, or platform."""
    service = SchedulingService()
    if workflow_id:
        schedules = await service.get_schedules_for_workflow(workflow_id, session)
        if status_filter:
            schedules = [s for s in schedules if s.status.upper() == status_filter.strip().upper()]
        if platform:
            schedules = [s for s in schedules if s.platform.lower() == platform.strip().lower()]
    else:
        schedules = await service.list_schedules(
            session=session,
            status_filter=status_filter,
            platform_filter=platform,
        )

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
    session: AsyncSession = Depends(get_db_session),
) -> ScheduleResponseSchema:
    """Fetch details of an individual schedule by its ID."""
    service = SchedulingService()
    sched = await service.get_schedule(schedule_id, session)
    if not sched:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Schedule '{schedule_id}' not found.",
        )
    return _format_schedule_response(sched)


@router.patch(
    "/{schedule_id}",
    response_model=ScheduleResponseSchema,
    summary="Update or reschedule an existing schedule",
)
async def update_schedule(
    schedule_id: str,
    payload: UpdateScheduleRequestSchema,
    session: AsyncSession = Depends(get_db_session),
) -> ScheduleResponseSchema:
    """Update the target execution timestamp or timezone of an existing schedule."""
    service = SchedulingService()
    try:
        updated = await service.update_schedule(
            schedule_id=schedule_id,
            session=session,
            scheduled_at=payload.scheduled_at,
            timezone_name=payload.timezone,
        )
        return _format_schedule_response(updated)
    except ValueError as val_err:
        err_msg = str(val_err)
        if "not found" in err_msg.lower():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=err_msg)
        if "future" in err_msg.lower() or "timezone" in err_msg.lower():
            raise HTTPException(status_code=422, detail=err_msg)
        if "completed" in err_msg.lower() or "running" in err_msg.lower():
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=err_msg)
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
    session: AsyncSession = Depends(get_db_session),
) -> ScheduleResponseSchema:
    """Cancel an active schedule prior to its execution."""
    service = SchedulingService()
    try:
        cancelled = await service.cancel_schedule(schedule_id, session)
        return _format_schedule_response(cancelled)
    except ValueError as val_err:
        err_msg = str(val_err)
        if "not found" in err_msg.lower():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=err_msg)
        if "completed" in err_msg.lower() or "running" in err_msg.lower():
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
    session: AsyncSession = Depends(get_db_session),
) -> ScheduleResponseSchema:
    """Trigger immediate publishing execution for a scheduled post."""
    service = SchedulingService()
    try:
        executed = await service.run_schedule_now(schedule_id, session)
        return _format_schedule_response(executed)
    except ValueError as val_err:
        err_msg = str(val_err)
        if "not found" in err_msg.lower():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=err_msg)
        if "already" in err_msg.lower() or "running" in err_msg.lower() or "completed" in err_msg.lower():
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=err_msg)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=err_msg)
    except Exception as err:
        logger.exception("Failed to run schedule '%s' immediately: %s", schedule_id, err)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error executing schedule: {err}",
        )
