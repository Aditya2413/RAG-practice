from uuid import UUID

import sqlalchemy as sa

from src.infrastructure.database.postgres.models.collection import Collection
from src.infrastructure.repositories.base import IRepository


class CollectionRepository(IRepository[Collection]):
    async def find_by_id(self, id: UUID, tenant_id: UUID | None = None) -> Collection | None:
        stmt = sa.select(Collection).where(Collection.id == id)
        if tenant_id is not None:
            stmt = stmt.where(Collection.tenant_id == tenant_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def find_by_name(self, name: str, tenant_id: UUID) -> Collection | None:
        result = await self.session.execute(
            sa.select(Collection).where(
                Collection.name == name, Collection.tenant_id == tenant_id
            )
        )
        return result.scalar_one_or_none()

    async def create(self, data: dict) -> Collection:
        collection = Collection(**data)
        self.session.add(collection)
        await self.session.commit()
        await self.session.refresh(collection)
        return collection

    async def update(self, id: UUID, data: dict, tenant_id: UUID | None = None) -> Collection:
        stmt = sa.update(Collection).where(Collection.id == id).values(**data)
        if tenant_id is not None:
            stmt = stmt.where(Collection.tenant_id == tenant_id)
        await self.session.execute(stmt)
        await self.session.commit()
        return await self.find_by_id(id)  # type: ignore[return-value]

    async def delete(self, id: UUID, tenant_id: UUID | None = None) -> None:
        stmt = sa.delete(Collection).where(Collection.id == id)
        if tenant_id is not None:
            stmt = stmt.where(Collection.tenant_id == tenant_id)
        await self.session.execute(stmt)
        await self.session.commit()

    async def list_by_tenant(
        self, tenant_id: UUID, skip: int = 0, limit: int = 20
    ) -> list[Collection]:
        result = await self.session.execute(
            sa.select(Collection)
            .where(Collection.tenant_id == tenant_id, Collection.status == "active")
            .order_by(Collection.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        return list(result.scalars().all())

    async def count_by_tenant(self, tenant_id: UUID) -> int:
        result = await self.session.execute(
            sa.select(sa.func.count()).where(
                Collection.tenant_id == tenant_id, Collection.status == "active"
            )
        )
        return result.scalar_one()
