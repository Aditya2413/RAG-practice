"""
Shared pytest fixtures for unit and integration tests.

Integration tests require the Docker stack to be running:
    make dev        # starts postgres, redis, rabbitmq, qdrant
    make migrate    # applies alembic migrations to ragbot_test DB

Environment:
    Set POSTGRES_DB=ragbot_test (or TEST_POSTGRES_DB) in .env to isolate
    test data from the dev database. The conftest creates the DB if absent.
"""
from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncGenerator
from typing import Any

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from src.api.dependencies import get_db
from src.api.main import create_app
from src.core.config import get_settings
from src.core.security import hash_password
from src.infrastructure.database.postgres.models.base import Base
from src.infrastructure.database.postgres.models.collection import Collection  # noqa: F401 — registers mapper
from src.infrastructure.database.postgres.models.tenant import Tenant, TenantConfig
from src.infrastructure.database.postgres.models.user import RefreshToken, User  # noqa: F401

# ---------------------------------------------------------------------------
# Event-loop policy — one loop for the whole test session
# ---------------------------------------------------------------------------
@pytest.fixture(scope="session")
def event_loop_policy():
    return asyncio.DefaultEventLoopPolicy()


# ---------------------------------------------------------------------------
# Test database engine (session-scoped — created once per pytest run)
# ---------------------------------------------------------------------------
@pytest.fixture(scope="session")
def test_db_url() -> str:
    s = get_settings()
    # Allow override via TEST_POSTGRES_DB env var; default: append "_test"
    test_db = f"{s.postgres_db}_test"
    return (
        f"postgresql+asyncpg://{s.postgres_user}:{s.postgres_password}"
        f"@{s.postgres_host}:{s.postgres_port}/{test_db}"
    )


@pytest_asyncio.fixture(scope="session")
async def test_engine(test_db_url: str):
    """Create all tables in the test DB at session start; drop at session end."""
    settings = get_settings()
    # Connect to the default DB to CREATE DATABASE if needed
    admin_url = (
        f"postgresql+asyncpg://{settings.postgres_user}:{settings.postgres_password}"
        f"@{settings.postgres_host}:{settings.postgres_port}/{settings.postgres_db}"
    )
    admin_engine = create_async_engine(admin_url, isolation_level="AUTOCOMMIT")
    test_db_name = test_db_url.rsplit("/", 1)[-1]
    async with admin_engine.connect() as conn:
        exists = await conn.execute(
            text("SELECT 1 FROM pg_database WHERE datname = :name"),
            {"name": test_db_name},
        )
        if not exists.scalar_one_or_none():
            await conn.execute(text(f'CREATE DATABASE "{test_db_name}"'))
    await admin_engine.dispose()

    engine = create_async_engine(test_db_url, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


# ---------------------------------------------------------------------------
# Per-test DB session — rolls back after each test for isolation
# ---------------------------------------------------------------------------
@pytest_asyncio.fixture
async def db_session(test_engine) -> AsyncGenerator[AsyncSession, None]:
    """Yield an async session; all writes are rolled back after the test."""
    TestSession = sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)
    async with TestSession() as session:
        async with session.begin():
            yield session
            await session.rollback()


# ---------------------------------------------------------------------------
# FastAPI test client with get_db overridden to use the test session
# ---------------------------------------------------------------------------
@pytest_asyncio.fixture
async def async_client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    app = create_app()

    async def _override_get_db() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        yield client

    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Factories
# ---------------------------------------------------------------------------
@pytest_asyncio.fixture
async def tenant_factory(db_session: AsyncSession):
    """Return an async callable that creates a Tenant + TenantConfig."""

    async def _create(name: str | None = None, slug: str | None = None) -> Tenant:
        name = name or f"tenant-{uuid.uuid4().hex[:8]}"
        slug = slug or name.lower().replace(" ", "-")
        tenant = Tenant(name=name, slug=slug)
        db_session.add(tenant)
        await db_session.flush()
        config = TenantConfig(tenant_id=tenant.id, config={})
        db_session.add(config)
        await db_session.flush()
        await db_session.refresh(tenant)
        return tenant

    return _create


@pytest_asyncio.fixture
async def user_factory(db_session: AsyncSession):
    """Return an async callable that creates a User for a given tenant."""

    async def _create(
        tenant_id: Any,
        email: str | None = None,
        password: str = "Test1234!",
        role: str = "CLIENT_USER",
        first_name: str = "Test",
        last_name: str = "User",
    ) -> tuple[User, str]:
        """Returns (User ORM object, raw password) for use in login calls."""
        email = email or f"user-{uuid.uuid4().hex[:8]}@example.com"
        user = User(
            tenant_id=tenant_id,
            email=email,
            password_hash=hash_password(password),
            role=role,
            first_name=first_name,
            last_name=last_name,
        )
        db_session.add(user)
        await db_session.flush()
        await db_session.refresh(user)
        return user, password

    return _create
