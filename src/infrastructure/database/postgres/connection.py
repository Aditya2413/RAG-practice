from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy import text

from src.core.config import get_settings

settings = get_settings()

# Async SQLAlchemy engine — created once at module import, reused for the app lifetime.
engine = create_async_engine(
    settings.database_url,
    pool_size=settings.database_pool_size,
    max_overflow=settings.database_max_overflow,
    echo=settings.app_env == "development",  # log SQL only in dev
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
