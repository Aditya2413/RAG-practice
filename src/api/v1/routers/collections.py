from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.dependencies import get_current_user, get_db, require_role
from src.api.v1.schemas.collection import (
    CollectionCreate,
    CollectionListResponse,
    CollectionResponse,
    CollectionUpdate,
)
from src.core.context import current_tenant_ctx
from src.core.exceptions import CollectionNotFoundError, DuplicateResourceError
from src.infrastructure.database.postgres.models.user import User
from src.infrastructure.repositories.collection_repository import CollectionRepository

router = APIRouter(prefix="/collections", tags=["collections"])


def _repo(db: AsyncSession) -> CollectionRepository:
    return CollectionRepository(db)


@router.get("", response_model=CollectionListResponse)
async def list_collections(
    skip: int = 0,
    limit: int = 20,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> CollectionListResponse:
    tenant = current_tenant_ctx.get()
    tenant_id = tenant.id if tenant else current_user.tenant_id
    repo = _repo(db)
    items = await repo.list_by_tenant(tenant_id, skip=skip, limit=limit)
    total = await repo.count_by_tenant(tenant_id)
    return CollectionListResponse(
        items=[CollectionResponse.model_validate(c) for c in items],
        total=total,
    )


@router.post("", response_model=CollectionResponse, status_code=201)
async def create_collection(
    body: CollectionCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("SUPER_ADMIN", "CLIENT_ADMIN")),
) -> CollectionResponse:
    tenant = current_tenant_ctx.get()
    tenant_id = tenant.id if tenant else current_user.tenant_id
    repo = _repo(db)
    existing = await repo.find_by_name(body.name, tenant_id)
    if existing:
        raise DuplicateResourceError(f"Collection '{body.name}' already exists in this tenant")
    collection = await repo.create({
        "tenant_id": tenant_id,
        "name": body.name,
        "description": body.description,
        "schema_hints": body.schema_hints,
        "created_by": current_user.id,
    })
    return CollectionResponse.model_validate(collection)


@router.get("/{collection_id}", response_model=CollectionResponse)
async def get_collection(
    collection_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> CollectionResponse:
    tenant = current_tenant_ctx.get()
    tenant_id = tenant.id if tenant else current_user.tenant_id
    collection = await _repo(db).find_by_id(collection_id, tenant_id)
    if collection is None:
        raise CollectionNotFoundError()
    return CollectionResponse.model_validate(collection)


@router.patch("/{collection_id}", response_model=CollectionResponse)
async def update_collection(
    collection_id: UUID,
    body: CollectionUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("SUPER_ADMIN", "CLIENT_ADMIN")),
) -> CollectionResponse:
    tenant = current_tenant_ctx.get()
    tenant_id = tenant.id if tenant else current_user.tenant_id
    repo = _repo(db)
    existing = await repo.find_by_id(collection_id, tenant_id)
    if existing is None:
        raise CollectionNotFoundError()
    data = body.model_dump(exclude_none=True)
    updated = await repo.update(collection_id, data, tenant_id)
    return CollectionResponse.model_validate(updated)


@router.delete("/{collection_id}", status_code=204)
async def delete_collection(
    collection_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("SUPER_ADMIN", "CLIENT_ADMIN")),
) -> None:
    tenant = current_tenant_ctx.get()
    tenant_id = tenant.id if tenant else current_user.tenant_id
    repo = _repo(db)
    existing = await repo.find_by_id(collection_id, tenant_id)
    if existing is None:
        raise CollectionNotFoundError()
    await repo.delete(collection_id, tenant_id)
