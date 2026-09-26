"""Unit and integration tests for workflow execution stage visibility and stage callbacks."""

from unittest.mock import AsyncMock

import pytest

from backend.app.agents.critic import CriticAgent
from backend.app.agents.planning import PlanningAgent
from backend.app.agents.research import ResearchAgent
from backend.app.agents.writer import WriterAgent
from backend.app.models.content import SocialPost
from backend.app.models.critic import CriticResult, QualityChecks
from backend.app.models.planning import ContentPlan
from backend.app.models.research import (
    ResearchRequest,
    ResearchResponse,
    Trend,
)
from backend.app.services.llm import LLMService
from backend.app.workflows.social_workflow import create_social_workflow
from backend.app.workflows.state import SocialWorkflowState, WorkflowStatus


# ------------------------------------------------------------------------------
# Fixtures and Helpers
# ------------------------------------------------------------------------------


def create_sample_research_request() -> ResearchRequest:
    """Create a sample ResearchRequest."""
    return ResearchRequest(
        niche="Artificial Intelligence",
        audience="AI Engineers and Students",
        platform="linkedin",
        keywords=["agents", "reasoning"],
    )


def create_sample_research_response() -> ResearchResponse:
    """Create a sample ResearchResponse."""
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
        request=create_sample_research_request(),
        trends=[trend],
        total_results_found=1,
        status="success",
    )


def create_sample_content_plan() -> ContentPlan:
    """Create a sample ContentPlan."""
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
    )


def create_sample_social_post() -> SocialPost:
    """Create a sample SocialPost."""
    return SocialPost(
        platform="linkedin",
        topic="Agentic AI in Enterprise Workflows",
        content="Autonomous multi-agent loops automate complex workflows.\n\nKey takeaways:\n- Error correction cycles\n- Structured state machines\n\nWhat agent pattern are you using?",
        character_count=180,
        content_type="single_post",
        hashtags=["#AI", "#SoftwareEngineering"],
        cta="What agent pattern are you using?",
        source_references=["https://venturebeat.com/ai/agentic-systems"],
    )


# ------------------------------------------------------------------------------
# Tests for Stage Visibility Callbacks & Preserving Failure Stages
# ------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_stage_callbacks_called_in_sequence():
    """Verify that stage_callback is called with RESEARCHING, PLANNING, WRITING, CRITIQUING, WAITING_FOR_HUMAN_REVIEW."""
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

    recorded_stages = []

    async def mock_stage_callback(stage: str, status: str) -> None:
        recorded_stages.append((stage, status))

    workflow = create_social_workflow(
        research_agent=mock_research,
        planning_agent=mock_planning,
        writer_agent=mock_writer,
        critic_agent=mock_critic,
        stage_callback=mock_stage_callback,
    )

    initial_state: SocialWorkflowState = {
        "request": create_sample_research_request(),
        "revision_count": 0,
        "max_revisions": 2,
        "status": WorkflowStatus.STARTING.value,
    }

    final_state = await workflow.ainvoke(initial_state)

    # Check that each stage callback was invoked in correct chronological order
    expected_stage_calls = [
        (WorkflowStatus.RESEARCHING.value, WorkflowStatus.RESEARCHING.value),
        (WorkflowStatus.PLANNING.value, WorkflowStatus.PLANNING.value),
        (WorkflowStatus.WRITING.value, WorkflowStatus.WRITING.value),
        (WorkflowStatus.CRITIQUING.value, WorkflowStatus.CRITIQUING.value),
        (WorkflowStatus.WAITING_FOR_HUMAN_REVIEW.value, WorkflowStatus.WAITING_FOR_HUMAN_REVIEW.value),
    ]

    assert recorded_stages == expected_stage_calls
    assert final_state["status"] == WorkflowStatus.WAITING_FOR_HUMAN_REVIEW.value
    assert final_state["current_stage"] == WorkflowStatus.WAITING_FOR_HUMAN_REVIEW.value


@pytest.mark.asyncio
async def test_research_failure_preserves_researching_stage():
    """Verify that failure in research_node preserves current_stage = RESEARCHING and status = FAILED."""
    mock_research = AsyncMock(spec=ResearchAgent)
    mock_research.research.side_effect = RuntimeError("Tavily API quota exceeded")

    recorded_stages = []

    async def mock_stage_callback(stage: str, status: str) -> None:
        recorded_stages.append((stage, status))

    workflow = create_social_workflow(
        research_agent=mock_research,
        stage_callback=mock_stage_callback,
    )

    initial_state: SocialWorkflowState = {
        "request": create_sample_research_request(),
        "status": WorkflowStatus.STARTING.value,
    }

    final_state = await workflow.ainvoke(initial_state)

    assert final_state["status"] == WorkflowStatus.FAILED.value
    assert final_state["current_stage"] == WorkflowStatus.RESEARCHING.value
    assert "Tavily API quota exceeded" in final_state["error"]
    assert recorded_stages == [(WorkflowStatus.RESEARCHING.value, WorkflowStatus.RESEARCHING.value)]


@pytest.mark.asyncio
async def test_planning_failure_preserves_planning_stage():
    """Verify that failure in planning_node preserves current_stage = PLANNING and status = FAILED (not RESEARCHING)."""
    mock_research = AsyncMock(spec=ResearchAgent)
    mock_research.research.return_value = create_sample_research_response()

    mock_planning = AsyncMock(spec=PlanningAgent)
    mock_planning.plan.side_effect = ValueError("LLM generated invalid plan schema")

    recorded_stages = []

    async def mock_stage_callback(stage: str, status: str) -> None:
        recorded_stages.append((stage, status))

    workflow = create_social_workflow(
        research_agent=mock_research,
        planning_agent=mock_planning,
        stage_callback=mock_stage_callback,
    )

    initial_state: SocialWorkflowState = {
        "request": create_sample_research_request(),
        "status": WorkflowStatus.STARTING.value,
    }

    final_state = await workflow.ainvoke(initial_state)

    assert final_state["status"] == WorkflowStatus.FAILED.value
    assert final_state["current_stage"] == WorkflowStatus.PLANNING.value
    assert final_state["current_stage"] != WorkflowStatus.RESEARCHING.value
    assert "LLM generated invalid plan schema" in final_state["error"]
    assert recorded_stages == [
        (WorkflowStatus.RESEARCHING.value, WorkflowStatus.RESEARCHING.value),
        (WorkflowStatus.PLANNING.value, WorkflowStatus.PLANNING.value),
    ]


@pytest.mark.asyncio
async def test_writing_failure_preserves_writing_stage():
    """Verify that failure in writer_node preserves current_stage = WRITING and status = FAILED."""
    mock_research = AsyncMock(spec=ResearchAgent)
    mock_research.research.return_value = create_sample_research_response()

    mock_planning = AsyncMock(spec=PlanningAgent)
    mock_planning.plan.return_value = create_sample_content_plan()

    mock_writer = AsyncMock(spec=WriterAgent)
    mock_writer.write.side_effect = TimeoutError("Gemini API connection timed out")

    recorded_stages = []

    async def mock_stage_callback(stage: str, status: str) -> None:
        recorded_stages.append((stage, status))

    workflow = create_social_workflow(
        research_agent=mock_research,
        planning_agent=mock_planning,
        writer_agent=mock_writer,
        stage_callback=mock_stage_callback,
    )

    initial_state: SocialWorkflowState = {
        "request": create_sample_research_request(),
        "status": WorkflowStatus.STARTING.value,
    }

    final_state = await workflow.ainvoke(initial_state)

    assert final_state["status"] == WorkflowStatus.FAILED.value
    assert final_state["current_stage"] == WorkflowStatus.WRITING.value
    assert "Gemini API connection timed out" in final_state["error"]
    assert (WorkflowStatus.WRITING.value, WorkflowStatus.WRITING.value) in recorded_stages


@pytest.mark.asyncio
async def test_critic_failure_preserves_critiquing_stage():
    """Verify that failure in critic_node preserves current_stage = CRITIQUING and status = FAILED."""
    mock_research = AsyncMock(spec=ResearchAgent)
    mock_research.research.return_value = create_sample_research_response()

    mock_planning = AsyncMock(spec=PlanningAgent)
    mock_planning.plan.return_value = create_sample_content_plan()

    mock_writer = AsyncMock(spec=WriterAgent)
    mock_writer.write.return_value = create_sample_social_post()

    mock_critic = AsyncMock(spec=CriticAgent)
    mock_critic.review.side_effect = RuntimeError("Critic evaluation model crashed")

    recorded_stages = []

    async def mock_stage_callback(stage: str, status: str) -> None:
        recorded_stages.append((stage, status))

    workflow = create_social_workflow(
        research_agent=mock_research,
        planning_agent=mock_planning,
        writer_agent=mock_writer,
        critic_agent=mock_critic,
        stage_callback=mock_stage_callback,
    )

    initial_state: SocialWorkflowState = {
        "request": create_sample_research_request(),
        "status": WorkflowStatus.STARTING.value,
    }

    final_state = await workflow.ainvoke(initial_state)

    assert final_state["status"] == WorkflowStatus.FAILED.value
    assert final_state["current_stage"] == WorkflowStatus.CRITIQUING.value
    assert "Critic evaluation model crashed" in final_state["error"]
    assert (WorkflowStatus.CRITIQUING.value, WorkflowStatus.CRITIQUING.value) in recorded_stages


@pytest.mark.asyncio
async def test_workflow_backward_compatibility_without_callback():
    """Verify that workflow executes identically when stage_callback is None."""
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

    workflow = create_social_workflow(
        research_agent=mock_research,
        planning_agent=mock_planning,
        writer_agent=mock_writer,
        critic_agent=mock_critic,
        stage_callback=None,
    )

    initial_state: SocialWorkflowState = {
        "request": create_sample_research_request(),
        "revision_count": 0,
        "max_revisions": 2,
        "status": WorkflowStatus.STARTING.value,
    }

    final_state = await workflow.ainvoke(initial_state)

    assert final_state["status"] == WorkflowStatus.WAITING_FOR_HUMAN_REVIEW.value
    assert final_state["current_stage"] == WorkflowStatus.WAITING_FOR_HUMAN_REVIEW.value
