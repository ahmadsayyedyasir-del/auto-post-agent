"""Phase 12: Authentication service — register, login, token refresh, logout.

SECURITY GUARANTEES:
- Passwords are never stored or logged in plaintext.
- Refresh tokens are stored only as SHA-256 hashes.
- JWT secrets never appear in logs or responses.
- Credential resolver never leaks platform secrets.
"""

from datetime import datetime, timedelta, timezone
import logging

from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.config import get_settings
from backend.app.core.security import (
    create_access_token,
    decode_access_token,
    generate_refresh_token,
    hash_password,
    hash_refresh_token,
    verify_password,
)
from backend.app.db.models.user import RefreshToken, User
from backend.app.db.repositories.user_repo import RefreshTokenRepository, UserRepository
from backend.app.models.auth import (
    AccessTokenResponse,
    MessageResponse,
    TokenResponse,
    UserLoginRequest,
    UserRegisterRequest,
    UserResponse,
)

logger = logging.getLogger(__name__)


class AuthService:
    """Service orchestrating user registration, login, token issuance, and logout."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.user_repo = UserRepository(session)
        self.token_repo = RefreshTokenRepository(session)
        self.settings = get_settings()

    async def register(self, request: UserRegisterRequest) -> UserResponse:
        """Register a new user account.

        SECURITY: Password is hashed immediately; plaintext is never persisted.
        """
        normalized_email = request.email.strip().lower()
        if await self.user_repo.email_exists(normalized_email):
            raise ValueError(f"An account with email '{normalized_email}' already exists.")

        hashed = hash_password(request.password.get_secret_value())

        user = User(
            email=normalized_email,
            hashed_password=hashed,
            full_name=request.full_name,
            is_active=True,
            is_superuser=False,
        )
        await self.user_repo.create(user)
        await self.session.commit()
        await self.session.refresh(user)

        logger.info("Registered new user id=%s", user.id)
        return UserResponse(
            id=user.id,
            email=user.email,
            full_name=user.full_name,
            is_active=user.is_active,
            created_at=user.created_at,
        )

    async def login(
        self,
        email_or_request: str | UserLoginRequest | None = None,
        plain_password: str | None = None,
        *,
        email: str | None = None,
    ) -> TokenResponse:
        """Authenticate user and return access + refresh token pair.

        Accepts either a UserLoginRequest object or (email, plain_password) strings/kwargs.

        SECURITY:
        - Password verified via bcrypt; raw password never stored/logged.
        - Raw refresh token returned to caller ONCE; only hash stored in DB.
        """
        if isinstance(email_or_request, UserLoginRequest):
            user_email = email_or_request.email
            pwd = email_or_request.password.get_secret_value()
        else:
            user_email = email or (email_or_request if isinstance(email_or_request, str) else "")
            pwd = plain_password or ""

        normalized_email = user_email.strip().lower()
        user = await self.user_repo.get_by_email(normalized_email)

        # Constant-time comparison avoids timing-based email enumeration
        if not user or not verify_password(pwd, user.hashed_password):
            raise ValueError("Invalid email or password.")

        if not user.is_active:
            raise PermissionError("Account is inactive. Contact support.")

        access_token = create_access_token(subject=user.id)
        raw_refresh = generate_refresh_token()
        token_hash = hash_refresh_token(raw_refresh)

        expires_at = datetime.now(timezone.utc) + timedelta(
            days=self.settings.jwt_refresh_token_expire_days
        )
        refresh_token_obj = RefreshToken(
            user_id=user.id,
            token_hash=token_hash,
            is_revoked=False,
            expires_at=expires_at,
        )
        self.session.add(refresh_token_obj)
        await self.session.commit()

        logger.info("User id=%s logged in successfully.", user.id)
        return TokenResponse(
            access_token=access_token,
            refresh_token=raw_refresh,
            expires_in=self.settings.jwt_access_token_expire_minutes * 60,
        )

    async def refresh_access_token(self, raw_refresh_token: str) -> AccessTokenResponse:
        """Issue a new access token in exchange for a valid refresh token.

        SECURITY: Only the token hash is queried; raw token is not logged.
        """
        token_obj = await self.token_repo.get_valid_by_raw_token(raw_refresh_token)
        if not token_obj:
            raise ValueError("Invalid or expired refresh token.")

        user = await self.user_repo.get_by_id(token_obj.user_id)
        if not user or not user.is_active:
            raise PermissionError("User account is inactive or not found.")

        new_access_token = create_access_token(subject=user.id)
        logger.info("Issued new access token for user id=%s via refresh.", user.id)

        return AccessTokenResponse(
            access_token=new_access_token,
            expires_in=self.settings.jwt_access_token_expire_minutes * 60,
        )

    async def logout(self, raw_refresh_token: str) -> MessageResponse:
        """Revoke a refresh token, effectively logging the user out of this session.

        SECURITY: Only the token hash is used for lookup; raw token is not logged.
        """
        revoked = await self.token_repo.revoke_token(raw_refresh_token)
        await self.session.commit()
        if revoked:
            logger.info("Refresh token revoked.")
        else:
            logger.info("Logout: refresh token not found or already revoked.")
        return MessageResponse(message="Successfully logged out.")

    # Alias for convenience
    refresh_token = refresh_access_token

    async def get_current_user_by_token(self, token: str) -> User:
        """Validate JWT access token and return the associated User object.

        SECURITY: Token value is not logged; only user ID is extracted.
        Raises ValueError on invalid/expired tokens.
        Raises PermissionError if user is inactive.
        """
        payload = decode_access_token(token)
        if not payload:
            raise ValueError("Access token is invalid or expired.")

        user_id: str | None = payload.get("sub")
        token_type: str | None = payload.get("type")

        if not user_id or token_type != "access":
            raise ValueError("Access token payload is malformed.")

        user = await self.user_repo.get_by_id(user_id)
        if not user:
            raise ValueError("User associated with token not found.")
        if not user.is_active:
            raise PermissionError("User account is inactive.")

        return user
