from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class CollectionCreate(BaseModel):
    name: str
    description: str | None = None
    schema_hints: dict = Field(default_factory=dict)


class CollectionUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    schema_hints: dict | None = None
    status: str | None = None


class CollectionResponse(BaseModel):
    id: UUID
    tenant_id: UUID
    name: str
    description: str | None
    schema_hints: dict
    status: str
    document_count: int
    created_at: datetime

    model_config = {"from_attributes": True}


class CollectionListResponse(BaseModel):
    items: list[CollectionResponse]
    total: int
