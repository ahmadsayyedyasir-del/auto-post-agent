"""SQLAlchemy ORM models for Post and Revision."""

from datetime import datetime
from typing import TYPE_CHECKING
import uuid

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.db.session import Base

if TYPE_CHECKING:
    from backend.app.db.models.feedback import Feedback
    from backend.app.db.models.publication import Publication
    from backend.app.db.models.schedule import Schedule
    from backend.app.db.models.workflow import WorkflowRun


class Post(Base):
    """Represents the active or published social media post for a given platform."""

    __tablename__ = "posts"

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
    platform: Mapped[str] = mapped_column(String(50), nullable=False)
    topic: Mapped[str] = mapped_column(String(255), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="DRAFT", index=True)
    content_type: Mapped[str] = mapped_column(String(50), nullable=False, default="single_post")
    language: Mapped[str] = mapped_column(String(50), nullable=False, default="English")
    hashtags: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    cta: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_references: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Relationships
    workflow_run: Mapped["WorkflowRun"] = relationship(back_populates="posts")
    revisions: Mapped[list["Revision"]] = relationship(
        back_populates="post",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="Revision.revision_number",
    )
    feedbacks: Mapped[list["Feedback"]] = relationship(
        back_populates="post",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    publications: Mapped[list["Publication"]] = relationship(
        back_populates="post",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    schedules: Mapped[list["Schedule"]] = relationship(
        back_populates="post",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class Revision(Base):
    """Historical snapshot of a post version generated during revision cycles."""

    __tablename__ = "revisions"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    post_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("posts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    workflow_run_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("workflow_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    revision_number: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    revision_source: Mapped[str] = mapped_column(String(50), nullable=False, default="AGENT")
    content: Mapped[str] = mapped_column(Text, nullable=False)
    hashtags: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    cta: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_references: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    revision_feedback: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )

    # Relationships
    post: Mapped["Post"] = relationship(back_populates="revisions")
    workflow_run: Mapped["WorkflowRun"] = relationship(back_populates="revisions")
    feedbacks: Mapped[list["Feedback"]] = relationship(
        back_populates="revision",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
