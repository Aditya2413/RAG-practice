import uuid
from datetime import datetime
from typing import Optional

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin


class Document(TimestampMixin, Base):
    __tablename__ = "documents"
    __table_args__ = (
        sa.UniqueConstraint("tenant_id", "sha256", name="uq_documents_tenant_sha256"),
        sa.Index("idx_documents_tenant", "tenant_id"),
        sa.Index("idx_documents_collection", "collection_id"),
        sa.Index("idx_documents_status", "status"),
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
    collection_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey("collections.id", ondelete="CASCADE"),
        nullable=False,
    )
    filename: Mapped[str] = mapped_column(sa.String(500), nullable=False)
    s3_key: Mapped[str] = mapped_column(sa.Text, nullable=False)
    mime_type: Mapped[str] = mapped_column(sa.String(100), nullable=False)
    file_size_bytes: Mapped[Optional[int]] = mapped_column(sa.BigInteger, nullable=True)
    sha256: Mapped[str] = mapped_column(sa.String(64), nullable=False)
    chunk_count: Mapped[int] = mapped_column(sa.Integer, server_default="0", nullable=False)
    status: Mapped[str] = mapped_column(sa.String(20), server_default="pending", nullable=False)
    # status values: pending | indexed | deleted | failed
    upload_metadata: Mapped[dict] = mapped_column(JSONB, server_default=sa.text("'{}'::jsonb"), nullable=False)
    uploaded_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    indexed_at: Mapped[Optional[datetime]] = mapped_column(sa.TIMESTAMP(timezone=True), nullable=True)
    deleted_at: Mapped[Optional[datetime]] = mapped_column(sa.TIMESTAMP(timezone=True), nullable=True)

    # Relationships
    collection: Mapped["Collection"] = relationship("Collection", back_populates="documents")  # noqa: F821
    ingestion_jobs: Mapped[list["IngestionJob"]] = relationship(  # noqa: F821
        "IngestionJob", back_populates="document", cascade="all, delete-orphan"
    )
