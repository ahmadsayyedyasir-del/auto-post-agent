"""SQLAlchemy ORM model for Schedule entity and automation job tracking."""

from datetime import datetime
from typing import TYPE_CHECKING
import uuid

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.db.session import Base

if TYPE_CHECKING:
    from backend.app.db.models.post import Post
    from backend.app.db.models.workflow import WorkflowRun


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
        DateTime(timezone=True),
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
        default="SCHEDULED",
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
    executed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Relationships
    workflow_run: Mapped["WorkflowRun"] = relationship(back_populates="schedules")
    post: Mapped["Post"] = relationship(back_populates="schedules")
