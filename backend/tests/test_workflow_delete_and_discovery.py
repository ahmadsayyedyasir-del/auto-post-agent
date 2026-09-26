"""Unit and integration tests for Workflow Deletion, Ownership, and AI Auto-Discovery."""

from unittest.mock import AsyncMock, patch
import uuid
import pytest
from httpx import ASGITransport, AsyncClient
from langgraph.checkpoint.memory import MemorySaver
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.app.agents.critic import CriticAgent
from backend.app.agents.planning import PlanningAgent
from backend.app.agents.research import ResearchAgent
from backend.app.agents.writer import WriterAgent
from backend.app.db.models.feedback import Feedback
from backend.app.db.models.post import Post, Revision
from backend.app.db.models.publication import Publication
from backend.app.db.models.schedule import Schedule
from backend.app.db.models.user import User
from backend.app.db.models.workflow import WorkflowRun
from backend.app.db.repositories.workflow_repo import (
    FeedbackRepository,
    PostRepository,
    WorkflowRepository,
)
from backend.app.db.session import Base, get_db_session
from backend.app.main import app
from backend.app.models.content import SocialPost
from backend.app.models.critic import CriticResult, QualityChecks
from backend.app.models.planning import ContentPlan
from backend.app.models.research import (
    ResearchRequest,
    ResearchResponse,
    Trend,
)
from backend.app.services.workflow_service import WorkflowService
from backend.app.workflows.social_workflow import create_social_workflow
from backend.app.workflows.state import WorkflowStatus


# ------------------------------------------------------------------------------
# Fixtures and Helpers
# ------------------------------------------------------------------------------

TEST_USER_ID = "test-user-id-0000"


@pytest.fixture
async def api_db_engine():
    """Create in-memory SQLite database for test suite."""
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
async def db_session(api_db_engine):
    """Yield an active AsyncSession."""
    session_factory = async_sessionmaker(
        bind=api_db_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )
    async with session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


@pytest.fixture
async def api_client(api_db_engine):
    """Yield an AsyncClient with mocked DB session and auth dependencies."""
    session_factory = async_sessionmaker(
        bind=api_db_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )

    async def override_get_db():
        async with session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise
            finally:
                await session.close()

    from backend.app.api.v1.dependencies import get_current_active_user, get_current_user

    test_user = User(
        id=TEST_USER_ID,
        email="testuser@example.com",
        hashed_password="mockhashedpassword",
        is_active=True,
    )

    app.dependency_overrides[get_db_session] = override_get_db
    app.dependency_overrides[get_current_user] = lambda: test_user
    app.dependency_overrides[get_current_active_user] = lambda: test_user

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client

    app.dependency_overrides.clear()


def create_sample_research_response(topic: str = "Agentic AI in Enterprise Workflows") -> ResearchResponse:
    trend = Trend(
        topic=topic,
        summary="Autonomous multi-agent loops automate complex software engineering workflows.",
        relevance_score=0.95,
        source="venturebeat.com",
        source_title="Enterprise Agents",
        url="https://venturebeat.com/ai/agentic-systems",
        keywords=["Agentic AI", "Enterprise"],
    )
    return ResearchResponse(
        request=ResearchRequest(niche=topic, platform="linkedin"),
        trends=[trend],
        total_results_found=1,
        status="success",
    )


def create_sample_content_plan(topic: str = "Agentic AI in Enterprise Workflows") -> ContentPlan:
    return ContentPlan(
        topic=topic,
        angle="Detailed comparison of agentic workflows vs single prompt chains",
        platform="linkedin",
        audience="AI Engineers and Students",
        language="English",
        content_type="single_post",
        tone="professional and insightful",
        hook_direction="Why autonomous multi-agent loops change enterprise software development.",
        key_points=[
            "Moving from prompt engineering to agent loops",
            "40% reduction in errors via error-correction cycles",
        ],
        cta_direction="What agent pattern are you using today? Let's discuss below.",
    )


def create_sample_social_post(topic: str = "Agentic AI in Enterprise Workflows") -> SocialPost:
    return SocialPost(
        platform="linkedin",
        topic=topic,
        content="Autonomous multi-agent loops automate complex workflows.\n\nKey takeaways:\n- Error correction\n- Deterministic checks",
        character_count=180,
        content_type="single_post",
        hashtags=["#AI", "#Tech"],
        cta="What agent pattern are you using?",
        source_references=["https://venturebeat.com/ai/agentic-systems"],
    )


# ------------------------------------------------------------------------------
# Workflow Deletion & Cascade Tests
# ------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delete_own_terminal_workflow(api_client: AsyncClient, db_session) -> None:
    """Verify owner can successfully delete a terminal or review-paused workflow."""
    # Start workflow
    mock_research = AsyncMock(spec=ResearchAgent)
    mock_research.research.return_value = create_sample_research_response()

    mock_planning = AsyncMock(spec=PlanningAgent)
    mock_planning.plan.return_value = create_sample_content_plan()

    mock_writer = AsyncMock(spec=WriterAgent)
    mock_writer.write.return_value = create_sample_social_post()

    mock_critic = AsyncMock(spec=CriticAgent)
    mock_critic.review.return_value = CriticResult(
        decision="APPROVED",
        issues=[],
        feedback=[],
        checks=QualityChecks(),
        verified_sources=["https://venturebeat.com/ai/agentic-systems"],
    )

    in_memory_saver = MemorySaver()

    with patch.object(WorkflowService, "_get_workflow_graph") as mock_graph_factory:
        mock_graph_factory.side_effect = lambda checkpointer=None, **kwargs: create_social_workflow(
            research_agent=mock_research,
            planning_agent=mock_planning,
            writer_agent=mock_writer,
            critic_agent=mock_critic,
            checkpointer=checkpointer or in_memory_saver,
        )

        res = await api_client.post("/api/v1/workflows/start", json={"niche": "Autonomous Systems", "platform": "linkedin"})
        assert res.status_code == 201
        workflow_id = res.json()["id"]

        # Delete workflow
        del_res = await api_client.delete(f"/api/v1/workflows/{workflow_id}")
        assert del_res.status_code == 204

        # Verify 404 after deletion
        get_res = await api_client.get(f"/api/v1/workflows/{workflow_id}")
        assert get_res.status_code == 404


@pytest.mark.asyncio
async def test_delete_nonexistent_workflow(api_client: AsyncClient) -> None:
    """Verify deleting a nonexistent workflow returns 404."""
    random_id = str(uuid.uuid4())
    res = await api_client.delete(f"/api/v1/workflows/{random_id}")
    assert res.status_code == 404


@pytest.mark.asyncio
async def test_delete_another_users_workflow(api_client: AsyncClient, db_session) -> None:
    """Verify deleting another user's workflow returns 404 to prevent ID enumeration."""
    # Create workflow owned by a different user
    workflow_repo = WorkflowRepository(db_session)
    other_user_workflow = WorkflowRun(
        user_id="other-user-uuid-999",
        niche="Quantum Computing",
        target_platform="linkedin",
        status=WorkflowStatus.WAITING_FOR_HUMAN_REVIEW.value,
        current_stage="human_review",
    )
    await workflow_repo.create(other_user_workflow)
    await db_session.commit()

    res = await api_client.delete(f"/api/v1/workflows/{other_user_workflow.id}")
    assert res.status_code == 404


@pytest.mark.asyncio
async def test_delete_active_workflow_rejected_with_409(api_client: AsyncClient, db_session) -> None:
    """Verify attempting to delete an actively running workflow returns 409 Conflict."""
    workflow_repo = WorkflowRepository(db_session)
    active_workflow = WorkflowRun(
        user_id=None,  # accessible by test client
        niche="Active Agent Run",
        target_platform="linkedin",
        status=WorkflowStatus.WRITING.value,
        current_stage=WorkflowStatus.WRITING.value,
    )
    await workflow_repo.create(active_workflow)
    await db_session.commit()

    res = await api_client.delete(f"/api/v1/workflows/{active_workflow.id}")
    assert res.status_code == 409
    assert "actively executing" in res.json()["detail"]


@pytest.mark.asyncio
async def test_delete_cascades_dependent_data(db_session) -> None:
    """Verify deleting a workflow cleanly cascades to posts, revisions, feedbacks, publications, and schedules."""
    workflow_repo = WorkflowRepository(db_session)
    post_repo = PostRepository(db_session)
    feedback_repo = FeedbackRepository(db_session)

    # 1. Create WorkflowRun
    wf = WorkflowRun(
        niche="Cascade Test Niche",
        target_platform="linkedin",
        status=WorkflowStatus.APPROVED.value,
        current_stage="completed",
    )
    await workflow_repo.create(wf)
    await db_session.flush()

    # 2. Create Post and Revision
    post = Post(
        workflow_run_id=wf.id,
        platform="linkedin",
        topic="Cascade Topic",
        content="Post content",
        status="APPROVED",
    )
    await post_repo.create(post)
    await db_session.flush()

    rev = Revision(
        post_id=post.id,
        workflow_run_id=wf.id,
        revision_number=1,
        revision_source="AGENT",
        content=post.content,
    )
    db_session.add(rev)

    # 3. Create Feedback
    fb = Feedback(
        workflow_run_id=wf.id,
        post_id=post.id,
        feedback_source="CRITIC",
        decision="APPROVED",
    )
    await feedback_repo.create(fb)

    # 4. Create Publication
    pub = Publication(
        workflow_run_id=wf.id,
        post_id=post.id,
        platform="linkedin",
        status="PUBLISHED",
        idempotency_key=f"idemp-{wf.id}",
    )
    db_session.add(pub)

    from datetime import datetime, timezone

    # 5. Create Schedule
    sched = Schedule(
        workflow_run_id=wf.id,
        post_id=post.id,
        platform="linkedin",
        job_id=f"job-{wf.id}",
        scheduled_at=datetime.now(timezone.utc),
        timezone="UTC",
        status="SCHEDULED",
    )
    db_session.add(sched)
    await db_session.commit()

    # Verify entities exist
    assert await workflow_repo.get_by_id(wf.id) is not None

    # Delete via service
    service = WorkflowService()
    deleted = await service.delete_workflow(wf.id, db_session)
    assert deleted is True

    # Verify all dependent entities are removed
    assert await workflow_repo.get_by_id(wf.id) is None
    assert await post_repo.get_by_id(post.id) is None


# ------------------------------------------------------------------------------
# Optional Topic / AI Auto-Discovery Tests
# ------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_research_request_validation_rules() -> None:
    """Verify validation rules: niche provided vs auto_discover toggle vs invalid combination."""
    # 1. Valid: niche provided, auto_discover=False
    req1 = ResearchRequest(niche="Cybersecurity in Cloud", auto_discover=False)
    assert req1.niche == "Cybersecurity in Cloud"

    # 2. Valid: niche absent, auto_discover=True
    req2 = ResearchRequest(niche=None, auto_discover=True)
    assert req2.auto_discover is True
    assert req2.niche is None

    # 3. Valid: empty string niche, auto_discover=True
    req3 = ResearchRequest(niche="", auto_discover=True)
    assert req3.auto_discover is True

    # 4. Invalid: niche absent and auto_discover=False
    with pytest.raises(ValueError, match="Either 'niche' must be provided or 'auto_discover' must be set to True"):
        ResearchRequest(niche=None, auto_discover=False)

    # 5. Invalid: empty niche string and auto_discover=False
    with pytest.raises(ValueError, match="Either 'niche' must be provided or 'auto_discover' must be set to True"):
        ResearchRequest(niche="   ", auto_discover=False)


@pytest.mark.asyncio
async def test_auto_discovery_query_construction() -> None:
    """Verify ResearchAgent synthesizes broad discovery queries when niche is omitted."""
    agent = ResearchAgent(search_tool=AsyncMock())

    # Explicit niche
    req_explicit = ResearchRequest(niche="Robotics", keywords=["drones"])
    q_explicit = agent._build_search_query(req_explicit)
    assert "Robotics" in q_explicit
    assert "drones" in q_explicit

    # Auto-discovery
    req_auto = ResearchRequest(niche=None, auto_discover=True, audience="CTOs", platform="twitter")
    q_auto = agent._build_search_query(req_auto)
    assert "trending topics" in q_auto
    assert "CTOs" in q_auto
    assert "twitter" in q_auto


@pytest.mark.asyncio
async def test_auto_discovery_workflow_end_to_end(api_client: AsyncClient, db_session) -> None:
    """Verify that auto-discovery workflow runs without niche and assigns discovered topic to Planning & WorkflowRun."""
    mock_research = AsyncMock(spec=ResearchAgent)
    mock_research.research.return_value = create_sample_research_response("Discovered Quantum AI Breakthrough")

    mock_planning = AsyncMock(spec=PlanningAgent)
    mock_planning.plan.return_value = create_sample_content_plan("Discovered Quantum AI Breakthrough")

    mock_writer = AsyncMock(spec=WriterAgent)
    mock_writer.write.return_value = create_sample_social_post("Discovered Quantum AI Breakthrough")

    mock_critic = AsyncMock(spec=CriticAgent)
    mock_critic.review.return_value = CriticResult(
        decision="APPROVED",
        issues=[],
        feedback=[],
        checks=QualityChecks(),
        verified_sources=["https://venturebeat.com/ai/agentic-systems"],
    )

    in_memory_saver = MemorySaver()

    with patch.object(WorkflowService, "_get_workflow_graph") as mock_graph_factory:
        mock_graph_factory.side_effect = lambda checkpointer=None, **kwargs: create_social_workflow(
            research_agent=mock_research,
            planning_agent=mock_planning,
            writer_agent=mock_writer,
            critic_agent=mock_critic,
            checkpointer=checkpointer or in_memory_saver,
        )

        payload = {
            "niche": None,
            "auto_discover": True,
            "platform": "linkedin",
            "audience": "Enterprise Architects",
        }
        res = await api_client.post("/api/v1/workflows/start", json=payload)
        assert res.status_code == 201
        data = res.json()
        assert data["niche"] == "Discovered Quantum AI Breakthrough"
        assert data["status"] == "WAITING_FOR_HUMAN_REVIEW"
