"""Scheduling service handling business logic, validation, timezone conversions, and execution binding."""

from datetime import datetime, timezone
import logging
from typing import Any
import uuid
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.config import Settings, get_settings
from backend.app.db.models.schedule import Schedule, ScheduleStatus
from backend.app.db.repositories.publication_repo import PublicationRepository
from backend.app.db.repositories.schedule_repo import ScheduleRepository
from backend.app.db.repositories.workflow_repo import PostRepository, WorkflowRepository
from backend.app.publishing.base import PlatformRegistry
from backend.app.publishing.service import PublishingService, create_default_platform_registry
from backend.app.scheduling.manager import ScheduleManager, get_schedule_manager
from backend.app.scheduling.schemas import CreateScheduleRequestSchema, UpdateScheduleRequestSchema
from backend.app.workflows.state import WorkflowStatus

logger = logging.getLogger(__name__)


class SchedulingService:
    """Service orchestrating social media post scheduling, validation, and lifecycle management."""

    def __init__(
        self,
        schedule_manager: ScheduleManager | None = None,
        publishing_service: PublishingService | None = None,
        platform_registry: PlatformRegistry | None = None,
        settings: Settings | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.schedule_manager = schedule_manager or get_schedule_manager()
        self.publishing_service = publishing_service
        self.platform_registry = platform_registry or create_default_platform_registry()

    def _normalize_and_validate_time(
        self,
        dt_input: datetime,
        tz_name: str,
    ) -> tuple[datetime, str]:
        """Validate IANA timezone and convert input datetime to UTC, ensuring it is in the future."""
        clean_tz_str = (tz_name or "UTC").strip()
        try:
            user_tz = ZoneInfo(clean_tz_str)
        except (ZoneInfoNotFoundError, ValueError) as err:
            raise ValueError(f"Invalid IANA timezone name: '{clean_tz_str}'.") from err

        if dt_input.tzinfo is None:
            local_dt = dt_input.replace(tzinfo=user_tz)
        else:
            local_dt = dt_input.astimezone(user_tz)

        utc_dt = local_dt.astimezone(timezone.utc)
        now_utc = datetime.now(timezone.utc)

        if (utc_dt - now_utc).total_seconds() < 0:
            raise ValueError(
                f"Scheduled time cannot be in the past. "
                f"Provided: {utc_dt.isoformat()}, Current UTC: {now_utc.isoformat()}."
            )

        return utc_dt, clean_tz_str

    async def create_schedule(
        self,
        request: CreateScheduleRequestSchema | None = None,
        session: AsyncSession | None = None,
        *,
        workflow_id: str | None = None,
        scheduled_at: datetime | None = None,
        timezone_name: str | None = None,
        platform_override: str | None = None,
        **kwargs: Any,
    ) -> Schedule:
        """Validate and create a new future publishing schedule for an approved workflow."""
        # Support both object schema and kwargs
        if request is not None and isinstance(request, CreateScheduleRequestSchema):
            wf_id = request.workflow_id
            sch_dt = request.scheduled_at
            tz_str = request.timezone
            plat_override = request.platform_override
        else:
            wf_id = workflow_id or kwargs.get("workflow_id")
            sch_dt = scheduled_at or kwargs.get("scheduled_at")
            tz_str = timezone_name or kwargs.get("timezone", "UTC")
            plat_override = platform_override or kwargs.get("platform_override")

        sess = session or kwargs.get("session")
        if sess is None:
            raise ValueError("AsyncSession is required for create_schedule.")

        if not wf_id:
            raise ValueError("workflow_id is required.")
        if not sch_dt:
            raise ValueError("scheduled_at datetime is required.")

        workflow_repo = WorkflowRepository(sess)
        post_repo = PostRepository(sess)
        schedule_repo = ScheduleRepository(sess)
        pub_repo = PublicationRepository(sess)

        # 1. Validate & convert target timestamp to UTC
        scheduled_at_utc, valid_tz = self._normalize_and_validate_time(sch_dt, tz_str)

        # 2. Fetch workflow with row-level locking
        workflow = await workflow_repo.get_with_relations_for_update(wf_id)
        if not workflow:
            raise ValueError(f"Workflow '{wf_id}' not found.")

        # 3. Verify workflow is in APPROVED state
        if workflow.status == WorkflowStatus.PUBLISHED.value:
            raise ValueError(
                f"Cannot schedule workflow '{wf_id}': workflow is already PUBLISHED."
            )
        if workflow.status != WorkflowStatus.APPROVED.value:
            raise ValueError(
                f"Cannot schedule workflow '{wf_id}': workflow is not APPROVED (current status: '{workflow.status}')."
            )

        # 4. Resolve target post
        posts = workflow.posts or await post_repo.get_by_workflow(wf_id)
        if not posts:
            raise ValueError(f"No generated post found for workflow '{wf_id}'.")
        target_post = posts[0]

        # 5. Resolve effective target platform & verify support
        effective_platform = (
            plat_override or target_post.platform or workflow.target_platform or "linkedin"
        ).strip().lower()
        self.platform_registry.get(effective_platform)  # Raises ValueError if unsupported

        # 6. Verify post is not already PUBLISHED on this platform
        if workflow.status == WorkflowStatus.PUBLISHED.value:
            raise ValueError(
                f"Cannot schedule workflow '{wf_id}': post is already PUBLISHED on '{effective_platform}'."
            )
        existing_pub = await pub_repo.get_by_workflow_and_platform(
            workflow_id=workflow.id,
            platform=effective_platform,
        )
        if existing_pub and existing_pub.status == "PUBLISHED":
            raise ValueError(
                f"Cannot schedule workflow '{wf_id}': post is already PUBLISHED on '{effective_platform}'."
            )

        # 7. Check for existing active schedule
        existing_active = await schedule_repo.get_active_by_workflow_id(workflow.id)
        if existing_active:
            raise ValueError(
                f"Workflow '{wf_id}' already has an active schedule "
                f"(Schedule ID: '{existing_active.id}', Status: '{existing_active.status}')."
            )

        # 8. Create Schedule entity
        schedule_id = str(uuid.uuid4())
        job_id = f"job_sched_{schedule_id}"

        schedule = Schedule(
            id=schedule_id,
            workflow_run_id=workflow.id,
            post_id=target_post.id,
            platform=effective_platform,
            scheduled_at=scheduled_at_utc,
            timezone=valid_tz,
            status=ScheduleStatus.SCHEDULED.value,
            job_id=job_id,
            attempt_count=0,
        )
        await schedule_repo.create(schedule)
        await sess.commit()
        await sess.refresh(schedule)

        # 9. Register job in APScheduler
        self.schedule_manager.add_schedule_job(
            schedule_id=schedule.id,
            scheduled_at_utc=scheduled_at_utc,
            job_id=job_id,
        )

        logger.info(
            "Created and registered schedule '%s' for workflow '%s' on '%s' at %s UTC",
            schedule.id,
            workflow.id,
            effective_platform,
            scheduled_at_utc.isoformat(),
        )
        return schedule

    async def get_schedule(
        self,
        schedule_id: str,
        session: AsyncSession,
    ) -> Schedule | None:
        """Fetch schedule by its unique ID."""
        repo = ScheduleRepository(session)
        return await repo.get_by_id(schedule_id)

    async def get_schedules_for_workflow(
        self,
        workflow_id: str,
        session: AsyncSession,
    ) -> list[Schedule]:
        """Fetch all schedules associated with a given workflow run."""
        repo = ScheduleRepository(session)
        return await repo.get_by_workflow_id(workflow_id)

    async def list_schedules(
        self,
        session: AsyncSession,
        status_filter: str | None = None,
        platform_filter: str | None = None,
    ) -> list[Schedule]:
        """List schedules with optional status and platform filtering."""
        stmt = select(Schedule).order_by(Schedule.created_at.desc())

        if status_filter:
            stmt = stmt.where(Schedule.status == status_filter.strip().upper())
        if platform_filter:
            stmt = stmt.where(Schedule.platform == platform_filter.strip().lower())

        res = await session.execute(stmt)
        return list(res.scalars().all())

    async def update_schedule(
        self,
        schedule_id: str,
        request: UpdateScheduleRequestSchema | None = None,
        session: AsyncSession | None = None,
        *,
        scheduled_at: datetime | None = None,
        timezone_name: str | None = None,
        **kwargs: Any,
    ) -> Schedule:
        """Update or reschedule an existing schedule with a new future publication timestamp."""
        sess = session or kwargs.get("session")
        if sess is None:
            raise ValueError("AsyncSession is required for update_schedule.")

        if request is not None and isinstance(request, UpdateScheduleRequestSchema):
            sch_dt = request.scheduled_at
            tz_str = request.timezone
        else:
            sch_dt = scheduled_at or kwargs.get("scheduled_at")
            tz_str = timezone_name or kwargs.get("timezone")

        schedule_repo = ScheduleRepository(sess)
        sched = await schedule_repo.get_by_id(schedule_id)
        if not sched:
            raise ValueError(f"Schedule '{schedule_id}' not found.")

        if sched.status != ScheduleStatus.SCHEDULED.value:
            raise ValueError(f"Cannot update/reschedule Schedule '{schedule_id}' in state '{sched.status}'.")

        target_dt = sch_dt or sched.scheduled_at
        target_tz = tz_str or sched.timezone
        new_utc, new_tz = self._normalize_and_validate_time(target_dt, target_tz)

        sched.scheduled_at = new_utc
        sched.timezone = new_tz
        sched.status = ScheduleStatus.SCHEDULED.value
        sched.last_error = None
        await sess.commit()
        await sess.refresh(sched)

        # Update in-memory scheduler job
        self.schedule_manager.reschedule_job(
            schedule_id=sched.id,
            job_id=sched.job_id,
            new_scheduled_at_utc=new_utc,
        )

        logger.info("Rescheduled schedule '%s' to %s UTC (%s)", sched.id, new_utc.isoformat(), new_tz)
        return sched

    async def cancel_schedule(
        self,
        schedule_id: str,
        session: AsyncSession,
    ) -> Schedule:
        """Cancel an active scheduled post."""
        schedule_repo = ScheduleRepository(session)
        sched = await schedule_repo.get_by_id(schedule_id)
        if not sched:
            raise ValueError(f"Schedule '{schedule_id}' not found.")

        if sched.status != ScheduleStatus.SCHEDULED.value:
            raise ValueError(f"Cannot cancel schedule in state '{sched.status}'.")

        sched.status = ScheduleStatus.CANCELLED.value
        await session.commit()
        await session.refresh(sched)

        # Remove from scheduler
        self.schedule_manager.remove_schedule_job(sched.job_id)
        logger.info("Cancelled schedule '%s'", sched.id)
        return sched

    async def run_schedule_now(
        self,
        schedule_id: str,
        session: AsyncSession,
    ) -> Schedule:
        """Immediately trigger execution of a scheduled post."""
        schedule_repo = ScheduleRepository(session)
        sched = await schedule_repo.get_by_id(schedule_id)
        if not sched:
            raise ValueError(f"Schedule '{schedule_id}' not found.")

        if sched.status == ScheduleStatus.COMPLETED.value:
            raise ValueError(f"Schedule '{schedule_id}' is already COMPLETED.")
        if sched.status == ScheduleStatus.RUNNING.value:
            raise ValueError(f"Schedule '{schedule_id}' is already actively RUNNING.")

        # Remove future timer trigger from scheduler if present
        self.schedule_manager.remove_schedule_job(sched.job_id)

        # Execute scheduled job logic through the single execution pipeline
        await self.schedule_manager.execute_scheduled_job(sched.id)
        await session.refresh(sched)
        return sched
