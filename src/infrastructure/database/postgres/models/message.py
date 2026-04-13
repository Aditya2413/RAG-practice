import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class Message(Base):
    """
    Persisted conversation turn — one row per user or assistant message.

    role values: user | assistant | system
    sources: list of retrieved chunk references used to generate the answer
    guardrail_flags: which guardrails triggered (input or output)
    """
    __tablename__ = "messages"
    __table_args__ = (
        sa.Index("idx_messages_session", "session_id"),
        sa.Index("idx_messages_tenant", "tenant_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=sa.text("gen_random_uuid()"),
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey("sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    role: Mapped[str] = mapped_column(sa.String(20), nullable=False)
    content: Mapped[str] = mapped_column(sa.Text, nullable=False)
    sources: Mapped[list] = mapped_column(JSONB, server_default=sa.text("'[]'::jsonb"), nullable=False)
    usage: Mapped[dict] = mapped_column(JSONB, server_default=sa.text("'{}'::jsonb"), nullable=False)
    cached: Mapped[bool] = mapped_column(sa.Boolean, server_default=sa.false(), nullable=False)
    guardrail_flags: Mapped[dict] = mapped_column(JSONB, server_default=sa.text("'{}'::jsonb"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        sa.TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False
    )

    # Relationship
    session: Mapped["Session"] = relationship("Session", back_populates="messages")  # noqa: F821
