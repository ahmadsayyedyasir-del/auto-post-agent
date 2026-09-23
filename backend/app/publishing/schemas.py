"""Pydantic request and response schemas for social media publishing endpoints."""

from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field


class PublishWorkflowRequestSchema(BaseModel):
    """Optional payload when requesting publication for an approved workflow."""

    model_config = ConfigDict(extra="ignore")

    platform_override: str | None = Field(
        default=None,
        description="Optional platform override (defaults to workflow target_platform)",
    )


class PublicationResponseSchema(BaseModel):
    """Structured response schema representing a Publication record."""

    model_config = ConfigDict(from_attributes=True)

    id: str = Field(..., description="Unique publication record identifier")
    workflow_run_id: str = Field(..., description="Associated workflow run identifier")
    post_id: str = Field(..., description="Associated post identifier")
    platform: str = Field(..., description="Target social media platform")
    status: str = Field(..., description="Current publishing status (PENDING, PUBLISHING, PUBLISHED, FAILED)")
    idempotency_key: str = Field(..., description="Unique deterministic idempotency key")
    external_post_id: str | None = Field(default=None, description="External platform post identifier / URN")
    external_url: str | None = Field(default=None, description="Public canonical URL of the published post")
    attempt_count: int = Field(default=0, description="Total number of execution attempts made")
    last_attempt_at: datetime | None = Field(default=None, description="Timestamp of the most recent publishing attempt")
    published_at: datetime | None = Field(default=None, description="Timestamp of confirmed publication success")
    error_code: str | None = Field(default=None, description="Diagnostic error code on failure")
    error_message: str | None = Field(default=None, description="Sanitized error message on failure")
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")


class PublicationListResponseSchema(BaseModel):
    """Collection of publication records for a workflow."""

    publications: list[PublicationResponseSchema] = Field(default_factory=list)
    total: int = Field(default=0)
