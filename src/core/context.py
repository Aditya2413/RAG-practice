from contextvars import ContextVar
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.infrastructure.database.postgres.models.tenant import Tenant
    from src.infrastructure.database.postgres.models.user import User

# Populated by RequestIDMiddleware
request_id_ctx: ContextVar[str] = ContextVar("request_id", default="")

# Populated by TenantContextMiddleware after JWT decode
current_tenant_ctx: ContextVar["Tenant | None"] = ContextVar("current_tenant", default=None)

# Populated by get_current_user dependency
current_user_ctx: ContextVar["User | None"] = ContextVar("current_user", default=None)
