"""Verixa policy schema (`verixa_policy`) — policies + policy test fixtures.

Per docs/06_data_model/DATA_MODEL.md §4.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from verixa_runtime.db import Base

SCHEMA_NAME = "verixa_policy"


class Policy(Base):
    """A Rego policy bundle, with version tracking."""

    __tablename__ = "policies"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "name", "version", name="tenant_name_version"
        ),
        Index("idx_policies_tenant_active", "tenant_id", "is_active"),
        Index("idx_policies_pack", "compliance_pack"),
        {"schema": SCHEMA_NAME},
    )

    policy_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str | None] = mapped_column(String, nullable=True)
    rego_source: Mapped[str] = mapped_column(String, nullable=False)
    rego_compiled_hash: Mapped[str] = mapped_column(String, nullable=False)
    version: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("1")
    )
    is_active: Mapped[bool] = mapped_column(
        nullable=False, server_default=text("TRUE")
    )
    compliance_pack: Mapped[str | None] = mapped_column(String, nullable=True)
    regulatory_mappings: Mapped[list[Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("NOW()"),
    )
    created_by: Mapped[str] = mapped_column(String, nullable=False)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False
    )


class PolicyTestFixture(Base):
    """Pass/fail/abstain fixture rows for policy unit testing."""

    __tablename__ = "policy_test_fixtures"
    __table_args__ = (
        CheckConstraint(
            "expected_result IN ('pass', 'fail', 'abstain')",
            name="expected_result",
        ),
        {"schema": SCHEMA_NAME},
    )

    fixture_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    policy_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(f"{SCHEMA_NAME}.policies.policy_id"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    input_payload: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False
    )
    expected_result: Mapped[str] = mapped_column(String, nullable=False)
    expected_reason: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("NOW()"),
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False
    )
