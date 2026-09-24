"""Comprehensive unit and integration tests for Phase 10: Social Media Publishing Layer."""

from datetime import datetime, timezone
import json
from typing import Any
import uuid

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.app.config import Settings
from backend.app.db.models.post import Post, Revision
from backend.app.db.models.publication import Publication
from backend.app.db.models.workflow import WorkflowRun
from backend.app.db.repositories.publication_repo import PublicationRepository
from backend.app.db.repositories.workflow_repo import PostRepository, WorkflowRepository
from backend.app.db.session import Base
from backend.app.main import app
from backend.app.publishing.base import (
    PermanentPlatformError,
    PlatformError,
    PlatformRegistry,
    PublicationResult,
    PublishingRequest,
    PublishingStatus,
    SocialPlatformPublisher,
    TransientPlatformError,
)
from backend.app.publishing.credentials import CredentialResolver, PlatformCredentials
from backend.app.publishing.platforms.linkedin import LinkedInPublisher
from backend.app.publishing.service import PublishingService
from backend.app.workflows.state import WorkflowStatus


# ------------------------------------------------------------------------------
# Test Fixtures
# ------------------------------------------------------------------------------


@pytest.fixture
async def async_engine():
    """Create an isolated in-memory SQLite database engine for testing."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest.fixture
async def db_session(async_engine):
    """Yield an async database session."""
    session_factory = async_sessionmaker(
        bind=async_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )
    async with session_factory() as session:
        yield session
        await session.rollback()


@pytest.fixture
def mock_credentials() -> PlatformCredentials:
    """Standard valid LinkedIn credentials for unit testing."""
    return PlatformCredentials(
        platform="linkedin",
        access_token="test_linkedin_access_token_12345",
        author_urn="urn:li:person:test_author_123",
        client_id="test_client_id",
        client_secret="test_client_secret",
    )


@pytest.fixture
def sample_publishing_request() -> PublishingRequest:
    """Standard test publishing request payload."""
    return PublishingRequest(
        content="Exciting updates on autonomous AI agents in 2026.",
        platform="linkedin",
        topic="AI Agents",
        hashtags=["AI", "Tech", "Innovation"],
        cta="Follow for more updates!",
        source_references=["https://arxiv.org/abs/2401.00001"],
        idempotency_key="pub_test_wf_1_post_1_linkedin",
    )


@pytest.fixture
async def approved_workflow_and_post(db_session: AsyncSession) -> tuple[WorkflowRun, Post]:
    """Helper fixture creating an approved WorkflowRun and associated Post in DB."""
    wf_repo = WorkflowRepository(db_session)
    post_repo = PostRepository(db_session)

    wf = WorkflowRun(
        niche="AI Technology",
        target_platform="linkedin",
        audience="Tech Professionals",
        language="English",
        status=WorkflowStatus.APPROVED.value,
        current_stage=WorkflowStatus.APPROVED.value,
        revision_count=1,
    )
    await wf_repo.create(wf)
    await db_session.flush()

    post = Post(
        workflow_run_id=wf.id,
        platform="linkedin",
        topic="AI Tech Trends",
        content="AI agents are revolutionizing automation pipelines in 2026.",
        status="APPROVED",
        content_type="single_post",
        language="English",
        hashtags=["AI", "Tech"],
        cta="What are your thoughts on agentic workflows?",
        source_references=["https://example.com/ai-trends"],
    )
    await post_repo.create(post)
    await db_session.commit()
    return wf, post


# ------------------------------------------------------------------------------
# 1. LinkedIn Adapter Unit Tests
# ------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_linkedin_payload_formatting(sample_publishing_request, mock_credentials):
    """Verify that LinkedInPublisher builds correct official REST API payload."""
    publisher = LinkedInPublisher()
    payload = publisher.build_payload(sample_publishing_request, mock_credentials.author_urn)

    assert payload["author"] == "urn:li:person:test_author_123"
    assert "Exciting updates on autonomous AI agents" in payload["commentary"]
    assert "#AI" in payload["commentary"]
    assert "Follow for more updates!" in payload["commentary"]
    assert payload["visibility"] == "PUBLIC"
    assert payload["distribution"]["feedDistribution"] == "MAIN_FEED"
    assert payload["lifecycleState"] == "PUBLISHED"


@pytest.mark.asyncio
async def test_linkedin_author_urn_normalization():
    """Verify author URN formatting handles bare IDs and full URNs."""
    publisher = LinkedInPublisher()
    assert publisher._normalize_author_urn("123456") == "urn:li:person:123456"
    assert publisher._normalize_author_urn("urn:li:organization:9876") == "urn:li:organization:9876"


@pytest.mark.asyncio
async def test_linkedin_publish_success_201(sample_publishing_request, mock_credentials):
    """Test successful 201 Created LinkedIn response parsing."""
    test_urn = "urn:li:share:7123456789012345678"

    def custom_handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == "Bearer test_linkedin_access_token_12345"
        assert request.headers["X-Restli-Protocol-Version"] == "2.0.0"
        return httpx.Response(
            status_code=201,
            headers={"x-restli-id": test_urn},
            json={"id": test_urn},
        )

    transport = httpx.MockTransport(custom_handler)
    async with httpx.AsyncClient(transport=transport) as client:
        publisher = LinkedInPublisher(http_client=client)
        result = await publisher.publish(sample_publishing_request, mock_credentials)

    assert result.success is True
    assert result.platform == "linkedin"
    assert result.external_post_id == test_urn
    assert result.external_url == f"https://www.linkedin.com/feed/update/{test_urn}/"
    assert result.published_at is not None


@pytest.mark.asyncio
async def test_linkedin_publish_permanent_errors(sample_publishing_request, mock_credentials):
    """Test that 400, 401, 403, and 422 trigger PermanentPlatformError."""
    error_cases = [
        (400, "LINKEDIN_BAD_REQUEST"),
        (401, "LINKEDIN_UNAUTHORIZED"),
        (403, "LINKEDIN_FORBIDDEN"),
        (422, "LINKEDIN_UNPROCESSABLE"),
    ]

    for status_code, expected_code in error_cases:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                status_code=status_code,
                json={"message": f"Simulated error {status_code}"},
            )

        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as client:
            publisher = LinkedInPublisher(http_client=client)
            with pytest.raises(PermanentPlatformError) as exc_info:
                await publisher.publish(sample_publishing_request, mock_credentials)

            assert exc_info.value.error_code == expected_code
            assert exc_info.value.is_retryable is False


@pytest.mark.asyncio
async def test_linkedin_publish_transient_errors(sample_publishing_request, mock_credentials):
    """Test that 429, 500, 503 trigger TransientPlatformError."""
    error_cases = [
        (429, "LINKEDIN_RATE_LIMITED"),
        (500, "LINKEDIN_SERVER_ERROR"),
        (503, "LINKEDIN_SERVER_ERROR"),
    ]

    for status_code, expected_code in error_cases:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                status_code=status_code,
                json={"message": f"Server issue {status_code}"},
            )

        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as client:
            publisher = LinkedInPublisher(http_client=client)
            with pytest.raises(TransientPlatformError) as exc_info:
                await publisher.publish(sample_publishing_request, mock_credentials)

            assert exc_info.value.error_code == expected_code
            assert exc_info.value.is_retryable is True


@pytest.mark.asyncio
async def test_linkedin_publish_timeout_and_network_error(sample_publishing_request, mock_credentials):
    """Test that client timeouts and network drop raise TransientPlatformError."""
    # Timeout test
    def timeout_handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("Read timed out")

    transport = httpx.MockTransport(timeout_handler)
    async with httpx.AsyncClient(transport=transport) as client:
        publisher = LinkedInPublisher(http_client=client)
        with pytest.raises(TransientPlatformError) as exc_info:
            await publisher.publish(sample_publishing_request, mock_credentials)
        assert exc_info.value.error_code == "LINKEDIN_TIMEOUT"

    # Network error test
    def network_handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("Connection refused")

    transport = httpx.MockTransport(network_handler)
    async with httpx.AsyncClient(transport=transport) as client:
        publisher = LinkedInPublisher(http_client=client)
        with pytest.raises(TransientPlatformError) as exc_info:
            await publisher.publish(sample_publishing_request, mock_credentials)
        assert exc_info.value.error_code == "LINKEDIN_NETWORK_ERROR"


# ------------------------------------------------------------------------------
# 2. Registry & Credential Resolver Tests
# ------------------------------------------------------------------------------


def test_platform_registry():
    """Verify registration, retrieval, and unsupported platform handling."""
    registry = PlatformRegistry()
    publisher = LinkedInPublisher()
    registry.register(publisher)

    assert registry.get("linkedin") == publisher
    assert registry.get("LINKEDIN") == publisher
    assert registry.supported_platforms() == ["linkedin"]

    with pytest.raises(ValueError, match="Unsupported social media platform 'twitter'"):
        registry.get("twitter")


def test_credential_resolver_success():
    """Verify resolution of configured LinkedIn credentials."""
    settings = Settings(
        linkedin_access_token="token_abc",
        linkedin_author_urn="urn:li:person:123",
        linkedin_client_id="client_xyz",
        linkedin_client_secret="secret_xyz",
    )
    resolver = CredentialResolver(settings=settings)
    creds = resolver.resolve("linkedin")

    assert creds.platform == "linkedin"
    assert creds.access_token == "token_abc"
    assert creds.author_urn == "urn:li:person:123"
    assert creds.client_id == "client_xyz"


def test_credential_resolver_missing_tokens():
    """Verify validation error when required tokens are missing."""
    settings = Settings(linkedin_access_token=None, linkedin_author_urn=None)
    resolver = CredentialResolver(settings=settings)

    with pytest.raises(PermanentPlatformError, match="LinkedIn access token is missing"):
        resolver.resolve("linkedin")

    settings_token_only = Settings(linkedin_access_token="tok", linkedin_author_urn=None)
    resolver_token_only = CredentialResolver(settings=settings_token_only)
    with pytest.raises(PermanentPlatformError, match="LinkedIn author URN is missing"):
        resolver_token_only.resolve("linkedin")


# ------------------------------------------------------------------------------
# 3. Publication Repository Tests
# ------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_publication_repository_crud(db_session, approved_workflow_and_post):
    """Test PublicationRepository creation, retrieval, and state update."""
    wf, post = approved_workflow_and_post
    repo = PublicationRepository(db_session)

    pub = Publication(
        workflow_run_id=wf.id,
        post_id=post.id,
        platform="linkedin",
        status=PublishingStatus.PENDING.value,
        idempotency_key=f"pub_{wf.id}_{post.id}_linkedin",
    )
    await repo.create(pub)
    await db_session.commit()

    # Query by ID
    fetched = await repo.get_by_id(pub.id)
    assert fetched is not None
    assert fetched.platform == "linkedin"
    assert fetched.status == PublishingStatus.PENDING.value
    assert fetched.attempt_count == 0

    # Record attempt
    await repo.record_attempt(pub.id, status="PUBLISHING")
    await db_session.commit()
    fetched = await repo.get_by_id(pub.id)
    assert fetched.attempt_count == 1
    assert fetched.status == "PUBLISHING"
    assert fetched.last_attempt_at is not None

    # Update status to PUBLISHED
    now = datetime.now(timezone.utc)
    await repo.update_status(
        publication_id=pub.id,
        status="PUBLISHED",
        external_post_id="urn:li:share:123",
        external_url="https://www.linkedin.com/feed/update/urn:li:share:123/",
        published_at=now,
    )
    await db_session.commit()
    fetched = await repo.get_by_id(pub.id)
    assert fetched.status == "PUBLISHED"
    assert fetched.external_post_id == "urn:li:share:123"
    assert fetched.external_url == "https://www.linkedin.com/feed/update/urn:li:share:123/"


# ------------------------------------------------------------------------------
# 4. Publishing Service Tests
# ------------------------------------------------------------------------------


class MockTestPublisher(SocialPlatformPublisher):
    """Mock publisher for deterministic service testing."""

    def __init__(self, platform: str = "linkedin") -> None:
        self._platform = platform
        self.call_count = 0
        self.responses: list[Any] = []

    @property
    def platform_name(self) -> str:
        return self._platform

    def set_responses(self, responses: list[Any]) -> None:
        self.responses = responses
        self.call_count = 0

    async def publish(self, request: PublishingRequest, credentials: PlatformCredentials) -> PublicationResult:
        self.call_count += 1
        if self.responses:
            resp = self.responses.pop(0)
            if isinstance(resp, Exception):
                raise resp
            return resp
        return PublicationResult(
            success=True,
            platform=self._platform,
            external_post_id=f"urn:li:share:mock_{self.call_count}",
            external_url=f"https://www.linkedin.com/feed/update/urn:li:share:mock_{self.call_count}/",
            published_at=datetime.now(timezone.utc),
        )


@pytest.mark.asyncio
async def test_publishing_service_success(db_session, approved_workflow_and_post, mock_credentials):
    """Test end-to-end publishing flow for an approved workflow."""
    wf, post = approved_workflow_and_post

    mock_pub = MockTestPublisher("linkedin")
    registry = PlatformRegistry()
    registry.register(mock_pub)

    settings = Settings(
        linkedin_access_token=mock_credentials.access_token,
        linkedin_author_urn=mock_credentials.author_urn,
    )
    service = PublishingService(
        platform_registry=registry,
        credential_resolver=CredentialResolver(settings=settings),
        max_retries=3,
    )

    pub = await service.publish_workflow_post(workflow_id=wf.id, session=db_session)

    assert pub.status == PublishingStatus.PUBLISHED.value
    assert pub.attempt_count == 1
    assert pub.external_post_id == "urn:li:share:mock_1"
    assert pub.external_url is not None
    assert mock_pub.call_count == 1


@pytest.mark.asyncio
async def test_publishing_service_unapproved_rejection(db_session):
    """Test that attempting to publish an unapproved workflow raises ValueError."""
    wf_repo = WorkflowRepository(db_session)
    post_repo = PostRepository(db_session)

    wf = WorkflowRun(
        niche="Tech",
        target_platform="linkedin",
        status=WorkflowStatus.WAITING_FOR_HUMAN_REVIEW.value,
    )
    await wf_repo.create(wf)
    await db_session.flush()

    post = Post(
        workflow_run_id=wf.id,
        platform="linkedin",
        topic="Tech",
        content="Draft copy",
        status="DRAFT",
    )
    await post_repo.create(post)
    await db_session.commit()

    service = PublishingService()
    with pytest.raises(ValueError, match="status is 'WAITING_FOR_HUMAN_REVIEW', expected 'APPROVED'"):
        await service.publish_workflow_post(workflow_id=wf.id, session=db_session)


@pytest.mark.asyncio
async def test_publishing_service_idempotency_duplicate(db_session, approved_workflow_and_post, mock_credentials):
    """Test that publishing an already published post returns existing record without re-publishing."""
    wf, post = approved_workflow_and_post

    mock_pub = MockTestPublisher("linkedin")
    registry = PlatformRegistry()
    registry.register(mock_pub)

    settings = Settings(
        linkedin_access_token=mock_credentials.access_token,
        linkedin_author_urn=mock_credentials.author_urn,
    )
    service = PublishingService(
        platform_registry=registry,
        credential_resolver=CredentialResolver(settings=settings),
    )

    # First publish
    pub1 = await service.publish_workflow_post(workflow_id=wf.id, session=db_session)
    assert pub1.status == PublishingStatus.PUBLISHED.value
    assert mock_pub.call_count == 1

    # Second publish call (should be idempotent no-op)
    pub2 = await service.publish_workflow_post(workflow_id=wf.id, session=db_session)
    assert pub2.id == pub1.id
    assert pub2.status == PublishingStatus.PUBLISHED.value
    assert mock_pub.call_count == 1  # No additional network call


@pytest.mark.asyncio
async def test_publishing_service_transient_retry_and_recovery(
    db_session, approved_workflow_and_post, mock_credentials
):
    """Test transient error on attempt 1 with recovery on attempt 2."""
    wf, post = approved_workflow_and_post

    mock_pub = MockTestPublisher("linkedin")
    mock_pub.set_responses([
        TransientPlatformError("503 Service Unavailable", error_code="LINKEDIN_503"),
        PublicationResult(
            success=True,
            platform="linkedin",
            external_post_id="urn:li:share:recovered",
            external_url="https://www.linkedin.com/feed/update/urn:li:share:recovered/",
            published_at=datetime.now(timezone.utc),
        ),
    ])

    registry = PlatformRegistry()
    registry.register(mock_pub)

    settings = Settings(
        linkedin_access_token=mock_credentials.access_token,
        linkedin_author_urn=mock_credentials.author_urn,
    )
    service = PublishingService(
        platform_registry=registry,
        credential_resolver=CredentialResolver(settings=settings),
        max_retries=3,
        base_backoff_seconds=0.01,  # Fast backoff for tests
    )

    pub = await service.publish_workflow_post(workflow_id=wf.id, session=db_session)

    assert pub.status == PublishingStatus.PUBLISHED.value
    assert pub.attempt_count == 2
    assert pub.external_post_id == "urn:li:share:recovered"
    assert mock_pub.call_count == 2


@pytest.mark.asyncio
async def test_publishing_service_transient_retry_exhaustion(
    db_session, approved_workflow_and_post, mock_credentials
):
    """Test transient error exhaustion across all 3 attempts."""
    wf, post = approved_workflow_and_post

    mock_pub = MockTestPublisher("linkedin")
    mock_pub.set_responses([
        TransientPlatformError("Timeout 1", error_code="TIMEOUT"),
        TransientPlatformError("Timeout 2", error_code="TIMEOUT"),
        TransientPlatformError("Timeout 3", error_code="TIMEOUT"),
    ])

    registry = PlatformRegistry()
    registry.register(mock_pub)

    settings = Settings(
        linkedin_access_token=mock_credentials.access_token,
        linkedin_author_urn=mock_credentials.author_urn,
    )
    service = PublishingService(
        platform_registry=registry,
        credential_resolver=CredentialResolver(settings=settings),
        max_retries=3,
        base_backoff_seconds=0.01,
    )

    pub = await service.publish_workflow_post(workflow_id=wf.id, session=db_session)

    assert pub.status == PublishingStatus.FAILED.value
    assert pub.attempt_count == 3
    assert pub.error_code == "TIMEOUT"
    assert mock_pub.call_count == 3


@pytest.mark.asyncio
async def test_publishing_service_permanent_error_no_retry(
    db_session, approved_workflow_and_post, mock_credentials
):
    """Test permanent 401 error fails immediately without retrying."""
    wf, post = approved_workflow_and_post

    mock_pub = MockTestPublisher("linkedin")
    mock_pub.set_responses([
        PermanentPlatformError("Unauthorized token", error_code="LINKEDIN_UNAUTHORIZED"),
        PublicationResult(success=True, platform="linkedin"),
    ])

    registry = PlatformRegistry()
    registry.register(mock_pub)

    settings = Settings(
        linkedin_access_token=mock_credentials.access_token,
        linkedin_author_urn=mock_credentials.author_urn,
    )
    service = PublishingService(
        platform_registry=registry,
        credential_resolver=CredentialResolver(settings=settings),
        max_retries=3,
        base_backoff_seconds=0.01,
    )

    pub = await service.publish_workflow_post(workflow_id=wf.id, session=db_session)

    assert pub.status == PublishingStatus.FAILED.value
    assert pub.attempt_count == 1
    assert pub.error_code == "LINKEDIN_UNAUTHORIZED"
    assert mock_pub.call_count == 1  # Exactly 1 attempt made


@pytest.mark.asyncio
async def test_publishing_service_manual_retry(
    db_session, approved_workflow_and_post, mock_credentials
):
    """Test manually retrying a previously failed publication."""
    wf, post = approved_workflow_and_post

    mock_pub = MockTestPublisher("linkedin")
    mock_pub.set_responses([
        PermanentPlatformError("Simulated failure", error_code="SIMULATED"),
        PublicationResult(
            success=True,
            platform="linkedin",
            external_post_id="urn:li:share:manual_retry_success",
            external_url="https://www.linkedin.com/feed/update/urn:li:share:manual_retry_success/",
            published_at=datetime.now(timezone.utc),
        ),
    ])

    registry = PlatformRegistry()
    registry.register(mock_pub)

    settings = Settings(
        linkedin_access_token=mock_credentials.access_token,
        linkedin_author_urn=mock_credentials.author_urn,
    )
    service = PublishingService(
        platform_registry=registry,
        credential_resolver=CredentialResolver(settings=settings),
        max_retries=1,
    )

    # Initial attempt fails
    failed_pub = await service.publish_workflow_post(workflow_id=wf.id, session=db_session)
    assert failed_pub.status == PublishingStatus.FAILED.value

    # Manual retry
    recovered_pub = await service.retry_publication(
        publication_id=failed_pub.id,
        session=db_session,
    )
    assert recovered_pub.status == PublishingStatus.PUBLISHED.value
    assert recovered_pub.external_post_id == "urn:li:share:manual_retry_success"
    assert recovered_pub.attempt_count == 2


# ------------------------------------------------------------------------------
# 5. REST API Integration Tests
# ------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_api_publish_workflow_success(async_engine, approved_workflow_and_post, mock_credentials, monkeypatch):
    """Test POST /api/v1/workflows/{id}/publish endpoint."""
    from backend.app.config import get_settings
    from backend.app.db.session import get_db_session

    wf, post = approved_workflow_and_post

    # Configure mock environment settings
    monkeypatch.setenv("LINKEDIN_ACCESS_TOKEN", mock_credentials.access_token)
    monkeypatch.setenv("LINKEDIN_AUTHOR_URN", mock_credentials.author_urn)
    get_settings.cache_clear()

    # Mock the LinkedIn HTTP transport inside PublishingService
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status_code=201,
            headers={"x-restli-id": "urn:li:share:api_test_123"},
            json={"id": "urn:li:share:api_test_123"},
        )

    session_factory = async_sessionmaker(
        bind=async_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async def override_get_db():
        async with session_factory() as session:
            yield session

    from backend.app.api.v1.dependencies import get_current_active_user
    from backend.app.db.models.user import User

    test_user = User(
        id="test-user-id-0000",
        email="testuser@example.com",
        hashed_password="mockhashedpassword",
        is_active=True,
    )

    app.dependency_overrides[get_db_session] = override_get_db
    app.dependency_overrides[get_current_active_user] = lambda: test_user

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        # Patch the default publisher's http client
        mock_transport = httpx.MockTransport(handler)
        mock_client = httpx.AsyncClient(transport=mock_transport)
        monkeypatch.setattr(
            "backend.app.publishing.service.create_default_platform_registry",
            lambda: (
                reg := PlatformRegistry(),
                reg.register(LinkedInPublisher(http_client=mock_client)),
                reg,
            )[-1],
        )

        resp = await client.post(f"/api/v1/workflows/{wf.id}/publish")
        assert resp.status_code == 200
        data = resp.json()
        assert data["workflow_run_id"] == wf.id
        assert data["status"] == "PUBLISHED"
        assert data["external_post_id"] == "urn:li:share:api_test_123"
        assert "token" not in json.dumps(data)

        # Query GET /api/v1/workflows/{id}/publication
        list_resp = await client.get(f"/api/v1/workflows/{wf.id}/publication")
        assert list_resp.status_code == 200
        list_data = list_resp.json()
        assert list_data["total"] == 1
        assert list_data["publications"][0]["id"] == data["id"]

        # Query GET /api/v1/publications/{id}
        get_resp = await client.get(f"/api/v1/publications/{data['id']}")
        assert get_resp.status_code == 200
        assert get_resp.json()["id"] == data["id"]

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_api_publish_unapproved_workflow_conflict(async_engine):
    """Test that POST /api/v1/workflows/{id}/publish returns 409 Conflict when unapproved."""
    from backend.app.api.v1.dependencies import get_current_active_user
    from backend.app.db.models.user import User
    from backend.app.db.session import get_db_session

    test_user = User(
        id="test-user-id-0000",
        email="testuser@example.com",
        hashed_password="mockhashedpassword",
        is_active=True,
    )

    session_factory = async_sessionmaker(bind=async_engine, class_=AsyncSession, expire_on_commit=False)

    async with session_factory() as session:
        wf_repo = WorkflowRepository(session)
        wf = WorkflowRun(
            niche="AI",
            target_platform="linkedin",
            status="WAITING_FOR_HUMAN_REVIEW",
        )
        await wf_repo.create(wf)
        await session.commit()
        unapproved_id = wf.id

    async def override_get_db():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_get_db
    app.dependency_overrides[get_current_active_user] = lambda: test_user

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        resp = await client.post(f"/api/v1/workflows/{unapproved_id}/publish")
        assert resp.status_code == 409
        assert "expected 'approved'" in resp.json()["detail"].lower()

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_api_publish_nonexistent_workflow_not_found(async_engine):
    """Test that POST /api/v1/workflows/{id}/publish returns 404 for invalid ID."""
    from backend.app.api.v1.dependencies import get_current_active_user
    from backend.app.db.models.user import User
    from backend.app.db.session import get_db_session

    test_user = User(
        id="test-user-id-0000",
        email="testuser@example.com",
        hashed_password="mockhashedpassword",
        is_active=True,
    )

    session_factory = async_sessionmaker(bind=async_engine, class_=AsyncSession, expire_on_commit=False)

    async def override_get_db():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_get_db
    app.dependency_overrides[get_current_active_user] = lambda: test_user

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        resp = await client.post(f"/api/v1/workflows/{uuid.uuid4()}/publish")
        assert resp.status_code == 404

    app.dependency_overrides.clear()
