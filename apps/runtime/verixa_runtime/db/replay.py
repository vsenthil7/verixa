"""Verixa replay schema (`verixa_replay`) — index for snapshot bundles.

Per docs/06_data_model/DATA_MODEL.md §6.

Each row points at one encrypted snapshot bundle in the object store
(MinIO in dev; S3-compatible in production). The bundle itself is
content-addressable via `bundle_hash` (SHA-256 of the encrypted bundle).

Phase 0 retention tier: 'hot' only. Warm/cold tier movement is a
Celery job (Phase 1; see DATA_MODEL.md §11).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    Index,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from verixa_runtime.db import Base

SCHEMA_NAME = "verixa_replay"


class ReplayIndex(Base):
    """Pointer to one encrypted snapshot bundle in the object store."""

    __tablename__ = "replay_index"
    __table_args__ = (
        CheckConstraint(
            "retention_tier IN ('hot', 'warm', 'cold')",
            name="retention_tier",
        ),
        UniqueConstraint(
            "tenant_id", "audit_id", name="tenant_audit"
        ),
        Index("idx_replay_audit", "audit_id"),
        Index(
            "idx_replay_retention",
            "tenant_id",
            "retention_tier",
            "expires_at",
        ),
        {"schema": SCHEMA_NAME},
    )

    replay_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    audit_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False
    )
    object_key: Mapped[str] = mapped_column(String, nullable=False)
    object_store_url: Mapped[str] = mapped_column(String, nullable=False)
    bundle_hash: Mapped[str] = mapped_column(String, nullable=False)
    encryption_key_id: Mapped[str] = mapped_column(String, nullable=False)
    bundle_size_bytes: Mapped[int | None] = mapped_column(
        BigInteger, nullable=True
    )
    retention_tier: Mapped[str] = mapped_column(String, nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("NOW()"),
    )
