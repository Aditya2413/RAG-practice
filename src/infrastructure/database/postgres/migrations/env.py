import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy.ext.asyncio import create_async_engine

from src.core.config import get_settings

# ---------------------------------------------------------------------------
# Import ALL models so SQLAlchemy registers them in Base.metadata before
# Alembic reads it. The order here must respect FK dependencies.
# ---------------------------------------------------------------------------
from src.infrastructure.database.postgres.models.base import Base  # noqa: F401
from src.infrastructure.database.postgres.models.tenant import Tenant, TenantConfig  # noqa: F401
from src.infrastructure.database.postgres.models.user import User, RefreshToken  # noqa: F401
from src.infrastructure.database.postgres.models.collection import Collection  # noqa: F401
from src.infrastructure.database.postgres.models.document import Document  # noqa: F401
from src.infrastructure.database.postgres.models.job import IngestionJob  # noqa: F401
from src.infrastructure.database.postgres.models.session import Session  # noqa: F401
from src.infrastructure.database.postgres.models.message import Message  # noqa: F401

# ---------------------------------------------------------------------------
# Alembic Config object — access alembic.ini values
# ---------------------------------------------------------------------------
config = context.config

# Wire Python logging from alembic.ini [loggers] section
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Tell Alembic to compare against ORM metadata (autogenerate support)
target_metadata = Base.metadata


# ---------------------------------------------------------------------------
# Offline mode — generate SQL script without a live DB connection
# ---------------------------------------------------------------------------
def run_migrations_offline() -> None:
    settings = get_settings()
    context.configure(
        url=settings.database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


# ---------------------------------------------------------------------------
# Online mode — run migrations against a live async DB connection
# ---------------------------------------------------------------------------
def do_run_migrations(connection):
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    settings = get_settings()
    engine = create_async_engine(settings.database_url)
    async with engine.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await engine.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


# ---------------------------------------------------------------------------
# Entry point — Alembic calls this module at runtime
# ---------------------------------------------------------------------------
if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
