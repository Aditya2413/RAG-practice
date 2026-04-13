from collections.abc import AsyncGenerator, Callable

from fastapi import Depends
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.context import current_tenant_ctx
from src.core.exceptions import AuthError, PermissionDeniedError
from src.core.security import decode_access_token
from src.infrastructure.database.postgres.connection import AsyncSessionLocal
from src.infrastructure.database.postgres.models.tenant import Tenant
from src.infrastructure.database.postgres.models.user import User
from src.infrastructure.repositories.user_repository import UserRepository

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/v1/auth/login", auto_error=False)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session


async def get_current_user(
    token: str | None = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    if token is None:
        raise AuthError()
    payload = decode_access_token(token)
    user_id = payload.get("sub")
    if user_id is None:
        raise AuthError("Token missing subject")
    repo = UserRepository(db)
    user = await repo.find_by_id(user_id)
    if user is None or not user.is_active:
        raise AuthError("User not found or inactive")
    return user


def require_role(*roles: str) -> Callable:
    """Return a FastAPI dependency that enforces role membership."""

    async def _check(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role not in roles:
            raise PermissionDeniedError(
                f"Role '{current_user.role}' is not allowed. Required: {list(roles)}"
            )
        return current_user

    return _check


def get_tenant_config() -> dict:
    """Return the current tenant's config JSONB dict from the ContextVar."""
    tenant: Tenant | None = current_tenant_ctx.get()
    if tenant is None or tenant.config is None:
        return {}
    return tenant.config.config
