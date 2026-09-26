"""Unit and integration tests for SQLAlchemy 2.x persistence layer, models, and repositories."""

from datetime import datetime
import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.app.db.models.feedback import Feedback
from backend.app.db.models.post import Post, Revision
from backend.app.db.models.workflow import WorkflowRun
from backend.app.db.repositories.workflow_repo import (
    FeedbackRepository,
    PostRepository,
    WorkflowRepository,
)
from backend.app.db.session import Base
from backend.app.models.content import SocialPost
from backend.app.models.critic import CriticResult, QualityChecks
from backend.app.models.planning import ContentPlan
from backend.app.models.research import ResearchRequest, ResearchResponse, Trend


# ------------------------------------------------------------------------------
# Test Fixtures
# ------------------------------------------------------------------------------


@pytest.fixture
async def async_engine():
    """Create an isolated in-memory SQLite database engine for testing."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest.fixture
async def db_session(async_engine):
    """Yield an async session with automatic rollback on test completion."""
    session_factory = async_sessionmaker(
        bind=async_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )
    async with session_factory() as session:
        yield session
        await session.rollback()


# ------------------------------------------------------------------------------
# 1. Engine & Schema Creation Tests
# ------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_database_schema_creation(async_engine) -> None:
    """Verify all database tables and schema objects are registered with metadata."""
    table_names = set(Base.metadata.tables.keys())
    assert "workflow_runs" in table_names
    assert "posts" in table_names
    assert "revisions" in table_names
    assert "feedbacks" in table_names


# ------------------------------------------------------------------------------
# 2. WorkflowRun Repository & Model Tests
# ------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_workflow_run_create_and_read(db_session: AsyncSession) -> None:
    """Verify creating, querying, and updating a WorkflowRun entity."""
    repo = WorkflowRepository(db_session)

    workflow = WorkflowRun(
        niche="Artificial Intelligence",
        target_platform="linkedin",
        audience="AI Engineers",
        language="English",
        status="STARTING",
        max_revisions=2,
        research_data={"total_results_found": 3},
        content_plan={"topic": "Agentic AI in Enterprise"},
    )
    created = await repo.create(workflow)
    await db_session.commit()

    assert created.id is not None
    assert len(created.id) == 36
    assert created.status == "STARTING"
    assert created.created_at is not None

    # Fetch by ID
    fetched = await repo.get_by_id(created.id)
    assert fetched is not None
    assert fetched.niche == "Artificial Intelligence"
    assert fetched.content_plan["topic"] == "Agentic AI in Enterprise"

    # Update status
    updated = await repo.update_status(
        workflow_id=created.id,
        status="WAITING_FOR_HUMAN_REVIEW",
        current_stage="human_review",
    )
    await db_session.commit()
    assert updated.status == "WAITING_FOR_HUMAN_REVIEW"
    assert updated.current_stage == "human_review"


@pytest.mark.asyncio
async def test_workflow_run_list_by_status(db_session: AsyncSession) -> None:
    """Verify querying workflow runs filtered by lifecycle status."""
    repo = WorkflowRepository(db_session)

    w1 = WorkflowRun(niche="AI", target_platform="linkedin", status="PLANNING")
    w2 = WorkflowRun(niche="Cloud", target_platform="twitter", status="WAITING_FOR_HUMAN_REVIEW")
    w3 = WorkflowRun(niche="Cybersecurity", target_platform="linkedin", status="WAITING_FOR_HUMAN_REVIEW")

    await repo.create(w1)
    await repo.create(w2)
    await repo.create(w3)
    await db_session.commit()

    pending_reviews = await repo.get_by_status("WAITING_FOR_HUMAN_REVIEW")
    assert len(pending_reviews) == 2
    assert {w.niche for w in pending_reviews} == {"Cloud", "Cybersecurity"}


# ------------------------------------------------------------------------------
# 3. Post & Historical Revision Tracking Tests
# ------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_post_creation_and_revision_snapshots(db_session: AsyncSession) -> None:
    """Verify that updating a post preserves historical draft snapshots in Revisions."""
    wf_repo = WorkflowRepository(db_session)
    post_repo = PostRepository(db_session)

    # 1. Create parent workflow
    workflow = await wf_repo.create(
        WorkflowRun(niche="AI", target_platform="linkedin", status="WRITING")
    )
    await db_session.commit()

    # 2. Create initial post draft
    post = Post(
        workflow_run_id=workflow.id,
        platform="linkedin",
        topic="Agentic AI in Enterprise",
        content="Draft 1: Initial draft with simple hooks.",
        status="DRAFT",
        hashtags=["#AI", "#Agents"],
        cta="What do you think?",
        source_references=["https://venturebeat.com/ai/agentic-systems"],
    )
    created_post = await post_repo.create(post)
    await db_session.commit()

    # 3. Snapshot Revision 1
    rev1 = await post_repo.create_revision_snapshot(
        post_id=created_post.id,
        revision_feedback=["Weak hook, make it more punchy."],
    )
    await db_session.commit()

    assert rev1.revision_number == 1
    assert "Draft 1" in rev1.content
    assert rev1.revision_feedback == ["Weak hook, make it more punchy."]

    # 4. Update post to Draft 2 and snapshot Revision 2
    created_post.content = "Draft 2: Revised draft with punchy opening hook!"
    created_post.hashtags = ["#AgenticAI", "#Enterprise", "#AI"]
    await post_repo.update(created_post)

    rev2 = await post_repo.create_revision_snapshot(
        post_id=created_post.id,
        revision_feedback=["Great hook! Fix character spacing."],
    )
    await db_session.commit()

    assert rev2.revision_number == 2
    assert "Draft 2" in rev2.content

    # 5. Verify post retains full revision history in order
    post_with_history = await post_repo.get_with_revisions(created_post.id)
    assert post_with_history is not None
    assert len(post_with_history.revisions) == 2
    assert post_with_history.revisions[0].revision_number == 1
    assert post_with_history.revisions[1].revision_number == 2
    assert post_with_history.content == "Draft 2: Revised draft with punchy opening hook!"


# ------------------------------------------------------------------------------
# 4. Feedback Persistence Tests
# ------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_critic_and_human_feedback_persistence(db_session: AsyncSession) -> None:
    """Verify recording Critic and Human evaluation feedback."""
    wf_repo = WorkflowRepository(db_session)
    post_repo = PostRepository(db_session)
    feedback_repo = FeedbackRepository(db_session)

    workflow = await wf_repo.create(
        WorkflowRun(niche="AI", target_platform="linkedin", status="CRITIQUING")
    )
    post = await post_repo.create(
        Post(
            workflow_run_id=workflow.id,
            platform="linkedin",
            topic="Agentic AI",
            content="Post content evaluating agent loops.",
            status="IN_REVIEW",
        )
    )
    await db_session.commit()

    # Record automated Critic feedback
    critic_fb = Feedback(
        workflow_run_id=workflow.id,
        post_id=post.id,
        feedback_source="CRITIC",
        decision="REVISE",
        issues=["Tone is too informal."],
        feedback_items=["Use professional tone for executive readers."],
        quality_checks={"tone": False, "clarity": True, "source_grounding": True},
        verified_sources=["https://venturebeat.com/ai/agentic-systems"],
        unverified_claims=[],
    )
    await feedback_repo.create(critic_fb)

    # Record Human feedback
    human_fb = Feedback(
        workflow_run_id=workflow.id,
        post_id=post.id,
        feedback_source="HUMAN",
        decision="APPROVED",
        issues=[],
        feedback_items=["Looks ready to publish."],
        reviewer_notes="Approved by Senior Marketing Director.",
    )
    await feedback_repo.create(human_fb)
    await db_session.commit()

    # Fetch feedback for post
    post_feedbacks = await feedback_repo.get_for_post(post.id)
    assert len(post_feedbacks) == 2
    assert {fb.feedback_source for fb in post_feedbacks} == {"CRITIC", "HUMAN"}


# ------------------------------------------------------------------------------
# 5. Cascading Deletion & Relationship Integrity Tests
# ------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_workflow_cascade_deletion(db_session: AsyncSession) -> None:
    """Verify deleting a WorkflowRun cascades and cleans up associated posts, revisions, and feedbacks."""
    wf_repo = WorkflowRepository(db_session)
    post_repo = PostRepository(db_session)
    fb_repo = FeedbackRepository(db_session)

    workflow = await wf_repo.create(WorkflowRun(niche="AI", target_platform="linkedin"))
    post = await post_repo.create(
        Post(workflow_run_id=workflow.id, platform="linkedin", topic="AI", content="Content")
    )
    await post_repo.create_revision_snapshot(post.id)
    await fb_repo.create(
        Feedback(
            workflow_run_id=workflow.id,
            post_id=post.id,
            feedback_source="CRITIC",
            decision="APPROVED",
        )
    )
    await db_session.commit()

    # Delete parent workflow
    deleted = await wf_repo.delete(workflow.id)
    await db_session.commit()
    assert deleted is True

    # Verify children are deleted
    assert await post_repo.get_by_id(post.id) is None
    revs = await db_session.execute(select(Revision).where(Revision.workflow_run_id == workflow.id))
    assert len(revs.scalars().all()) == 0
    fbs = await db_session.execute(select(Feedback).where(Feedback.workflow_run_id == workflow.id))
    assert len(fbs.scalars().all()) == 0


# ------------------------------------------------------------------------------
# 6. Transaction Rollback Tests
# ------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_transaction_rollback_on_error(db_session: AsyncSession) -> None:
    """Verify that uncommitted operations roll back cleanly upon errors."""
    repo = WorkflowRepository(db_session)

    workflow = WorkflowRun(niche="AI", target_platform="linkedin")
    await repo.create(workflow)

    # Rollback without commit
    await db_session.rollback()

    fetched = await repo.get_by_id(workflow.id)
    assert fetched is None


# ------------------------------------------------------------------------------
# 7. Human Rejection & Safe Defaults Tests
# ------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_workflow_run_rejection_defaults(db_session: AsyncSession) -> None:
    """Verify that new and existing workflows default to 0 human rejections and max 3."""
    repo = WorkflowRepository(db_session)

    workflow = WorkflowRun(
        niche="Machine Learning",
        target_platform="twitter",
    )
    created = await repo.create(workflow)
    await db_session.commit()

    fetched = await repo.get_by_id(created.id)
    assert fetched is not None
    assert fetched.human_rejection_count == 0
    assert fetched.max_human_rejections == 3


def test_alembic_migration_0006_upgrade_downgrade() -> None:
    """Verify that Alembic migration 0006 executes upgrade and downgrade cleanly."""
    from alembic.config import Config
    from alembic import command
    from pathlib import Path
    import tempfile

    backend_dir = Path(__file__).resolve().parent.parent
    ini_path = backend_dir / "alembic.ini"

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp_db:
        db_path = Path(tmp_db.name)

    try:
        cfg = Config(str(ini_path))
        cfg.set_main_option("script_location", str(backend_dir / "alembic"))
        cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")

        # Upgrade to head (including 0006)
        command.upgrade(cfg, "head")

        # Downgrade 1 revision (reverts 0006)
        command.downgrade(cfg, "-1")

        # Upgrade back to head
        command.upgrade(cfg, "head")
    finally:
        if db_path.exists():
            try:
                db_path.unlink()
            except Exception:
                pass

