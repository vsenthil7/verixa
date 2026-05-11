"""Verixa registry schema (`verixa_registry`) — agents, workflows, models, tools.

Per docs/09_data_model/DATA_MODEL.md §3.

Notes on Phase 0 simplifications:
  - workflows.triad_policy_id and escalation_policy_id are NOT FKs in
    Phase 0 (would create a circular dependency with verixa_policy).
    Stored as nullable UUIDs with app-level integrity. Phase 1 adds
    deferrable FKs.
  - tenant_id is a plain UUID, not yet FK-enforced to verixa_tenancy.tenants
    (matches Phase 0 of the spec).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    ARRAY,
    Boolean,
    CheckConstraint,
    DateTime,
    Index,
    Numeric,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from verixa_runtime.db import Base

SCHEMA_NAME = "verixa_registry"


class Agent(Base):
    """A registered AI agent that can take governed actions."""

    __tablename__ = "agents"
    __table_args__ = (
        Index("idx_agents_tenant_active", "tenant_id", "is_active"),
        Index("idx_agents_spiffe", "spiffe_id"),
        {"schema": SCHEMA_NAME},
    )

    agent_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    spiffe_id: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    display_name: Mapped[str] = mapped_column(String, nullable=False)
    role: Mapped[str] = mapped_column(String, nullable=False)
    workflow_ids: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(UUID(as_uuid=True)),
        nullable=False,
        server_default=text("ARRAY[]::uuid[]"),
    )
    primary_model: Mapped[str | None] = mapped_column(String, nullable=True)
    primary_model_hash: Mapped[str | None] = mapped_column(
        String, nullable=True
    )
    sdk_version: Mapped[str | None] = mapped_column(String, nullable=True)
    risk_baseline: Mapped[Decimal] = mapped_column(
        Numeric(4, 3), nullable=False, server_default=text("0.500")
    )
    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("TRUE")
    )
    registered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("NOW()"),
    )
    deactivated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_by: Mapped[str] = mapped_column(String, nullable=False)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False
    )


class Workflow(Base):
    """A registered workflow context for governed actions."""

    __tablename__ = "workflows"
    __table_args__ = (
        CheckConstraint(
            "risk_classification IN ('low', 'medium', 'high', 'critical')",
            name="risk_classification",
        ),
        Index("idx_workflows_tenant_active", "tenant_id", "is_active"),
        Index("idx_workflows_sector", "sector"),
        {"schema": SCHEMA_NAME},
    )

    workflow_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str | None] = mapped_column(String, nullable=True)
    risk_classification: Mapped[str] = mapped_column(String, nullable=False)
    sector: Mapped[str] = mapped_column(String, nullable=False)
    compliance_packs: Mapped[list[str]] = mapped_column(
        ARRAY(String),
        nullable=False,
        server_default=text("ARRAY[]::text[]"),
    )
    triad_policy_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    escalation_policy_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    retention_tier: Mapped[str] = mapped_column(
        String,
        nullable=False,
        server_default=text("'enterprise_production'"),
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("TRUE")
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
    created_by: Mapped[str] = mapped_column(String, nullable=False)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False
    )


class Tool(Base):
    """A registered tool schema (function-call surface) the agent may invoke."""

    __tablename__ = "tools"
    __table_args__ = (
        UniqueConstraint("tenant_id", "name", name="tenant_name"),
        {"schema": SCHEMA_NAME},
    )

    tool_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    schema_json: Mapped[dict[str, Any]] = mapped_column(
        "schema", JSONB, nullable=False
    )
    risk_baseline: Mapped[Decimal] = mapped_column(
        Numeric(4, 3), nullable=False, server_default=text("0.500")
    )
    sensitive_arguments: Mapped[list[str]] = mapped_column(
        ARRAY(String),
        nullable=False,
        server_default=text("ARRAY[]::text[]"),
    )
    allowed_workflow_ids: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(UUID(as_uuid=True)),
        nullable=False,
        server_default=text("ARRAY[]::uuid[]"),
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("TRUE")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("NOW()"),
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False
    )


class Model(Base):
    """A registered model (primary, reviewer, or verifier role)."""

    __tablename__ = "models"
    __table_args__ = (
        CheckConstraint(
            "role IN ('primary', 'reviewer', 'verifier')", name="role"
        ),
        UniqueConstraint(
            "tenant_id",
            "name",
            "version_hash",
            name="tenant_name_version",
        ),
        {"schema": SCHEMA_NAME},
    )

    model_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    family: Mapped[str] = mapped_column(String, nullable=False)
    version_hash: Mapped[str] = mapped_column(String, nullable=False)
    role: Mapped[str] = mapped_column(String, nullable=False)
    deployment_target: Mapped[str] = mapped_column(String, nullable=False)
    quantisation: Mapped[str | None] = mapped_column(String, nullable=True)
    full_precision: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("FALSE")
    )
    parameters_billion: Mapped[Decimal | None] = mapped_column(
        Numeric(5, 1), nullable=True
    )
    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("TRUE")
    )
    registered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("NOW()"),
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False
    )
