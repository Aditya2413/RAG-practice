import uuid
from datetime import datetime
from typing import Optional

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class Session(Base):
    """
    A conversation session between a user and the RAG chatbot.
    config_snapshot captures the tenant config at session creation time so
    mid-session config changes don't disrupt an ongoing conversation.

    status values: active | ended | expired
    """
    __tablename__ = "sessions"
    __table_args__ = (
        sa.Index("idx_sessions_user", "user_id"),
        sa.Index("idx_sessions_tenant", "tenant_id"),
        sa.Index("idx_sessions_status", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=sa.text("gen_random_uuid()"),
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(sa.String(20), server_default="active", nullable=False)
    config_snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False)
    turn_count: Mapped[int] = mapped_column(sa.Integer, server_default="0", nullable=False)
    last_active_at: Mapped[datetime] = mapped_column(
        sa.TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        sa.TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False
    )
    ended_at: Mapped[Optional[datetime]] = mapped_column(sa.TIMESTAMP(timezone=True), nullable=True)

    # Relationships
    messages: Mapped[list["Message"]] = relationship(  # noqa: F821
        "Message", back_populates="session", cascade="all, delete-orphan"
    )
