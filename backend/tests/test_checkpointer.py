"""Unit and integration tests for LangGraph Checkpointing and persistence across restarts."""

import os
import tempfile
import pytest
from unittest.mock import AsyncMock

from langgraph.checkpoint.memory import MemorySaver
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.types import Command

from backend.app.agents.critic import CriticAgent
from backend.app.agents.planning import PlanningAgent
from backend.app.agents.research import ResearchAgent
from backend.app.agents.writer import WriterAgent
from backend.app.config import Settings
from backend.app.models.content import SocialPost
from backend.app.models.critic import CriticResult, QualityChecks
from backend.app.models.planning import ContentPlan
from backend.app.models.research import ResearchRequest, ResearchResponse, Trend
from backend.app.workflows.checkpointer import (
    create_in_memory_checkpointer,
    get_workflow_checkpointer,
)
from backend.app.workflows.social_workflow import create_social_workflow
from backend.app.workflows.state import SocialWorkflowState, WorkflowStatus


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
async def test_in_memory_checkpointer_creation() -> None:
    """Verify in-memory checkpointer factory creates a valid MemorySaver."""
    saver = create_in_memory_checkpointer()
    assert isinstance(saver, MemorySaver)

    cfg = Settings(checkpointer_type="memory")
    async with get_workflow_checkpointer(cfg) as checkpointer:
        assert isinstance(checkpointer, MemorySaver)


@pytest.mark.asyncio
async def test_sqlite_checkpointer_persistence_and_restart() -> None:
    """Verify that SQLite checkpointer persists state and resumes correctly after simulated server restart."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = os.path.join(tmp_dir, "test_checkpoints.db")

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

        thread_id = "test-thread-persistence-uuid"
        config = {"configurable": {"thread_id": thread_id}}

        # Phase 1: Run workflow on Server Instance 1 until interrupt
        async with AsyncSqliteSaver.from_conn_string(db_path) as saver1:
            graph1 = create_social_workflow(
                research_agent=mock_research,
                planning_agent=mock_planning,
                writer_agent=mock_writer,
                critic_agent=mock_critic,
                checkpointer=saver1,
            )

            initial_state: SocialWorkflowState = {
                "request": create_sample_research_request(),
                "revision_count": 0,
                "agent_revision_count": 0,
                "human_revision_count": 0,
                "max_revisions": 2,
                "status": WorkflowStatus.STARTING.value,
            }

            state1 = await graph1.ainvoke(initial_state, config=config)
            assert state1["status"] == WorkflowStatus.WAITING_FOR_HUMAN_REVIEW.value
            assert "__interrupt__" in state1

            snap1 = await graph1.aget_state(config)
            assert snap1.next == ("human_review",)
            assert len(snap1.tasks) == 1
            assert len(snap1.tasks[0].interrupts) == 1

        # Phase 2: Simulate complete server shutdown & restart with Server Instance 2
        async with AsyncSqliteSaver.from_conn_string(db_path) as saver2:
            graph2 = create_social_workflow(
                research_agent=mock_research,
                planning_agent=mock_planning,
                writer_agent=mock_writer,
                critic_agent=mock_critic,
                checkpointer=saver2,
            )

            # Inspect persistent state from fresh graph instance
            snap2 = await graph2.aget_state(config)
            assert snap2.next == ("human_review",)
            assert snap2.values["status"] == WorkflowStatus.WAITING_FOR_HUMAN_REVIEW.value
            assert snap2.values["social_post"] is not None

            # Resume execution on fresh server instance with APPROVE
            resumed_state = await graph2.ainvoke(
                Command(resume={"action": "APPROVE"}),
                config=config,
            )

            assert resumed_state["status"] == WorkflowStatus.APPROVED.value
            assert resumed_state["human_decision"] == "APPROVE"

            snap_final = await graph2.aget_state(config)
            assert snap_final.next == ()
