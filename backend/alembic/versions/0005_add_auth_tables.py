"""Add users, platform_credentials, refresh_tokens tables and user_id FK to workflow_runs.

Revision ID: 0005_add_auth_tables
Revises: 0004_add_schedules_table
Create Date: 2026-09-24 10:00:00.000000

Phase 12: Authentication, Authorization & Platform Credential Management.
- Creates users table
- Creates platform_credentials table (Fernet-encrypted credential storage)
- Creates refresh_tokens table (hashed tokens only)
- Adds nullable user_id FK to workflow_runs for ownership tracking
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0005_add_auth_tables"
down_revision: Union[str, None] = "0004_add_schedules_table"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # -----------------------------------------------------------------------
    # 1. Create users table
    # -----------------------------------------------------------------------
    op.create_table(
        "users",
        sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
        sa.Column("email", sa.String(length=255), unique=True, nullable=False),
        sa.Column("hashed_password", sa.Text(), nullable=False),
        sa.Column("full_name", sa.String(length=255), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("is_superuser", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)
    op.create_index("ix_users_created_at", "users", ["created_at"])

    # -----------------------------------------------------------------------
    # 2. Create platform_credentials table (Fernet-encrypted at rest)
    # -----------------------------------------------------------------------
    op.create_table(
        "platform_credentials",
        sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
        sa.Column(
            "user_id",
            sa.String(length=36),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("platform", sa.String(length=50), nullable=False),
        sa.Column("credential_key", sa.String(length=100), nullable=False),
        # Fernet-encrypted credential value — never store plaintext
        sa.Column("credential_value_encrypted", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_platform_credentials_user_id", "platform_credentials", ["user_id"])
    op.create_index("ix_platform_credentials_platform", "platform_credentials", ["platform"])
    op.create_index(
        "uq_user_platform_credential_key",
        "platform_credentials",
        ["user_id", "platform", "credential_key"],
        unique=True,
    )

    # -----------------------------------------------------------------------
    # 3. Create refresh_tokens table (only SHA-256 hash stored)
    # -----------------------------------------------------------------------
    op.create_table(
        "refresh_tokens",
        sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
        sa.Column(
            "user_id",
            sa.String(length=36),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("token_hash", sa.String(length=255), unique=True, nullable=False),
        sa.Column("is_revoked", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_refresh_tokens_user_id", "refresh_tokens", ["user_id"])
    op.create_index("ix_refresh_tokens_token_hash", "refresh_tokens", ["token_hash"], unique=True)

    # -----------------------------------------------------------------------
    # 4. Add nullable user_id FK to workflow_runs (backward compatible)
    # -----------------------------------------------------------------------
    with op.batch_alter_table("workflow_runs") as batch_op:
        batch_op.add_column(
            sa.Column(
                "user_id",
                sa.String(length=36),
                sa.ForeignKey("users.id", name="fk_workflow_runs_user_id", ondelete="SET NULL"),
                nullable=True,
            )
        )
        batch_op.create_index("ix_workflow_runs_user_id", ["user_id"])


def downgrade() -> None:
    # Remove user_id FK from workflow_runs
    with op.batch_alter_table("workflow_runs") as batch_op:
        batch_op.drop_index("ix_workflow_runs_user_id")
        batch_op.drop_column("user_id")

    # Drop refresh_tokens
    op.drop_index("ix_refresh_tokens_token_hash", table_name="refresh_tokens")
    op.drop_index("ix_refresh_tokens_user_id", table_name="refresh_tokens")
    op.drop_table("refresh_tokens")

    # Drop platform_credentials
    op.drop_index("uq_user_platform_credential_key", table_name="platform_credentials")
    op.drop_index("ix_platform_credentials_platform", table_name="platform_credentials")
    op.drop_index("ix_platform_credentials_user_id", table_name="platform_credentials")
    op.drop_table("platform_credentials")

    # Drop users
    op.drop_index("ix_users_created_at", table_name="users")
    op.drop_index("ix_users_email", table_name="users")
    op.drop_table("users")
