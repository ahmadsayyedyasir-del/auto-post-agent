"""Unit and integration tests for LangGraph orchestration workflow and state transitions."""

from typing import Any
from unittest.mock import AsyncMock

import pytest

from backend.app.agents.critic import CriticAgent
from backend.app.agents.planning import PlanningAgent
from backend.app.agents.research import ResearchAgent
from backend.app.agents.writer import WriterAgent
from backend.app.models.content import SocialPost, WriterRequest
from backend.app.models.critic import CriticResult, QualityChecks, ReviewRequest
from backend.app.models.planning import ContentPlan, PlanningRequest
from backend.app.models.research import (
    ResearchRequest,
    ResearchResponse,
    Trend,
)
from backend.app.services.llm import LLMProvider, LLMService
from backend.app.workflows.social_workflow import create_social_workflow
from backend.app.workflows.state import SocialWorkflowState, WorkflowStatus


# ------------------------------------------------------------------------------
# Fixtures and Helpers
# ------------------------------------------------------------------------------


def create_mock_llm_service() -> LLMService:
    """Create a dummy LLMService to allow offline agent instantiation."""
    class DummyProvider(LLMProvider):
        @property
        def provider_name(self) -> str:
            return "dummy"

        @property
        def model_name(self) -> str:
            return "dummy-model"

        async def generate(self, prompt: str, system_prompt: str | None = None, **kwargs: Any) -> str:
            return ""

        async def generate_structured(
            self,
            schema: type[Any],
            prompt: str,
            system_prompt: str | None = None,
            **kwargs: Any,
        ) -> Any:
            return None

    return LLMService(provider=DummyProvider())


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
        source_references=["https://venturebeat.com/ai/agentic-systems"],
        selected_trend_topic="Agentic AI in Enterprise Workflows",
    )


def create_sample_social_post(content: str | None = None) -> SocialPost:
    """Create a sample SocialPost."""
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
# 1. Graph Compilation Tests
# ------------------------------------------------------------------------------


def test_social_workflow_graph_compilation() -> None:
    """Verify LangGraph workflow compiles cleanly and defines required nodes."""
    workflow = create_social_workflow(llm_service=create_mock_llm_service())
    assert workflow is not None
    graph_repr = workflow.get_graph()
    node_names = set(graph_repr.nodes.keys())
    assert "research" in node_names
    assert "planning" in node_names
    assert "writer" in node_names
    assert "critic" in node_names
    assert "human_review" in node_names


# ------------------------------------------------------------------------------
# 2. Happy Path Workflow Execution Tests
# ------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_workflow_happy_path_approved() -> None:
    """Verify end-to-end happy path: Research -> Planning -> Writer -> Critic (APPROVED) -> Human Review."""
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
        llm_service=create_mock_llm_service(),
    )

    initial_state: SocialWorkflowState = {
        "request": create_sample_research_request(),
        "revision_count": 0,
        "max_revisions": 2,
        "status": WorkflowStatus.STARTING.value,
    }

    final_state = await workflow.ainvoke(initial_state)

    assert final_state["status"] == WorkflowStatus.WAITING_FOR_HUMAN_REVIEW.value
    assert final_state["human_review_required"] is True
    assert final_state["revision_count"] == 0
    assert final_state["critic_result"].decision == "APPROVED"
    assert final_state["social_post"] is not None
    assert final_state["content_plan"] is not None
    assert final_state["research"] is not None
    assert final_state.get("error") is None

    assert mock_research.research.call_count == 1
    assert mock_planning.plan.call_count == 1
    assert mock_writer.write.call_count == 1
    assert mock_critic.review.call_count == 1


# ------------------------------------------------------------------------------
# 3. Revision Loop Tests
# ------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_workflow_single_revision_path() -> None:
    """Verify revision path: Writer -> Critic (REVISE) -> Writer (revised) -> Critic (APPROVED)."""
    mock_research = AsyncMock(spec=ResearchAgent)
    mock_research.research.return_value = create_sample_research_response()

    mock_planning = AsyncMock(spec=PlanningAgent)
    mock_planning.plan.return_value = create_sample_content_plan()

    post_v1 = create_sample_social_post("Draft 1 with weak hook.")
    post_v2 = create_sample_social_post("Draft 2 with improved punchy hook.")

    mock_writer = AsyncMock(spec=WriterAgent)
    mock_writer.write.side_effect = [post_v1, post_v2]

    critic_revise = CriticResult(
        decision="REVISE",
        issues=["Weak opening hook."],
        feedback=["Make the opening hook punchy and bold."],
        checks=QualityChecks(clarity=False),
    )
    critic_approve = CriticResult(
        decision="APPROVED",
        issues=[],
        feedback=[],
        checks=QualityChecks(),
    )

    mock_critic = AsyncMock(spec=CriticAgent)
    mock_critic.review.side_effect = [critic_revise, critic_approve]

    workflow = create_social_workflow(
        research_agent=mock_research,
        planning_agent=mock_planning,
        writer_agent=mock_writer,
        critic_agent=mock_critic,
        llm_service=create_mock_llm_service(),
    )

    initial_state: SocialWorkflowState = {
        "request": create_sample_research_request(),
        "revision_count": 0,
        "max_revisions": 2,
        "status": WorkflowStatus.STARTING.value,
    }

    final_state = await workflow.ainvoke(initial_state)

    assert final_state["status"] == WorkflowStatus.WAITING_FOR_HUMAN_REVIEW.value
    assert final_state["revision_count"] == 1
    assert final_state["critic_result"].decision == "APPROVED"
    assert final_state["social_post"].content == post_v2.content

    assert mock_writer.write.call_count == 2
    assert mock_critic.review.call_count == 2

    # Verify revision feedback and previous_post were passed to Writer
    second_writer_call_arg: WriterRequest = mock_writer.write.call_args_list[1][0][0]
    assert any("hook" in fb.lower() for fb in second_writer_call_arg.revision_feedback)
    assert second_writer_call_arg.previous_post == post_v1


@pytest.mark.asyncio
async def test_workflow_max_revisions_bounded_termination() -> None:
    """Verify that continuous REVISE decisions terminate cleanly at max_revisions and route to Human Review."""
    mock_research = AsyncMock(spec=ResearchAgent)
    mock_research.research.return_value = create_sample_research_response()

    mock_planning = AsyncMock(spec=PlanningAgent)
    mock_planning.plan.return_value = create_sample_content_plan()

    mock_writer = AsyncMock(spec=WriterAgent)
    mock_writer.write.return_value = create_sample_social_post()

    mock_critic = AsyncMock(spec=CriticAgent)
    mock_critic.review.return_value = CriticResult(
        decision="REVISE",
        issues=["Tone is not optimal."],
        feedback=["Adjust tone."],
        checks=QualityChecks(tone=False),
    )

    max_revisions = 2
    workflow = create_social_workflow(
        research_agent=mock_research,
        planning_agent=mock_planning,
        writer_agent=mock_writer,
        critic_agent=mock_critic,
        llm_service=create_mock_llm_service(),
    )

    initial_state: SocialWorkflowState = {
        "request": create_sample_research_request(),
        "revision_count": 0,
        "max_revisions": max_revisions,
        "status": WorkflowStatus.STARTING.value,
    }

    final_state = await workflow.ainvoke(initial_state)

    assert final_state["status"] == WorkflowStatus.WAITING_FOR_HUMAN_REVIEW.value
    assert final_state["human_review_required"] is True
    assert final_state["revision_count"] == max_revisions
    assert final_state["critic_result"].decision == "REVISE"

    assert mock_writer.write.call_count == 1 + max_revisions
    assert mock_critic.review.call_count == 1 + max_revisions


# ------------------------------------------------------------------------------
# 4. Error Handling and State Integrity Tests
# ------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_workflow_handles_research_failure() -> None:
    """Verify workflow sets FAILED status when ResearchAgent fails."""
    mock_research = AsyncMock(spec=ResearchAgent)
    mock_research.research.side_effect = RuntimeError("Search provider timeout")

    workflow = create_social_workflow(
        research_agent=mock_research,
        llm_service=create_mock_llm_service(),
    )

    initial_state: SocialWorkflowState = {
        "request": create_sample_research_request(),
        "status": WorkflowStatus.STARTING.value,
    }

    final_state = await workflow.ainvoke(initial_state)

    assert final_state["status"] == WorkflowStatus.FAILED.value
    assert "Search provider timeout" in final_state["error"]


@pytest.mark.asyncio
async def test_workflow_handles_planning_failure() -> None:
    """Verify workflow sets FAILED status when PlanningAgent fails."""
    mock_research = AsyncMock(spec=ResearchAgent)
    mock_research.research.return_value = create_sample_research_response()

    mock_planning = AsyncMock(spec=PlanningAgent)
    mock_planning.plan.side_effect = RuntimeError("Planning validation error")

    workflow = create_social_workflow(
        research_agent=mock_research,
        planning_agent=mock_planning,
        llm_service=create_mock_llm_service(),
    )

    initial_state: SocialWorkflowState = {
        "request": create_sample_research_request(),
        "status": WorkflowStatus.STARTING.value,
    }

    final_state = await workflow.ainvoke(initial_state)

    assert final_state["status"] == WorkflowStatus.FAILED.value
    assert "Planning validation error" in final_state["error"]


@pytest.mark.asyncio
async def test_workflow_handles_writer_failure() -> None:
    """Verify workflow sets FAILED status when WriterAgent fails."""
    mock_research = AsyncMock(spec=ResearchAgent)
    mock_research.research.return_value = create_sample_research_response()

    mock_planning = AsyncMock(spec=PlanningAgent)
    mock_planning.plan.return_value = create_sample_content_plan()

    mock_writer = AsyncMock(spec=WriterAgent)
    mock_writer.write.side_effect = RuntimeError("LLM context window exhausted")

    workflow = create_social_workflow(
        research_agent=mock_research,
        planning_agent=mock_planning,
        writer_agent=mock_writer,
        llm_service=create_mock_llm_service(),
    )

    initial_state: SocialWorkflowState = {
        "request": create_sample_research_request(),
        "status": WorkflowStatus.STARTING.value,
    }

    final_state = await workflow.ainvoke(initial_state)

    assert final_state["status"] == WorkflowStatus.FAILED.value
    assert "LLM context window exhausted" in final_state["error"]


@pytest.mark.asyncio
async def test_workflow_handles_critic_failure() -> None:
    """Verify workflow sets FAILED status when CriticAgent fails."""
    mock_research = AsyncMock(spec=ResearchAgent)
    mock_research.research.return_value = create_sample_research_response()

    mock_planning = AsyncMock(spec=PlanningAgent)
    mock_planning.plan.return_value = create_sample_content_plan()

    mock_writer = AsyncMock(spec=WriterAgent)
    mock_writer.write.return_value = create_sample_social_post()

    mock_critic = AsyncMock(spec=CriticAgent)
    mock_critic.review.side_effect = RuntimeError("Critic parsing error")

    workflow = create_social_workflow(
        research_agent=mock_research,
        planning_agent=mock_planning,
        writer_agent=mock_writer,
        critic_agent=mock_critic,
        llm_service=create_mock_llm_service(),
    )

    initial_state: SocialWorkflowState = {
        "request": create_sample_research_request(),
        "status": WorkflowStatus.STARTING.value,
    }

    final_state = await workflow.ainvoke(initial_state)

    assert final_state["status"] == WorkflowStatus.FAILED.value
    assert "Critic parsing error" in final_state["error"]


@pytest.mark.asyncio
async def test_workflow_state_completeness_for_future_frontend() -> None:
    """Verify that final workflow state exposes all information required by frontend/API."""
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
        llm_service=create_mock_llm_service(),
    )

    final_state = await workflow.ainvoke({
        "request": create_sample_research_request(),
        "status": WorkflowStatus.STARTING.value,
    })

    assert "request" in final_state
    assert "research" in final_state
    assert "content_plan" in final_state
    assert "social_post" in final_state
    assert "critic_result" in final_state
    assert "status" in final_state
    assert "human_review_required" in final_state
    assert "revision_count" in final_state
    assert final_state["status"] == WorkflowStatus.WAITING_FOR_HUMAN_REVIEW.value
