"""Domain-specific repositories for WorkflowRun, Post, Revision, and Feedback entities."""

import logging
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.app.db.models.feedback import Feedback
from backend.app.db.models.post import Post, Revision
from backend.app.db.models.workflow import WorkflowRun
from backend.app.db.repositories.base import BaseRepository

logger = logging.getLogger(__name__)


class WorkflowRepository(BaseRepository[WorkflowRun]):
    """Repository handling WorkflowRun persistence and queries."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(WorkflowRun, session)

    async def get_with_relations(self, workflow_id: str) -> WorkflowRun | None:
        """Fetch a workflow run including all related posts, revisions, feedback, publications, and schedules."""
        stmt = (
            select(WorkflowRun)
            .where(WorkflowRun.id == workflow_id)
            .options(
                selectinload(WorkflowRun.posts),
                selectinload(WorkflowRun.revisions),
                selectinload(WorkflowRun.feedbacks),
                selectinload(WorkflowRun.publications),
                selectinload(WorkflowRun.schedules),
            )
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_with_relations_for_update(self, workflow_id: str) -> WorkflowRun | None:
        """Fetch a workflow run including relations with row-level locking (FOR UPDATE) if supported by database dialect."""
        stmt = (
            select(WorkflowRun)
            .where(WorkflowRun.id == workflow_id)
            .options(
                selectinload(WorkflowRun.posts),
                selectinload(WorkflowRun.revisions),
                selectinload(WorkflowRun.feedbacks),
                selectinload(WorkflowRun.publications),
                selectinload(WorkflowRun.schedules),
            )
        )
        bind = self.session.get_bind()
        if bind is not None and getattr(bind.dialect, "name", "") != "sqlite":
            stmt = stmt.with_for_update()

        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_status(self, status: str) -> list[WorkflowRun]:
        """Fetch workflow runs matching a specific status (e.g., WAITING_FOR_HUMAN_REVIEW)."""
        stmt = select(WorkflowRun).where(WorkflowRun.status == status).order_by(WorkflowRun.created_at.desc())
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def update_status(
        self,
        workflow_id: str,
        status: str,
        current_stage: str | None = None,
        error_message: str | None = None,
    ) -> WorkflowRun | None:
        """Update lifecycle status and stage for a given workflow run."""
        workflow = await self.get_by_id(workflow_id)
        if workflow:
            workflow.status = status
            if current_stage is not None:
                workflow.current_stage = current_stage
            if error_message is not None:
                workflow.error_message = error_message
            await self.session.flush()
        return workflow


class PostRepository(BaseRepository[Post]):
    """Repository handling Post and Revision persistence and history tracking."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(Post, session)

    async def get_with_revisions(self, post_id: str) -> Post | None:
        """Fetch a post with its ordered revision history."""
        stmt = (
            select(Post)
            .where(Post.id == post_id)
            .options(selectinload(Post.revisions), selectinload(Post.feedbacks))
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_workflow(self, workflow_id: str) -> list[Post]:
        """Fetch all posts created within a specific workflow run."""
        stmt = select(Post).where(Post.workflow_run_id == workflow_id).order_by(Post.created_at.asc())
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def create_revision_snapshot(
        self,
        post_id: str,
        revision_feedback: list[str] | None = None,
        revision_source: str = "AGENT",
    ) -> Revision:
        """Capture the current state of a post as a new historical Revision entry."""
        post = await self.get_by_id(post_id)
        if not post:
            raise ValueError(f"Cannot snapshot revision: Post '{post_id}' not found.")

        stmt = select(func.coalesce(func.max(Revision.revision_number), 0)).where(
            Revision.post_id == post_id
        )
        res = await self.session.execute(stmt)
        current_max = res.scalar_one()
        next_rev_num = int(current_max) + 1

        revision = Revision(
            post_id=post.id,
            workflow_run_id=post.workflow_run_id,
            revision_number=next_rev_num,
            revision_source=revision_source,
            content=post.content,
            hashtags=list(post.hashtags or []),
            cta=post.cta,
            source_references=list(post.source_references or []),
            revision_feedback=revision_feedback or [],
        )
        self.session.add(revision)
        await self.session.flush()
        return revision


class FeedbackRepository(BaseRepository[Feedback]):
    """Repository handling automated Critic and human review Feedback persistence."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(Feedback, session)

    async def get_for_post(self, post_id: str) -> list[Feedback]:
        """Fetch all feedback records for a specific post."""
        stmt = select(Feedback).where(Feedback.post_id == post_id).order_by(Feedback.created_at.desc())
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_for_workflow(self, workflow_id: str) -> list[Feedback]:
        """Fetch all feedback records across an entire workflow run."""
        stmt = select(Feedback).where(Feedback.workflow_run_id == workflow_id).order_by(Feedback.created_at.desc())
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
