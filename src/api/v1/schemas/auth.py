from uuid import UUID

from pydantic import BaseModel, EmailStr


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    first_name: str
    last_name: str
    tenant_slug: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    refresh_token: str


class UserProfile(BaseModel):
    id: UUID
    tenant_id: UUID
    email: str
    role: str
    first_name: str | None
    last_name: str | None
    is_active: bool

    model_config = {"from_attributes": True}
