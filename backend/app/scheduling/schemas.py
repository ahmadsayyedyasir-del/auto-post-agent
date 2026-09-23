"""Pydantic request and response schemas for social media post scheduling and automation."""

from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field


class CreateScheduleRequestSchema(BaseModel):
    """Payload schema to schedule an approved workflow post."""

    model_config = ConfigDict(extra="ignore")

    workflow_id: str = Field(..., description="Approved workflow run ID to schedule")
    scheduled_at: datetime = Field(..., description="Target publication date and time")
    timezone: str = Field(
        default="UTC",
        description="IANA timezone string (e.g., 'Asia/Karachi', 'America/New_York', 'UTC')",
    )
    platform_override: str | None = Field(
        default=None,
        description="Optional platform override (defaults to workflow target_platform)",
    )


class UpdateScheduleRequestSchema(BaseModel):
    """Payload schema to update or reschedule an existing schedule."""

    model_config = ConfigDict(extra="ignore")

    scheduled_at: datetime | None = Field(
        default=None,
        description="Updated target publication date and time",
    )
    timezone: str | None = Field(
        default=None,
        description="Updated IANA timezone string",
    )


class ScheduleResponseSchema(BaseModel):
    """Structured response schema representing a Schedule record."""

    model_config = ConfigDict(from_attributes=True)

    id: str = Field(..., description="Unique schedule record identifier")
    workflow_run_id: str = Field(..., description="Associated workflow run identifier")
    post_id: str = Field(..., description="Associated post identifier")
    platform: str = Field(..., description="Target social media platform")
    scheduled_at: datetime = Field(..., description="Scheduled publication timestamp in UTC")
    timezone: str = Field(..., description="Original user IANA timezone")
    status: str = Field(..., description="Current schedule status (SCHEDULED, RUNNING, COMPLETED, FAILED, CANCELLED)")
    job_id: str = Field(..., description="Deterministic scheduler job identifier")
    attempt_count: int = Field(default=0, description="Total execution attempts made")
    last_error: str | None = Field(default=None, description="Diagnostic error message on failure")
    executed_at: datetime | None = Field(default=None, description="Timestamp of execution attempt")
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")


class ScheduleListResponseSchema(BaseModel):
    """Collection response schema for multiple schedules."""

    schedules: list[ScheduleResponseSchema] = Field(default_factory=list)
    total: int = Field(default=0)
