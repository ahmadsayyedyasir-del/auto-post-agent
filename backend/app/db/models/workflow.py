"""SQLAlchemy ORM model for WorkflowRun."""

from datetime import datetime
from typing import TYPE_CHECKING, Any
import uuid

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.db.session import Base

if TYPE_CHECKING:
    from backend.app.db.models.feedback import Feedback
    from backend.app.db.models.post import Post, Revision
    from backend.app.db.models.publication import Publication
    from backend.app.db.models.schedule import Schedule
    from backend.app.db.models.user import User


class WorkflowRun(Base):
    """Represents a complete social media workflow execution lifecycle."""

    __tablename__ = "workflow_runs"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    # Phase 12: nullable for backward compatibility with legacy workflow records
    user_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    niche: Mapped[str] = mapped_column(String(255), nullable=False)
    target_platform: Mapped[str] = mapped_column(String(50), nullable=False, default="linkedin")
    audience: Mapped[str | None] = mapped_column(String(255), nullable=True)
    language: Mapped[str] = mapped_column(String(50), nullable=False, default="English")
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="STARTING", index=True)
    current_stage: Mapped[str | None] = mapped_column(String(50), nullable=True)
    revision_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    agent_revision_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    human_revision_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    human_rejection_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_human_rejections: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    max_revisions: Mapped[int] = mapped_column(Integer, nullable=False, default=2)
    research_data: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    content_plan: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

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
    posts: Mapped[list["Post"]] = relationship(
        back_populates="workflow_run",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    revisions: Mapped[list["Revision"]] = relationship(
        back_populates="workflow_run",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    feedbacks: Mapped[list["Feedback"]] = relationship(
        back_populates="workflow_run",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    publications: Mapped[list["Publication"]] = relationship(
        back_populates="workflow_run",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    schedules: Mapped[list["Schedule"]] = relationship(
        back_populates="workflow_run",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    # Phase 12: owner reference (nullable)
    user: Mapped["User | None"] = relationship(back_populates="workflow_runs")
