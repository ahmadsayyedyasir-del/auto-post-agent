"""Critic / Reviewer domain schemas and custom exceptions for content evaluation."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from backend.app.models.content import SocialPost
from backend.app.models.planning import ContentPlan
from backend.app.models.research import ResearchResponse

CriticDecision = Literal["APPROVED", "REVISE"]


class CriticError(Exception):
    """Base exception for critic domain errors."""

    def __init__(self, message: str, original_error: Exception | None = None) -> None:
        super().__init__(message)
        self.original_error = original_error


class InvalidReviewRequestError(CriticError):
    """Raised when attempting to review with a missing or malformed post or plan."""


class CriticValidationFailedError(CriticError):
    """Raised when bounded critic LLM evaluation retries are exhausted."""


class QualityChecks(BaseModel):
    """Individual quality and compliance dimensions evaluated by the Critic Agent."""

    model_config = ConfigDict(extra="ignore")

    relevance: bool = Field(default=True, description="Does the post address the planned topic and angle?")
    plan_adherence: bool = Field(default=True, description="Does the post incorporate key points and CTA?")
    source_grounding: bool = Field(default=True, description="Are citations and factual claims supported?")
    clarity: bool = Field(default=True, description="Is the post well-structured, coherent, and readable?")
    tone: bool = Field(default=True, description="Does the post match the desired tone of voice?")
    platform_fit: bool = Field(default=True, description="Does the formatting align with platform conventions?")
    length: bool = Field(default=True, description="Does the post respect platform character bounds?")
    cta: bool = Field(default=True, description="Is the required call to action present and aligned?")
    hashtags: bool = Field(default=True, description="Are hashtags appropriate in count and format?")
    originality: bool = Field(default=True, description="Is the post free of obvious duplication or excessive filler?")


class ReviewRequest(BaseModel):
    """Input parameters for the Critic Agent to evaluate a SocialPost."""

    model_config = ConfigDict(extra="ignore")

    post: SocialPost = Field(..., description="Generated social media post to evaluate")
    plan: ContentPlan = Field(..., description="Original ContentPlan used as strategic ground truth")
    research: ResearchResponse | None = Field(
        default=None,
        description="Optional original research evidence for factual and source verification",
    )
    brand_guidelines: str | None = Field(
        default=None,
        description="Optional brand rules or editorial constraints",
    )


class CriticResult(BaseModel):
    """Structured evaluation output produced by the Critic Agent."""

    model_config = ConfigDict(extra="ignore")

    decision: CriticDecision = Field(
        ...,
        description="Final verdict: 'APPROVED' or 'REVISE'",
    )
    issues: list[str] = Field(
        default_factory=list,
        description="Specific problems identified during deterministic or LLM evaluation",
    )
    feedback: list[str] = Field(
        default_factory=list,
        description="Actionable guidance for the Writer Agent to improve the post on revision",
    )
    checks: QualityChecks = Field(
        default_factory=QualityChecks,
        description="Detailed breakdown of evaluated quality dimensions",
    )
    verified_sources: list[str] = Field(
        default_factory=list,
        description="List of source URLs/citations confirmed against supplied research evidence",
    )
    unverified_claims: list[str] = Field(
        default_factory=list,
        description="Claims or citations that could not be verified from supplied research",
    )
    evaluation_notes: str | None = Field(
        default=None,
        description="Optional high-level evaluation summary or contextual notes",
    )
