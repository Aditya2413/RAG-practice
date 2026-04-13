from uuid import UUID

from src.core.exceptions import DuplicateResourceError, TenantNotFoundError
from src.infrastructure.database.postgres.models.tenant import Tenant
from src.infrastructure.repositories.tenant_repository import TenantRepository


class TenantService:
    def __init__(self, tenant_repo: TenantRepository) -> None:
        self._repo = tenant_repo

    async def get_tenant(self, id: UUID) -> Tenant:
        tenant = await self._repo.find_by_id(id)
        if tenant is None:
            raise TenantNotFoundError()
        return tenant

    async def create_tenant(self, name: str, slug: str, plan: str = "starter") -> Tenant:
        existing = await self._repo.find_by_slug(slug)
        if existing:
            raise DuplicateResourceError(f"Tenant with slug '{slug}' already exists")
        return await self._repo.create({"name": name, "slug": slug, "plan": plan})

    async def update_tenant(self, id: UUID, data: dict) -> Tenant:
        tenant = await self._repo.find_by_id(id)
        if tenant is None:
            raise TenantNotFoundError()
        return await self._repo.update(id, data)

    async def list_tenants(self) -> list[Tenant]:
        return await self._repo.list_active()
