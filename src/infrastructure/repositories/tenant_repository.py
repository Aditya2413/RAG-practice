from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.orm import selectinload

from src.infrastructure.database.postgres.models.tenant import Tenant, TenantConfig
from src.infrastructure.repositories.base import IRepository


class TenantRepository(IRepository[Tenant]):
    async def find_by_id(self, id: UUID) -> Tenant | None:
        result = await self.session.execute(
            sa.select(Tenant)
            .options(selectinload(Tenant.config))
            .where(Tenant.id == id)
        )
        return result.scalar_one_or_none()

    async def find_by_slug(self, slug: str) -> Tenant | None:
        result = await self.session.execute(
            sa.select(Tenant)
            .options(selectinload(Tenant.config))
            .where(Tenant.slug == slug)
        )
        return result.scalar_one_or_none()

    async def create(self, data: dict) -> Tenant:
        tenant = Tenant(**data)
        self.session.add(tenant)
        await self.session.flush()  # get id before creating config
        config = TenantConfig(tenant_id=tenant.id, config={})
        self.session.add(config)
        await self.session.commit()
        await self.session.refresh(tenant)
        # reload with config eager-loaded
        return await self.find_by_id(tenant.id)  # type: ignore[return-value]

    async def update(self, id: UUID, data: dict) -> Tenant:
        await self.session.execute(
            sa.update(Tenant).where(Tenant.id == id).values(**data)
        )
        await self.session.commit()
        return await self.find_by_id(id)  # type: ignore[return-value]

    async def delete(self, id: UUID) -> None:
        await self.session.execute(sa.delete(Tenant).where(Tenant.id == id))
        await self.session.commit()

    async def list_active(self) -> list[Tenant]:
        result = await self.session.execute(
            sa.select(Tenant)
            .options(selectinload(Tenant.config))
            .where(Tenant.status == "active")
            .order_by(Tenant.created_at.desc())
        )
        return list(result.scalars().all())
