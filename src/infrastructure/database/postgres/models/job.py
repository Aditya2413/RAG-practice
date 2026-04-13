import uuid
from datetime import datetime
from typing import Optional

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class IngestionJob(Base):
    """
    Tracks the progress of a single document through the ingestion pipeline.

    status values: PENDING | QUEUED | DOWNLOADING | CLASSIFYING | PARSING
                   | CHUNKING | EMBEDDING | INDEXING | COMPLETED | FAILED
    """
    __tablename__ = "ingestion_jobs"
    __table_args__ = (
        sa.Index("idx_jobs_document", "document_id"),
        sa.Index("idx_jobs_tenant", "tenant_id"),
        sa.Index("idx_jobs_status", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=sa.text("gen_random_uuid()"),
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey("tenants.id"),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(sa.String(30), server_default="PENDING", nullable=False)
    progress_pct: Mapped[int] = mapped_column(sa.Integer, server_default="0", nullable=False)
    chunk_count: Mapped[Optional[int]] = mapped_column(sa.Integer, nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(sa.Text, nullable=True)
    error_stack: Mapped[Optional[str]] = mapped_column(sa.Text, nullable=True)
    attempt_count: Mapped[int] = mapped_column(sa.Integer, server_default="0", nullable=False)
    celery_task_id: Mapped[Optional[str]] = mapped_column(sa.String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        sa.TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False
    )
    started_at: Mapped[Optional[datetime]] = mapped_column(sa.TIMESTAMP(timezone=True), nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(sa.TIMESTAMP(timezone=True), nullable=True)

    # Relationship
    document: Mapped["Document"] = relationship("Document", back_populates="ingestion_jobs")  # noqa: F821
