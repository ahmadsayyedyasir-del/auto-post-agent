"""Platform credentials models and resolution mechanism."""

from dataclasses import dataclass
from datetime import datetime
import logging

from backend.app.config import Settings, get_settings
from backend.app.publishing.base import PermanentPlatformError

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PlatformCredentials:
    """Encapsulates credentials required to authenticate and publish to a platform."""

    platform: str
    access_token: str
    author_urn: str
    client_id: str | None = None
    client_secret: str | None = None
    token_expires_at: datetime | None = None


class CredentialResolver:
    """Resolves and validates platform credentials from environment settings or secure stores."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def resolve(self, platform: str) -> PlatformCredentials:
        """Resolve credentials for the specified platform."""
        norm_platform = platform.strip().lower()

        if norm_platform == "linkedin":
            token = self.settings.linkedin_access_token
            author_urn = self.settings.linkedin_author_urn

            if not token or not token.strip():
                raise PermanentPlatformError(
                    message="LinkedIn access token is missing. Please set LINKEDIN_ACCESS_TOKEN in environment.",
                    error_code="MISSING_LINKEDIN_TOKEN",
                )
            if not author_urn or not author_urn.strip():
                raise PermanentPlatformError(
                    message="LinkedIn author URN is missing. Please set LINKEDIN_AUTHOR_URN in environment (e.g., 'urn:li:person:...').",
                    error_code="MISSING_LINKEDIN_AUTHOR_URN",
                )

            return PlatformCredentials(
                platform="linkedin",
                access_token=token.strip(),
                author_urn=author_urn.strip(),
                client_id=self.settings.linkedin_client_id,
                client_secret=self.settings.linkedin_client_secret,
            )

        raise PermanentPlatformError(
            message=f"No credential provider available for platform: '{platform}'.",
            error_code="UNSUPPORTED_PLATFORM_CREDENTIALS",
        )
