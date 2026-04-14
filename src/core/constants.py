# ---------------------------------------------------------------------------
# Roles — must match the values stored in users.role (DB column)
# ---------------------------------------------------------------------------
ROLE_SUPER_ADMIN = "SUPER_ADMIN"
ROLE_CLIENT_ADMIN = "CLIENT_ADMIN"
ROLE_CLIENT_USER = "CLIENT_USER"

ALL_ROLES: tuple[str, ...] = (ROLE_SUPER_ADMIN, ROLE_CLIENT_ADMIN, ROLE_CLIENT_USER)

# ---------------------------------------------------------------------------
# Pagination defaults
# ---------------------------------------------------------------------------
DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100
