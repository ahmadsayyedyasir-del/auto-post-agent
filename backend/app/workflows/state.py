"""Centralized workflow state and status definitions for the LangGraph orchestration pipeline."""

from enum import Enum
from typing import TypedDict

from backend.app.models.content import SocialPost
from backend.app.models.critic import CriticResult
from backend.app.models.planning import ContentPlan
from backend.app.models.research import ResearchRequest, ResearchResponse


class WorkflowStatus(str, Enum):
    """Lifecycle status states for the social media generation workflow."""

    STARTING = "STARTING"
    RESEARCHING = "RESEARCHING"
    PLANNING = "PLANNING"
    WRITING = "WRITING"
    CRITIQUING = "CRITIQUING"
    WAITING_FOR_HUMAN_REVIEW = "WAITING_FOR_HUMAN_REVIEW"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class SocialWorkflowState(TypedDict, total=False):
    """Centralized, serializable state dictionary passed between LangGraph nodes."""

    request: ResearchRequest
    research: ResearchResponse | None
    content_plan: ContentPlan | None
    social_post: SocialPost | None
    critic_result: CriticResult | None
    revision_feedback: list[str]
    revision_count: int
    max_revisions: int
    status: str
    human_review_required: bool
    error: str | None
