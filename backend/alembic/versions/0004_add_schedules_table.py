"""Add schedules table for social media automation and scheduling layer.

Revision ID: 0004_add_schedules_table
Revises: 0003_add_publications_table
Create Date: 2026-09-23 00:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0004_add_schedules_table"
down_revision: Union[str, None] = "0003_add_publications_table"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "schedules",
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
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("timezone", sa.String(length=100), nullable=False, server_default="UTC"),
        sa.Column("status", sa.String(length=50), nullable=False, server_default="SCHEDULED"),
        sa.Column("job_id", sa.String(length=128), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("executed_at", sa.DateTime(timezone=True), nullable=True),
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
    op.create_index("ix_schedules_workflow_run_id", "schedules", ["workflow_run_id"])
    op.create_index("ix_schedules_post_id", "schedules", ["post_id"])
    op.create_index("ix_schedules_status", "schedules", ["status"])
    op.create_index("ix_schedules_scheduled_at", "schedules", ["scheduled_at"])
    op.create_index("ix_schedules_job_id", "schedules", ["job_id"], unique=True)
    op.create_index("ix_schedules_created_at", "schedules", ["created_at"])
    op.create_index(
        "uq_active_workflow_schedule",
        "schedules",
        ["workflow_run_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('SCHEDULED', 'RUNNING')"),
        sqlite_where=sa.text("status IN ('SCHEDULED', 'RUNNING')"),
    )


def downgrade() -> None:
    op.drop_index("uq_active_workflow_schedule", table_name="schedules")
    op.drop_index("ix_schedules_created_at", table_name="schedules")
    op.drop_index("ix_schedules_job_id", table_name="schedules")
    op.drop_index("ix_schedules_scheduled_at", table_name="schedules")
    op.drop_index("ix_schedules_status", table_name="schedules")
    op.drop_index("ix_schedules_post_id", table_name="schedules")
    op.drop_index("ix_schedules_workflow_run_id", table_name="schedules")
    op.drop_table("schedules")
