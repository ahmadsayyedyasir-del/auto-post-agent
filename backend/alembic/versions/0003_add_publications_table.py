"""Add publications table for social media publishing layer.

Revision ID: 0003_add_publications_table
Revises: 0002_hitl_checkpoint_revision_source
Create Date: 2026-09-23 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0003_add_publications_table"
down_revision: Union[str, None] = "0002_hitl_checkpoint_revision_source"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "publications",
        sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
        sa.Column(
            "workflow_run_id",
            sa.String(length=36),
            sa.ForeignKey("workflow_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "post_id",
            sa.String(length=36),
            sa.ForeignKey("posts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("platform", sa.String(length=50), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False, server_default="PENDING"),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("external_post_id", sa.String(length=255), nullable=True),
        sa.Column("external_url", sa.Text(), nullable=True),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_code", sa.String(length=100), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
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
        sa.UniqueConstraint("workflow_run_id", "platform", name="uq_publications_workflow_platform"),
    )
    op.create_index("ix_publications_workflow_run_id", "publications", ["workflow_run_id"])
    op.create_index("ix_publications_post_id", "publications", ["post_id"])
    op.create_index("ix_publications_status", "publications", ["status"])
    op.create_index("ix_publications_idempotency_key", "publications", ["idempotency_key"], unique=True)
    op.create_index("ix_publications_created_at", "publications", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_publications_created_at", table_name="publications")
    op.drop_index("ix_publications_idempotency_key", table_name="publications")
    op.drop_index("ix_publications_status", table_name="publications")
    op.drop_index("ix_publications_post_id", table_name="publications")
    op.drop_index("ix_publications_workflow_run_id", table_name="publications")
    op.drop_table("publications")
