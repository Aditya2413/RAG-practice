import uuid
from datetime import datetime
from typing import Optional

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin


class Tenant(TimestampMixin, Base):
    __tablename__ = "tenants"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=sa.text("gen_random_uuid()"),
    )
    name: Mapped[str] = mapped_column(sa.String(255), nullable=False)
    slug: Mapped[str] = mapped_column(sa.String(100), unique=True, nullable=False)
    status: Mapped[str] = mapped_column(sa.String(20), server_default="active", nullable=False)
    plan: Mapped[str] = mapped_column(sa.String(50), server_default="starter", nullable=False)

    # Relationships
    config: Mapped[Optional["TenantConfig"]] = relationship(
        "TenantConfig", back_populates="tenant", uselist=False, cascade="all, delete-orphan"
    )
    users: Mapped[list["User"]] = relationship("User", back_populates="tenant")  # noqa: F821
    collections: Mapped[list["Collection"]] = relationship("Collection", back_populates="tenant")  # noqa: F821


class TenantConfig(Base):
    __tablename__ = "tenant_configs"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey("tenants.id", ondelete="CASCADE"),
        primary_key=True,
    )
    config: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=sa.text("'{}'::jsonb"))
    updated_at: Mapped[datetime] = mapped_column(
        sa.TIMESTAMP(timezone=True),
        server_default=sa.func.now(),
        onupdate=sa.func.now(),
        nullable=False,
    )
    updated_by: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)

    # Relationship
    tenant: Mapped["Tenant"] = relationship("Tenant", back_populates="config")
