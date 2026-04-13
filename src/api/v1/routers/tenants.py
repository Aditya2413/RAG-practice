from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.dependencies import get_db, require_role
from src.api.v1.schemas.tenant import TenantCreate, TenantResponse, TenantUpdate
from src.infrastructure.database.postgres.models.user import User
from src.infrastructure.repositories.tenant_repository import TenantRepository
from src.services.tenant.tenant_service import TenantService

router = APIRouter(prefix="/tenants", tags=["tenants"])


def _service(db: AsyncSession) -> TenantService:
    return TenantService(TenantRepository(db))


@router.get("", response_model=list[TenantResponse])
async def list_tenants(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_role("SUPER_ADMIN")),
) -> list[TenantResponse]:
    tenants = await _service(db).list_tenants()
    return [TenantResponse.model_validate(t) for t in tenants]


@router.post("", response_model=TenantResponse, status_code=201)
async def create_tenant(
    body: TenantCreate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_role("SUPER_ADMIN")),
) -> TenantResponse:
    tenant = await _service(db).create_tenant(body.name, body.slug, body.plan)
    return TenantResponse.model_validate(tenant)


@router.get("/{tenant_id}", response_model=TenantResponse)
async def get_tenant(
    tenant_id: UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_role("SUPER_ADMIN", "CLIENT_ADMIN")),
) -> TenantResponse:
    tenant = await _service(db).get_tenant(tenant_id)
    return TenantResponse.model_validate(tenant)


@router.patch("/{tenant_id}", response_model=TenantResponse)
async def update_tenant(
    tenant_id: UUID,
    body: TenantUpdate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_role("SUPER_ADMIN")),
) -> TenantResponse:
    data = body.model_dump(exclude_none=True)
    tenant = await _service(db).update_tenant(tenant_id, data)
    return TenantResponse.model_validate(tenant)
