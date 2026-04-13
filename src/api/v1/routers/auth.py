import sqlalchemy as sa
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.dependencies import get_current_user, get_db
from src.api.v1.schemas.auth import LoginRequest, RefreshRequest, TokenResponse, UserProfile
from src.core.exceptions import AuthError
from src.core.security import (
    create_access_token,
    create_refresh_token,
    hash_refresh_token,
    refresh_token_expires_at,
    verify_password,
)
from src.infrastructure.database.postgres.models.user import User
from src.infrastructure.repositories.user_repository import UserRepository

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest, db: AsyncSession = Depends(get_db)) -> TokenResponse:
    repo = UserRepository(db)

    # Login is email-only (cross-tenant) — SUPER_ADMIN in particular spans all tenants.
    result = await db.execute(sa.select(User).where(User.email == body.email))
    user = result.scalar_one_or_none()

    if user is None or not user.is_active or not verify_password(body.password, user.password_hash):
        raise AuthError("Invalid email or password")

    payload = {
        "sub": str(user.id),
        "tenant_id": str(user.tenant_id),
        "role": user.role,
    }
    access_token = create_access_token(payload)
    raw_refresh, refresh_hash = create_refresh_token()

    await repo.create_refresh_token(user.id, refresh_hash, refresh_token_expires_at())
    await repo.update_last_login(user.id)

    return TokenResponse(access_token=access_token, refresh_token=raw_refresh)


@router.post("/refresh", response_model=TokenResponse)
async def refresh(body: RefreshRequest, db: AsyncSession = Depends(get_db)) -> TokenResponse:
    repo = UserRepository(db)
    token_hash = hash_refresh_token(body.refresh_token)
    stored = await repo.find_refresh_token(token_hash)
    if stored is None:
        raise AuthError("Invalid or expired refresh token")

    # Rotation: revoke old, issue new
    await repo.revoke_refresh_token(token_hash)
    user = await repo.find_by_id(stored.user_id)
    if user is None or not user.is_active:
        raise AuthError("User not found or inactive")

    payload = {
        "sub": str(user.id),
        "tenant_id": str(user.tenant_id),
        "role": user.role,
    }
    access_token = create_access_token(payload)
    raw_refresh, refresh_hash = create_refresh_token()
    await repo.create_refresh_token(user.id, refresh_hash, refresh_token_expires_at())

    return TokenResponse(access_token=access_token, refresh_token=raw_refresh)


@router.post("/logout", status_code=204)
async def logout(body: RefreshRequest, db: AsyncSession = Depends(get_db)) -> None:
    repo = UserRepository(db)
    token_hash = hash_refresh_token(body.refresh_token)
    await repo.revoke_refresh_token(token_hash)


@router.get("/me", response_model=UserProfile)
async def get_me(current_user: User = Depends(get_current_user)) -> UserProfile:
    return UserProfile.model_validate(current_user)
