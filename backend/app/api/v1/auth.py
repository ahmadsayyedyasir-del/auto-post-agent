"""Phase 12: Authentication API endpoints — register, login, refresh, logout, profile."""

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.api.v1.dependencies import get_current_active_user
from backend.app.db.models.user import User
from backend.app.db.session import get_db_session
from backend.app.models.auth import (
    AccessTokenResponse,
    MessageResponse,
    TokenRefreshRequest,
    TokenResponse,
    UserRegisterRequest,
    UserResponse,
)
from backend.app.models.auth import UserLoginRequest
from backend.app.services.auth_service import AuthService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new user account",
)
async def register(
    request: UserRegisterRequest,
    session: AsyncSession = Depends(get_db_session),
) -> UserResponse:
    """Register a new user.

    Stores only a bcrypt hash of the password. Returns the user profile (no password fields).
    """
    auth_service = AuthService(session)
    try:
        return await auth_service.register(request)
    except ValueError as err:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(err),
        )
    except Exception as err:
        logger.exception("Registration error: %s", type(err).__name__)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Registration failed. Please try again.",
        )


@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Authenticate and receive access + refresh tokens",
)
async def login(
    credentials: UserLoginRequest,
    session: AsyncSession = Depends(get_db_session),
) -> TokenResponse:
    """Authenticate with email and password.

    Returns a JWT access token and an opaque refresh token.
    The refresh token is returned once and stored only as a hash on the server.

    SECURITY: This endpoint intentionally returns a generic error for both
    bad email and bad password to prevent user enumeration.
    """
    auth_service = AuthService(session)
    try:
        return await auth_service.login(
            email=credentials.email,
            plain_password=credentials.password.get_secret_value(),
        )
    except PermissionError as err:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(err),
            headers={"WWW-Authenticate": "Bearer"},
        )
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except Exception as err:
        logger.exception("Login error: %s", type(err).__name__)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Login failed. Please try again.",
        )


@router.post(
    "/refresh",
    response_model=AccessTokenResponse,
    summary="Obtain a new access token using a valid refresh token",
)
async def refresh_token(
    payload: TokenRefreshRequest,
    session: AsyncSession = Depends(get_db_session),
) -> AccessTokenResponse:
    """Exchange a valid refresh token for a new short-lived access token.

    SECURITY: The raw refresh token is never logged or echoed in the response.
    """
    auth_service = AuthService(session)
    try:
        return await auth_service.refresh_access_token(payload.refresh_token)
    except PermissionError as err:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(err),
            headers={"WWW-Authenticate": "Bearer"},
        )
    except ValueError as err:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(err),
            headers={"WWW-Authenticate": "Bearer"},
        )
    except Exception as err:
        logger.exception("Token refresh error: %s", type(err).__name__)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Token refresh failed.",
        )


@router.post(
    "/logout",
    response_model=MessageResponse,
    summary="Revoke a refresh token (logout current session)",
)
async def logout(
    payload: TokenRefreshRequest,
    session: AsyncSession = Depends(get_db_session),
) -> MessageResponse:
    """Revoke a refresh token to end the current session.

    After this call, the provided refresh token can no longer be used.
    The access token will remain valid until it expires naturally.
    """
    auth_service = AuthService(session)
    try:
        return await auth_service.logout(payload.refresh_token)
    except Exception as err:
        logger.exception("Logout error: %s", type(err).__name__)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Logout failed.",
        )


@router.get(
    "/me",
    response_model=UserResponse,
    summary="Get the currently authenticated user's profile",
)
async def get_me(
    current_user: User = Depends(get_current_active_user),
) -> UserResponse:
    """Return the profile of the currently authenticated user.

    SECURITY: Response contains no password hashes, tokens, or platform credentials.
    """
    return UserResponse(
        id=current_user.id,
        email=current_user.email,
        full_name=current_user.full_name,
        is_active=current_user.is_active,
        created_at=current_user.created_at,
    )
