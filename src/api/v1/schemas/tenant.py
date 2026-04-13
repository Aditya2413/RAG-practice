from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class TenantCreate(BaseModel):
    name: str
    slug: str
    plan: str = "starter"


class TenantUpdate(BaseModel):
    name: str | None = None
    status: str | None = None
    plan: str | None = None


class TenantResponse(BaseModel):
    id: UUID
    name: str
    slug: str
    status: str
    plan: str
    created_at: datetime

    model_config = {"from_attributes": True}
