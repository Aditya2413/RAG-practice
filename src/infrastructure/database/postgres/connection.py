import ssl

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy import text

from src.core.config import get_settings

# Import all ORM models so SQLAlchemy's mapper registry is fully populated
# before any relationship string-reference (e.g. "Document") is resolved.
# Without this, repositories that import only one model file trigger mapper
# configuration while sibling models are still unknown → InvalidRequestError.
import src.infrastructure.database.postgres.models  # noqa: F401

settings = get_settings()

# Build asyncpg connect_args — add SSL context for RDS (verify-full).
_connect_args: dict = {}
if settings.postgres_ssl:
    _ssl_ctx = ssl.create_default_context(cafile=settings.postgres_ssl_cert)
    _connect_args["ssl"] = _ssl_ctx

# Async SQLAlchemy engine — created once at module import, reused for the app lifetime.
engine = create_async_engine(
    settings.database_url,
    pool_size=settings.database_pool_size,
    max_overflow=settings.database_max_overflow,
    echo=settings.app_env == "development",  # log SQL only in dev
    connect_args=_connect_args,
)

# Session factory — used in FastAPI dependencies to open per-request DB sessions.
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def check_db() -> bool:
    """Ping the database with a trivial query. Used by /health/ready."""
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False
