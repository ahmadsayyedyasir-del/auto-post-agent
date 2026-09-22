"""Add revision_source and dual revision counters for HITL workflows.

Revision ID: 0002_hitl_checkpoint_revision_source
Revises: 0001_initial_schema
Create Date: 2026-09-22 20:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0002_hitl_checkpoint_revision_source"
down_revision: Union[str, None] = "0001_initial_schema"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add agent_revision_count and human_revision_count to workflow_runs
    op.add_column(
        "workflow_runs",
        sa.Column("agent_revision_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "workflow_runs",
        sa.Column("human_revision_count", sa.Integer(), nullable=False, server_default="0"),
    )

    # Add revision_source to revisions
    op.add_column(
        "revisions",
        sa.Column("revision_source", sa.String(length=50), nullable=False, server_default="AGENT"),
    )


def downgrade() -> None:
    op.drop_column("revisions", "revision_source")
    op.drop_column("workflow_runs", "human_revision_count")
    op.drop_column("workflow_runs", "agent_revision_count")
