"""Content generation domain schemas and custom exceptions for the Writer Agent."""

from pydantic import BaseModel, ConfigDict, Field

from backend.app.models.planning import ContentPlan


class WriterError(Exception):
    """Base exception for writer domain errors."""

    def __init__(self, message: str, original_error: Exception | None = None) -> None:
        super().__init__(message)
        self.original_error = original_error


class InvalidPlanError(WriterError):
    """Raised when attempting to write content from an invalid or incomplete ContentPlan."""


class UngroundedContentError(WriterError):
    """Raised when generated content violates source grounding or plan adherence rules."""


class PlatformConstraintError(WriterError):
    """Raised when generated content violates platform-specific format or length bounds."""


class WriterValidationFailedError(WriterError):
    """Raised when bounded writer generation retries are exhausted without producing a valid post."""


class WriterRequest(BaseModel):
    """Input parameters for the Writer Agent to generate platform-specific post copy."""

    model_config = ConfigDict(extra="ignore")

    plan: ContentPlan = Field(..., description="Validated ContentPlan from Phase 4")
    platform: str | None = Field(
        default=None,
        description="Target platform override (defaults to plan.platform if not specified)",
    )
    audience: str | None = Field(
        default=None,
        description="Target audience override (defaults to plan.audience if not specified)",
    )
    language: str | None = Field(
        default=None,
        description="Language override (defaults to plan.language if not specified)",
    )
    tone: str | None = Field(
        default=None,
        description="Tone override (defaults to plan.tone if not specified)",
    )

    def get_effective_platform(self) -> str:
        """Return the effective platform target, preferring explicit override over plan."""
        return (self.platform or self.plan.platform or "linkedin").strip().lower()

    def get_effective_audience(self) -> str:
        """Return the effective audience, preferring explicit override over plan."""
        return (self.audience or self.plan.audience or "General Audience").strip()

    def get_effective_language(self) -> str:
        """Return the effective language, preferring explicit override over plan."""
        return (self.language or self.plan.language or "English").strip()

    def get_effective_tone(self) -> str:
        """Return the effective tone, preferring explicit override over plan."""
        return (self.tone or self.plan.tone or "professional").strip()


class SocialPost(BaseModel):
    """Structured, platform-aware social media post output from the Writer Agent."""

    model_config = ConfigDict(extra="ignore")

    platform: str = Field(..., min_length=2, description="Target social platform (e.g., 'linkedin', 'twitter')")
    content: str = Field(..., min_length=1, description="Generated social media post text copy")
    topic: str = Field(..., min_length=1, description="Topic aligned with the ContentPlan")
    language: str = Field(default="English", min_length=2, description="Language of the post")
    content_type: str = Field(default="single_post", min_length=2, description="Content format (e.g., single_post, thread)")
    hashtags: list[str] = Field(
        default_factory=list,
        description="List of relevant hashtags without excessive stuffing",
    )
    cta: str | None = Field(
        default=None,
        description="Explicit call-to-action direction or prompt used in the post",
    )
    source_references: list[str] = Field(
        default_factory=list,
        description="Grounded source URLs or citations preserved from the ContentPlan",
    )
