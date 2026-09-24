"""Integration tests for FastAPI Workflow and HITL Review REST API endpoints."""

from typing import Any
from unittest.mock import AsyncMock, patch
import pytest
from httpx import ASGITransport, AsyncClient
from langgraph.checkpoint.memory import MemorySaver
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.app.agents.critic import CriticAgent
from backend.app.agents.planning import PlanningAgent
from backend.app.agents.research import ResearchAgent
from backend.app.agents.writer import WriterAgent
from backend.app.db.models.post import Post
from backend.app.db.models.workflow import WorkflowRun
from backend.app.db.repositories.workflow_repo import PostRepository, WorkflowRepository
from backend.app.db.session import Base, get_db_session
from backend.app.main import app
from backend.app.models.content import SocialPost
from backend.app.models.critic import CriticResult, QualityChecks
from backend.app.models.planning import ContentPlan
from backend.app.models.research import ResearchRequest, ResearchResponse, Trend
from backend.app.services.workflow_service import WorkflowService
from backend.app.workflows.state import HumanReviewAction, WorkflowStatus


# ------------------------------------------------------------------------------
# Fixtures
# ------------------------------------------------------------------------------


@pytest.fixture
async def api_db_engine():
    """Create in-memory SQLite database for API testing."""
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
async def api_client(api_db_engine):
    """Yield an AsyncClient with mocked DB session dependency."""
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
    from backend.app.db.models.user import User

    test_user = User(
        id="test-user-id-0000",
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


def create_sample_research_response() -> ResearchResponse:
    trend = Trend(
        topic="Agentic AI in Enterprise Workflows",
        summary="Autonomous multi-agent loops automate complex software engineering workflows.",
        relevance_score=0.95,
        source="venturebeat.com",
        source_title="Enterprise Agents",
        url="https://venturebeat.com/ai/agentic-systems",
        keywords=["Agentic AI", "Enterprise"],
    )
    return ResearchResponse(
        request=ResearchRequest(niche="AI", platform="linkedin"),
        trends=[trend],
        total_results_found=1,
        status="success",
    )


def create_sample_content_plan() -> ContentPlan:
    return ContentPlan(
        topic="Agentic AI in Enterprise Workflows",
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
        source_references=["https://venturebeat.com/ai/agentic-systems"],
        selected_trend_topic="Agentic AI in Enterprise Workflows",
    )


def create_sample_social_post(content: str | None = None) -> SocialPost:
    return SocialPost(
        platform="linkedin",
        content=content or (
            "Why autonomous multi-agent loops change enterprise software development.\n\n"
            "Key takeaways:\n"
            "- Moving from prompt engineering to agent loops\n"
            "- 40% reduction in operational errors\n\n"
            "What agent pattern are you using today? Let's discuss below."
        ),
        topic="Agentic AI in Enterprise Workflows",
        language="English",
        content_type="single_post",
        hashtags=["#AgenticAI", "#MachineLearning"],
        cta="What agent pattern are you using today? Let's discuss below.",
        source_references=["https://venturebeat.com/ai/agentic-systems"],
    )


# ------------------------------------------------------------------------------
# API Tests
# ------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_api_start_workflow_and_get_details(api_client) -> None:
    """Test POST /api/v1/workflows/start runs to WAITING_FOR_HUMAN_REVIEW and GET retrieves details."""
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
        from backend.app.workflows.social_workflow import create_social_workflow
        mock_graph_factory.side_effect = lambda checkpointer=None: create_social_workflow(
            research_agent=mock_research,
            planning_agent=mock_planning,
            writer_agent=mock_writer,
            critic_agent=mock_critic,
            checkpointer=checkpointer or in_memory_saver,
        )

        # 1. Start Workflow
        start_payload = {
            "niche": "Artificial Intelligence",
            "audience": "AI Engineers",
            "platform": "linkedin",
            "language": "English",
        }
        res = await api_client.post("/api/v1/workflows/start", json=start_payload)
        assert res.status_code == 201
        data = res.json()
        assert data["status"] == "WAITING_FOR_HUMAN_REVIEW"
        assert len(data["posts"]) == 1
        assert data["posts"][0]["topic"] == "Agentic AI in Enterprise Workflows"
        assert len(data["posts"][0]["revisions"]) == 1
        assert data["posts"][0]["revisions"][0]["revision_source"] == "AGENT"
        workflow_id = data["id"]

        # 2. Get Workflow Details
        get_res = await api_client.get(f"/api/v1/workflows/{workflow_id}")
        assert get_res.status_code == 200
        get_data = get_res.json()
        assert get_data["id"] == workflow_id
        assert get_data["status"] == "WAITING_FOR_HUMAN_REVIEW"


@pytest.mark.asyncio
async def test_api_submit_review_approve_and_duplicate_conflict(api_client) -> None:
    """Test human APPROVE and verify duplicate reviews return 409 Conflict."""
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
        from backend.app.workflows.social_workflow import create_social_workflow
        mock_graph_factory.side_effect = lambda checkpointer=None: create_social_workflow(
            research_agent=mock_research,
            planning_agent=mock_planning,
            writer_agent=mock_writer,
            critic_agent=mock_critic,
            checkpointer=checkpointer or in_memory_saver,
        )

        # 1. Start Workflow
        start_payload = {"niche": "Artificial Intelligence", "platform": "linkedin"}
        res = await api_client.post("/api/v1/workflows/start", json=start_payload)
        workflow_id = res.json()["id"]

        # 2. Submit APPROVE Review
        review_payload = {"action": "APPROVE"}
        review_res = await api_client.post(f"/api/v1/workflows/{workflow_id}/review", json=review_payload)
        assert review_res.status_code == 200
        assert review_res.json()["status"] == "APPROVED"
        assert review_res.json()["posts"][0]["status"] == "APPROVED"

        # 3. Submit Duplicate APPROVE -> 409 Conflict
        dup_res = await api_client.post(f"/api/v1/workflows/{workflow_id}/review", json=review_payload)
        assert dup_res.status_code == 409
        assert "Invalid workflow state transition" in dup_res.json()["detail"]


@pytest.mark.asyncio
async def test_api_submit_review_revise_and_timeline(api_client) -> None:
    """Test human REVISE and verify revision timeline reflects HUMAN source."""
    mock_research = AsyncMock(spec=ResearchAgent)
    mock_research.research.return_value = create_sample_research_response()

    mock_planning = AsyncMock(spec=PlanningAgent)
    mock_planning.plan.return_value = create_sample_content_plan()

    post1 = create_sample_social_post("Draft 1 content.")
    post2 = create_sample_social_post("Draft 2 improved content.")

    mock_writer = AsyncMock(spec=WriterAgent)
    mock_writer.write.side_effect = [post1, post2]

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
        from backend.app.workflows.social_workflow import create_social_workflow
        mock_graph_factory.side_effect = lambda checkpointer=None: create_social_workflow(
            research_agent=mock_research,
            planning_agent=mock_planning,
            writer_agent=mock_writer,
            critic_agent=mock_critic,
            checkpointer=checkpointer or in_memory_saver,
        )

        # 1. Start Workflow
        start_payload = {"niche": "AI", "platform": "linkedin"}
        res = await api_client.post("/api/v1/workflows/start", json=start_payload)
        workflow_id = res.json()["id"]

        # 2. Submit REVISE
        revise_payload = {
            "action": "REVISE",
            "feedback": ["Add a stronger conclusion."],
        }
        rev_res = await api_client.post(f"/api/v1/workflows/{workflow_id}/review", json=revise_payload)
        assert rev_res.status_code == 200
        rev_data = rev_res.json()
        assert rev_data["status"] == "WAITING_FOR_HUMAN_REVIEW"
        assert rev_data["human_revision_count"] == 1
        assert rev_data["revision_count"] == 1

        # 3. Get Revisions Timeline
        timeline_res = await api_client.get(f"/api/v1/workflows/{workflow_id}/revisions")
        assert timeline_res.status_code == 200
        timeline = timeline_res.json()
        assert len(timeline) == 2
        assert timeline[0]["revision_source"] == "AGENT"
        assert timeline[1]["revision_source"] == "HUMAN"
        assert timeline[1]["content"] == post2.content


@pytest.mark.asyncio
async def test_api_submit_review_edit_and_reject(api_client) -> None:
    """Test human EDIT and REJECT actions."""
    mock_research = AsyncMock(spec=ResearchAgent)
    mock_research.research.return_value = create_sample_research_response()

    mock_planning = AsyncMock(spec=PlanningAgent)
    mock_planning.plan.return_value = create_sample_content_plan()

    mock_writer = AsyncMock(spec=WriterAgent)
    mock_writer.write.return_value = create_sample_social_post("Draft 1.")

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
        from backend.app.workflows.social_workflow import create_social_workflow
        mock_graph_factory.side_effect = lambda checkpointer=None: create_social_workflow(
            research_agent=mock_research,
            planning_agent=mock_planning,
            writer_agent=mock_writer,
            critic_agent=mock_critic,
            checkpointer=checkpointer or in_memory_saver,
        )

        # 1. Start Workflow
        start_payload = {"niche": "AI", "platform": "linkedin"}
        res = await api_client.post("/api/v1/workflows/start", json=start_payload)
        workflow_id = res.json()["id"]

        # 2. Submit EDIT
        edit_payload = {
            "action": "EDIT",
            "content": "Updated manually by human reviewer.",
        }
        edit_res = await api_client.post(f"/api/v1/workflows/{workflow_id}/review", json=edit_payload)
        assert edit_res.status_code == 200
        edit_data = edit_res.json()
        assert edit_data["human_revision_count"] == 1
        assert edit_data["posts"][0]["content"] == "Updated manually by human reviewer."

        # 3. Reject
        reject_payload = {"action": "REJECT"}
        reject_res = await api_client.post(f"/api/v1/workflows/{workflow_id}/review", json=reject_payload)
        assert reject_res.status_code == 200
        assert reject_res.json()["status"] == "REJECTED"


@pytest.mark.asyncio
async def test_api_submit_review_validation_errors(api_client) -> None:
    """Test validation errors: 404 nonexistent, 422 invalid payload, 400 missing content/feedback."""
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
        from backend.app.workflows.social_workflow import create_social_workflow
        mock_graph_factory.side_effect = lambda checkpointer=None: create_social_workflow(
            research_agent=mock_research,
            planning_agent=mock_planning,
            writer_agent=mock_writer,
            critic_agent=mock_critic,
            checkpointer=checkpointer or in_memory_saver,
        )

        # 1. Nonexistent workflow -> 404
        bad_id_res = await api_client.post("/api/v1/workflows/nonexistent-uuid/review", json={"action": "APPROVE"})
        assert bad_id_res.status_code == 404

        # 2. Start valid workflow
        start_res = await api_client.post("/api/v1/workflows/start", json={"niche": "AI", "platform": "linkedin"})
        wf_id = start_res.json()["id"]

        # 3. Invalid action enum -> 422
        bad_action_res = await api_client.post(f"/api/v1/workflows/{wf_id}/review", json={"action": "INVALID_ACTION"})
        assert bad_action_res.status_code == 422

        # 4. EDIT without content -> 400
        empty_edit_res = await api_client.post(f"/api/v1/workflows/{wf_id}/review", json={"action": "EDIT", "content": ""})
        assert empty_edit_res.status_code == 400
        assert "Direct EDIT action requires" in empty_edit_res.json()["detail"]

        # 5. REVISE without feedback -> 400
        empty_revise_res = await api_client.post(f"/api/v1/workflows/{wf_id}/review", json={"action": "REVISE", "feedback": []})
        assert empty_revise_res.status_code == 400
        assert "REVISE action requires actionable 'feedback'" in empty_revise_res.json()["detail"]

