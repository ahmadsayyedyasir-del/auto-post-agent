"""Base generic asynchronous repository for SQLAlchemy ORM operations."""

from typing import Generic, TypeVar
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

T = TypeVar("T")


class BaseRepository(Generic[T]):
    """Generic async repository providing standard CRUD operations."""

    def __init__(self, model_cls: type[T], session: AsyncSession) -> None:
        self.model_cls = model_cls
        self.session = session

    async def get_by_id(self, entity_id: str) -> T | None:
        """Fetch an entity by its primary key ID."""
        return await self.session.get(self.model_cls, entity_id)

    async def create(self, entity: T) -> T:
        """Add and persist a new entity."""
        self.session.add(entity)
        await self.session.flush()
        return entity

    async def update(self, entity: T) -> T:
        """Merge and flush updates for an existing entity."""
        merged = await self.session.merge(entity)
        await self.session.flush()
        return merged

    async def delete(self, entity_id: str) -> bool:
        """Delete an entity by its primary key ID."""
        entity = await self.get_by_id(entity_id)
        if entity is not None:
            await self.session.delete(entity)
            await self.session.flush()
            return True
        return False

    async def list_all(self, limit: int = 100, offset: int = 0) -> list[T]:
        """Fetch a paginated list of entities."""
        query = select(self.model_cls).limit(limit).offset(offset)
        result = await self.session.execute(query)
        return list(result.scalars().all())
