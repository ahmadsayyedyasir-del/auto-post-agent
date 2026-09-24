"""Phase 12: Pydantic schemas for per-user platform credential management API.

SECURITY: Credential values are NEVER returned in API responses.
The API only confirms existence/metadata of stored credentials.
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Supported platforms and credential keys
# ---------------------------------------------------------------------------

SUPPORTED_PLATFORMS = Literal["linkedin"]

LINKEDIN_CREDENTIAL_KEYS = Literal[
    "access_token",
    "author_urn",
    "client_id",
    "client_secret",
]

# ---------------------------------------------------------------------------
# Request schemas
# ---------------------------------------------------------------------------


class UpsertCredentialRequest(BaseModel):
    """Request schema for adding or updating a platform credential."""

    platform: str = Field(..., description="Platform name, e.g. 'linkedin'.")
    credential_key: str = Field(
        ...,
        description="Credential key name, e.g. 'access_token', 'author_urn'.",
    )
    credential_value: str = Field(
        ...,
        min_length=1,
        description="The plaintext credential value. Encrypted before storage.",
    )


class DeleteCredentialRequest(BaseModel):
    """Request schema for deleting a platform credential."""

    platform: str = Field(..., description="Platform name.")
    credential_key: str = Field(..., description="Credential key to delete.")


# ---------------------------------------------------------------------------
# Response schemas — NO credential values exposed
# ---------------------------------------------------------------------------


class CredentialMetadataResponse(BaseModel):
    """Metadata about a stored credential — the value itself is NEVER returned."""

    id: str
    platform: str
    credential_key: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class CredentialListResponse(BaseModel):
    """List of credential metadata entries for a user."""

    credentials: list[CredentialMetadataResponse]
    total: int


class CredentialDeleteResponse(BaseModel):
    """Response confirming a credential deletion."""

    deleted: bool
    platform: str
    credential_key: str
