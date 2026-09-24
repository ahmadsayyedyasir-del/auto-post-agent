"""Phase 12: Repositories for User, PlatformCredential, and RefreshToken entities."""

import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.security import hash_refresh_token
from backend.app.db.models.user import PlatformCredential, RefreshToken, User
from backend.app.db.repositories.base import BaseRepository

logger = logging.getLogger(__name__)


class UserRepository(BaseRepository[User]):
    """Repository for User persistence and lookup."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(User, session)

    async def get_by_email(self, email: str) -> User | None:
        """Fetch a user by their unique email address."""
        stmt = select(User).where(User.email == email.strip().lower())
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_active_by_email(self, email: str) -> User | None:
        """Fetch an active user by email. Returns None if user is inactive."""
        user = await self.get_by_email(email)
        if user and user.is_active:
            return user
        return None

    async def email_exists(self, email: str) -> bool:
        """Return True if a user with the given email already exists."""
        user = await self.get_by_email(email)
        return user is not None

    async def get_all(self, limit: int = 100, offset: int = 0) -> list[User]:
        """Fetch all users (admin use)."""
        stmt = select(User).order_by(User.created_at.desc()).limit(limit).offset(offset)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())


class PlatformCredentialRepository(BaseRepository[PlatformCredential]):
    """Repository for PlatformCredential persistence and lookup.

    SECURITY: This repository stores and retrieves encrypted credential values.
    Raw/decrypted credential values are NEVER stored, logged, or returned from
    this repository layer. Decryption happens in the CredentialResolver only.
    """

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(PlatformCredential, session)

    async def get_by_user_and_platform_key(
        self,
        user_id: str,
        platform: str,
        credential_key: str,
    ) -> PlatformCredential | None:
        """Fetch a specific credential row by user, platform, and credential key."""
        stmt = select(PlatformCredential).where(
            PlatformCredential.user_id == user_id,
            PlatformCredential.platform == platform.strip().lower(),
            PlatformCredential.credential_key == credential_key.strip(),
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_all_for_user_and_platform(
        self,
        user_id: str,
        platform: str,
    ) -> list[PlatformCredential]:
        """Fetch all credential rows for a specific user and platform."""
        stmt = select(PlatformCredential).where(
            PlatformCredential.user_id == user_id,
            PlatformCredential.platform == platform.strip().lower(),
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_all_for_user(self, user_id: str) -> list[PlatformCredential]:
        """Fetch all credential rows for a user across all platforms."""
        stmt = select(PlatformCredential).where(
            PlatformCredential.user_id == user_id
        ).order_by(PlatformCredential.platform, PlatformCredential.credential_key)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def upsert_credential(
        self,
        user_id: str,
        platform: str,
        credential_key: str,
        encrypted_value: str,
    ) -> PlatformCredential:
        """Create or update a platform credential entry for a user.

        SECURITY: *encrypted_value* must already be Fernet-encrypted before
        being passed to this method. This repository never handles plaintext.
        """
        existing = await self.get_by_user_and_platform_key(
            user_id=user_id,
            platform=platform,
            credential_key=credential_key,
        )
        if existing:
            existing.credential_value_encrypted = encrypted_value
            await self.session.flush()
            return existing

        credential = PlatformCredential(
            user_id=user_id,
            platform=platform.strip().lower(),
            credential_key=credential_key.strip(),
            credential_value_encrypted=encrypted_value,
        )
        self.session.add(credential)
        await self.session.flush()
        return credential

    async def delete_credential(
        self,
        user_id: str,
        platform: str,
        credential_key: str,
    ) -> bool:
        """Delete a specific credential. Returns True if deleted, False if not found."""
        existing = await self.get_by_user_and_platform_key(user_id, platform, credential_key)
        if not existing:
            return False
        await self.session.delete(existing)
        await self.session.flush()
        return True


class RefreshTokenRepository(BaseRepository[RefreshToken]):
    """Repository for RefreshToken persistence, validation, and revocation.

    SECURITY: This repository stores and queries only the SHA-256 hash of
    refresh tokens. Raw tokens are NEVER stored.
    """

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(RefreshToken, session)

    async def get_valid_by_raw_token(self, raw_token: str) -> RefreshToken | None:
        """Look up an active, non-revoked, non-expired refresh token by its raw value.

        SECURITY: Hashes the raw token before querying; raw value is not logged.
        """
        token_hash = hash_refresh_token(raw_token)
        now = datetime.now(timezone.utc)
        stmt = select(RefreshToken).where(
            RefreshToken.token_hash == token_hash,
            RefreshToken.is_revoked == False,  # noqa: E712
            RefreshToken.expires_at > now,
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def revoke_token(self, raw_token: str) -> bool:
        """Revoke a refresh token by its raw value. Returns True if found and revoked."""
        token_hash = hash_refresh_token(raw_token)
        stmt = select(RefreshToken).where(RefreshToken.token_hash == token_hash)
        result = await self.session.execute(stmt)
        token = result.scalar_one_or_none()
        if token:
            token.is_revoked = True
            await self.session.flush()
            return True
        return False

    async def revoke_all_for_user(self, user_id: str) -> int:
        """Revoke all refresh tokens for a given user. Returns count of tokens revoked."""
        stmt = select(RefreshToken).where(
            RefreshToken.user_id == user_id,
            RefreshToken.is_revoked == False,  # noqa: E712
        )
        result = await self.session.execute(stmt)
        tokens = list(result.scalars().all())
        for tok in tokens:
            tok.is_revoked = True
        if tokens:
            await self.session.flush()
        return len(tokens)

    async def delete_expired_tokens(self) -> int:
        """Remove all expired tokens (maintenance). Returns count deleted."""
        now = datetime.now(timezone.utc)
        stmt = select(RefreshToken).where(RefreshToken.expires_at <= now)
        result = await self.session.execute(stmt)
        tokens = list(result.scalars().all())
        for tok in tokens:
            await self.session.delete(tok)
        if tokens:
            await self.session.flush()
        return len(tokens)
