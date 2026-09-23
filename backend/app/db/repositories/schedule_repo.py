"""Repository handling Schedule database persistence, queries, and atomic state updates."""

from datetime import datetime, timezone
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db.models.schedule import Schedule, ScheduleStatus
from backend.app.db.repositories.base import BaseRepository

logger = logging.getLogger(__name__)


class ScheduleRepository(BaseRepository[Schedule]):
    """Repository handling Schedule persistence, state queries, and atomic status transitions."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(Schedule, session)

    async def get_by_workflow_id(self, workflow_id: str) -> list[Schedule]:
        """Fetch all schedules created for a specific workflow run."""
        stmt = (
            select(Schedule)
            .where(Schedule.workflow_run_id == workflow_id)
            .order_by(Schedule.created_at.desc())
        )
        res = await self.session.execute(stmt)
        return list(res.scalars().all())

    async def get_by_workflow(self, workflow_id: str) -> list[Schedule]:
        """Alias for get_by_workflow_id."""
        return await self.get_by_workflow_id(workflow_id)

    async def get_active_by_workflow_id(self, workflow_id: str) -> Schedule | None:
        """Fetch the active (SCHEDULED or RUNNING) schedule for a workflow."""
        stmt = select(Schedule).where(
            Schedule.workflow_run_id == workflow_id,
            Schedule.status.in_([ScheduleStatus.SCHEDULED.value, ScheduleStatus.RUNNING.value]),
        )
        res = await self.session.execute(stmt)
        return res.scalar_one_or_none()

    async def get_active_by_workflow_and_platform(
        self,
        workflow_id: str,
        platform: str,
    ) -> Schedule | None:
        """Fetch an active (SCHEDULED or RUNNING) schedule for a workflow and platform."""
        stmt = select(Schedule).where(
            Schedule.workflow_run_id == workflow_id,
            Schedule.platform == platform.strip().lower(),
            Schedule.status.in_([ScheduleStatus.SCHEDULED.value, ScheduleStatus.RUNNING.value]),
        )
        res = await self.session.execute(stmt)
        return res.scalar_one_or_none()

    async def get_active_by_workflow_and_platform_for_update(
        self,
        workflow_id: str,
        platform: str,
    ) -> Schedule | None:
        """Fetch an active schedule with row-level locking (FOR UPDATE) where supported."""
        stmt = select(Schedule).where(
            Schedule.workflow_run_id == workflow_id,
            Schedule.platform == platform.strip().lower(),
            Schedule.status.in_([ScheduleStatus.SCHEDULED.value, ScheduleStatus.RUNNING.value]),
        )
        bind = self.session.get_bind()
        if bind is not None and getattr(bind.dialect, "name", "") != "sqlite":
            stmt = stmt.with_for_update()

        res = await self.session.execute(stmt)
        return res.scalar_one_or_none()

    async def get_by_job_id(self, job_id: str) -> Schedule | None:
        """Fetch schedule matching a unique scheduler job identifier."""
        stmt = select(Schedule).where(Schedule.job_id == job_id)
        res = await self.session.execute(stmt)
        return res.scalar_one_or_none()

    async def get_all_active_schedules(self) -> list[Schedule]:
        """Fetch all currently active SCHEDULED jobs across all workflows (used during restart recovery)."""
        stmt = (
            select(Schedule)
            .where(Schedule.status == ScheduleStatus.SCHEDULED.value)
            .order_by(Schedule.scheduled_at.asc())
        )
        res = await self.session.execute(stmt)
        return list(res.scalars().all())

    async def get_orphaned_running_schedules(self) -> list[Schedule]:
        """Fetch any schedule left in RUNNING state (e.g. from an abrupt process termination)."""
        stmt = select(Schedule).where(Schedule.status == ScheduleStatus.RUNNING.value)
        res = await self.session.execute(stmt)
        return list(res.scalars().all())

    async def update_status(
        self,
        schedule_id: str,
        status: str,
        last_error: str | None = None,
        executed_at: datetime | None = None,
    ) -> Schedule | None:
        """Update schedule lifecycle status and execution diagnostics."""
        sched = await self.get_by_id(schedule_id)
        if sched:
            sched.status = status
            if last_error is not None:
                sched.last_error = last_error
            if executed_at is not None:
                sched.executed_at = executed_at
            await self.session.flush()
        return sched

    async def record_execution_attempt(
        self,
        schedule_id: str,
    ) -> Schedule | None:
        """Increment execution attempt counter and transition status to RUNNING."""
        sched = await self.get_by_id(schedule_id)
        if sched:
            sched.attempt_count += 1
            sched.status = ScheduleStatus.RUNNING.value
            await self.session.flush()
        return sched
