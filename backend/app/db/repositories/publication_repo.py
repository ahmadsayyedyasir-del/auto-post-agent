"""Repository handling Publication persistence, query filters, and state transitions."""

from datetime import datetime, timezone
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db.models.publication import Publication
from backend.app.db.repositories.base import BaseRepository

logger = logging.getLogger(__name__)


class PublicationRepository(BaseRepository[Publication]):
    """Repository handling Publication database queries and state updates."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(Publication, session)

    async def get_by_workflow_and_platform(
        self,
        workflow_id: str,
        platform: str,
    ) -> Publication | None:
        """Fetch the publication record for a given workflow and platform."""
        stmt = select(Publication).where(
            Publication.workflow_run_id == workflow_id,
            Publication.platform == platform.strip().lower(),
        )
        res = await self.session.execute(stmt)
        return res.scalar_one_or_none()

    async def get_by_workflow_and_platform_for_update(
        self,
        workflow_id: str,
        platform: str,
    ) -> Publication | None:
        """Fetch publication record with row-level locking (FOR UPDATE) where supported."""
        stmt = select(Publication).where(
            Publication.workflow_run_id == workflow_id,
            Publication.platform == platform.strip().lower(),
        )
        bind = self.session.get_bind()
        if bind is not None and getattr(bind.dialect, "name", "") != "sqlite":
            stmt = stmt.with_for_update()

        res = await self.session.execute(stmt)
        return res.scalar_one_or_none()

    async def get_by_idempotency_key(self, idempotency_key: str) -> Publication | None:
        """Fetch publication record matching a specific unique idempotency key."""
        stmt = select(Publication).where(Publication.idempotency_key == idempotency_key)
        res = await self.session.execute(stmt)
        return res.scalar_one_or_none()

    async def get_by_workflow(self, workflow_id: str) -> list[Publication]:
        """Fetch all publications created for a given workflow run."""
        stmt = (
            select(Publication)
            .where(Publication.workflow_run_id == workflow_id)
            .order_by(Publication.created_at.desc())
        )
        res = await self.session.execute(stmt)
        return list(res.scalars().all())

    async def update_status(
        self,
        publication_id: str,
        status: str,
        external_post_id: str | None = None,
        external_url: str | None = None,
        published_at: datetime | None = None,
        error_code: str | None = None,
        error_message: str | None = None,
    ) -> Publication | None:
        """Update publication status and external metadata."""
        publication = await self.get_by_id(publication_id)
        if publication:
            publication.status = status
            if external_post_id is not None:
                publication.external_post_id = external_post_id
            if external_url is not None:
                publication.external_url = external_url
            if published_at is not None:
                publication.published_at = published_at
            if error_code is not None:
                publication.error_code = error_code
            if error_message is not None:
                publication.error_message = error_message
            await self.session.flush()
        return publication

    async def record_attempt(
        self,
        publication_id: str,
        status: str = "PUBLISHING",
    ) -> Publication | None:
        """Increment attempt count and update last attempt timestamp."""
        publication = await self.get_by_id(publication_id)
        if publication:
            publication.attempt_count += 1
            publication.last_attempt_at = datetime.now(timezone.utc)
            publication.status = status
            await self.session.flush()
        return publication
