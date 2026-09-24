"""Phase 12: API endpoints for per-user platform credential management.

SECURITY:
- All endpoints require authentication.
- Credential values are encrypted with Fernet before storage.
- Credential values are NEVER returned in API responses (only metadata).
- Endpoints are scoped to the authenticated user only (no cross-user access).
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.api.v1.dependencies import get_current_active_user
from backend.app.core.security import encrypt_credential
from backend.app.db.models.user import User
from backend.app.db.repositories.user_repo import PlatformCredentialRepository
from backend.app.db.session import get_db_session
from backend.app.publishing.credential_schemas import (
    CredentialDeleteResponse,
    CredentialListResponse,
    CredentialMetadataResponse,
    UpsertCredentialRequest,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/credentials", tags=["Platform Credentials"])


@router.post(
    "",
    response_model=CredentialMetadataResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Store or update a platform credential for the authenticated user",
)
async def upsert_credential(
    request: UpsertCredentialRequest,
    current_user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_db_session),
) -> CredentialMetadataResponse:
    """Store or update a platform credential (e.g. LinkedIn access token).

    The value is Fernet-encrypted before storage. It cannot be retrieved
    afterward — only updated or deleted. Returns only metadata.

    SECURITY: The plaintext credential_value is not logged or stored.
    """
    repo = PlatformCredentialRepository(session)

    norm_platform = request.platform.strip().lower()
    norm_key = request.credential_key.strip()

    # Encrypt before storage — plaintext never persisted
    encrypted_value = encrypt_credential(request.credential_value)

    credential = await repo.upsert_credential(
        user_id=current_user.id,
        platform=norm_platform,
        credential_key=norm_key,
        encrypted_value=encrypted_value,
    )
    await session.commit()
    await session.refresh(credential)

    logger.info(
        "Upserted credential platform=%s key=%s for user_id=%s",
        norm_platform,
        norm_key,
        current_user.id,
    )
    return CredentialMetadataResponse(
        id=credential.id,
        platform=credential.platform,
        credential_key=credential.credential_key,
        created_at=credential.created_at,
        updated_at=credential.updated_at,
    )


@router.get(
    "",
    response_model=CredentialListResponse,
    summary="List metadata for all platform credentials stored by the authenticated user",
)
async def list_credentials(
    current_user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_db_session),
) -> CredentialListResponse:
    """Return metadata for all platform credentials stored for the authenticated user.

    SECURITY: Values are never returned — only platform name, key name, and timestamps.
    """
    repo = PlatformCredentialRepository(session)
    credentials = await repo.get_all_for_user(current_user.id)
    items = [
        CredentialMetadataResponse(
            id=c.id,
            platform=c.platform,
            credential_key=c.credential_key,
            created_at=c.created_at,
            updated_at=c.updated_at,
        )
        for c in credentials
    ]
    return CredentialListResponse(credentials=items, total=len(items))


@router.get(
    "/{platform}",
    response_model=CredentialListResponse,
    summary="List metadata for credentials stored for a specific platform",
)
async def list_platform_credentials(
    platform: str,
    current_user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_db_session),
) -> CredentialListResponse:
    """List all credential key names stored for a specific platform."""
    repo = PlatformCredentialRepository(session)
    norm_platform = platform.strip().lower()
    credentials = await repo.get_all_for_user_and_platform(current_user.id, norm_platform)
    items = [
        CredentialMetadataResponse(
            id=c.id,
            platform=c.platform,
            credential_key=c.credential_key,
            created_at=c.created_at,
            updated_at=c.updated_at,
        )
        for c in credentials
    ]
    return CredentialListResponse(credentials=items, total=len(items))


@router.delete(
    "/{platform}/{credential_key}",
    response_model=CredentialDeleteResponse,
    summary="Delete a specific platform credential",
)
async def delete_credential(
    platform: str,
    credential_key: str,
    current_user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_db_session),
) -> CredentialDeleteResponse:
    """Delete a stored platform credential by platform and key name."""
    repo = PlatformCredentialRepository(session)
    norm_platform = platform.strip().lower()
    norm_key = credential_key.strip()

    deleted = await repo.delete_credential(
        user_id=current_user.id,
        platform=norm_platform,
        credential_key=norm_key,
    )
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Credential '{norm_key}' for platform '{norm_platform}' not found.",
        )
    await session.commit()
    logger.info(
        "Deleted credential platform=%s key=%s for user_id=%s",
        norm_platform,
        norm_key,
        current_user.id,
    )
    return CredentialDeleteResponse(
        deleted=True,
        platform=norm_platform,
        credential_key=norm_key,
    )
