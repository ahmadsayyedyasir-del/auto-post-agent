"""Official LinkedIn REST API publishing adapter."""

from datetime import datetime, timezone
import logging
from typing import Any

import httpx

from backend.app.config import get_settings
from backend.app.publishing.base import (
    PermanentPlatformError,
    PublicationResult,
    PublishingRequest,
    SocialPlatformPublisher,
    TransientPlatformError,
)
from backend.app.publishing.credentials import PlatformCredentials

logger = logging.getLogger(__name__)

LINKEDIN_POSTS_API_URL = "https://api.linkedin.com/rest/posts"


class LinkedInPublisher(SocialPlatformPublisher):
    """Adapter executing post publication against the official LinkedIn Versioned REST API."""

    def __init__(
        self,
        api_url: str = LINKEDIN_POSTS_API_URL,
        api_version: str | None = None,
        http_client: httpx.AsyncClient | None = None,
        timeout_seconds: float = 30.0,
    ) -> None:
        self.api_url = api_url
        self.api_version = api_version or get_settings().linkedin_api_version
        self._http_client = http_client
        self.timeout_seconds = timeout_seconds

    @property
    def platform_name(self) -> str:
        return "linkedin"

    def _normalize_author_urn(self, author_urn: str) -> str:
        """Ensure author URN conforms to 'urn:li:person:...' or 'urn:li:organization:... format."""
        raw = author_urn.strip()
        if raw.startswith("urn:li:"):
            return raw
        # If bare ID is provided, default to person URN
        return f"urn:li:person:{raw}"

    def _format_public_url(self, post_urn: str) -> str:
        """Construct canonical public LinkedIn feed URL from post URN."""
        return f"https://www.linkedin.com/feed/update/{post_urn}/"

    def build_payload(self, request: PublishingRequest, author_urn: str) -> dict[str, Any]:
        """Construct official LinkedIn REST API post payload."""
        full_text = request.get_full_text()
        normalized_author = self._normalize_author_urn(author_urn)

        return {
            "author": normalized_author,
            "commentary": full_text,
            "visibility": "PUBLIC",
            "distribution": {
                "feedDistribution": "MAIN_FEED",
                "targetEntities": [],
                "thirdPartyDistributionChannels": [],
            },
            "lifecycleState": "PUBLISHED",
            "isReshareDisabledByAuthor": False,
        }

    async def publish(
        self,
        request: PublishingRequest,
        credentials: PlatformCredentials,
    ) -> PublicationResult:
        """Publish post text to LinkedIn via REST API."""
        if not credentials.access_token:
            raise PermanentPlatformError(
                message="LinkedIn publishing requires a valid access token.",
                error_code="MISSING_LINKEDIN_TOKEN",
            )
        if not credentials.author_urn:
            raise PermanentPlatformError(
                message="LinkedIn publishing requires a valid author URN.",
                error_code="MISSING_LINKEDIN_AUTHOR_URN",
            )

        headers = {
            "Authorization": f"Bearer {credentials.access_token}",
            "LinkedIn-Version": self.api_version,
            "X-Restli-Protocol-Version": "2.0.0",
            "Content-Type": "application/json",
        }

        payload = self.build_payload(request, credentials.author_urn)

        logger.info(
            "Dispatching LinkedIn post for author '%s' (content length: %d chars)",
            credentials.author_urn,
            len(payload.get("commentary", "")),
        )

        try:
            if self._http_client is not None:
                response = await self._http_client.post(
                    self.api_url,
                    json=payload,
                    headers=headers,
                    timeout=self.timeout_seconds,
                )
            else:
                async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                    response = await client.post(
                        self.api_url,
                        json=payload,
                        headers=headers,
                    )
        except httpx.TimeoutException as timeout_err:
            logger.warning("LinkedIn API request timed out: %s", timeout_err)
            raise TransientPlatformError(
                message=f"LinkedIn API timed out after {self.timeout_seconds}s: {timeout_err}",
                error_code="LINKEDIN_TIMEOUT",
                original_error=timeout_err,
            ) from timeout_err
        except httpx.NetworkError as net_err:
            logger.warning("LinkedIn API network error: %s", net_err)
            raise TransientPlatformError(
                message=f"LinkedIn network connection failed: {net_err}",
                error_code="LINKEDIN_NETWORK_ERROR",
                original_error=net_err,
            ) from net_err
        except Exception as err:
            logger.exception("Unexpected error during LinkedIn publish HTTP request: %s", err)
            raise TransientPlatformError(
                message=f"Unexpected publishing client error: {err}",
                error_code="LINKEDIN_CLIENT_ERROR",
                original_error=err,
            ) from err

        # Process HTTP Response
        return self._handle_response(response)

    def _handle_response(self, response: httpx.Response) -> PublicationResult:
        """Translate raw HTTP response from LinkedIn into PublicationResult or PlatformError."""
        status_code = response.status_code

        # 201 Created (Standard LinkedIn post creation success)
        if status_code in (200, 201):
            post_urn = response.headers.get("x-restli-id") or response.headers.get("X-RestLi-Id")
            response_json: dict[str, Any] = {}
            try:
                response_json = response.json()
            except Exception:
                pass

            if not post_urn and isinstance(response_json, dict):
                post_urn = response_json.get("id")

            if not post_urn:
                # Fallback identifier if header not returned
                post_urn = f"urn:li:share:unknown_{int(datetime.now(timezone.utc).timestamp())}"

            external_url = self._format_public_url(post_urn)
            logger.info("LinkedIn post successfully published. Post URN: '%s'", post_urn)

            return PublicationResult(
                success=True,
                platform="linkedin",
                external_post_id=post_urn,
                external_url=external_url,
                published_at=datetime.now(timezone.utc),
                raw_response=response_json if response_json else {"status": status_code},
            )

        # Parse error payload safely
        error_body = {}
        try:
            error_body = response.json()
        except Exception:
            error_body = {"raw": response.text[:500]}

        error_message = error_body.get("message") or response.text or f"HTTP {status_code}"

        logger.warning(
            "LinkedIn API returned error status %d: %s",
            status_code,
            error_message,
        )

        if status_code == 400:
            raise PermanentPlatformError(
                message=f"LinkedIn Bad Request (400): {error_message}",
                error_code="LINKEDIN_BAD_REQUEST",
            )
        elif status_code == 401:
            raise PermanentPlatformError(
                message=f"LinkedIn Unauthorized (401): {error_message}",
                error_code="LINKEDIN_UNAUTHORIZED",
            )
        elif status_code == 403:
            raise PermanentPlatformError(
                message=f"LinkedIn Forbidden (403): {error_message}",
                error_code="LINKEDIN_FORBIDDEN",
            )
        elif status_code == 422:
            raise PermanentPlatformError(
                message=f"LinkedIn Unprocessable Entity (422): {error_message}",
                error_code="LINKEDIN_UNPROCESSABLE",
            )
        elif status_code == 429:
            raise TransientPlatformError(
                message=f"LinkedIn Rate Limited (429): {error_message}",
                error_code="LINKEDIN_RATE_LIMITED",
            )
        elif status_code in (500, 502, 503, 504):
            raise TransientPlatformError(
                message=f"LinkedIn Server Error ({status_code}): {error_message}",
                error_code="LINKEDIN_SERVER_ERROR",
            )
        else:
            raise PermanentPlatformError(
                message=f"LinkedIn unexpected error ({status_code}): {error_message}",
                error_code=f"LINKEDIN_HTTP_{status_code}",
            )
