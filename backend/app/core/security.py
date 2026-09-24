"""Phase 12: Security utilities — password hashing, JWT tokens, and Fernet credential encryption.

SECURITY BOUNDARIES:
- Passwords are hashed with bcrypt via passlib; raw passwords never stored or logged.
- JWT secrets never appear in logs, repr, or API responses.
- Fernet key never appears in logs, repr, or API responses.
- Refresh tokens are stored only as SHA-256 hashes; raw tokens are issued once.
"""

from datetime import datetime, timedelta, timezone
from hashlib import sha256
import logging
import secrets
from typing import Any

import bcrypt
from cryptography.fernet import Fernet, InvalidToken
from jose import JWTError, jwt

from backend.app.config import get_settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Password hashing (bcrypt)
# ---------------------------------------------------------------------------


def hash_password(plain_password: str) -> str:
    """Return bcrypt hash of *plain_password*. Never log input or output."""
    pwd_bytes = plain_password.encode("utf-8")
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(pwd_bytes, salt).decode("utf-8")


# Alias for compatibility
get_password_hash = hash_password


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify *plain_password* against stored *hashed_password*."""
    try:
        return bcrypt.checkpw(
            plain_password.encode("utf-8"),
            hashed_password.encode("utf-8"),
        )
    except Exception:
        return False


# ---------------------------------------------------------------------------
# JWT access tokens
# ---------------------------------------------------------------------------

ACCESS_TOKEN_TYPE = "access"


def create_access_token(
    subject: str,
    *,
    expires_delta: timedelta | None = None,
    extra_claims: dict[str, Any] | None = None,
) -> str:
    """Issue a signed JWT access token.

    SECURITY: JWT_SECRET_KEY never logged; token not returned in any log message.
    """
    settings = get_settings()
    now = datetime.now(timezone.utc)
    expire = now + (
        expires_delta
        if expires_delta is not None
        else timedelta(minutes=settings.jwt_access_token_expire_minutes)
    )
    payload: dict[str, Any] = {
        "sub": subject,
        "type": ACCESS_TOKEN_TYPE,
        "iat": now,
        "exp": expire,
    }
    if extra_claims:
        payload.update(extra_claims)

    return jwt.encode(
        payload,
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )


def decode_access_token(token: str) -> dict[str, Any] | None:
    """Decode and validate a JWT access token, returning the payload or None on error.

    SECURITY: token value is never logged.
    """
    settings = get_settings()
    try:
        return jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
        )
    except JWTError:
        return None


# ---------------------------------------------------------------------------
# Refresh tokens
# ---------------------------------------------------------------------------

REFRESH_TOKEN_BYTES = 64  # 512-bit raw token


def generate_refresh_token() -> str:
    """Generate a cryptographically secure opaque refresh token.

    Returns the raw token (issued to client once only).
    """
    return secrets.token_hex(REFRESH_TOKEN_BYTES)


def hash_refresh_token(raw_token: str) -> str:
    """Return SHA-256 hex digest of *raw_token* for secure DB storage."""
    return sha256(raw_token.encode()).hexdigest()


# ---------------------------------------------------------------------------
# Fernet credential encryption
# ---------------------------------------------------------------------------


def _get_fernet() -> Fernet:
    """Return a Fernet instance using the configured CREDENTIAL_ENCRYPTION_KEY.

    SECURITY: Key is loaded from settings only (environment), never hardcoded.
    The key object itself is not logged or repr'd.
    """
    settings = get_settings()
    key_str = (settings.credential_encryption_key or "").strip()
    if not key_str:
        raise RuntimeError(
            "CREDENTIAL_ENCRYPTION_KEY is not configured. "
            "Set a 32 url-safe base64-encoded key in the environment."
        )
    try:
        return Fernet(key_str.encode("utf-8"))
    except Exception as exc:
        raise RuntimeError(
            "CREDENTIAL_ENCRYPTION_KEY is invalid. It must be 32 url-safe base64-encoded bytes."
        ) from exc


def encrypt_credential(plaintext: str) -> str:
    """Encrypt a platform credential value with Fernet symmetric encryption.

    Returns URL-safe base64-encoded ciphertext string.
    SECURITY: plaintext is never logged.
    """
    fernet = _get_fernet()
    encrypted_bytes = fernet.encrypt(plaintext.encode())
    return encrypted_bytes.decode()


def decrypt_credential(ciphertext: str) -> str:
    """Decrypt a Fernet-encrypted credential value.

    Raises cryptography.fernet.InvalidToken if ciphertext is invalid or tampered.
    SECURITY: decrypted value is never logged.
    """
    fernet = _get_fernet()
    try:
        plaintext_bytes = fernet.decrypt(ciphertext.encode())
        return plaintext_bytes.decode()
    except (InvalidToken, Exception) as err:
        logger.error("Credential decryption failed: %s", type(err).__name__)
        raise InvalidToken("Credential decryption failed.") from err
