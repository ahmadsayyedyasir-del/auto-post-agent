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

    # LLM Service Configuration
    groq_api_key: str | None = None
    llm_provider: str = "groq"
    llm_model: str = "llama-3.3-70b-versatile"
    llm_temperature: float = Field(default=0.2, ge=0.0, le=2.0)
    llm_max_tokens: int | None = None
    llm_max_retries: int = Field(default=3, ge=1, le=10)


@lru_cache
def get_settings() -> Settings:
    """Return a cached instance of the application settings."""
    return Settings()
