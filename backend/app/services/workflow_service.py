"""Workflow orchestration service coordinating database persistence and LangGraph HITL execution."""

import logging
from typing import Any

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.types import Command
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.agents.critic import CriticAgent
from backend.app.agents.planning import PlanningAgent
from backend.app.agents.research import ResearchAgent
from backend.app.agents.writer import WriterAgent
from backend.app.config import get_settings
from backend.app.db.models.feedback import Feedback
from backend.app.db.models.post import Post
from backend.app.db.models.workflow import WorkflowRun
from backend.app.db.repositories.workflow_repo import (
    FeedbackRepository,
    PostRepository,
    WorkflowRepository,
)
from backend.app.models.research import ResearchRequest
from backend.app.services.llm import LLMService
from backend.app.workflows.checkpointer import get_workflow_checkpointer
from backend.app.workflows.social_workflow import create_social_workflow
from backend.app.workflows.state import HumanReviewAction, SocialWorkflowState, WorkflowStatus

logger = logging.getLogger(__name__)


class WorkflowService:
    """Service managing workflow execution lifecycle, human reviews, and database synchronization."""

    def __init__(
        self,
        llm_service: LLMService | None = None,
        research_agent: ResearchAgent | None = None,
        planning_agent: PlanningAgent | None = None,
        writer_agent: WriterAgent | None = None,
        critic_agent: CriticAgent | None = None,
        checkpointer: BaseCheckpointSaver | None = None,
    ) -> None:
        self.llm_service = llm_service
        self.research_agent = research_agent
        self.planning_agent = planning_agent
        self.writer_agent = writer_agent
        self.critic_agent = critic_agent
        self.checkpointer = checkpointer

    @staticmethod
    def _create_stage_callback(
        workflow_id: str,
        session: AsyncSession,
    ):
        """Create an async callback that persists stage transitions to the DB during graph execution.

        This enables frontend polling to observe intermediate stages (RESEARCHING, PLANNING, etc.)
        instead of only seeing the final state after ainvoke completes.
        """
        async def _persist_stage(stage: str, status: str) -> None:
            repo = WorkflowRepository(session)
            await repo.update_status(
                workflow_id=workflow_id,
                status=status,
                current_stage=stage,
            )
            await session.commit()

        return _persist_stage

    def _get_workflow_graph(
        self,
        checkpointer: BaseCheckpointSaver | None = None,
        stage_callback=None,
    ):
        """Construct compiled workflow graph with resolved checkpointer."""
        active_checkpointer = checkpointer or self.checkpointer
        return create_social_workflow(
            research_agent=self.research_agent,
            planning_agent=self.planning_agent,
            writer_agent=self.writer_agent,
            critic_agent=self.critic_agent,
            llm_service=self.llm_service,
            checkpointer=active_checkpointer,
            stage_callback=stage_callback,
        )

    def _instantiate_workflow_graph(
        self,
        checkpointer: BaseCheckpointSaver | None = None,
        stage_callback=None,
    ):
        """Helper to invoke _get_workflow_graph respecting mock signatures that omit stage_callback."""
        try:
            return self._get_workflow_graph(checkpointer=checkpointer, stage_callback=stage_callback)
        except TypeError:
            return self._get_workflow_graph(checkpointer=checkpointer)

    async def start_workflow(
        self,
        request: ResearchRequest,
        session: AsyncSession,
        checkpointer: BaseCheckpointSaver | None = None,
        user_id: str | None = None,
    ) -> WorkflowRun:
        """Initialize and execute a new workflow until the human review checkpoint is reached."""
        workflow_repo = WorkflowRepository(session)
        post_repo = PostRepository(session)
        feedback_repo = FeedbackRepository(session)

        # 1. Create initial WorkflowRun entity in DB
        initial_niche = request.niche.strip() if request.niche and request.niche.strip() else "Auto-Discovery"
        workflow_run = WorkflowRun(
            user_id=user_id,
            niche=initial_niche,
            target_platform=request.platform,
            audience=request.audience,
            language=request.language,
            status=WorkflowStatus.STARTING.value,
            current_stage=WorkflowStatus.RESEARCHING.value,
            revision_count=0,
            agent_revision_count=0,
            human_revision_count=0,
            human_rejection_count=0,
            max_human_rejections=3,
            max_revisions=2,
        )
        await workflow_repo.create(workflow_run)
        await session.flush()

        workflow_id = str(workflow_run.id)
        config = {"configurable": {"thread_id": workflow_id}}

        # Create the stage persistence callback for intermediate stage visibility
        stage_cb = self._create_stage_callback(workflow_id, session)

        initial_state: SocialWorkflowState = {
            "request": request,
            "revision_count": 0,
            "agent_revision_count": 0,
            "human_revision_count": 0,
            "human_rejection_count": 0,
            "max_human_rejections": workflow_run.max_human_rejections,
            "max_revisions": workflow_run.max_revisions,
            "status": WorkflowStatus.STARTING.value,
        }

        # 2. Execute graph with checkpointer
        async def _execute_with_saver(saver: BaseCheckpointSaver):
            graph = self._instantiate_workflow_graph(checkpointer=saver, stage_callback=stage_cb)
            return await graph.ainvoke(initial_state, config=config)

        if checkpointer or self.checkpointer:
            active_saver = checkpointer or self.checkpointer
            state = await _execute_with_saver(active_saver)
        else:
            async with get_workflow_checkpointer() as saver:
                state = await _execute_with_saver(saver)

        # 3. Synchronize database state with graph execution state
        workflow_run.status = state.get("status", WorkflowStatus.WAITING_FOR_HUMAN_REVIEW.value)
        workflow_run.current_stage = state.get("current_stage", workflow_run.status)
        workflow_run.revision_count = state.get("revision_count", 0)
        workflow_run.agent_revision_count = state.get("agent_revision_count", 0)
        workflow_run.human_revision_count = state.get("human_revision_count", 0)
        workflow_run.human_rejection_count = state.get("human_rejection_count", 0)
        workflow_run.max_human_rejections = state.get("max_human_rejections", 3)

        if state.get("research"):
            workflow_run.research_data = state["research"].model_dump()
            if (workflow_run.niche == "Auto-Discovery" or not workflow_run.niche) and state["research"].trends:
                workflow_run.niche = state["research"].trends[0].topic
        if state.get("content_plan"):
            workflow_run.content_plan = state["content_plan"].model_dump()
        if state.get("error"):
            workflow_run.error_message = state["error"]

        # 4. Create Post & initial Revision snapshot if generated
        social_post = state.get("social_post")
        if social_post:
            post = Post(
                workflow_run_id=workflow_run.id,
                platform=social_post.platform,
                topic=social_post.topic,
                content=social_post.content,
                status="DRAFT",
                content_type=social_post.content_type,
                language=social_post.language,
                hashtags=social_post.hashtags,
                cta=social_post.cta,
                source_references=social_post.source_references,
            )
            await post_repo.create(post)
            await session.flush()

            # Record initial snapshot
            await post_repo.create_revision_snapshot(
                post_id=post.id,
                revision_feedback=[],
                revision_source="AGENT",
            )

            # Record Critic Feedback
            critic_result = state.get("critic_result")
            if critic_result:
                feedback_entity = Feedback(
                    workflow_run_id=workflow_run.id,
                    post_id=post.id,
                    feedback_source="CRITIC",
                    decision=critic_result.decision,
                    issues=critic_result.issues,
                    feedback_items=critic_result.feedback,
                    quality_checks=critic_result.checks.model_dump() if critic_result.checks else None,
                    verified_sources=critic_result.verified_sources,
                    unverified_claims=critic_result.unverified_claims,
                )
                await feedback_repo.create(feedback_entity)

        await session.commit()
        return await workflow_repo.get_with_relations(workflow_id)

    async def submit_human_review(
        self,
        workflow_id: str,
        action: HumanReviewAction | str,
        session: AsyncSession,
        feedback: list[str] | str | None = None,
        content: str | None = None,
        checkpointer: BaseCheckpointSaver | None = None,
    ) -> WorkflowRun:
        """Submit human review decision, resume the LangGraph workflow, and persist updates."""
        workflow_repo = WorkflowRepository(session)
        post_repo = PostRepository(session)
        feedback_repo = FeedbackRepository(session)

        # 1. Fetch workflow and validate status with row-level locking
        workflow_run = await workflow_repo.get_with_relations_for_update(workflow_id)
        if not workflow_run:
            raise ValueError(f"Workflow '{workflow_id}' not found.")

        if workflow_run.status != WorkflowStatus.WAITING_FOR_HUMAN_REVIEW.value:
            raise ValueError(
                f"Invalid workflow state transition: workflow status is '{workflow_run.status}', "
                f"expected '{WorkflowStatus.WAITING_FOR_HUMAN_REVIEW.value}'."
            )

        action_str = action.value if isinstance(action, HumanReviewAction) else str(action).upper()
        if action_str not in [a.value for a in HumanReviewAction]:
            raise ValueError(f"Unrecognized review action: '{action_str}'.")

        feedback_list = [feedback] if isinstance(feedback, str) else (feedback or [])

        # Validate action-specific payload requirements
        if action_str == HumanReviewAction.EDIT.value and (not content or not content.strip()):
            raise ValueError("Direct EDIT action requires non-empty 'content'.")
        if action_str == HumanReviewAction.REVISE.value and (
            not feedback_list or not any(f.strip() for f in feedback_list if isinstance(f, str))
        ):
            raise ValueError("REVISE action requires actionable 'feedback' instructions.")

        # 2. Prepare resume command
        resume_payload: dict[str, Any] = {
            "action": action_str,
            "feedback": feedback_list,
            "content": content,
        }

        config = {"configurable": {"thread_id": workflow_id}}

        # Create the stage persistence callback for intermediate stage visibility
        stage_cb = self._create_stage_callback(workflow_id, session)

        # 3. Resume LangGraph execution from interrupt checkpoint
        async def _resume_with_saver(saver: BaseCheckpointSaver):
            graph = self._instantiate_workflow_graph(checkpointer=saver, stage_callback=stage_cb)
            return await graph.ainvoke(Command(resume=resume_payload), config=config)

        if checkpointer or self.checkpointer:
            active_saver = checkpointer or self.checkpointer
            resumed_state = await _resume_with_saver(active_saver)
        else:
            async with get_workflow_checkpointer() as saver:
                resumed_state = await _resume_with_saver(saver)

        # 4. Synchronize DB records
        workflow_run.status = resumed_state.get("status", WorkflowStatus.APPROVED.value)
        workflow_run.current_stage = resumed_state.get("current_stage", workflow_run.status)
        workflow_run.revision_count = resumed_state.get("revision_count", workflow_run.revision_count)
        workflow_run.agent_revision_count = resumed_state.get("agent_revision_count", workflow_run.agent_revision_count)
        workflow_run.human_revision_count = resumed_state.get("human_revision_count", workflow_run.human_revision_count)
        workflow_run.human_rejection_count = resumed_state.get("human_rejection_count", workflow_run.human_rejection_count)
        workflow_run.max_human_rejections = resumed_state.get("max_human_rejections", workflow_run.max_human_rejections)

        if resumed_state.get("error"):
            workflow_run.error_message = resumed_state["error"]

        posts = await post_repo.get_by_workflow(workflow_id)
        current_post = posts[0] if posts else None

        if current_post:
            # Record human review feedback entry
            human_feedback = Feedback(
                workflow_run_id=workflow_run.id,
                post_id=current_post.id,
                feedback_source="HUMAN",
                decision=action_str,
                issues=[],
                feedback_items=feedback_list,
                reviewer_notes=f"Human action: {action_str}",
            )
            await feedback_repo.create(human_feedback)

            # If EDIT, update post content and create revision snapshot
            if action_str == HumanReviewAction.EDIT.value and content:
                current_post.content = content
                await post_repo.create_revision_snapshot(
                    post_id=current_post.id,
                    revision_feedback=feedback_list,
                    revision_source="HUMAN",
                )

            # If REVISE or REJECT (non-terminal loop), record updated post generated by Writer
            latest_post = resumed_state.get("social_post")
            if latest_post and action_str in (HumanReviewAction.REVISE.value, HumanReviewAction.REJECT.value):
                current_post.content = latest_post.content
                current_post.hashtags = latest_post.hashtags
                current_post.cta = latest_post.cta
                current_post.source_references = latest_post.source_references
                await post_repo.create_revision_snapshot(
                    post_id=current_post.id,
                    revision_feedback=feedback_list or resumed_state.get("revision_feedback", []),
                    revision_source="HUMAN",
                )

            # Update post status on approval or rejection
            if workflow_run.status == WorkflowStatus.APPROVED.value:
                current_post.status = "APPROVED"
            elif workflow_run.status == WorkflowStatus.REJECTED.value:
                current_post.status = "REJECTED"

            # Record critic result if updated
            latest_critic = resumed_state.get("critic_result")
            if latest_critic and action_str in (HumanReviewAction.REVISE.value, HumanReviewAction.EDIT.value, HumanReviewAction.REJECT.value):
                critic_feedback = Feedback(
                    workflow_run_id=workflow_run.id,
                    post_id=current_post.id,
                    feedback_source="CRITIC",
                    decision=latest_critic.decision,
                    issues=latest_critic.issues,
                    feedback_items=latest_critic.feedback,
                    quality_checks=latest_critic.checks.model_dump() if latest_critic.checks else None,
                    verified_sources=latest_critic.verified_sources,
                    unverified_claims=latest_critic.unverified_claims,
                )
                await feedback_repo.create(critic_feedback)

        await session.commit()
        return await workflow_repo.get_with_relations(workflow_id)

    async def get_workflow(self, workflow_id: str, session: AsyncSession) -> WorkflowRun | None:
        """Fetch complete workflow entity with all related posts, revisions, and feedbacks."""
        repo = WorkflowRepository(session)
        return await repo.get_with_relations(workflow_id)

    async def delete_workflow(
        self,
        workflow_id: str,
        session: AsyncSession,
        user_id: str | None = None,
    ) -> bool:
        """Delete a workflow run and all its cascading records (posts, revisions, feedbacks, publications, schedules).

        Validation:
        - If workflow not found -> returns False.
        - If workflow is owned by another user -> returns False.
        - If workflow is actively running -> raises ValueError (mapped to 409 Conflict in API).
        - Terminal and review-paused workflows are cleanly deleted.
        """
        repo = WorkflowRepository(session)
        workflow = await repo.get_with_relations(workflow_id)
        if not workflow:
            return False

        if user_id is not None and workflow.user_id is not None and workflow.user_id != user_id:
            return False

        active_statuses = {
            WorkflowStatus.STARTING.value,
            WorkflowStatus.RESEARCHING.value,
            WorkflowStatus.PLANNING.value,
            WorkflowStatus.WRITING.value,
            WorkflowStatus.CRITIQUING.value,
            "PUBLISHING",
            "RUNNING",
        }
        if workflow.status in active_statuses:
            raise ValueError(
                f"Cannot delete workflow '{workflow_id}' while it is actively executing (status: {workflow.status})."
            )

        await repo.delete(workflow_id)
        await session.commit()
        return True
