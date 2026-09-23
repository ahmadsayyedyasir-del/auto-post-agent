"""APScheduler manager handling in-memory async job scheduling and restart recovery."""

import asyncio
from datetime import datetime, timezone
from enum import Enum
import logging
from typing import Any

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.date import DateTrigger
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.config import Settings, get_settings
from backend.app.db.models.schedule import Schedule, ScheduleStatus
from backend.app.db.repositories.schedule_repo import ScheduleRepository
from backend.app.db.repositories.workflow_repo import WorkflowRepository
from backend.app.db.session import get_session_factory
from backend.app.publishing.service import PublishingService
from backend.app.workflows.state import WorkflowStatus

logger = logging.getLogger(__name__)

_global_schedule_manager: "ScheduleManager | None" = None


async def execute_scheduled_job(schedule_id: str) -> None:
    """Module-level trigger callback executed by APScheduler when a scheduled job fires."""
    manager = get_schedule_manager()
    await manager.execute_scheduled_job(schedule_id)


class ScheduleManager:
    """Manages APScheduler AsyncIOScheduler instance, job registration, and startup recovery."""

    def __init__(
        self,
        scheduler: AsyncIOScheduler | None = None,
        session_factory: Any = None,
        publishing_service: PublishingService | None = None,
        settings: Settings | None = None,
    ) -> None:
        self.scheduler = scheduler or AsyncIOScheduler(timezone="UTC")
        self._session_factory = session_factory
        self._publishing_service = publishing_service
        self.settings = settings or get_settings()

    @property
    def session_factory(self) -> Any:
        """Return the active session factory or lazily retrieve the application's session factory."""
        if self._session_factory is not None:
            return self._session_factory
        return get_session_factory()

    @property
    def publishing_service(self) -> PublishingService:
        """Return the injected publishing service or lazily instantiate one."""
        if self._publishing_service is not None:
            return self._publishing_service
        return PublishingService()

    def start(self) -> None:
        """Start the background scheduler if not already running."""
        if not self.scheduler.running:
            self.scheduler.start()
            logger.info("APScheduler AsyncIOScheduler started successfully.")

    def shutdown(self, wait: bool = False) -> None:
        """Shut down the background scheduler."""
        if self.scheduler.running:
            self.scheduler.shutdown(wait=wait)
            logger.info("APScheduler AsyncIOScheduler shut down.")

    @property
    def is_running(self) -> bool:
        """Return True if the scheduler is active."""
        return self.scheduler.running

    def add_schedule_job(
        self,
        schedule_id: str,
        scheduled_at_utc: datetime,
        job_id: str,
    ) -> None:
        """Register or replace a one-time job in APScheduler at the specified UTC datetime."""
        run_dt = scheduled_at_utc
        if run_dt.tzinfo is None:
            run_dt = run_dt.replace(tzinfo=timezone.utc)
        else:
            run_dt = run_dt.astimezone(timezone.utc)

        trigger = DateTrigger(run_date=run_dt, timezone="UTC")
        self.scheduler.add_job(
            func=execute_scheduled_job,
            trigger=trigger,
            args=[schedule_id],
            id=job_id,
            replace_existing=True,
            misfire_grace_time=self.settings.scheduler_misfire_grace_time_seconds,
        )
        logger.info(
            "Registered scheduled job '%s' for schedule '%s' at %s UTC",
            job_id,
            schedule_id,
            run_dt.isoformat(),
        )

    def get_job(self, job_id: str) -> Any:
        """Retrieve a job by its unique identifier from the scheduler."""
        return self.scheduler.get_job(job_id)

    def remove_schedule_job(self, job_id: str) -> bool:
        """Remove a job from the scheduler if registered."""
        job = self.scheduler.get_job(job_id)
        if job:
            self.scheduler.remove_job(job_id)
            logger.info("Removed scheduled job '%s' from scheduler.", job_id)
            return True
        return False

    def reschedule_job(
        self,
        schedule_id: str,
        job_id: str,
        new_scheduled_at_utc: datetime,
    ) -> None:
        """Update the trigger datetime of an existing job."""
        self.remove_schedule_job(job_id)
        self.add_schedule_job(
            schedule_id=schedule_id,
            scheduled_at_utc=new_scheduled_at_utc,
            job_id=job_id,
        )

    async def execute_scheduled_job(self, schedule_id: str) -> None:
        """Execute a scheduled job: validate schedule state, check approval, call PublishingService."""
        logger.info("Executing scheduled job for schedule '%s'", schedule_id)
        session_factory = self.session_factory
        publishing_service = self.publishing_service

        async with session_factory() as session:
            schedule_repo = ScheduleRepository(session)
            workflow_repo = WorkflowRepository(session)

            # 1. Fetch schedule and verify status
            sched = await schedule_repo.get_by_id(schedule_id)
            if not sched:
                logger.warning("Scheduled job execution aborted: Schedule '%s' not found.", schedule_id)
                return

            if sched.status != ScheduleStatus.SCHEDULED.value:
                logger.warning(
                    "Scheduled job execution skipped: Schedule '%s' is in '%s' status (expected 'SCHEDULED').",
                    schedule_id,
                    sched.status,
                )
                return

            # 2. Transition status to RUNNING
            await schedule_repo.record_execution_attempt(sched.id)
            await session.commit()
            await session.refresh(sched)

            # 3. Verify workflow is still in APPROVED status at execution time
            workflow = await workflow_repo.get_by_id(sched.workflow_run_id)
            if not workflow or workflow.status != WorkflowStatus.APPROVED.value:
                wf_status = getattr(workflow, "status", "NOT_FOUND")
                err_msg = (
                    f"Execution aborted: workflow '{sched.workflow_run_id}' is not in APPROVED status "
                    f"at execution time (current status: '{wf_status}')."
                )
                logger.error("Schedule '%s' failed: %s", sched.id, err_msg)
                await schedule_repo.update_status(
                    schedule_id=sched.id,
                    status=ScheduleStatus.FAILED.value,
                    last_error=err_msg,
                    executed_at=datetime.now(timezone.utc),
                )
                await session.commit()
                return

            # 4. Invoke PublishingService
            try:
                publication = await publishing_service.publish_workflow_post(
                    workflow_id=sched.workflow_run_id,
                    session=session,
                    platform_override=sched.platform,
                )

                if publication.status == "PUBLISHED":
                    logger.info(
                        "Schedule '%s' successfully published. Publication ID: '%s', External Post ID: '%s'",
                        sched.id,
                        publication.id,
                        publication.external_post_id,
                    )
                    await schedule_repo.update_status(
                        schedule_id=sched.id,
                        status=ScheduleStatus.COMPLETED.value,
                        last_error=None,
                        executed_at=publication.published_at or datetime.now(timezone.utc),
                    )
                else:
                    err_msg = publication.error_message or "Platform publication failed."
                    logger.error("Schedule '%s' publication failed: %s", sched.id, err_msg)
                    await schedule_repo.update_status(
                        schedule_id=sched.id,
                        status=ScheduleStatus.FAILED.value,
                        last_error=err_msg,
                        executed_at=datetime.now(timezone.utc),
                    )
                await session.commit()

            except Exception as err:
                logger.exception("Schedule '%s' encountered an unexpected execution error: %s", sched.id, err)
                await schedule_repo.update_status(
                    schedule_id=sched.id,
                    status=ScheduleStatus.FAILED.value,
                    last_error=str(err),
                    executed_at=datetime.now(timezone.utc),
                )
                await session.commit()

    async def recover_schedules(self, session: AsyncSession | None = None) -> int:
        """Recover and re-register active schedules from database upon application startup."""
        if session is not None:
            return await self._recover_schedules_with_session(session)
        async with self.session_factory() as sess:
            return await self._recover_schedules_with_session(sess)

    async def _recover_schedules_with_session(self, session: AsyncSession) -> int:
        """Internal helper for schedule recovery logic."""
        schedule_repo = ScheduleRepository(session)
        now_utc = datetime.now(timezone.utc)
        recovered_count = 0

        # 1. Handle orphaned RUNNING schedules from prior abrupt crash
        orphaned = await schedule_repo.get_orphaned_running_schedules()
        for s in orphaned:
            logger.warning(
                "Marking orphaned RUNNING schedule '%s' as FAILED on startup recovery.",
                s.id,
            )
            await schedule_repo.update_status(
                schedule_id=s.id,
                status=ScheduleStatus.FAILED.value,
                last_error="Orphaned running schedule on startup recovery: application terminated while in RUNNING state.",
                executed_at=now_utc,
            )
        if orphaned:
            await session.commit()

        # 2. Re-register active SCHEDULED records
        active_schedules = await schedule_repo.get_all_active_schedules()
        for sched in active_schedules:
            sched_dt = sched.scheduled_at
            if sched_dt.tzinfo is None:
                sched_dt = sched_dt.replace(tzinfo=timezone.utc)
            else:
                sched_dt = sched_dt.astimezone(timezone.utc)

            # Check if job is still in the future or within misfire grace window
            if sched_dt > now_utc:
                self.add_schedule_job(
                    schedule_id=sched.id,
                    scheduled_at_utc=sched_dt,
                    job_id=sched.job_id,
                )
                recovered_count += 1
            else:
                # Overdue job: check misfire grace window
                elapsed_seconds = (now_utc - sched_dt).total_seconds()
                if elapsed_seconds <= self.settings.scheduler_misfire_grace_time_seconds:
                    logger.info(
                        "Recovering overdue schedule '%s' (missed %ds ago) by dispatching immediately.",
                        sched.id,
                        int(elapsed_seconds),
                    )
                    asyncio.create_task(self.execute_scheduled_job(sched.id))
                    recovered_count += 1
                else:
                    logger.warning(
                        "Schedule '%s' missed execution window (%ds elapsed). Marking as FAILED.",
                        sched.id,
                        int(elapsed_seconds),
                    )
                    await schedule_repo.update_status(
                        schedule_id=sched.id,
                        status=ScheduleStatus.FAILED.value,
                        last_error=f"Overdue scheduled execution time elapsed while application was offline ({int(elapsed_seconds)}s overdue).",
                        executed_at=now_utc,
                    )

        if active_schedules:
            await session.commit()

        return recovered_count


def get_schedule_manager() -> ScheduleManager:
    """Return the singleton ScheduleManager instance."""
    global _global_schedule_manager
    if _global_schedule_manager is None:
        _global_schedule_manager = ScheduleManager()
    return _global_schedule_manager


def set_schedule_manager(manager: ScheduleManager | None) -> None:
    """Override singleton ScheduleManager instance (primarily for testing)."""
    global _global_schedule_manager
    _global_schedule_manager = manager
