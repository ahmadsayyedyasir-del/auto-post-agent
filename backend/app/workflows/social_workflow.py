"""LangGraph state machine orchestration for Research -> Planning -> Writer -> Critic workflow."""

import logging
from typing import Any, Callable

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from backend.app.agents.critic import CriticAgent
from backend.app.agents.planning import PlanningAgent
from backend.app.agents.research import ResearchAgent
from backend.app.agents.writer import WriterAgent
from backend.app.models.content import SocialPost, WriterRequest
from backend.app.models.critic import CriticResult, ReviewRequest
from backend.app.models.planning import ContentPlan, PlanningRequest
from backend.app.models.research import ResearchRequest, ResearchResponse
from backend.app.workflows.state import SocialWorkflowState, WorkflowStatus

logger = logging.getLogger(__name__)


def create_social_workflow(
    research_agent: ResearchAgent | None = None,
    planning_agent: PlanningAgent | None = None,
    writer_agent: WriterAgent | None = None,
    critic_agent: CriticAgent | None = None,
    llm_service: Any | None = None,
) -> CompiledStateGraph:
    """Construct and compile the multi-agent social media content workflow using LangGraph."""
    # Lazy/injected agent resolution
    def get_research_agent() -> ResearchAgent:
        nonlocal research_agent
        if research_agent is None:
            research_agent = ResearchAgent(llm_service=llm_service)
        return research_agent

    def get_planning_agent() -> PlanningAgent:
        nonlocal planning_agent
        if planning_agent is None:
            planning_agent = PlanningAgent(llm_service=llm_service)
        return planning_agent

    def get_writer_agent() -> WriterAgent:
        nonlocal writer_agent
        if writer_agent is None:
            writer_agent = WriterAgent(llm_service=llm_service)
        return writer_agent

    def get_critic_agent() -> CriticAgent:
        nonlocal critic_agent
        if critic_agent is None:
            critic_agent = CriticAgent(llm_service=llm_service)
        return critic_agent

    # --------------------------------------------------------------------------
    # Node Definitions
    # --------------------------------------------------------------------------

    async def research_node(state: SocialWorkflowState) -> dict[str, Any]:
        """Execute ResearchAgent to discover trends and source evidence."""
        if state.get("error"):
            return {"status": WorkflowStatus.FAILED.value}

        request = state.get("request")
        if not request:
            logger.error("research_node failed: 'request' missing from workflow state.")
            return {
                "error": "ResearchRequest is missing from workflow state.",
                "status": WorkflowStatus.FAILED.value,
            }

        logger.info("Executing research_node for niche: '%s'", request.niche)
        try:
            agent = get_research_agent()
            research_response: ResearchResponse = await agent.research(request)
            return {
                "research": research_response,
                "status": WorkflowStatus.PLANNING.value,
                "error": None,
            }
        except Exception as err:
            logger.exception("research_node encountered an error: %s", err)
            return {
                "error": f"ResearchAgent error: {err}",
                "status": WorkflowStatus.FAILED.value,
            }

    async def planning_node(state: SocialWorkflowState) -> dict[str, Any]:
        """Execute PlanningAgent to formulate structured content strategy."""
        if state.get("error"):
            return {"status": WorkflowStatus.FAILED.value}

        research = state.get("research")
        request = state.get("request")
        if not research or not request:
            logger.error("planning_node failed: 'research' or 'request' missing from state.")
            return {
                "error": "ResearchResponse or ResearchRequest missing from workflow state.",
                "status": WorkflowStatus.FAILED.value,
            }

        logger.info("Executing planning_node for niche: '%s'", request.niche)
        try:
            planning_req = PlanningRequest(
                research=research,
                niche=request.niche,
                audience=request.audience,
                platform=request.platform,
                language=request.language,
                content_goal="educational",
            )
            agent = get_planning_agent()
            content_plan: ContentPlan = await agent.plan(planning_req)
            return {
                "content_plan": content_plan,
                "status": WorkflowStatus.WRITING.value,
                "error": None,
            }
        except Exception as err:
            logger.exception("planning_node encountered an error: %s", err)
            return {
                "error": f"PlanningAgent error: {err}",
                "status": WorkflowStatus.FAILED.value,
            }

    async def writer_node(state: SocialWorkflowState) -> dict[str, Any]:
        """Execute WriterAgent to generate or revise platform-tailored social copy."""
        if state.get("error"):
            return {"status": WorkflowStatus.FAILED.value}

        plan = state.get("content_plan")
        if not plan:
            logger.error("writer_node failed: 'content_plan' missing from state.")
            return {
                "error": "ContentPlan missing from workflow state.",
                "status": WorkflowStatus.FAILED.value,
            }

        request = state.get("request")
        effective_platform = request.platform if request else plan.platform
        revision_feedback = state.get("revision_feedback", [])
        previous_post = state.get("social_post")

        # Track revision count when revising
        current_revisions = state.get("revision_count", 0)
        is_revision = bool(state.get("critic_result") and state["critic_result"].decision == "REVISE")
        new_revision_count = current_revisions + (1 if is_revision else 0)

        logger.info(
            "Executing writer_node for topic '%s' on '%s' (revision cycle: %d)",
            plan.topic,
            effective_platform,
            new_revision_count,
        )

        try:
            writer_req = WriterRequest(
                plan=plan,
                platform=effective_platform,
                audience=request.audience if request else plan.audience,
                language=request.language if request else plan.language,
                tone=plan.tone,
                revision_feedback=revision_feedback,
                previous_post=previous_post,
            )
            agent = get_writer_agent()
            social_post: SocialPost = await agent.write(writer_req)
            return {
                "social_post": social_post,
                "revision_count": new_revision_count,
                "status": WorkflowStatus.CRITIQUING.value,
                "error": None,
            }
        except Exception as err:
            logger.exception("writer_node encountered an error: %s", err)
            return {
                "error": f"WriterAgent error: {err}",
                "status": WorkflowStatus.FAILED.value,
            }

    async def critic_node(state: SocialWorkflowState) -> dict[str, Any]:
        """Execute CriticAgent to evaluate post quality, compliance, and grounding."""
        if state.get("error"):
            return {"status": WorkflowStatus.FAILED.value}

        post = state.get("social_post")
        plan = state.get("content_plan")
        if not post or not plan:
            logger.error("critic_node failed: 'social_post' or 'content_plan' missing from state.")
            return {
                "error": "SocialPost or ContentPlan missing from workflow state.",
                "status": WorkflowStatus.FAILED.value,
            }

        research = state.get("research")
        logger.info("Executing critic_node for topic '%s'", post.topic)

        try:
            review_req = ReviewRequest(
                post=post,
                plan=plan,
                research=research,
            )
            agent = get_critic_agent()
            critic_result: CriticResult = await agent.review(review_req)

            # Consolidate actionable feedback for potential revision
            combined_feedback: list[str] = []
            if critic_result.feedback:
                combined_feedback.extend(critic_result.feedback)
            if critic_result.issues:
                for issue in critic_result.issues:
                    if issue not in combined_feedback:
                        combined_feedback.append(issue)

            return {
                "critic_result": critic_result,
                "revision_feedback": combined_feedback,
                "status": (
                    WorkflowStatus.WAITING_FOR_HUMAN_REVIEW.value
                    if critic_result.decision == "APPROVED"
                    else WorkflowStatus.WRITING.value
                ),
                "error": None,
            }
        except Exception as err:
            logger.exception("critic_node encountered an error: %s", err)
            return {
                "error": f"CriticAgent error: {err}",
                "status": WorkflowStatus.FAILED.value,
            }

    async def human_review_node(state: SocialWorkflowState) -> dict[str, Any]:
        """Final workflow checkpoint establishing human review readiness."""
        logger.info(
            "Executing human_review_node (final status: WAITING_FOR_HUMAN_REVIEW, revision_count: %d)",
            state.get("revision_count", 0),
        )
        return {
            "status": WorkflowStatus.WAITING_FOR_HUMAN_REVIEW.value,
            "human_review_required": True,
        }

    # --------------------------------------------------------------------------
    # Conditional Edge Router
    # --------------------------------------------------------------------------

    def route_after_critic(state: SocialWorkflowState) -> str:
        """Route conditionally based on Critic decision and bounded revision limits."""
        if state.get("error"):
            logger.warning("Workflow state has error; routing to end.")
            return "end"

        critic_result = state.get("critic_result")
        if not critic_result:
            logger.warning("No CriticResult found in state; routing to human_review.")
            return "human_review"

        if critic_result.decision == "APPROVED":
            logger.info("Critic approved post; routing to human_review_node.")
            return "human_review"

        # REVISE path with bounded revision loop
        revision_count = state.get("revision_count", 0)
        max_revisions = state.get("max_revisions", 2)

        if revision_count < max_revisions:
            logger.info(
                "Critic requested REVISE (cycle %d < max %d); routing back to writer_node.",
                revision_count,
                max_revisions,
            )
            return "writer"

        logger.info(
            "Critic requested REVISE but max_revisions reached (%d/%d); routing to human_review_node.",
            revision_count,
            max_revisions,
        )
        return "human_review"

    # --------------------------------------------------------------------------
    # Graph Construction
    # --------------------------------------------------------------------------

    builder = StateGraph(SocialWorkflowState)

    # Add nodes
    builder.add_node("research", research_node)
    builder.add_node("planning", planning_node)
    builder.add_node("writer", writer_node)
    builder.add_node("critic", critic_node)
    builder.add_node("human_review", human_review_node)

    # Add edges
    builder.add_edge(START, "research")
    builder.add_edge("research", "planning")
    builder.add_edge("planning", "writer")
    builder.add_edge("writer", "critic")

    # Add conditional routing after critic
    builder.add_conditional_edges(
        "critic",
        route_after_critic,
        {
            "writer": "writer",
            "human_review": "human_review",
            "end": END,
        },
    )

    builder.add_edge("human_review", END)

    return builder.compile()
