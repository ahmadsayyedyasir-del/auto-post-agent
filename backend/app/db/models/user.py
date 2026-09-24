"""SQLAlchemy ORM models for User, PlatformCredential, and RefreshToken (Phase 12)."""

from datetime import datetime
from typing import TYPE_CHECKING
import uuid

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.db.session import Base

if TYPE_CHECKING:
    from backend.app.db.models.workflow import WorkflowRun


class User(Base):
    """Represents an authenticated application user."""

    __tablename__ = "users"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    email: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        nullable=False,
        index=True,
    )
    hashed_password: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    full_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_superuser: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Relationships
    platform_credentials: Mapped[list["PlatformCredential"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    refresh_tokens: Mapped[list["RefreshToken"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    workflow_runs: Mapped[list["WorkflowRun"]] = relationship(
        back_populates="user",
        lazy="dynamic",
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<User id={self.id!r} email=**REDACTED**>"


class PlatformCredential(Base):
    """Encrypted per-user platform credentials (e.g. LinkedIn tokens).

    SECURITY: The ``credential_value`` field is Fernet-encrypted at rest.
    Credentials are NEVER stored in plaintext and NEVER returned to clients.
    """

    __tablename__ = "platform_credentials"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    platform: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
    )
    credential_key: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )
    # Fernet-encrypted credential value — NEVER log or return raw
    credential_value_encrypted: Mapped[str] = mapped_column(Text, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Relationship
    user: Mapped["User"] = relationship(back_populates="platform_credentials")

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<PlatformCredential id={self.id!r} "
            f"user_id={self.user_id!r} "
            f"platform={self.platform!r} "
            f"key={self.credential_key!r}>"
        )


class RefreshToken(Base):
    """Hashed refresh token for secure JWT refresh flow.

    SECURITY: Only the hash of the refresh token is stored, never the raw token.
    """

    __tablename__ = "refresh_tokens"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    token_hash: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        unique=True,
        index=True,
    )
    is_revoked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # Relationship
    user: Mapped["User"] = relationship(back_populates="refresh_tokens")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<RefreshToken id={self.id!r} user_id={self.user_id!r} revoked={self.is_revoked}>"
