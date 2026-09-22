"""Checkpointer factory providing Memory, SQLite, and PostgreSQL persistence for LangGraph workflows."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
import logging
import os
from typing import Any

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import MemorySaver
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from backend.app.config import Settings, get_settings

logger = logging.getLogger(__name__)


def create_in_memory_checkpointer() -> MemorySaver:
    """Create an in-memory checkpointer for testing and fast transient runs."""
    return MemorySaver()


@asynccontextmanager
async def get_workflow_checkpointer(
    settings: Settings | None = None,
) -> AsyncGenerator[BaseCheckpointSaver, None]:
    """Provide an asynchronous checkpointer context based on application configuration."""
    cfg = settings or get_settings()
    checkpointer_type = cfg.checkpointer_type.lower()

    if checkpointer_type == "memory":
        logger.debug("Using MemorySaver checkpointer")
        yield MemorySaver()
    elif checkpointer_type == "sqlite":
        db_path = cfg.checkpoint_db_path
        db_dir = os.path.dirname(db_path)
        if db_dir:
            os.makedirs(db_dir, exist_ok=True)
        logger.debug("Initializing AsyncSqliteSaver with path: %s", db_path)
        async with AsyncSqliteSaver.from_conn_string(db_path) as saver:
            yield saver
    elif checkpointer_type == "postgres":
        logger.debug("Initializing AsyncPostgresSaver with DATABASE_URL")
        from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

        # Convert SQLAlchemy URL if necessary (e.g., postgresql+asyncpg:// to postgresql://)
        pg_url = cfg.database_url.replace("+asyncpg", "")
        async with AsyncPostgresSaver.from_conn_string(pg_url) as saver:
            await saver.setup()
            yield saver
    else:
        logger.warning("Unrecognized checkpointer type '%s', falling back to MemorySaver", checkpointer_type)
        yield MemorySaver()
