"""Abstract domain interfaces, schemas, exceptions, and registry for social media platform publishing."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from backend.app.publishing.credentials import PlatformCredentials


class PublishingStatus(str, Enum):
    """Lifecycle status states for an external platform publication."""

    PENDING = "PENDING"
    PUBLISHING = "PUBLISHING"
    PUBLISHED = "PUBLISHED"
    FAILED = "FAILED"


@dataclass(frozen=True)
class PublishingRequest:
    """Standardized post payload dispatched to platform adapters."""

    content: str
    platform: str
    topic: str = ""
    hashtags: list[str] = field(default_factory=list)
    cta: str | None = None
    source_references: list[str] = field(default_factory=list)
    idempotency_key: str = ""

    def get_full_text(self) -> str:
        """Compose clean, publication-ready body text with CTA and hashtags."""
        parts = [self.content.strip()]
        if self.cta and self.cta.strip() and self.cta.strip() not in self.content:
            parts.append(f"\n{self.cta.strip()}")
        if self.hashtags:
            clean_tags = [
                h if h.startswith("#") else f"#{h}"
                for h in self.hashtags
                if h.strip()
            ]
            if clean_tags:
                tags_str = " ".join(clean_tags)
                if tags_str not in self.content:
                    parts.append(f"\n{tags_str}")
        return "\n".join(parts)


@dataclass(frozen=True)
class PublicationResult:
    """Structured result returned by a platform publisher adapter."""

    success: bool
    platform: str
    external_post_id: str | None = None
    external_url: str | None = None
    published_at: datetime | None = None
    error_code: str | None = None
    error_message: str | None = None
    is_retryable: bool = False
    raw_response: dict[str, Any] | None = None
    retryable: bool | None = None

    def __post_init__(self) -> None:
        if self.retryable is not None and not self.is_retryable:
            object.__setattr__(self, "is_retryable", self.retryable)


class PlatformError(Exception):
    """Base domain exception for social media platform publishing failures."""

    def __init__(
        self,
        message: str,
        error_code: str | None = None,
        is_retryable: bool = False,
        original_error: Exception | None = None,
    ) -> None:
        super().__init__(message)
        self.error_code = error_code
        self.is_retryable = is_retryable
        self.original_error = original_error


class TransientPlatformError(PlatformError):
    """Temporary or retryable failure (e.g., rate limits, network timeouts, 5xx server errors)."""

    def __init__(
        self,
        message: str,
        error_code: str | None = "TRANSIENT_ERROR",
        original_error: Exception | None = None,
    ) -> None:
        super().__init__(
            message=message,
            error_code=error_code,
            is_retryable=True,
            original_error=original_error,
        )


class PermanentPlatformError(PlatformError):
    """Unrecoverable failure (e.g., invalid token, forbidden scope, schema validation error)."""

    def __init__(
        self,
        message: str,
        error_code: str | None = "PERMANENT_ERROR",
        original_error: Exception | None = None,
    ) -> None:
        super().__init__(
            message=message,
            error_code=error_code,
            is_retryable=False,
            original_error=original_error,
        )


class SocialPlatformPublisher(ABC):
    """Abstract interface defining official platform publishing adapters."""

    @property
    @abstractmethod
    def platform_name(self) -> str:
        """Canonical platform name (e.g. 'linkedin', 'twitter')."""
        pass

    @abstractmethod
    async def publish(
        self,
        request: PublishingRequest,
        credentials: "PlatformCredentials",
    ) -> PublicationResult:
        """Publish content to the external platform API and return structured result."""
        pass


class PlatformRegistry:
    """Registry maintaining initialized social media platform publishers."""

    def __init__(self) -> None:
        self._publishers: dict[str, SocialPlatformPublisher] = {}

    def register(self, publisher: SocialPlatformPublisher) -> None:
        """Register a platform publisher adapter instance."""
        self._publishers[publisher.platform_name.strip().lower()] = publisher

    def get(self, platform: str) -> SocialPlatformPublisher:
        """Retrieve publisher adapter for a given platform name."""
        key = platform.strip().lower()
        if key not in self._publishers:
            supported = ", ".join(sorted(self._publishers.keys())) or "none"
            raise ValueError(
                f"Unsupported social media platform '{platform}'. Supported platforms: [{supported}]."
            )
        return self._publishers[key]

    def supported_platforms(self) -> list[str]:
        """List all currently registered platform keys."""
        return sorted(self._publishers.keys())
