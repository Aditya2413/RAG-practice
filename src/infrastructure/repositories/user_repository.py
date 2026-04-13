from datetime import datetime
from uuid import UUID

import sqlalchemy as sa

from src.infrastructure.database.postgres.models.user import RefreshToken, User
from src.infrastructure.repositories.base import IRepository


class UserRepository(IRepository[User]):
    async def find_by_id(self, id: UUID) -> User | None:
        result = await self.session.execute(sa.select(User).where(User.id == id))
        return result.scalar_one_or_none()

    async def find_by_email_and_tenant(self, email: str, tenant_id: UUID) -> User | None:
        result = await self.session.execute(
            sa.select(User).where(User.email == email, User.tenant_id == tenant_id)
        )
        return result.scalar_one_or_none()

    async def create(self, data: dict) -> User:
        user = User(**data)
        self.session.add(user)
        await self.session.commit()
        await self.session.refresh(user)
        return user

    async def update(self, id: UUID, data: dict) -> User:
        await self.session.execute(sa.update(User).where(User.id == id).values(**data))
        await self.session.commit()
        return await self.find_by_id(id)  # type: ignore[return-value]

    async def delete(self, id: UUID) -> None:
        await self.session.execute(sa.delete(User).where(User.id == id))
        await self.session.commit()

    async def update_last_login(self, id: UUID) -> None:
        await self.session.execute(
            sa.update(User)
            .where(User.id == id)
            .values(last_login_at=sa.func.now())
        )
        await self.session.commit()

    # ── Refresh token operations ──────────────────────────────────────────────

    async def find_refresh_token(self, token_hash: str) -> RefreshToken | None:
        result = await self.session.execute(
            sa.select(RefreshToken).where(
                RefreshToken.token_hash == token_hash,
                RefreshToken.revoked.is_(False),
                RefreshToken.expires_at > sa.func.now(),
            )
        )
        return result.scalar_one_or_none()

    async def create_refresh_token(
        self, user_id: UUID, token_hash: str, expires_at: datetime
    ) -> RefreshToken:
        token = RefreshToken(user_id=user_id, token_hash=token_hash, expires_at=expires_at)
        self.session.add(token)
        await self.session.commit()
        await self.session.refresh(token)
        return token

    async def revoke_refresh_token(self, token_hash: str) -> None:
        await self.session.execute(
            sa.update(RefreshToken)
            .where(RefreshToken.token_hash == token_hash)
            .values(revoked=True)
        )
        await self.session.commit()

    async def revoke_all_user_tokens(self, user_id: UUID) -> None:
        await self.session.execute(
            sa.update(RefreshToken)
            .where(RefreshToken.user_id == user_id, RefreshToken.revoked.is_(False))
            .values(revoked=True)
        )
        await self.session.commit()
