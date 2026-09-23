"""SQLAlchemy ORM model for Schedule entity and automation job tracking."""

from datetime import datetime, timezone
from enum import Enum
from typing import TYPE_CHECKING, Any
import uuid

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, func, text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import TypeDecorator

from backend.app.db.session import Base

if TYPE_CHECKING:
    from backend.app.db.models.post import Post
    from backend.app.db.models.workflow import WorkflowRun


class UTCDateTime(TypeDecorator):
    """DateTime type ensuring timezone-aware UTC datetimes across all DB engines including SQLite."""

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_result_value(self, value: Any, dialect: Any) -> Any:
        if value is not None and isinstance(value, datetime) and value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value


class ScheduleStatus(str, Enum):
    """Lifecycle statuses for a scheduled publishing job."""

    SCHEDULED = "SCHEDULED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class Schedule(Base):
    """Represents a scheduled automation job for an approved social media post."""

    __tablename__ = "schedules"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    workflow_run_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("workflow_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    post_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("posts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    platform: Mapped[str] = mapped_column(String(50), nullable=False)
    scheduled_at: Mapped[datetime] = mapped_column(
        UTCDateTime,
        nullable=False,
        index=True,
    )  # Normalized & stored in UTC
    timezone: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        default="UTC",
    )  # Original user IANA timezone (e.g. 'Asia/Karachi', 'America/New_York')
    status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default=ScheduleStatus.SCHEDULED.value,
        index=True,
    )  # SCHEDULED, RUNNING, COMPLETED, FAILED, CANCELLED
    job_id: Mapped[str] = mapped_column(
        String(128),
        unique=True,
        nullable=False,
        index=True,
    )  # Deterministic scheduler job identifier: job_sched_{schedule_id}
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    executed_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime,
        server_default=func.now(),
        nullable=False,
        index=True,
    )
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime,
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Relationships
    workflow_run: Mapped["WorkflowRun"] = relationship(back_populates="schedules")
    post: Mapped["Post"] = relationship(back_populates="schedules")

    __table_args__ = (
        Index(
            "uq_active_workflow_schedule",
            "workflow_run_id",
            unique=True,
            postgresql_where=text("status IN ('SCHEDULED', 'RUNNING')"),
            sqlite_where=text("status IN ('SCHEDULED', 'RUNNING')"),
        ),
    )
