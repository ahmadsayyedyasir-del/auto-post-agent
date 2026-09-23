"""Comprehensive unit and integration tests for Phase 11: Scheduling & Automation Layer."""

from datetime import datetime, timedelta, timezone
import json
from typing import Any
from unittest.mock import AsyncMock, patch
import uuid
import zoneinfo

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.app.config import Settings
from backend.app.db.models.post import Post
from backend.app.db.models.publication import Publication
from backend.app.db.models.schedule import Schedule
from backend.app.db.models.workflow import WorkflowRun
from backend.app.db.repositories.schedule_repo import ScheduleRepository
from backend.app.db.repositories.workflow_repo import PostRepository, WorkflowRepository
from backend.app.db.session import Base
from backend.app.main import app
from backend.app.publishing.base import (
    PlatformRegistry,
    PublicationResult,
    PublishingRequest,
    PublishingStatus,
    SocialPlatformPublisher,
)
from backend.app.publishing.credentials import CredentialResolver, PlatformCredentials
from backend.app.publishing.service import PublishingService
from backend.app.scheduling.manager import ScheduleManager, ScheduleStatus
from backend.app.scheduling.schemas import (
    CreateScheduleRequestSchema,
    UpdateScheduleRequestSchema,
)
from backend.app.scheduling.service import SchedulingService
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
def session_factory(async_engine):
    """Factory to create new sessions for background tasks."""
    return async_sessionmaker(
        bind=async_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )


class MockPublisher(SocialPlatformPublisher):
    """Mock social media publisher for testing scheduling executions."""

    def __init__(self, platform_name: str = "linkedin"):
        self._platform_name = platform_name
        self.published_requests: list[PublishingRequest] = []
        self.should_fail = False
        self.error_message = "Simulated publishing failure"

    @property
    def platform_name(self) -> str:
        return self._platform_name

    async def publish(self, request: PublishingRequest, credentials: PlatformCredentials) -> PublicationResult:
        if self.should_fail:
            return PublicationResult(
                success=False,
                platform=self.platform_name,
                error_code="SIMULATED_FAILURE",
                error_message=self.error_message,
                retryable=False,
            )
        self.published_requests.append(request)
        return PublicationResult(
            success=True,
            platform=self.platform_name,
            external_post_id=f"urn:li:share:{uuid.uuid4().hex[:8]}",
            external_url="https://linkedin.com/test",
            published_at=datetime.now(timezone.utc),
        )

    async def validate_credentials(self, credentials: PlatformCredentials) -> bool:
        return True


@pytest.fixture
def mock_publisher() -> MockPublisher:
    return MockPublisher("linkedin")


@pytest.fixture
def test_publishing_service(mock_publisher) -> PublishingService:
    registry = PlatformRegistry()
    registry.register(mock_publisher)
    settings = Settings(
        linkedin_access_token="mock_token",
        linkedin_author_urn="urn:li:person:mock_person",
    )
    return PublishingService(
        platform_registry=registry,
        credential_resolver=CredentialResolver(settings=settings),
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
        topic="AI Scheduling Trends",
        content="Automated scheduling ensures timely social media engagement.",
        status="APPROVED",
        content_type="single_post",
        language="English",
        hashtags=["AI", "Scheduling"],
        cta="Learn more about our scheduling features!",
        source_references=["https://example.com/scheduling"],
    )
    await post_repo.create(post)
    await db_session.commit()
    return wf, post


@pytest.fixture
async def unapproved_workflow_and_post(db_session: AsyncSession) -> tuple[WorkflowRun, Post]:
    """Helper fixture creating a workflow in HUMAN_REVIEW stage (not approved)."""
    wf_repo = WorkflowRepository(db_session)
    post_repo = PostRepository(db_session)

    wf = WorkflowRun(
        niche="AI Technology",
        target_platform="linkedin",
        audience="Tech Professionals",
        language="English",
        status=WorkflowStatus.HUMAN_REVIEW.value,
        current_stage=WorkflowStatus.HUMAN_REVIEW.value,
        revision_count=1,
    )
    await wf_repo.create(wf)
    await db_session.flush()

    post = Post(
        workflow_run_id=wf.id,
        platform="linkedin",
        topic="AI Draft",
        content="Draft awaiting approval.",
        status="DRAFT",
        content_type="single_post",
        language="English",
        hashtags=["Draft"],
        cta=None,
        source_references=[],
    )
    await post_repo.create(post)
    await db_session.commit()
    return wf, post


# ------------------------------------------------------------------------------
# 1. Schedule Repository & ORM Model Tests
# ------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_schedule_repository_crud(db_session: AsyncSession, approved_workflow_and_post):
    """Verify standard CRUD operations on ScheduleRepository."""
    wf, post = approved_workflow_and_post
    repo = ScheduleRepository(db_session)

    scheduled_time = datetime.now(timezone.utc) + timedelta(hours=2)
    schedule = Schedule(
        workflow_run_id=wf.id,
        post_id=post.id,
        platform="linkedin",
        scheduled_at=scheduled_time,
        timezone="UTC",
        status=ScheduleStatus.SCHEDULED.value,
        job_id=f"job_{wf.id}",
    )

    created = await repo.create(schedule)
    await db_session.commit()

    assert created.id is not None
    assert created.status == ScheduleStatus.SCHEDULED.value

    # Get by ID
    fetched = await repo.get_by_id(created.id)
    assert fetched is not None
    assert fetched.workflow_run_id == wf.id

    # Get by workflow ID
    by_wf = await repo.get_by_workflow_id(wf.id)
    assert len(by_wf) == 1
    assert by_wf[0].id == created.id

    # Get active by workflow ID
    active = await repo.get_active_by_workflow_id(wf.id)
    assert active is not None
    assert active.id == created.id

    # Update status
    updated = await repo.update_status(created.id, ScheduleStatus.COMPLETED.value)
    assert updated is not None
    assert updated.status == ScheduleStatus.COMPLETED.value

    # After completion, active schedule should be None
    active_after = await repo.get_active_by_workflow_id(wf.id)
    assert active_after is None


@pytest.mark.asyncio
async def test_schedule_unique_active_constraint(db_session: AsyncSession, approved_workflow_and_post):
    """Verify that multiple active schedules for the same workflow violate unique index."""
    wf, post = approved_workflow_and_post
    wf_id = wf.id
    post_id = post.id
    repo = ScheduleRepository(db_session)

    sch1 = Schedule(
        workflow_run_id=wf_id,
        post_id=post_id,
        platform="linkedin",
        scheduled_at=datetime.now(timezone.utc) + timedelta(hours=1),
        timezone="UTC",
        status=ScheduleStatus.SCHEDULED.value,
        job_id=f"job_1_{wf_id}",
    )
    await repo.create(sch1)
    await db_session.commit()

    sch2 = Schedule(
        workflow_run_id=wf_id,
        post_id=post_id,
        platform="linkedin",
        scheduled_at=datetime.now(timezone.utc) + timedelta(hours=2),
        timezone="UTC",
        status=ScheduleStatus.SCHEDULED.value,
        job_id=f"job_2_{wf_id}",
    )
    sch1_id = sch1.id
    with pytest.raises(Exception):
        await repo.create(sch2)
        await db_session.commit()
    await db_session.rollback()

    # Transition sch1 to RUNNING and verify a new SCHEDULED schedule is still blocked at DB level
    sch1_refetched = await repo.get_by_id(sch1_id)
    assert sch1_refetched is not None
    sch1_refetched.status = ScheduleStatus.RUNNING.value
    await db_session.commit()

    sch3 = Schedule(
        workflow_run_id=wf_id,
        post_id=post_id,
        platform="linkedin",
        scheduled_at=datetime.now(timezone.utc) + timedelta(hours=3),
        timezone="UTC",
        status=ScheduleStatus.SCHEDULED.value,
        job_id=f"job_3_{wf_id}",
    )
    with pytest.raises(Exception):
        await repo.create(sch3)
        await db_session.commit()
    await db_session.rollback()


# ------------------------------------------------------------------------------
# 2. Scheduling Service & Timezone Handling Tests
# ------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_scheduling_service_create_success(
    db_session: AsyncSession, approved_workflow_and_post, test_publishing_service
):
    """Verify successful schedule creation with IANA timezone conversion."""
    wf, post = approved_workflow_and_post
    manager = ScheduleManager(session_factory=None, publishing_service=test_publishing_service)
    manager.start()

    service = SchedulingService(schedule_manager=manager, publishing_service=test_publishing_service)

    # Schedule 5 hours in future in Asia/Karachi (UTC+5)
    future_karachi = datetime.now(zoneinfo.ZoneInfo("Asia/Karachi")) + timedelta(hours=5)
    request = CreateScheduleRequestSchema(
        workflow_id=wf.id,
        scheduled_at=future_karachi,
        timezone="Asia/Karachi",
    )

    schedule = await service.create_schedule(request, db_session)
    assert schedule.id is not None
    assert schedule.status == ScheduleStatus.SCHEDULED.value
    assert schedule.timezone == "Asia/Karachi"
    assert schedule.scheduled_at.tzinfo is not None

    # Verify job is scheduled in APScheduler
    job = manager.get_job(schedule.job_id)
    assert job is not None

    manager.shutdown()


@pytest.mark.asyncio
async def test_scheduling_service_invalid_timezone(
    db_session: AsyncSession, approved_workflow_and_post, test_publishing_service
):
    """Verify that invalid timezone strings are rejected with ValueError."""
    wf, post = approved_workflow_and_post
    manager = ScheduleManager(session_factory=None, publishing_service=test_publishing_service)
    service = SchedulingService(schedule_manager=manager, publishing_service=test_publishing_service)

    request = CreateScheduleRequestSchema(
        workflow_id=wf.id,
        scheduled_at=datetime.now() + timedelta(hours=2),
        timezone="Invalid/Timezone_Name",
    )

    with pytest.raises(ValueError, match="Invalid IANA timezone"):
        await service.create_schedule(request, db_session)


@pytest.mark.asyncio
async def test_scheduling_service_past_time_rejected(
    db_session: AsyncSession, approved_workflow_and_post, test_publishing_service
):
    """Verify that scheduling in the past is rejected."""
    wf, post = approved_workflow_and_post
    manager = ScheduleManager(session_factory=None, publishing_service=test_publishing_service)
    service = SchedulingService(schedule_manager=manager, publishing_service=test_publishing_service)

    past_time = datetime.now(timezone.utc) - timedelta(minutes=10)
    request = CreateScheduleRequestSchema(
        workflow_id=wf.id,
        scheduled_at=past_time,
        timezone="UTC",
    )

    with pytest.raises(ValueError, match="cannot be in the past"):
        await service.create_schedule(request, db_session)


@pytest.mark.asyncio
async def test_scheduling_service_unapproved_workflow_rejected(
    db_session: AsyncSession, unapproved_workflow_and_post, test_publishing_service
):
    """Verify that scheduling an unapproved workflow is rejected."""
    wf, post = unapproved_workflow_and_post
    manager = ScheduleManager(session_factory=None, publishing_service=test_publishing_service)
    service = SchedulingService(schedule_manager=manager, publishing_service=test_publishing_service)

    future_time = datetime.now(timezone.utc) + timedelta(hours=2)
    request = CreateScheduleRequestSchema(
        workflow_id=wf.id,
        scheduled_at=future_time,
        timezone="UTC",
    )

    with pytest.raises(ValueError, match="is not APPROVED"):
        await service.create_schedule(request, db_session)


@pytest.mark.asyncio
async def test_scheduling_service_already_published_workflow_rejected(
    db_session: AsyncSession, approved_workflow_and_post, test_publishing_service
):
    """Verify that scheduling an already PUBLISHED workflow is rejected."""
    wf, post = approved_workflow_and_post
    wf_repo = WorkflowRepository(db_session)
    await wf_repo.update_status(wf.id, WorkflowStatus.PUBLISHED.value)
    await db_session.commit()

    manager = ScheduleManager(session_factory=None, publishing_service=test_publishing_service)
    service = SchedulingService(schedule_manager=manager, publishing_service=test_publishing_service)

    future_time = datetime.now(timezone.utc) + timedelta(hours=2)
    request = CreateScheduleRequestSchema(
        workflow_id=wf.id,
        scheduled_at=future_time,
        timezone="UTC",
    )

    with pytest.raises(ValueError, match="already PUBLISHED"):
        await service.create_schedule(request, db_session)


@pytest.mark.asyncio
async def test_scheduling_service_duplicate_active_schedule_rejected(
    db_session: AsyncSession, approved_workflow_and_post, test_publishing_service
):
    """Verify that attempting to create a second active schedule raises ValueError."""
    wf, post = approved_workflow_and_post
    manager = ScheduleManager(session_factory=None, publishing_service=test_publishing_service)
    manager.start()
    service = SchedulingService(schedule_manager=manager, publishing_service=test_publishing_service)

    future_time = datetime.now(timezone.utc) + timedelta(hours=2)
    request = CreateScheduleRequestSchema(
        workflow_id=wf.id,
        scheduled_at=future_time,
        timezone="UTC",
    )

    sch1 = await service.create_schedule(request, db_session)
    assert sch1 is not None

    # Second attempt
    with pytest.raises(ValueError, match="already has an active schedule"):
        await service.create_schedule(request, db_session)

    manager.shutdown()


@pytest.mark.asyncio
async def test_scheduling_service_cancel_schedule(
    db_session: AsyncSession, approved_workflow_and_post, test_publishing_service
):
    """Verify cancelling an active schedule."""
    wf, post = approved_workflow_and_post
    manager = ScheduleManager(session_factory=None, publishing_service=test_publishing_service)
    manager.start()
    service = SchedulingService(schedule_manager=manager, publishing_service=test_publishing_service)

    future_time = datetime.now(timezone.utc) + timedelta(hours=2)
    request = CreateScheduleRequestSchema(
        workflow_id=wf.id,
        scheduled_at=future_time,
        timezone="UTC",
    )
    schedule = await service.create_schedule(request, db_session)
    assert manager.get_job(schedule.job_id) is not None

    cancelled = await service.cancel_schedule(schedule.id, db_session)
    assert cancelled.status == ScheduleStatus.CANCELLED.value
    assert manager.get_job(schedule.job_id) is None

    # Cancelling again should raise ValueError
    with pytest.raises(ValueError, match="Cannot cancel schedule in state"):
        await service.cancel_schedule(schedule.id, db_session)

    manager.shutdown()


@pytest.mark.asyncio
async def test_scheduling_service_reschedule(
    db_session: AsyncSession, approved_workflow_and_post, test_publishing_service
):
    """Verify updating the scheduled time and timezone of an active schedule."""
    wf, post = approved_workflow_and_post
    manager = ScheduleManager(session_factory=None, publishing_service=test_publishing_service)
    manager.start()
    service = SchedulingService(schedule_manager=manager, publishing_service=test_publishing_service)

    future_time = datetime.now(timezone.utc) + timedelta(hours=2)
    request = CreateScheduleRequestSchema(
        workflow_id=wf.id,
        scheduled_at=future_time,
        timezone="UTC",
    )
    schedule = await service.create_schedule(request, db_session)

    new_time = datetime.now(timezone.utc) + timedelta(hours=5)
    update_req = UpdateScheduleRequestSchema(
        scheduled_at=new_time,
        timezone="Europe/London",
    )
    updated = await service.update_schedule(schedule.id, update_req, db_session)

    assert updated.timezone == "Europe/London"
    assert updated.status == ScheduleStatus.SCHEDULED.value

    job = manager.get_job(schedule.job_id)
    assert job is not None
    assert job.next_run_time is not None

    manager.shutdown()


# ------------------------------------------------------------------------------
# 3. Scheduled Job Execution Tests
# ------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_schedule_execution_success(
    session_factory, approved_workflow_and_post, test_publishing_service, mock_publisher
):
    """Verify successful execution of a scheduled job via ScheduleManager."""
    wf, post = approved_workflow_and_post
    manager = ScheduleManager(session_factory=session_factory, publishing_service=test_publishing_service)
    manager.start()

    async with session_factory() as session:
        service = SchedulingService(schedule_manager=manager, publishing_service=test_publishing_service)
        future_time = datetime.now(timezone.utc) + timedelta(hours=1)
        request = CreateScheduleRequestSchema(
            workflow_id=wf.id,
            scheduled_at=future_time,
            timezone="UTC",
        )
        schedule = await service.create_schedule(request, session)
        schedule_id = schedule.id

    # Execute manually
    await manager.execute_scheduled_job(schedule_id=schedule_id)

    # Verify DB state
    async with session_factory() as session:
        repo = ScheduleRepository(session)
        sch = await repo.get_by_id(schedule_id)
        assert sch.status == ScheduleStatus.COMPLETED.value
        assert sch.executed_at is not None
        assert sch.attempt_count == 1
        assert sch.last_error is None

        # Verify publication was created
        wf_repo = WorkflowRepository(session)
        hydrated_wf = await wf_repo.get_with_relations(wf.id)
        assert len(hydrated_wf.publications) == 1
        assert hydrated_wf.publications[0].status == PublishingStatus.PUBLISHED.value
        assert hydrated_wf.status == WorkflowStatus.PUBLISHED.value

    manager.shutdown()


@pytest.mark.asyncio
async def test_schedule_execution_publishing_failure(
    session_factory, approved_workflow_and_post, test_publishing_service, mock_publisher
):
    """Verify that when publishing fails during execution, schedule records FAILED status."""
    wf, post = approved_workflow_and_post
    mock_publisher.should_fail = True
    mock_publisher.error_message = "LinkedIn API rate limit exceeded"

    manager = ScheduleManager(session_factory=session_factory, publishing_service=test_publishing_service)
    manager.start()

    async with session_factory() as session:
        service = SchedulingService(schedule_manager=manager, publishing_service=test_publishing_service)
        future_time = datetime.now(timezone.utc) + timedelta(hours=1)
        request = CreateScheduleRequestSchema(
            workflow_id=wf.id,
            scheduled_at=future_time,
            timezone="UTC",
        )
        schedule = await service.create_schedule(request, session)
        schedule_id = schedule.id

    # Execute
    await manager.execute_scheduled_job(schedule_id=schedule_id)

    # Verify schedule marked FAILED
    async with session_factory() as session:
        repo = ScheduleRepository(session)
        sch = await repo.get_by_id(schedule_id)
        assert sch.status == ScheduleStatus.FAILED.value
        assert "LinkedIn API rate limit" in (sch.last_error or "")
        assert sch.attempt_count == 1

    manager.shutdown()


@pytest.mark.asyncio
async def test_schedule_execution_revoked_approval(
    session_factory, approved_workflow_and_post, test_publishing_service, mock_publisher
):
    """Verify that if workflow status was changed prior to execution, schedule fails safely."""
    wf, post = approved_workflow_and_post
    manager = ScheduleManager(session_factory=session_factory, publishing_service=test_publishing_service)
    manager.start()

    async with session_factory() as session:
        service = SchedulingService(schedule_manager=manager, publishing_service=test_publishing_service)
        future_time = datetime.now(timezone.utc) + timedelta(hours=1)
        request = CreateScheduleRequestSchema(
            workflow_id=wf.id,
            scheduled_at=future_time,
            timezone="UTC",
        )
        schedule = await service.create_schedule(request, session)
        schedule_id = schedule.id

        # Revoke approval
        wf_repo = WorkflowRepository(session)
        await wf_repo.update_status(wf.id, WorkflowStatus.REJECTED.value)
        await session.commit()

    # Execute scheduled job
    await manager.execute_scheduled_job(schedule_id=schedule_id)

    # Verify schedule marked FAILED due to workflow not being APPROVED
    async with session_factory() as session:
        repo = ScheduleRepository(session)
        sch = await repo.get_by_id(schedule_id)
        assert sch.status == ScheduleStatus.FAILED.value
        assert "not in APPROVED status" in sch.last_error
        assert len(mock_publisher.published_requests) == 0

    manager.shutdown()


# ------------------------------------------------------------------------------
# 4. Startup Recovery Tests
# ------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_startup_recovery(session_factory, approved_workflow_and_post, test_publishing_service):
    """Verify startup recovery handles future schedules, overdue schedules, and orphaned running jobs."""
    wf, post = approved_workflow_and_post

    # Create 3 schedules in DB directly:
    # 1. Future SCHEDULED (should be re-registered in scheduler)
    # 2. Past SCHEDULED (overdue, should be marked FAILED)
    # 3. Orphaned RUNNING (crash recovery, should be marked FAILED)
    now = datetime.now(timezone.utc)

    async with session_factory() as session:
        repo = ScheduleRepository(session)

        future_sch = Schedule(
            workflow_run_id=wf.id,
            post_id=post.id,
            platform="linkedin",
            scheduled_at=now + timedelta(hours=3),
            timezone="UTC",
            status=ScheduleStatus.SCHEDULED.value,
            job_id="job_future_123",
        )
        await repo.create(future_sch)
        await session.commit()
        future_id = future_sch.id

    # For overdue and orphaned tests, create another workflow
    async with session_factory() as session:
        wf_repo = WorkflowRepository(session)
        post_repo = PostRepository(session)
        wf2 = WorkflowRun(
            niche="AI Technology",
            target_platform="linkedin",
            status=WorkflowStatus.APPROVED.value,
        )
        await wf_repo.create(wf2)
        await session.flush()
        post2 = Post(
            workflow_run_id=wf2.id,
            platform="linkedin",
            topic="Test",
            content="Content",
            status="APPROVED",
        )
        await post_repo.create(post2)
        await session.flush()

        repo = ScheduleRepository(session)
        overdue_sch = Schedule(
            workflow_run_id=wf2.id,
            post_id=post2.id,
            platform="linkedin",
            scheduled_at=now - timedelta(hours=2),
            timezone="UTC",
            status=ScheduleStatus.SCHEDULED.value,
            job_id="job_overdue_456",
        )
        await repo.create(overdue_sch)

        wf3 = WorkflowRun(
            niche="AI Technology",
            target_platform="linkedin",
            status=WorkflowStatus.APPROVED.value,
        )
        await wf_repo.create(wf3)
        await session.flush()
        post3 = Post(
            workflow_run_id=wf3.id,
            platform="linkedin",
            topic="Test 3",
            content="Content 3",
            status="APPROVED",
        )
        await post_repo.create(post3)
        await session.flush()

        orphaned_sch = Schedule(
            workflow_run_id=wf3.id,
            post_id=post3.id,
            platform="linkedin",
            scheduled_at=now - timedelta(minutes=30),
            timezone="UTC",
            status=ScheduleStatus.RUNNING.value,
            job_id="job_orphaned_789",
        )
        await repo.create(orphaned_sch)
        await session.commit()
        overdue_id = overdue_sch.id
        orphaned_id = orphaned_sch.id

    # Initialize manager and run recovery
    manager = ScheduleManager(session_factory=session_factory, publishing_service=test_publishing_service)
    manager.start()

    recovered_count = await manager.recover_schedules()
    assert recovered_count == 1  # 1 future job re-registered

    # Future job must be in APScheduler
    assert manager.get_job("job_future_123") is not None

    # Check database states
    async with session_factory() as session:
        repo = ScheduleRepository(session)

        f_sch = await repo.get_by_id(future_id)
        assert f_sch.status == ScheduleStatus.SCHEDULED.value

        o_sch = await repo.get_by_id(overdue_id)
        assert o_sch.status == ScheduleStatus.FAILED.value
        assert "Overdue" in (o_sch.last_error or "")

        orp_sch = await repo.get_by_id(orphaned_id)
        assert orp_sch.status == ScheduleStatus.FAILED.value
        assert "Orphaned" in (orp_sch.last_error or "")

    manager.shutdown()


# ------------------------------------------------------------------------------
# 5. REST API Integration Tests
# ------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_api_create_schedule_success(
    async_engine, approved_workflow_and_post, test_publishing_service, monkeypatch
):
    """Test POST /api/v1/schedules endpoint."""
    from backend.app.db.session import get_db_session

    wf, post = approved_workflow_and_post

    session_factory = async_sessionmaker(
        bind=async_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async def override_get_db():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_get_db

    # Attach manager to app.state
    manager = ScheduleManager(session_factory=session_factory, publishing_service=test_publishing_service)
    manager.start()
    app.state.schedule_manager = manager

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        future_time = (datetime.now(timezone.utc) + timedelta(hours=3)).isoformat()
        payload = {
            "workflow_id": wf.id,
            "scheduled_at": future_time,
            "timezone": "UTC",
        }
        resp = await client.post("/api/v1/schedules", json=payload)
        assert resp.status_code == 201
        data = resp.json()
        assert data["workflow_run_id"] == wf.id
        assert data["status"] == "SCHEDULED"
        assert data["timezone"] == "UTC"
        schedule_id = data["id"]

        # GET /api/v1/schedules/{id}
        get_resp = await client.get(f"/api/v1/schedules/{schedule_id}")
        assert get_resp.status_code == 200
        assert get_resp.json()["id"] == schedule_id

        # GET /api/v1/schedules (list)
        list_resp = await client.get("/api/v1/schedules")
        assert list_resp.status_code == 200
        list_data = list_resp.json()
        assert list_data["total"] >= 1
        assert any(s["id"] == schedule_id for s in list_data["schedules"])

        # GET /api/v1/workflows/{wf_id} should include schedules
        wf_resp = await client.get(f"/api/v1/workflows/{wf.id}")
        assert wf_resp.status_code == 200
        wf_data = wf_resp.json()
        assert len(wf_data["schedules"]) == 1
        assert wf_data["schedules"][0]["id"] == schedule_id

        # PATCH /api/v1/schedules/{id}
        new_time = (datetime.now(timezone.utc) + timedelta(hours=6)).isoformat()
        patch_resp = await client.patch(
            f"/api/v1/schedules/{schedule_id}",
            json={"scheduled_at": new_time, "timezone": "Asia/Tokyo"},
        )
        assert patch_resp.status_code == 200
        assert patch_resp.json()["timezone"] == "Asia/Tokyo"

        # DELETE /api/v1/schedules/{id}
        del_resp = await client.delete(f"/api/v1/schedules/{schedule_id}")
        assert del_resp.status_code == 200
        assert del_resp.json()["status"] == "CANCELLED"

    manager.shutdown()
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_api_schedule_run_now(
    async_engine, approved_workflow_and_post, test_publishing_service, mock_publisher
):
    """Test POST /api/v1/schedules/{id}/run manual trigger endpoint."""
    from backend.app.db.session import get_db_session

    wf, post = approved_workflow_and_post

    session_factory = async_sessionmaker(
        bind=async_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async def override_get_db():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_get_db

    manager = ScheduleManager(session_factory=session_factory, publishing_service=test_publishing_service)
    manager.start()
    app.state.schedule_manager = manager

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        # Create schedule
        future_time = (datetime.now(timezone.utc) + timedelta(hours=3)).isoformat()
        create_resp = await client.post(
            "/api/v1/schedules",
            json={"workflow_id": wf.id, "scheduled_at": future_time, "timezone": "UTC"},
        )
        assert create_resp.status_code == 201
        schedule_id = create_resp.json()["id"]

        # Run now
        run_resp = await client.post(f"/api/v1/schedules/{schedule_id}/run")
        assert run_resp.status_code == 200
        run_data = run_resp.json()
        assert run_data["status"] == "COMPLETED"
        assert run_data["executed_at"] is not None

    manager.shutdown()
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_api_schedule_error_responses(
    async_engine, approved_workflow_and_post, unapproved_workflow_and_post, test_publishing_service
):
    """Test API error status codes for validation, unapproved workflow, and non-existent schedule."""
    from backend.app.db.session import get_db_session

    approved_wf, _ = approved_workflow_and_post
    unapproved_wf, _ = unapproved_workflow_and_post

    session_factory = async_sessionmaker(
        bind=async_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async def override_get_db():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_get_db

    manager = ScheduleManager(session_factory=session_factory, publishing_service=test_publishing_service)
    manager.start()
    app.state.schedule_manager = manager

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        future_time = (datetime.now(timezone.utc) + timedelta(hours=3)).isoformat()
        past_time = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()

        # 1. Unapproved workflow -> 409 Conflict
        resp1 = await client.post(
            "/api/v1/schedules",
            json={"workflow_id": unapproved_wf.id, "scheduled_at": future_time, "timezone": "UTC"},
        )
        assert resp1.status_code == 409

        # 2. Past scheduled time -> 400 Bad Request
        resp2 = await client.post(
            "/api/v1/schedules",
            json={"workflow_id": approved_wf.id, "scheduled_at": past_time, "timezone": "UTC"},
        )
        assert resp2.status_code == 400

        # 3. Invalid timezone -> 400 Bad Request
        resp3 = await client.post(
            "/api/v1/schedules",
            json={"workflow_id": approved_wf.id, "scheduled_at": future_time, "timezone": "Bad/Zone"},
        )
        assert resp3.status_code == 400

        # 4. Get non-existent schedule -> 404
        resp4 = await client.get("/api/v1/schedules/non-existent-id")
        assert resp4.status_code == 404

        # 5. Cancel non-existent schedule -> 404
        resp5 = await client.delete("/api/v1/schedules/non-existent-id")
        assert resp5.status_code == 404

    manager.shutdown()
    app.dependency_overrides.clear()
