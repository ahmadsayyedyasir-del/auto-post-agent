"""Initial schema for workflow_runs, posts, revisions, and feedbacks.

Revision ID: 0001_initial_schema
Revises: 
Create Date: 2026-09-22 17:15:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0001_initial_schema"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Table: workflow_runs
    op.create_table(
        "workflow_runs",
        sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
        sa.Column("niche", sa.String(length=255), nullable=False),
        sa.Column("target_platform", sa.String(length=50), nullable=False),
        sa.Column("audience", sa.String(length=255), nullable=True),
        sa.Column("language", sa.String(length=50), nullable=False, server_default="English"),
        sa.Column("status", sa.String(length=50), nullable=False, server_default="STARTING"),
        sa.Column("current_stage", sa.String(length=50), nullable=True),
        sa.Column("revision_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_revisions", sa.Integer(), nullable=False, server_default="2"),
        sa.Column("research_data", sa.JSON(), nullable=True),
        sa.Column("content_plan", sa.JSON(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_workflow_runs_status", "workflow_runs", ["status"])
    op.create_index("ix_workflow_runs_created_at", "workflow_runs", ["created_at"])

    # 2. Table: posts
    op.create_table(
        "posts",
        sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
        sa.Column("workflow_run_id", sa.String(length=36), sa.ForeignKey("workflow_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("platform", sa.String(length=50), nullable=False),
        sa.Column("topic", sa.String(length=255), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False, server_default="DRAFT"),
        sa.Column("content_type", sa.String(length=50), nullable=False, server_default="single_post"),
        sa.Column("language", sa.String(length=50), nullable=False, server_default="English"),
        sa.Column("hashtags", sa.JSON(), nullable=False),
        sa.Column("cta", sa.Text(), nullable=True),
        sa.Column("source_references", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_posts_workflow_run_id", "posts", ["workflow_run_id"])
    op.create_index("ix_posts_status", "posts", ["status"])

    # 3. Table: revisions
    op.create_table(
        "revisions",
        sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
        sa.Column("post_id", sa.String(length=36), sa.ForeignKey("posts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("workflow_run_id", sa.String(length=36), sa.ForeignKey("workflow_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("revision_number", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("hashtags", sa.JSON(), nullable=False),
        sa.Column("cta", sa.Text(), nullable=True),
        sa.Column("source_references", sa.JSON(), nullable=False),
        sa.Column("revision_feedback", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_revisions_post_id", "revisions", ["post_id"])
    op.create_index("ix_revisions_workflow_run_id", "revisions", ["workflow_run_id"])
    op.create_index("ix_revisions_created_at", "revisions", ["created_at"])

    # 4. Table: feedbacks
    op.create_table(
        "feedbacks",
        sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
        sa.Column("workflow_run_id", sa.String(length=36), sa.ForeignKey("workflow_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("post_id", sa.String(length=36), sa.ForeignKey("posts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("revision_id", sa.String(length=36), sa.ForeignKey("revisions.id", ondelete="CASCADE"), nullable=True),
        sa.Column("feedback_source", sa.String(length=50), nullable=False, server_default="CRITIC"),
        sa.Column("decision", sa.String(length=50), nullable=False, server_default="REVISE"),
        sa.Column("issues", sa.JSON(), nullable=False),
        sa.Column("feedback_items", sa.JSON(), nullable=False),
        sa.Column("quality_checks", sa.JSON(), nullable=True),
        sa.Column("verified_sources", sa.JSON(), nullable=False),
        sa.Column("unverified_claims", sa.JSON(), nullable=False),
        sa.Column("reviewer_notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_feedbacks_workflow_run_id", "feedbacks", ["workflow_run_id"])
    op.create_index("ix_feedbacks_post_id", "feedbacks", ["post_id"])
    op.create_index("ix_feedbacks_revision_id", "feedbacks", ["revision_id"])
    op.create_index("ix_feedbacks_created_at", "feedbacks", ["created_at"])


def downgrade() -> None:
    op.drop_table("feedbacks")
    op.drop_table("revisions")
    op.drop_table("posts")
    op.drop_table("workflow_runs")
