"""Comprehensive integration tests for LangGraph Human-in-the-Loop (HITL) pause, resume, revision, and edit validation."""

from unittest.mock import AsyncMock
import pytest
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command

from backend.app.agents.critic import CriticAgent
from backend.app.agents.planning import PlanningAgent
from backend.app.agents.research import ResearchAgent
from backend.app.agents.writer import WriterAgent
from backend.app.models.content import SocialPost, WriterRequest
from backend.app.models.critic import CriticResult, QualityChecks, ReviewRequest
from backend.app.models.planning import ContentPlan
from backend.app.models.research import ResearchRequest, ResearchResponse, Trend
from backend.app.workflows.social_workflow import create_social_workflow
from backend.app.workflows.state import HumanReviewAction, SocialWorkflowState, WorkflowStatus


def create_sample_research_request() -> ResearchRequest:
    return ResearchRequest(
        niche="Artificial Intelligence",
        audience="AI Engineers and Students",
        platform="linkedin",
        keywords=["agents", "reasoning"],
    )


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
        request=create_sample_research_request(),
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


@pytest.mark.asyncio
async def test_workflow_pause_at_human_review() -> None:
    """Verify workflow executes through Critic and pauses cleanly at human_review node."""
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

    checkpointer = MemorySaver()
    workflow = create_social_workflow(
        research_agent=mock_research,
        planning_agent=mock_planning,
        writer_agent=mock_writer,
        critic_agent=mock_critic,
        checkpointer=checkpointer,
    )

    config = {"configurable": {"thread_id": "thread-hitl-pause"}}
    initial_state: SocialWorkflowState = {
        "request": create_sample_research_request(),
        "revision_count": 0,
        "agent_revision_count": 0,
        "human_revision_count": 0,
        "max_revisions": 2,
        "status": WorkflowStatus.STARTING.value,
    }

    state = await workflow.ainvoke(initial_state, config=config)

    assert state["status"] == WorkflowStatus.WAITING_FOR_HUMAN_REVIEW.value
    assert "__interrupt__" in state

    snapshot = await workflow.aget_state(config)
    assert snapshot.next == ("human_review",)
    assert len(snapshot.tasks) == 1
    assert snapshot.values["social_post"] is not None
    assert snapshot.values["critic_result"].decision == "APPROVED"


@pytest.mark.asyncio
async def test_workflow_resume_after_approve() -> None:
    """Verify resuming with APPROVE finalizes workflow with terminal APPROVED status."""
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

    checkpointer = MemorySaver()
    workflow = create_social_workflow(
        research_agent=mock_research,
        planning_agent=mock_planning,
        writer_agent=mock_writer,
        critic_agent=mock_critic,
        checkpointer=checkpointer,
    )

    config = {"configurable": {"thread_id": "thread-hitl-approve"}}
    initial_state: SocialWorkflowState = {
        "request": create_sample_research_request(),
        "revision_count": 0,
        "agent_revision_count": 0,
        "human_revision_count": 0,
        "max_revisions": 2,
        "status": WorkflowStatus.STARTING.value,
    }

    await workflow.ainvoke(initial_state, config=config)

    # Resume with APPROVE
    resumed_state = await workflow.ainvoke(
        Command(resume={"action": HumanReviewAction.APPROVE.value}),
        config=config,
    )

    assert resumed_state["status"] == WorkflowStatus.APPROVED.value
    assert resumed_state["human_decision"] == HumanReviewAction.APPROVE.value
    assert resumed_state.get("human_review_required") is False

    snapshot = await workflow.aget_state(config)
    assert snapshot.next == ()


@pytest.mark.asyncio
async def test_workflow_resume_after_reject() -> None:
    """Verify resuming with REJECT transitions workflow to terminal REJECTED status."""
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

    checkpointer = MemorySaver()
    workflow = create_social_workflow(
        research_agent=mock_research,
        planning_agent=mock_planning,
        writer_agent=mock_writer,
        critic_agent=mock_critic,
        checkpointer=checkpointer,
    )

    config = {"configurable": {"thread_id": "thread-hitl-reject"}}
    initial_state: SocialWorkflowState = {
        "request": create_sample_research_request(),
        "revision_count": 0,
        "agent_revision_count": 0,
        "human_revision_count": 0,
        "max_revisions": 2,
        "status": WorkflowStatus.STARTING.value,
    }

    await workflow.ainvoke(initial_state, config=config)

    # Resume with REJECT
    resumed_state = await workflow.ainvoke(
        Command(resume={"action": HumanReviewAction.REJECT.value}),
        config=config,
    )

    assert resumed_state["status"] == WorkflowStatus.REJECTED.value
    assert resumed_state["human_decision"] == HumanReviewAction.REJECT.value


@pytest.mark.asyncio
async def test_workflow_resume_after_revise_preserves_state() -> None:
    """Verify resuming with REVISE routes to Writer -> Critic -> Human Review inside graph."""
    mock_research = AsyncMock(spec=ResearchAgent)
    mock_research.research.return_value = create_sample_research_response()

    mock_planning = AsyncMock(spec=PlanningAgent)
    mock_planning.plan.return_value = create_sample_content_plan()

    post_v1 = create_sample_social_post("Draft 1 with technical jargon.")
    post_v2 = create_sample_social_post("Draft 2 simplified for students.")

    mock_writer = AsyncMock(spec=WriterAgent)
    mock_writer.write.side_effect = [post_v1, post_v2]

    critic_ok = CriticResult(
        decision="APPROVED",
        issues=[],
        feedback=[],
        checks=QualityChecks(),
        verified_sources=["https://venturebeat.com/ai/agentic-systems"],
    )

    mock_critic = AsyncMock(spec=CriticAgent)
    mock_critic.review.return_value = critic_ok

    checkpointer = MemorySaver()
    workflow = create_social_workflow(
        research_agent=mock_research,
        planning_agent=mock_planning,
        writer_agent=mock_writer,
        critic_agent=mock_critic,
        checkpointer=checkpointer,
    )

    config = {"configurable": {"thread_id": "thread-hitl-revise"}}
    initial_state: SocialWorkflowState = {
        "request": create_sample_research_request(),
        "revision_count": 0,
        "agent_revision_count": 0,
        "human_revision_count": 0,
        "max_revisions": 2,
        "status": WorkflowStatus.STARTING.value,
    }

    # First pass: pauses at Human Review
    await workflow.ainvoke(initial_state, config=config)
    assert mock_writer.write.call_count == 1
    assert mock_critic.review.call_count == 1

    # Resume with REVISE
    human_feedback_text = "Simplify explanations for beginner students."
    resumed_state = await workflow.ainvoke(
        Command(resume={
            "action": HumanReviewAction.REVISE.value,
            "feedback": [human_feedback_text],
        }),
        config=config,
    )

    # Verifies writer was called a second time with human feedback and previous post
    assert mock_writer.write.call_count == 2
    assert mock_critic.review.call_count == 2

    second_writer_req: WriterRequest = mock_writer.write.call_args_list[1][0][0]
    assert human_feedback_text in second_writer_req.revision_feedback
    assert second_writer_req.previous_post == post_v1

    # Pauses at Human Review again!
    assert resumed_state["status"] == WorkflowStatus.WAITING_FOR_HUMAN_REVIEW.value
    assert resumed_state["human_revision_count"] == 1
    assert resumed_state["revision_count"] == 1
    assert resumed_state["revision_source"] == "HUMAN"
    assert resumed_state["social_post"].content == post_v2.content

    # Finally approve
    final_state = await workflow.ainvoke(
        Command(resume={"action": HumanReviewAction.APPROVE.value}),
        config=config,
    )
    assert final_state["status"] == WorkflowStatus.APPROVED.value


@pytest.mark.asyncio
async def test_human_edit_validation_routing() -> None:
    """Verify that human EDIT routes to Critic for quality validation before approval."""
    mock_research = AsyncMock(spec=ResearchAgent)
    mock_research.research.return_value = create_sample_research_response()

    mock_planning = AsyncMock(spec=PlanningAgent)
    mock_planning.plan.return_value = create_sample_content_plan()

    mock_writer = AsyncMock(spec=WriterAgent)
    mock_writer.write.return_value = create_sample_social_post("Draft 1 content.")

    mock_critic = AsyncMock(spec=CriticAgent)
    mock_critic.review.return_value = CriticResult(
        decision="APPROVED",
        issues=[],
        feedback=[],
        checks=QualityChecks(),
        verified_sources=["https://venturebeat.com/ai/agentic-systems"],
    )

    checkpointer = MemorySaver()
    workflow = create_social_workflow(
        research_agent=mock_research,
        planning_agent=mock_planning,
        writer_agent=mock_writer,
        critic_agent=mock_critic,
        checkpointer=checkpointer,
    )

    config = {"configurable": {"thread_id": "thread-hitl-edit"}}
    initial_state: SocialWorkflowState = {
        "request": create_sample_research_request(),
        "revision_count": 0,
        "agent_revision_count": 0,
        "human_revision_count": 0,
        "max_revisions": 2,
        "status": WorkflowStatus.STARTING.value,
    }

    # First pass
    await workflow.ainvoke(initial_state, config=config)
    assert mock_critic.review.call_count == 1

    # Human submits direct EDIT
    edited_text = "This is manually edited content by human editor."
    resumed_state = await workflow.ainvoke(
        Command(resume={
            "action": HumanReviewAction.EDIT.value,
            "content": edited_text,
        }),
        config=config,
    )

    # Critic was invoked again to validate human edit
    assert mock_critic.review.call_count == 2
    critic_second_call_req: ReviewRequest = mock_critic.review.call_args_list[1][0][0]
    assert critic_second_call_req.post.content == edited_text

    assert resumed_state["social_post"].content == edited_text
    assert resumed_state["human_revision_count"] == 1
    assert resumed_state["revision_source"] == "HUMAN"
