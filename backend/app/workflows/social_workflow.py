"""LangGraph state machine orchestration for Research -> Planning -> Writer -> Critic -> Human Review workflow."""

import logging
from typing import Any, Callable, Awaitable

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import interrupt

from backend.app.agents.critic import CriticAgent
from backend.app.agents.planning import PlanningAgent
from backend.app.agents.research import ResearchAgent
from backend.app.agents.writer import WriterAgent
from backend.app.models.content import SocialPost, WriterRequest
from backend.app.models.critic import CriticResult, ReviewRequest
from backend.app.models.planning import ContentPlan, PlanningRequest
from backend.app.models.research import ResearchRequest, ResearchResponse
from backend.app.workflows.state import HumanReviewAction, SocialWorkflowState, WorkflowStatus

logger = logging.getLogger(__name__)


# Type alias for the optional stage persistence callback.
# Signature: async (stage: str, status: str) -> None
StageCallback = Callable[[str, str], Awaitable[None]]


def create_social_workflow(
    research_agent: ResearchAgent | None = None,
    planning_agent: PlanningAgent | None = None,
    writer_agent: WriterAgent | None = None,
    critic_agent: CriticAgent | None = None,
    llm_service: Any | None = None,
    checkpointer: BaseCheckpointSaver | None = None,
    stage_callback: StageCallback | None = None,
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
            return {}

        # Persist RESEARCHING stage to DB for frontend polling visibility
        if stage_callback:
            await stage_callback(WorkflowStatus.RESEARCHING.value, WorkflowStatus.RESEARCHING.value)

        request = state.get("request")
        if not request:
            logger.error("research_node failed: 'request' missing from workflow state.")
            return {
                "error": "ResearchRequest is missing from workflow state.",
                "status": WorkflowStatus.FAILED.value,
                "current_stage": WorkflowStatus.RESEARCHING.value,
            }

        logger.info("Executing research_node for niche: '%s'", request.niche)
        try:
            agent = get_research_agent()
            research_response: ResearchResponse = await agent.research(request)
            return {
                "research": research_response,
                "status": WorkflowStatus.PLANNING.value,
                "current_stage": WorkflowStatus.PLANNING.value,
                "error": None,
            }
        except Exception as err:
            logger.exception("research_node encountered an error: %s", err)
            return {
                "error": f"ResearchAgent error: {err}",
                "status": WorkflowStatus.FAILED.value,
                "current_stage": WorkflowStatus.RESEARCHING.value,
            }

    async def planning_node(state: SocialWorkflowState) -> dict[str, Any]:
        """Execute PlanningAgent to formulate structured content strategy."""
        if state.get("error"):
            return {}

        # Persist PLANNING stage to DB for frontend polling visibility
        if stage_callback:
            await stage_callback(WorkflowStatus.PLANNING.value, WorkflowStatus.PLANNING.value)

        research = state.get("research")
        request = state.get("request")
        if not research or not request:
            logger.error("planning_node failed: 'research' or 'request' missing from state.")
            return {
                "error": "ResearchResponse or ResearchRequest missing from workflow state.",
                "status": WorkflowStatus.FAILED.value,
                "current_stage": WorkflowStatus.PLANNING.value,
            }

        effective_niche = (
            request.niche.strip()
            if request.niche and request.niche.strip()
            else (research.trends[0].topic if research and research.trends else "Auto-Discovered Trend")
        )
        logger.info("Executing planning_node for niche: '%s'", effective_niche)
        try:
            planning_req = PlanningRequest(
                research=research,
                niche=effective_niche,
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
                "current_stage": WorkflowStatus.WRITING.value,
                "error": None,
            }
        except Exception as err:
            logger.exception("planning_node encountered an error: %s", err)
            return {
                "error": f"PlanningAgent error: {err}",
                "status": WorkflowStatus.FAILED.value,
                "current_stage": WorkflowStatus.PLANNING.value,
            }

    async def writer_node(state: SocialWorkflowState) -> dict[str, Any]:
        """Execute WriterAgent to generate or revise platform-tailored social copy."""
        if state.get("error"):
            return {}

        # Persist WRITING stage to DB for frontend polling visibility
        if stage_callback:
            await stage_callback(WorkflowStatus.WRITING.value, WorkflowStatus.WRITING.value)

        plan = state.get("content_plan")
        if not plan:
            logger.error("writer_node failed: 'content_plan' missing from state.")
            return {
                "error": "ContentPlan missing from workflow state.",
                "status": WorkflowStatus.FAILED.value,
                "current_stage": WorkflowStatus.WRITING.value,
            }

        request = state.get("request")
        effective_platform = request.platform if request else plan.platform
        revision_feedback = state.get("revision_feedback", [])
        previous_post = state.get("social_post")

        current_revisions = state.get("revision_count", 0)
        current_agent_revisions = state.get("agent_revision_count", 0)
        current_human_revisions = state.get("human_revision_count", 0)
        current_human_rejections = state.get("human_rejection_count", 0)
        revision_source = state.get("revision_source", "AGENT")

        is_revision = bool(
            (state.get("critic_result") and state["critic_result"].decision == "REVISE")
            or revision_feedback
        )

        new_agent_revisions = current_agent_revisions
        new_human_revisions = current_human_revisions

        if is_revision and previous_post is not None:
            if revision_source == "HUMAN":
                new_human_revisions = current_human_revisions
            else:
                new_agent_revisions = current_agent_revisions + 1
            new_revision_count = new_agent_revisions + new_human_revisions
        else:
            new_revision_count = current_revisions

        logger.info(
            "Executing writer_node for topic '%s' on '%s' (total revisions: %d, agent: %d, human: %d)",
            plan.topic,
            effective_platform,
            new_revision_count,
            new_agent_revisions,
            new_human_revisions,
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
                "agent_revision_count": new_agent_revisions,
                "human_revision_count": new_human_revisions,
                "human_rejection_count": current_human_rejections,
                "status": WorkflowStatus.CRITIQUING.value,
                "current_stage": WorkflowStatus.CRITIQUING.value,
                "error": None,
            }
        except Exception as err:
            logger.exception("writer_node encountered an error: %s", err)
            return {
                "error": f"WriterAgent error: {err}",
                "status": WorkflowStatus.FAILED.value,
                "current_stage": WorkflowStatus.WRITING.value,
            }

    async def critic_node(state: SocialWorkflowState) -> dict[str, Any]:
        """Execute CriticAgent to evaluate post quality, compliance, and grounding."""
        if state.get("error"):
            return {}

        # Persist CRITIQUING stage to DB for frontend polling visibility
        if stage_callback:
            await stage_callback(WorkflowStatus.CRITIQUING.value, WorkflowStatus.CRITIQUING.value)

        post = state.get("social_post")
        plan = state.get("content_plan")
        if not post or not plan:
            logger.error("critic_node failed: 'social_post' or 'content_plan' missing from state.")
            return {
                "error": "SocialPost or ContentPlan missing from workflow state.",
                "status": WorkflowStatus.FAILED.value,
                "current_stage": WorkflowStatus.CRITIQUING.value,
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

            agent_revisions = state.get("agent_revision_count", 0)
            max_revisions = state.get("max_revisions", 2)
            is_approved = critic_result.decision == "APPROVED"
            is_max_reached = agent_revisions >= max_revisions

            next_status = (
                WorkflowStatus.WAITING_FOR_HUMAN_REVIEW.value
                if (is_approved or is_max_reached)
                else WorkflowStatus.WRITING.value
            )

            # Determine the next current_stage based on routing
            if is_approved or is_max_reached:
                next_stage = WorkflowStatus.WAITING_FOR_HUMAN_REVIEW.value
            else:
                next_stage = WorkflowStatus.WRITING.value

            return {
                "critic_result": critic_result,
                "revision_feedback": combined_feedback,
                "status": next_status,
                "current_stage": next_stage,
                "human_review_required": bool(is_approved or is_max_reached),
                "error": None,
            }
        except Exception as err:
            logger.exception("critic_node encountered an error: %s", err)
            return {
                "error": f"CriticAgent error: {err}",
                "status": WorkflowStatus.FAILED.value,
                "current_stage": WorkflowStatus.CRITIQUING.value,
            }

    async def human_review_node(state: SocialWorkflowState) -> dict[str, Any]:
        """HITL interruption node pausing execution until human review decision is submitted."""
        if state.get("error"):
            return {}

        # Persist WAITING_FOR_HUMAN_REVIEW stage to DB for frontend polling visibility
        if stage_callback:
            await stage_callback(
                WorkflowStatus.WAITING_FOR_HUMAN_REVIEW.value,
                WorkflowStatus.WAITING_FOR_HUMAN_REVIEW.value,
            )

        logger.info(
            "Executing human_review_node (suspending for human review, total revisions: %d, rejections: %d)",
            state.get("revision_count", 0),
            state.get("human_rejection_count", 0),
        )

        review_prompt_data = {
            "action_required": "human_review",
            "topic": state["content_plan"].topic if state.get("content_plan") else "",
            "platform": state["request"].platform if state.get("request") else "linkedin",
            "current_post": state.get("social_post").model_dump() if state.get("social_post") else None,
            "critic_result": state.get("critic_result").model_dump() if state.get("critic_result") else None,
            "revision_count": state.get("revision_count", 0),
            "agent_revision_count": state.get("agent_revision_count", 0),
            "human_revision_count": state.get("human_revision_count", 0),
            "human_rejection_count": state.get("human_rejection_count", 0),
            "max_human_rejections": state.get("max_human_rejections", 3),
        }

        # LangGraph native interrupt suspending execution until Command(resume=...)
        review_data: dict[str, Any] = interrupt(review_prompt_data)

        action = str(review_data.get("action", HumanReviewAction.APPROVE.value)).upper()
        feedback_raw = review_data.get("feedback")
        if isinstance(feedback_raw, str):
            feedback_list = [feedback_raw]
        elif isinstance(feedback_raw, list):
            feedback_list = [str(item) for item in feedback_raw]
        else:
            feedback_list = []

        edited_content = review_data.get("content")

        current_tot = state.get("revision_count", 0)
        current_human = state.get("human_revision_count", 0)
        current_rejections = state.get("human_rejection_count", 0)
        max_human_rejections = state.get("max_human_rejections", 3)

        if action == HumanReviewAction.EDIT.value:
            updated_post = state.get("social_post")
            if updated_post and edited_content:
                updated_post = updated_post.model_copy(update={"content": edited_content})
            return {
                "human_decision": HumanReviewAction.EDIT.value,
                "social_post": updated_post,
                "edited_content": edited_content,
                "revision_source": "HUMAN",
                "human_revision_count": current_human + 1,
                "revision_count": current_tot + 1,
                "status": WorkflowStatus.CRITIQUING.value,
                "human_review_required": False,
            }
        elif action == HumanReviewAction.REVISE.value:
            return {
                "human_decision": HumanReviewAction.REVISE.value,
                "human_feedback": feedback_list,
                "revision_feedback": feedback_list,
                "revision_source": "HUMAN",
                "human_revision_count": current_human + 1,
                "revision_count": current_tot + 1,
                "status": WorkflowStatus.WRITING.value,
                "human_review_required": False,
            }
        elif action == HumanReviewAction.REJECT.value:
            if current_rejections < max_human_rejections:
                new_rejections = current_rejections + 1
                rejection_feedback = feedback_list or [
                    "Draft was rejected by human reviewer. Please generate a fresh, improved variation with an engaging angle."
                ]
                logger.info(
                    "Human rejected draft (attempt %d of %d). Routing back to writer for improvement.",
                    new_rejections,
                    max_human_rejections,
                )
                return {
                    "human_decision": HumanReviewAction.REJECT.value,
                    "human_rejection_count": new_rejections,
                    "human_feedback": feedback_list,
                    "revision_feedback": rejection_feedback,
                    "revision_source": "HUMAN",
                    "status": WorkflowStatus.WRITING.value,
                    "human_review_required": False,
                }
            else:
                logger.info(
                    "Human rejected draft and max rejections reached (%d/%d). Terminating workflow.",
                    current_rejections + 1,
                    max_human_rejections,
                )
                return {
                    "human_decision": HumanReviewAction.REJECT.value,
                    "human_rejection_count": current_rejections + 1,
                    "human_feedback": feedback_list,
                    "status": WorkflowStatus.REJECTED.value,
                    "human_review_required": False,
                }
        else:
            # Default APPROVE
            return {
                "human_decision": HumanReviewAction.APPROVE.value,
                "status": WorkflowStatus.APPROVED.value,
                "human_review_required": False,
            }

    async def finalize_node(state: SocialWorkflowState) -> dict[str, Any]:
        """Finalize workflow and ensure terminal status."""
        if state.get("error"):
            return {
                "status": WorkflowStatus.FAILED.value,
                "current_stage": state.get("current_stage", WorkflowStatus.FAILED.value),
            }

        decision = state.get("human_decision")
        if decision == HumanReviewAction.REJECT.value and state.get("status") == WorkflowStatus.REJECTED.value:
            final_status = WorkflowStatus.REJECTED.value
        elif decision == HumanReviewAction.APPROVE.value:
            final_status = WorkflowStatus.APPROVED.value
        else:
            final_status = state.get("status", WorkflowStatus.APPROVED.value)

        logger.info("Workflow completed with final status: %s", final_status)
        return {
            "status": final_status,
            "current_stage": final_status,
            "human_review_required": False,
        }

    # --------------------------------------------------------------------------
    # Conditional Edge Routers
    # --------------------------------------------------------------------------

    def route_after_critic(state: SocialWorkflowState) -> str:
        """Route conditionally based on Critic decision and bounded revision limits."""
        if state.get("error"):
            logger.warning("Workflow state has error; routing to end.")
            return "finalize"

        critic_result = state.get("critic_result")
        if not critic_result:
            logger.warning("No CriticResult found in state; routing to human_review.")
            return "human_review"

        if critic_result.decision == "APPROVED":
            logger.info("Critic approved post; routing to human_review_node.")
            return "human_review"

        # REVISE path with bounded autonomous agent revision loop
        agent_revision_count = state.get("agent_revision_count", 0)
        max_revisions = state.get("max_revisions", 2)

        if agent_revision_count < max_revisions:
            logger.info(
                "Critic requested REVISE (agent cycle %d < max %d); routing back to writer_node.",
                agent_revision_count,
                max_revisions,
            )
            return "writer"

        logger.info(
            "Critic requested REVISE but max_revisions reached (%d/%d); routing to human_review_node.",
            agent_revision_count,
            max_revisions,
        )
        return "human_review"

    def route_after_human_review(state: SocialWorkflowState) -> str:
        """Route conditionally based on human decision."""
        if state.get("error"):
            return "finalize"

        decision = state.get("human_decision")
        if decision == HumanReviewAction.REVISE.value:
            logger.info("Human requested REVISE; routing to writer_node.")
            return "writer"
        elif decision == HumanReviewAction.EDIT.value:
            logger.info("Human submitted EDIT; routing to critic_node for validation.")
            return "critic"
        elif decision == HumanReviewAction.REJECT.value:
            if state.get("status") == WorkflowStatus.WRITING.value:
                logger.info(
                    "Human submitted REJECT (rejection %d/%d); routing back to writer_node for improvement.",
                    state.get("human_rejection_count", 0),
                    state.get("max_human_rejections", 3),
                )
                return "writer"
            logger.info("Human submitted terminal REJECT; routing to finalize.")
            return "finalize"
        else:
            logger.info("Human submitted APPROVE; routing to finalize.")
            return "finalize"

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
    builder.add_node("finalize", finalize_node)

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
            "finalize": "finalize",
        },
    )

    # Add conditional routing after human review
    builder.add_conditional_edges(
        "human_review",
        route_after_human_review,
        {
            "writer": "writer",
            "critic": "critic",
            "finalize": "finalize",
        },
    )

    builder.add_edge("finalize", END)

    return builder.compile(checkpointer=checkpointer)
