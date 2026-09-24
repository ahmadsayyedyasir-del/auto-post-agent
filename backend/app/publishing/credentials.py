"""Platform credentials models and resolution mechanism.

Phase 12 additions:
- AsyncCredentialResolver: resolves credentials from per-user DB storage (Fernet-decrypted)
  with optional fallback to environment config.
- Existing CredentialResolver preserved unchanged for backward compatibility.

SECURITY:
- Decrypted credential values are held only in memory, in the dataclass, during request handling.
- Decrypted values are never logged, repr'd, or serialized.
- DB storage uses Fernet encryption (see PlatformCredential model).
"""

from dataclasses import dataclass
from datetime import datetime
import logging

from backend.app.config import Settings, get_settings
from backend.app.publishing.base import PermanentPlatformError

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PlatformCredentials:
    """Encapsulates credentials required to authenticate and publish to a platform.

    SECURITY: This dataclass holds decrypted values IN MEMORY ONLY.
    It must never be serialized to JSON, stored in the database, or placed
    into LangGraph state or checkpoints.
    """

    platform: str
    access_token: str
    author_urn: str
    client_id: str | None = None
    client_secret: str | None = None
    token_expires_at: datetime | None = None

    def __repr__(self) -> str:  # pragma: no cover
        """Redact all sensitive fields from repr output."""
        return (
            f"PlatformCredentials("
            f"platform={self.platform!r}, "
            f"access_token=**REDACTED**, "
            f"author_urn=**REDACTED**)"
        )


class CredentialResolver:
    """Resolves and validates platform credentials from environment settings.

    PRESERVED UNCHANGED from Phase 10/11 for backward compatibility.
    Used by PublishingService when no user_id is provided (legacy behavior).
    """

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def resolve(self, platform: str) -> PlatformCredentials:
        """Resolve credentials for the specified platform from environment settings."""
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


class AsyncCredentialResolver:
    """Async per-user credential resolver with DB lookup and environment fallback.

    Phase 12: Resolves credentials from the per-user PlatformCredential table
    (Fernet-decrypted) and optionally falls back to environment settings.

    SECURITY:
    - Decrypted values are held only in the returned PlatformCredentials dataclass.
    - The dataclass must NOT be placed in LangGraph state or checkpoints.
    - Decrypted values are NEVER logged.
    """

    def __init__(
        self,
        settings: Settings | None = None,
        allow_env_fallback: bool = True,
    ) -> None:
        self.settings = settings or get_settings()
        self.allow_env_fallback = allow_env_fallback

    async def resolve(
        self,
        platform: str,
        user_id: str,
        session: "AsyncSession",  # type: ignore[name-defined]  # noqa: F821
    ) -> PlatformCredentials:
        """Resolve platform credentials for a specific user.

        Lookup order:
        1. Per-user DB credentials (PlatformCredential table, Fernet-decrypted).
        2. Environment settings fallback (if allow_env_fallback=True and DB has no entry).

        SECURITY: Decrypted values are never logged or returned in API responses.

        Args:
            platform: Target platform name (e.g. 'linkedin').
            user_id: The authenticated user's ID.
            session: Active async database session for DB lookup.

        Raises:
            PermanentPlatformError: If credentials cannot be resolved from any source.
        """
        from backend.app.core.security import decrypt_credential
        from backend.app.db.repositories.user_repo import PlatformCredentialRepository
        from cryptography.fernet import InvalidToken

        norm_platform = platform.strip().lower()
        cred_repo = PlatformCredentialRepository(session)

        if norm_platform == "linkedin":
            rows = await cred_repo.get_all_for_user_and_platform(user_id, "linkedin")
            cred_map: dict[str, str] = {}
            for row in rows:
                try:
                    cred_map[row.credential_key] = decrypt_credential(row.credential_value_encrypted)
                except InvalidToken:
                    logger.error(
                        "Failed to decrypt credential key='%s' for user_id='%s'. Skipping.",
                        row.credential_key,
                        user_id,
                    )

            # Try to build from DB credentials
            access_token = cred_map.get("access_token")
            author_urn = cred_map.get("author_urn")
            client_id = cred_map.get("client_id")
            client_secret = cred_map.get("client_secret")

            if access_token and author_urn:
                logger.debug(
                    "Resolved LinkedIn credentials from DB for user_id='%s'.", user_id
                )
                return PlatformCredentials(
                    platform="linkedin",
                    access_token=access_token,
                    author_urn=author_urn,
                    client_id=client_id,
                    client_secret=client_secret,
                )

            # Fallback to environment settings
            if self.allow_env_fallback:
                env_token = self.settings.linkedin_access_token
                env_author_urn = self.settings.linkedin_author_urn
                if env_token and env_token.strip() and env_author_urn and env_author_urn.strip():
                    logger.debug(
                        "Resolved LinkedIn credentials from environment for user_id='%s' (DB had incomplete credentials).",
                        user_id,
                    )
                    return PlatformCredentials(
                        platform="linkedin",
                        access_token=env_token.strip(),
                        author_urn=env_author_urn.strip(),
                        client_id=self.settings.linkedin_client_id,
                        client_secret=self.settings.linkedin_client_secret,
                    )

            # Build helpful error message
            missing_keys = []
            if not access_token:
                missing_keys.append("access_token")
            if not author_urn:
                missing_keys.append("author_urn")
            raise PermanentPlatformError(
                message=(
                    f"LinkedIn credentials for user '{user_id}' are incomplete. "
                    f"Missing keys: {missing_keys}. "
                    f"Store credentials via POST /api/v1/credentials."
                ),
                error_code="MISSING_USER_LINKEDIN_CREDENTIALS",
            )

        raise PermanentPlatformError(
            message=f"No credential provider available for platform: '{platform}'.",
            error_code="UNSUPPORTED_PLATFORM_CREDENTIALS",
        )
