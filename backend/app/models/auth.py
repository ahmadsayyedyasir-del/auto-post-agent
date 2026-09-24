"""Phase 12: Pydantic schemas for authentication API requests and responses.

SECURITY: Password fields use SecretStr to prevent accidental logging/repr exposure.
Access tokens and refresh tokens are not included in user profile responses.
"""

from datetime import datetime

from pydantic import BaseModel, EmailStr, Field, SecretStr


# ---------------------------------------------------------------------------
# Request schemas
# ---------------------------------------------------------------------------


class UserRegisterRequest(BaseModel):
    """Schema for new user registration."""

    email: EmailStr = Field(..., description="Valid email address.")
    password: SecretStr = Field(
        ...,
        min_length=8,
        description="Plain-text password (min 8 chars). Stored only as bcrypt hash.",
    )
    full_name: str | None = Field(
        default=None,
        max_length=255,
        description="Optional display name.",
    )


class UserLoginRequest(BaseModel):
    """Schema for user login credentials."""

    email: EmailStr = Field(..., description="Registered email address.")
    password: SecretStr = Field(..., description="Plain-text password.")


class TokenRefreshRequest(BaseModel):
    """Schema for submitting a refresh token to obtain a new access token."""

    refresh_token: str = Field(..., description="Opaque refresh token issued at login.")


# ---------------------------------------------------------------------------
# Response schemas — NEVER include passwords, hashes, or raw tokens
# ---------------------------------------------------------------------------


class UserResponse(BaseModel):
    """Public user profile — no sensitive fields."""

    id: str
    email: str
    full_name: str | None
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class TokenResponse(BaseModel):
    """Auth token pair returned on login and token refresh.

    SECURITY: raw refresh token value is returned only once at login.
    The server stores only its SHA-256 hash.
    """

    access_token: str
    token_type: str = "bearer"
    expires_in: int = Field(description="Access token TTL in seconds.")
    refresh_token: str = Field(description="Opaque refresh token. Store securely.")


class AccessTokenResponse(BaseModel):
    """New access token returned on refresh (refresh token is not rotated here)."""

    access_token: str
    token_type: str = "bearer"
    expires_in: int = Field(description="Access token TTL in seconds.")


class MessageResponse(BaseModel):
    """Generic message response for logout and similar operations."""

    message: str
