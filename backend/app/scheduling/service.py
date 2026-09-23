"""Scheduling service handling business logic, validation, timezone conversions, and execution binding."""

from datetime import datetime, timezone
import logging
from typing import Any
import uuid
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.config import Settings, get_settings
from backend.app.db.models.schedule import Schedule
from backend.app.db.repositories.publication_repo import PublicationRepository
from backend.app.db.repositories.schedule_repo import ScheduleRepository
from backend.app.db.repositories.workflow_repo import PostRepository, WorkflowRepository
from backend.app.publishing.base import PlatformRegistry
from backend.app.publishing.service import create_default_platform_registry
from backend.app.scheduling.manager import ScheduleManager, execute_scheduled_job, get_schedule_manager
from backend.app.workflows.state import WorkflowStatus

logger = logging.getLogger(__name__)


class SchedulingService:
    """Service orchestrating social media post scheduling, validation, and lifecycle management."""

    def __init__(
        self,
        schedule_manager: ScheduleManager | None = None,
        platform_registry: PlatformRegistry | None = None,
        settings: Settings | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.schedule_manager = schedule_manager or get_schedule_manager()
        self.platform_registry = platform_registry or create_default_platform_registry()

    def _normalize_and_validate_time(
        self,
        dt_input: datetime,
        tz_name: str,
    ) -> tuple[datetime, str]:
        """Validate IANA timezone and convert input datetime to UTC, ensuring it is in the future."""
        clean_tz_str = tz_name.strip()
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

        if (utc_dt - now_utc).total_seconds() < 15:
            raise ValueError(
                f"Scheduled time must be in the future (at least 15 seconds from now). "
                f"Provided: {utc_dt.isoformat()}, Current UTC: {now_utc.isoformat()}."
            )

        return utc_dt, clean_tz_str

    async def create_schedule(
        self,
        workflow_id: str,
        scheduled_at: datetime,
        timezone_name: str,
        session: AsyncSession,
        platform_override: str | None = None,
    ) -> Schedule:
        """Validate and create a new future publishing schedule for an approved workflow."""
        workflow_repo = WorkflowRepository(session)
        post_repo = PostRepository(session)
        schedule_repo = ScheduleRepository(session)
        pub_repo = PublicationRepository(session)

        # 1. Validate & convert target timestamp to UTC
        scheduled_at_utc, valid_tz = self._normalize_and_validate_time(scheduled_at, timezone_name)

        # 2. Fetch workflow with row-level locking
        workflow = await workflow_repo.get_with_relations_for_update(workflow_id)
        if not workflow:
            raise ValueError(f"Workflow '{workflow_id}' not found.")

        # 3. Verify workflow is in APPROVED state
        if workflow.status != WorkflowStatus.APPROVED.value:
            raise ValueError(
                f"Cannot schedule workflow '{workflow_id}': status is '{workflow.status}', "
                f"expected '{WorkflowStatus.APPROVED.value}'."
            )

        # 4. Resolve target post
        posts = workflow.posts or await post_repo.get_by_workflow(workflow_id)
        if not posts:
            raise ValueError(f"No generated post found for workflow '{workflow_id}'.")
        target_post = posts[0]

        # 5. Resolve effective target platform & verify support
        effective_platform = (
            platform_override or target_post.platform or workflow.target_platform or "linkedin"
        ).strip().lower()
        self.platform_registry.get(effective_platform)  # Raises ValueError if unsupported

        # 6. Verify post is not already PUBLISHED on this platform
        existing_pub = await pub_repo.get_by_workflow_and_platform(
            workflow_id=workflow.id,
            platform=effective_platform,
        )
        if existing_pub and existing_pub.status == "PUBLISHED":
            raise ValueError(
                f"Cannot schedule workflow '{workflow_id}': post is already PUBLISHED on '{effective_platform}'."
            )

        # 7. Check for existing active schedule
        existing_active = await schedule_repo.get_active_by_workflow_and_platform(
            workflow_id=workflow.id,
            platform=effective_platform,
        )
        if existing_active:
            raise ValueError(
                f"An active schedule already exists for workflow '{workflow_id}' on platform '{effective_platform}' "
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
            status="SCHEDULED",
            job_id=job_id,
            attempt_count=0,
        )
        await schedule_repo.create(schedule)
        await session.commit()
        await session.refresh(schedule)

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
        return await repo.get_by_workflow(workflow_id)

    async def list_schedules(
        self,
        session: AsyncSession,
        status_filter: str | None = None,
        platform_filter: str | None = None,
    ) -> list[Schedule]:
        """List schedules with optional status and platform filtering."""
        repo = ScheduleRepository(session)
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
        session: AsyncSession,
        scheduled_at: datetime | None = None,
        timezone_name: str | None = None,
    ) -> Schedule:
        """Update or reschedule an existing schedule with a new future publication timestamp."""
        schedule_repo = ScheduleRepository(session)
        sched = await schedule_repo.get_by_id(schedule_id)
        if not sched:
            raise ValueError(f"Schedule '{schedule_id}' not found.")

        if sched.status == "COMPLETED":
            raise ValueError(f"Cannot update Schedule '{schedule_id}': status is already COMPLETED.")
        if sched.status == "RUNNING":
            raise ValueError(f"Cannot update Schedule '{schedule_id}': schedule is actively RUNNING.")

        # Determine target datetime and timezone
        target_dt = scheduled_at or sched.scheduled_at
        target_tz = timezone_name or sched.timezone
        new_utc, new_tz = self._normalize_and_validate_time(target_dt, target_tz)

        sched.scheduled_at = new_utc
        sched.timezone = new_tz
        sched.status = "SCHEDULED"
        sched.last_error = None
        await session.commit()
        await session.refresh(sched)

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

        if sched.status == "COMPLETED":
            raise ValueError(f"Cannot cancel Schedule '{schedule_id}': status is already COMPLETED.")
        if sched.status == "RUNNING":
            raise ValueError(f"Cannot cancel Schedule '{schedule_id}': schedule is actively RUNNING.")

        sched.status = "CANCELLED"
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

        if sched.status == "COMPLETED":
            raise ValueError(f"Schedule '{schedule_id}' is already COMPLETED.")
        if sched.status == "RUNNING":
            raise ValueError(f"Schedule '{schedule_id}' is already actively RUNNING.")

        # Remove future timer trigger from scheduler if present
        self.schedule_manager.remove_schedule_job(sched.job_id)

        # Execute scheduled job logic
        await execute_scheduled_job(sched.id)
        await session.refresh(sched)
        return sched
