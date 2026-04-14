"""
Integration tests — Auth flow (JWT + RBAC)

Covers: register, login, /me, refresh, logout, and edge cases.

Requires Docker stack: make dev && make migrate
"""
from __future__ import annotations

import pytest
from httpx import AsyncClient


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
async def _login(client: AsyncClient, email: str, password: str) -> dict:
    resp = await client.post(
        "/v1/auth/login", json={"email": email, "password": password}
    )
    return resp


async def _bearer(client: AsyncClient, email: str, password: str) -> str:
    resp = await _login(client, email, password)
    assert resp.status_code == 200
    return resp.json()["access_token"]


# ---------------------------------------------------------------------------
# Register
# ---------------------------------------------------------------------------
class TestRegister:
    async def test_register_success(self, async_client: AsyncClient, tenant_factory):
        tenant = await tenant_factory(slug="acme")
        resp = await async_client.post(
            "/v1/auth/register",
            json={
                "email": "alice@acme.com",
                "password": "Secret123!",
                "first_name": "Alice",
                "last_name": "Smith",
                "tenant_slug": tenant.slug,
            },
        )
        assert resp.status_code == 201
        body = resp.json()
        assert "access_token" in body
        assert "refresh_token" in body
        assert body["token_type"] == "bearer"

    async def test_register_duplicate_email(self, async_client: AsyncClient, tenant_factory):
        tenant = await tenant_factory(slug="corp")
        payload = {
            "email": "bob@corp.com",
            "password": "Secret123!",
            "first_name": "Bob",
            "last_name": "Jones",
            "tenant_slug": tenant.slug,
        }
        resp1 = await async_client.post("/v1/auth/register", json=payload)
        assert resp1.status_code == 201

        resp2 = await async_client.post("/v1/auth/register", json=payload)
        assert resp2.status_code == 409

    async def test_register_invalid_tenant_slug(self, async_client: AsyncClient):
        resp = await async_client.post(
            "/v1/auth/register",
            json={
                "email": "ghost@nowhere.com",
                "password": "Secret123!",
                "first_name": "Ghost",
                "last_name": "User",
                "tenant_slug": "does-not-exist",
            },
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Login
# ---------------------------------------------------------------------------
class TestLogin:
    async def test_login_success(self, async_client: AsyncClient, tenant_factory, user_factory):
        tenant = await tenant_factory()
        user, password = await user_factory(tenant.id, email="login@example.com")
        resp = await _login(async_client, user.email, password)

        assert resp.status_code == 200
        body = resp.json()
        assert "access_token" in body
        assert "refresh_token" in body

    async def test_login_wrong_password(
        self, async_client: AsyncClient, tenant_factory, user_factory
    ):
        tenant = await tenant_factory()
        user, _ = await user_factory(tenant.id, email="wrongpw@example.com")
        resp = await _login(async_client, user.email, "definitely-wrong")
        assert resp.status_code == 401

    async def test_login_unknown_email(self, async_client: AsyncClient):
        resp = await _login(async_client, "nobody@nowhere.com", "pass")
        assert resp.status_code == 401

    async def test_login_inactive_user(
        self, async_client: AsyncClient, tenant_factory, user_factory, db_session
    ):
        from src.infrastructure.database.postgres.models.user import User
        import sqlalchemy as sa

        tenant = await tenant_factory()
        user, password = await user_factory(tenant.id, email="inactive@example.com")

        # Deactivate the user directly via the session
        await db_session.execute(
            sa.update(User).where(User.id == user.id).values(is_active=False)
        )
        await db_session.flush()

        resp = await _login(async_client, user.email, password)
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# GET /me
# ---------------------------------------------------------------------------
class TestGetMe:
    async def test_get_me_authenticated(
        self, async_client: AsyncClient, tenant_factory, user_factory
    ):
        tenant = await tenant_factory()
        user, password = await user_factory(
            tenant.id, email="me@example.com", role="CLIENT_USER"
        )
        token = await _bearer(async_client, user.email, password)

        resp = await async_client.get(
            "/v1/auth/me", headers={"Authorization": f"Bearer {token}"}
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["email"] == user.email
        assert body["role"] == "CLIENT_USER"
        assert str(body["tenant_id"]) == str(tenant.id)

    async def test_get_me_unauthenticated(self, async_client: AsyncClient):
        resp = await async_client.get("/v1/auth/me")
        assert resp.status_code == 401

    async def test_get_me_invalid_token(self, async_client: AsyncClient):
        resp = await async_client.get(
            "/v1/auth/me", headers={"Authorization": "Bearer totally.fake.token"}
        )
        assert resp.status_code == 401

    async def test_tenant_context_matches_jwt(
        self, async_client: AsyncClient, tenant_factory, user_factory
    ):
        """tenant_id in /me response must match the tenant used at login."""
        tenant = await tenant_factory()
        user, password = await user_factory(tenant.id, email="ctx@example.com")
        token = await _bearer(async_client, user.email, password)

        resp = await async_client.get(
            "/v1/auth/me", headers={"Authorization": f"Bearer {token}"}
        )
        assert resp.status_code == 200
        assert str(resp.json()["tenant_id"]) == str(tenant.id)


# ---------------------------------------------------------------------------
# Refresh
# ---------------------------------------------------------------------------
class TestRefresh:
    async def test_refresh_token_issues_new_pair(
        self, async_client: AsyncClient, tenant_factory, user_factory
    ):
        tenant = await tenant_factory()
        user, password = await user_factory(tenant.id, email="refresh@example.com")
        login_resp = await _login(async_client, user.email, password)
        assert login_resp.status_code == 200
        old_refresh = login_resp.json()["refresh_token"]

        refresh_resp = await async_client.post(
            "/v1/auth/refresh", json={"refresh_token": old_refresh}
        )
        assert refresh_resp.status_code == 200
        body = refresh_resp.json()
        assert "access_token" in body
        assert "refresh_token" in body
        # New refresh token must differ from the old one (rotation)
        assert body["refresh_token"] != old_refresh

    async def test_refresh_token_cannot_be_reused(
        self, async_client: AsyncClient, tenant_factory, user_factory
    ):
        tenant = await tenant_factory()
        user, password = await user_factory(tenant.id, email="reuse@example.com")
        login_resp = await _login(async_client, user.email, password)
        old_refresh = login_resp.json()["refresh_token"]

        # First use — succeeds
        await async_client.post("/v1/auth/refresh", json={"refresh_token": old_refresh})

        # Second use of same token — must fail (token was revoked on first use)
        resp2 = await async_client.post(
            "/v1/auth/refresh", json={"refresh_token": old_refresh}
        )
        assert resp2.status_code == 401

    async def test_refresh_invalid_token(self, async_client: AsyncClient):
        resp = await async_client.post(
            "/v1/auth/refresh", json={"refresh_token": "not-a-real-token"}
        )
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Logout
# ---------------------------------------------------------------------------
class TestLogout:
    async def test_logout_revokes_refresh_token(
        self, async_client: AsyncClient, tenant_factory, user_factory
    ):
        tenant = await tenant_factory()
        user, password = await user_factory(tenant.id, email="logout@example.com")
        login_resp = await _login(async_client, user.email, password)
        refresh_token = login_resp.json()["refresh_token"]

        # Logout
        logout_resp = await async_client.post(
            "/v1/auth/logout", json={"refresh_token": refresh_token}
        )
        assert logout_resp.status_code == 204

        # Attempting to refresh with the revoked token must fail
        resp = await async_client.post(
            "/v1/auth/refresh", json={"refresh_token": refresh_token}
        )
        assert resp.status_code == 401
