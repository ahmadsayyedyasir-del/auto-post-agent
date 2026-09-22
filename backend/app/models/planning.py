"""Planning domain schemas and custom exceptions for content strategy formulation."""

from pydantic import BaseModel, ConfigDict, Field

from backend.app.models.research import ResearchResponse


class PlanningError(Exception):
    """Base exception for planning domain errors."""

    def __init__(self, message: str, original_error: Exception | None = None) -> None:
        super().__init__(message)
        self.original_error = original_error


class EmptyResearchError(PlanningError):
    """Raised when attempting to plan from empty or invalid research data."""


class UngroundedPlanError(PlanningError):
    """Raised when a generated content plan cannot be grounded in research findings."""


class PlanningValidationFailedError(PlanningError):
    """Raised when bounded planning generation retries are exhausted without producing a valid plan."""


class PlanningRequest(BaseModel):
    """Input parameters for formulating a content plan from research."""

    model_config = ConfigDict(extra="ignore")

    research: ResearchResponse = Field(..., description="Structured research output from Phase 3")
    niche: str = Field(..., min_length=2, description="Target niche or domain")
    audience: str = Field(default="AI practitioners, students, and enthusiasts", min_length=2, description="Target audience")
    platform: str = Field(default="linkedin", min_length=2, description="Target platform (e.g., 'linkedin', 'twitter')")
    language: str = Field(default="English", min_length=2, description="Content language")
    content_goal: str = Field(
        default="educational",
        description="Core goal of the post (e.g., 'educational', 'thought_leadership', 'engagement', 'storytelling')",
    )
    preferred_tone: str = Field(
        default="professional and engaging",
        description="Desired tone of voice (e.g., 'conversational', 'analytical', 'authoritative', 'inspirational')",
    )
    content_type: str = Field(
        default="single_post",
        description="Target content format (e.g., 'single_post', 'carousel', 'thread', 'article')",
    )


class ContentPlan(BaseModel):
    """Structured, source-grounded content strategy output from the Planning Agent."""

    model_config = ConfigDict(extra="ignore")

    topic: str = Field(..., min_length=3, description="Selected trend topic title")
    angle: str = Field(..., min_length=10, description="Strategic angle or perspective taken for the content")
    platform: str = Field(..., min_length=2, description="Target social platform")
    audience: str = Field(..., min_length=2, description="Target reader demographic")
    language: str = Field(default="English", min_length=2, description="Language of the planned post")
    content_type: str = Field(default="single_post", min_length=2, description="Format of the content (e.g. single_post, thread)")
    tone: str = Field(..., min_length=2, description="Selected tone of voice for the copy")
    hook_direction: str = Field(..., min_length=10, description="Guidance for crafting an engaging opening hook")
    key_points: list[str] = Field(
        ...,
        min_length=1,
        description="Structured list of core points/arguments to cover (at least 1 required)",
    )
    cta_direction: str = Field(
        ...,
        min_length=5,
        description="Direction for call-to-action (e.g., question to spark comments, share prompt)",
    )
    source_references: list[str] = Field(
        default_factory=list,
        description="List of grounded source URLs or citations from the research evidence",
    )
    selected_trend_topic: str | None = Field(
        default=None,
        description="Exact matching trend topic title from the ResearchResponse",
    )
    reasoning: str | None = Field(
        default=None,
        description="Strategic justification for why this topic and angle were chosen",
    )
