"""Add human_rejection_count and max_human_rejections to workflow_runs.

Revision ID: 0006_add_human_rejection_count
Revises: 0005_add_auth_tables
Create Date: 2026-09-26 12:00:00.000000

Phase HITL: 3-cycle human rejection improvement loop.
- Adds human_rejection_count (default 0)
- Adds max_human_rejections (default 3)
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0006_add_human_rejection_count"
down_revision: Union[str, None] = "0005_add_auth_tables"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("workflow_runs") as batch_op:
        batch_op.add_column(
            sa.Column(
                "human_rejection_count",
                sa.Integer(),
                nullable=False,
                server_default="0",
            )
        )
        batch_op.add_column(
            sa.Column(
                "max_human_rejections",
                sa.Integer(),
                nullable=False,
                server_default="3",
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("workflow_runs") as batch_op:
        batch_op.drop_column("max_human_rejections")
        batch_op.drop_column("human_rejection_count")
