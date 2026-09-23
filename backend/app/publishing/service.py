"""Publishing service coordinating platform adapters, idempotency, bounded retries, and persistence."""

import asyncio
from datetime import datetime, timezone
import logging
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.config import Settings, get_settings
from backend.app.db.models.publication import Publication
from backend.app.db.repositories.publication_repo import PublicationRepository
from backend.app.db.repositories.workflow_repo import PostRepository, WorkflowRepository
from backend.app.publishing.base import (
    PermanentPlatformError,
    PlatformRegistry,
    PublicationResult,
    PublishingRequest,
    PublishingStatus,
    TransientPlatformError,
)
from backend.app.publishing.credentials import CredentialResolver, PlatformCredentials
from backend.app.publishing.platforms.linkedin import LinkedInPublisher
from backend.app.workflows.state import WorkflowStatus

logger = logging.getLogger(__name__)


def create_default_platform_registry() -> PlatformRegistry:
    """Instantiate and populate default platform adapter registry."""
    registry = PlatformRegistry()
    registry.register(LinkedInPublisher())
    return registry


class PublishingService:
    """Service orchestrating social media publishing execution, idempotency, and retries."""

    def __init__(
        self,
        platform_registry: PlatformRegistry | None = None,
        credential_resolver: CredentialResolver | None = None,
        settings: Settings | None = None,
        max_retries: int | None = None,
        base_backoff_seconds: float | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.registry = platform_registry or create_default_platform_registry()
        self.credential_resolver = credential_resolver or CredentialResolver(self.settings)
        self.max_retries = (
            max_retries
            if max_retries is not None
            else self.settings.publishing_max_retries
        )
        self.base_backoff_seconds = (
            base_backoff_seconds
            if base_backoff_seconds is not None
            else self.settings.publishing_base_backoff_seconds
        )

    def generate_idempotency_key(
        self,
        workflow_id: str,
        post_id: str,
        platform: str,
    ) -> str:
        """Generate deterministic idempotency key for workflow post on target platform."""
        return f"pub_{workflow_id}_{post_id}_{platform.strip().lower()}"

    async def publish_workflow_post(
        self,
        workflow_id: str,
        session: AsyncSession,
        platform_override: str | None = None,
    ) -> Publication:
        """Execute publishing workflow for an approved content post with idempotency and retry guards."""
        workflow_repo = WorkflowRepository(session)
        post_repo = PostRepository(session)
        pub_repo = PublicationRepository(session)

        # 1. Fetch workflow with row-level locking
        workflow = await workflow_repo.get_with_relations_for_update(workflow_id)
        if not workflow:
            raise ValueError(f"Workflow '{workflow_id}' not found.")

        # 2. Verify workflow status is APPROVED
        if workflow.status != WorkflowStatus.APPROVED.value:
            raise ValueError(
                f"Cannot publish workflow '{workflow_id}': status is '{workflow.status}', "
                f"expected '{WorkflowStatus.APPROVED.value}'."
            )

        # 3. Resolve target post
        posts = workflow.posts or await post_repo.get_by_workflow(workflow_id)
        if not posts:
            raise ValueError(f"No generated post found for workflow '{workflow_id}'.")
        target_post = posts[0]

        # 4. Determine effective target platform
        effective_platform = (
            platform_override or target_post.platform or workflow.target_platform or "linkedin"
        ).strip().lower()

        # 5. Resolve platform adapter & credentials before creating DB records
        publisher = self.registry.get(effective_platform)
        credentials = self.credential_resolver.resolve(effective_platform)

        # 6. Idempotency Check & Publication record creation
        idempotency_key = self.generate_idempotency_key(
            workflow_id=workflow.id,
            post_id=target_post.id,
            platform=effective_platform,
        )

        publication = await pub_repo.get_by_workflow_and_platform_for_update(
            workflow_id=workflow.id,
            platform=effective_platform,
        )

        if publication:
            if publication.status == PublishingStatus.PUBLISHED.value:
                logger.info(
                    "Publication '%s' for workflow '%s' on '%s' is already PUBLISHED (idempotent match).",
                    publication.id,
                    workflow_id,
                    effective_platform,
                )
                return publication

            if publication.status == PublishingStatus.PUBLISHING.value:
                # Check for in-flight concurrency (recent attempt < 60s)
                if publication.last_attempt_at:
                    now = datetime.now(timezone.utc)
                    last_at = publication.last_attempt_at
                    if last_at.tzinfo is None:
                        last_at = last_at.replace(tzinfo=timezone.utc)
                    elapsed = (now - last_at).total_seconds()
                    if elapsed < 60:
                        raise ValueError(
                            f"Publication for workflow '{workflow_id}' is currently in-flight "
                            f"(attempt started {int(elapsed)}s ago)."
                        )
        else:
            publication = Publication(
                workflow_run_id=workflow.id,
                post_id=target_post.id,
                platform=effective_platform,
                status=PublishingStatus.PENDING.value,
                idempotency_key=idempotency_key,
                attempt_count=0,
            )
            await pub_repo.create(publication)
            await session.flush()

        # 7. Build standardized PublishingRequest
        pub_request = PublishingRequest(
            content=target_post.content,
            platform=effective_platform,
            topic=target_post.topic,
            hashtags=list(target_post.hashtags or []),
            cta=target_post.cta,
            source_references=list(target_post.source_references or []),
            idempotency_key=idempotency_key,
        )

        # 8. Execute bounded retry publishing loop
        return await self._execute_publishing_loop(
            publication=publication,
            request=pub_request,
            publisher=publisher,
            credentials=credentials,
            session=session,
            pub_repo=pub_repo,
        )

    async def retry_publication(
        self,
        publication_id: str,
        session: AsyncSession,
    ) -> Publication:
        """Retry a previously failed publication."""
        pub_repo = PublicationRepository(session)
        post_repo = PostRepository(session)
        workflow_repo = WorkflowRepository(session)

        publication = await pub_repo.get_by_id(publication_id)
        if not publication:
            raise ValueError(f"Publication '{publication_id}' not found.")

        if publication.status == PublishingStatus.PUBLISHED.value:
            raise ValueError(
                f"Publication '{publication_id}' is already successfully published."
            )

        workflow = await workflow_repo.get_by_id(publication.workflow_run_id)
        if not workflow or workflow.status != WorkflowStatus.APPROVED.value:
            raise ValueError(
                f"Cannot retry publication '{publication_id}': workflow is not in APPROVED state."
            )

        post = await post_repo.get_by_id(publication.post_id)
        if not post:
            raise ValueError(
                f"Associated post '{publication.post_id}' for publication '{publication_id}' not found."
            )

        publisher = self.registry.get(publication.platform)
        credentials = self.credential_resolver.resolve(publication.platform)

        pub_request = PublishingRequest(
            content=post.content,
            platform=publication.platform,
            topic=post.topic,
            hashtags=list(post.hashtags or []),
            cta=post.cta,
            source_references=list(post.source_references or []),
            idempotency_key=publication.idempotency_key,
        )

        return await self._execute_publishing_loop(
            publication=publication,
            request=pub_request,
            publisher=publisher,
            credentials=credentials,
            session=session,
            pub_repo=pub_repo,
        )

    async def _execute_publishing_loop(
        self,
        publication: Publication,
        request: PublishingRequest,
        publisher: Any,
        credentials: PlatformCredentials,
        session: AsyncSession,
        pub_repo: PublicationRepository,
    ) -> Publication:
        """Bounded retry loop executing publisher calls with exponential backoff."""
        max_attempts = self.max_retries
        last_error_code: str | None = None
        last_error_message: str | None = None

        for attempt in range(1, max_attempts + 1):
            await pub_repo.record_attempt(publication.id, status=PublishingStatus.PUBLISHING.value)
            await session.commit()

            logger.info(
                "Executing publication attempt %d/%d for publication '%s' on '%s'",
                attempt,
                max_attempts,
                publication.id,
                publication.platform,
            )

            try:
                result: PublicationResult = await publisher.publish(request, credentials)

                if result.success:
                    await pub_repo.update_status(
                        publication_id=publication.id,
                        status=PublishingStatus.PUBLISHED.value,
                        external_post_id=result.external_post_id,
                        external_url=result.external_url,
                        published_at=result.published_at or datetime.now(timezone.utc),
                        error_code=None,
                        error_message=None,
                    )
                    await session.commit()
                    await session.refresh(publication)
                    logger.info(
                        "Publication '%s' succeeded on attempt %d. External ID: '%s'",
                        publication.id,
                        attempt,
                        result.external_post_id,
                    )
                    return publication

                # If result was not successful and marked not retryable
                last_error_code = result.error_code or "PUBLISH_FAILED"
                last_error_message = result.error_message or "Platform publication failed."
                if not result.is_retryable:
                    break

            except TransientPlatformError as transient_err:
                last_error_code = transient_err.error_code or "TRANSIENT_ERROR"
                last_error_message = str(transient_err)
                logger.warning(
                    "Publication '%s' attempt %d failed with transient error: %s",
                    publication.id,
                    attempt,
                    last_error_message,
                )
                if attempt < max_attempts:
                    backoff_delay = self.base_backoff_seconds * (2 ** (attempt - 1))
                    logger.info("Applying exponential backoff: sleeping for %.2fs", backoff_delay)
                    await asyncio.sleep(backoff_delay)
                else:
                    logger.error(
                        "Publication '%s' exhausted all %d attempts.",
                        publication.id,
                        max_attempts,
                    )
            except PermanentPlatformError as permanent_err:
                last_error_code = permanent_err.error_code or "PERMANENT_ERROR"
                last_error_message = str(permanent_err)
                logger.error(
                    "Publication '%s' encountered permanent error on attempt %d: %s. Aborting retries.",
                    publication.id,
                    attempt,
                    last_error_message,
                )
                break
            except Exception as unhandled_err:
                last_error_code = "UNEXPECTED_ERROR"
                last_error_message = str(unhandled_err)
                logger.exception(
                    "Publication '%s' encountered unexpected error on attempt %d: %s",
                    publication.id,
                    attempt,
                    unhandled_err,
                )
                break

        # Mark final status as FAILED if loop finishes without success
        await pub_repo.update_status(
            publication_id=publication.id,
            status=PublishingStatus.FAILED.value,
            error_code=last_error_code,
            error_message=last_error_message,
        )
        await session.commit()
        await session.refresh(publication)
        return publication

    async def get_publications_for_workflow(
        self,
        workflow_id: str,
        session: AsyncSession,
    ) -> list[Publication]:
        """Fetch all publications for a given workflow."""
        pub_repo = PublicationRepository(session)
        return await pub_repo.get_by_workflow(workflow_id)

    async def get_publication_by_id(
        self,
        publication_id: str,
        session: AsyncSession,
    ) -> Publication | None:
        """Fetch a specific publication by ID."""
        pub_repo = PublicationRepository(session)
        return await pub_repo.get_by_id(publication_id)
