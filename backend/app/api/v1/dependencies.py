"""Phase 12: FastAPI dependency for resolving the currently authenticated user.

SECURITY:
- Token extracted from Authorization: Bearer header only (not query params).
- Inactive users receive 401, not 403, to avoid user enumeration.
- All errors return generic messages without leaking internal details.
"""

import logging

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db.models.user import User
from backend.app.db.session import get_db_session
from backend.app.services.auth_service import AuthService

logger = logging.getLogger(__name__)

_bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
    session: AsyncSession = Depends(get_db_session),
) -> User:
    """FastAPI dependency: extract and validate Bearer JWT, return authenticated User.

    Returns 401 Unauthorized on any token problem (expired, invalid, missing).
    Returns 401 if the user account is inactive.
    """
    if not credentials or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated. Provide a valid Bearer token.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    auth_service = AuthService(session)
    try:
        user = await auth_service.get_current_user_by_token(credentials.credentials)
    except PermissionError as err:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(err),
            headers={"WWW-Authenticate": "Bearer"},
        )
    except (ValueError, Exception):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired access token.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return user


async def get_current_active_user(
    current_user: User = Depends(get_current_user),
) -> User:
    """Dependency that requires an active (non-disabled) user."""
    if not current_user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Account is inactive.",
        )
    return current_user
