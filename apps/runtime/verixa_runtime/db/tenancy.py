"""Verixa tenancy schema (`verixa_tenancy`).

Phase 0 minimal: a `tenants` table that pins the tenant record fixture
seeding depends on. Cross-schema tenant_id references in registry/audit/
replay/etc. point at this table by UUID (FK enforcement at app level for
hackathon; full RLS + role-scoped credentials in Phase 1).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, String, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from verixa_runtime.db import Base

SCHEMA_NAME = "verixa_tenancy"


class Tenant(Base):
    """A single tenant of the Verixa control plane."""

    __tablename__ = "tenants"
    __table_args__ = {"schema": SCHEMA_NAME}

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    display_name: Mapped[str] = mapped_column(String(256), nullable=False)
    slug: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    deployment_tier: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default=text("'tier_2'")
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("TRUE")
    )
    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("NOW()"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("NOW()"),
    )

    def __repr__(self) -> str:
        return f"<Tenant {self.slug} ({self.tenant_id})>"
