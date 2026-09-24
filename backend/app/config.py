"""Centralized application configuration management using pydantic-settings."""

from functools import lru_cache
from typing import Literal
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables or .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Core Application Configuration
    app_name: str = "AI Social Media Automation Platform"
    app_version: str = "0.1.0"
    app_env: Literal["development", "staging", "production", "test"] = "development"
    debug: bool = False
    log_level: str = "INFO"

    # Server Configuration
    host: str = "127.0.0.1"
    port: int = 8000
    api_v1_str: str = "/api/v1"

    # LLM Service Configuration (Phase 2)
    groq_api_key: str | None = None
    llm_provider: str = "groq"
    llm_model: str = "llama-3.3-70b-versatile"
    llm_temperature: float = Field(default=0.2, ge=0.0, le=2.0)
    llm_max_tokens: int | None = None
    llm_max_retries: int = Field(default=3, ge=1, le=10)

    # Search & Research Tools Configuration (Phase 3)
    tavily_api_key: str | None = None
    search_max_retries: int = Field(default=2, ge=1, le=5)

    # Planning Agent Configuration (Phase 4)
    planning_max_retries: int = Field(default=2, ge=1, le=5)

    # Database & Persistence Configuration (Phase 8)
    database_url: str = "sqlite+aiosqlite:///./social_media.db"
    database_echo: bool = False
    database_pool_size: int = Field(default=5, ge=1, le=50)
    database_max_overflow: int = Field(default=10, ge=0, le=50)
    database_pool_recycle: int = Field(default=3600, ge=60)

    # LangGraph HITL Checkpoint Configuration (Phase 9)
    checkpointer_type: Literal["memory", "sqlite", "postgres"] = "sqlite"
    checkpoint_db_path: str = "data/checkpoints.db"

    # Social Media Publishing Configuration (Phase 10)
    linkedin_client_id: str | None = None
    linkedin_client_secret: str | None = None
    linkedin_access_token: str | None = None
    linkedin_author_urn: str | None = None
    linkedin_api_version: str = "202401"
    publishing_max_retries: int = Field(default=3, ge=1, le=10)
    publishing_base_backoff_seconds: float = Field(default=1.0, ge=0.1, le=60.0)

    # Social Media Scheduling Configuration (Phase 11)
    scheduler_misfire_grace_time_seconds: int = Field(default=900, ge=60, le=86400)
    scheduler_startup_recovery_enabled: bool = True

    # Authentication & Security Configuration (Phase 12)
    # JWT
    jwt_secret_key: str = Field(
        default="",
        description="Secret key for signing JWT tokens. Set a strong random value in production.",
    )
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = Field(default=30, ge=1, le=10080)
    jwt_refresh_token_expire_days: int = Field(default=7, ge=1, le=90)

    # Platform Credential Encryption (Fernet symmetric key, 32 url-safe base64-encoded bytes)
    credential_encryption_key: str = Field(
        default="",
        description="Fernet base64 symmetric key for encrypting stored platform credentials.",
    )


@lru_cache
def get_settings() -> Settings:
    """Return a cached instance of the application settings."""
    return Settings()

