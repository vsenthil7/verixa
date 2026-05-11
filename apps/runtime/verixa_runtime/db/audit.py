"""Verixa audit ledger schema (`verixa_audit`) — hash-chained + Ed25519-signed.

Per docs/09_data_model/DATA_MODEL.md §5.

The audit ledger is the single most important schema in Verixa. Every
governed action emits exactly one entry. The `hash_chain_self` of each
entry is computed deterministically from the entry's content + the
prior entry's hash; the `signature` is Ed25519 over that hash. Tampering
with any field breaks the chain.

Phase 0 storage notes:
  - Public Ed25519 keys are stored in Postgres (signing_keys.public_key_pem)
    for offline verifier convenience.
  - Private keys are NEVER in Postgres. They live in HashiCorp Vault.
  - The CP-4 cryptographic primitives module computes hash_chain_self and
    signature; this schema only stores them.
  - Hash-chain genesis: sequence_number = 0, hash_chain_prev = sha256(
    'verixa-genesis-' || tenant_id).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from verixa_runtime.db import Base

SCHEMA_NAME = "verixa_audit"


class AuditEntry(Base):
    """One governed-action record in the hash-chained audit ledger.

    APPEND-ONLY by application convention. Postgres does not enforce
    immutability at the table level (no triggers in Phase 0); the chain
    itself is the tamper-evident layer — any UPDATE to a committed row
    will invalidate `hash_chain_self` against its content, and the
    signature against the public key.
    """

    __tablename__ = "audit_entries"
    __table_args__ = (
        CheckConstraint(
            "decision IN ('allow', 'deny', 'escalate', 'pending')",
            name="decision",
        ),
        UniqueConstraint(
            "tenant_id", "sequence_number", name="tenant_sequence"
        ),
        Index(
            "idx_audit_tenant_time",
            "tenant_id",
            text("event_time DESC"),
        ),
        Index(
            "idx_audit_workflow",
            "tenant_id",
            "workflow_id",
            text("event_time DESC"),
        ),
        Index(
            "idx_audit_agent",
            "tenant_id",
            "agent_id",
            text("event_time DESC"),
        ),
        Index("idx_audit_decision", "tenant_id", "decision"),
        Index(
            "idx_audit_risk_high",
            "tenant_id",
            text("event_time DESC"),
            postgresql_where=text("risk_classification = 'high'"),
        ),
        {"schema": SCHEMA_NAME},
    )

    audit_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False
    )
    sequence_number: Mapped[int] = mapped_column(BigInteger, nullable=False)
    event_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    # Subject of governance ----------------------------------------------------
    workflow_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False
    )
    agent_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False
    )
    action_type: Mapped[str] = mapped_column(String, nullable=False)
    tool_name: Mapped[str | None] = mapped_column(String, nullable=True)

    # Decision ---------------------------------------------------------------
    decision: Mapped[str] = mapped_column(String, nullable=False)
    reason: Mapped[str | None] = mapped_column(String, nullable=True)
    risk_score: Mapped[Decimal | None] = mapped_column(
        Numeric(4, 3), nullable=True
    )
    risk_classification: Mapped[str | None] = mapped_column(
        String, nullable=True
    )

    # Triad ------------------------------------------------------------------
    triad_invoked: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("FALSE")
    )
    triad_review_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )

    # Hash chain + signature -------------------------------------------------
    hash_chain_prev: Mapped[str | None] = mapped_column(
        String, nullable=True
    )
    hash_chain_self: Mapped[str] = mapped_column(String, nullable=False)
    signature: Mapped[str] = mapped_column(String, nullable=False)
    signing_key_id: Mapped[str] = mapped_column(String, nullable=False)

    # Runtime metadata -------------------------------------------------------
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    request_id: Mapped[str | None] = mapped_column(String, nullable=True)
    trace_id: Mapped[str | None] = mapped_column(String, nullable=True)

    # Regulatory mapping -----------------------------------------------------
    policies_applied: Mapped[list[Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )

    def __repr__(self) -> str:
        return (
            f"<AuditEntry seq={self.sequence_number} "
            f"decision={self.decision} audit_id={self.audit_id}>"
        )


class SigningKey(Base):
    """Registry of Ed25519 public keys used to verify audit signatures.

    Private keys live in HashiCorp Vault (production) or
    `~/.verixa/dev-vault/` (local dev). Postgres only stores public keys
    so offline verification (the `tools/audit_verify.py` CLI in CP-5.3)
    can run without Vault access.
    """

    __tablename__ = "signing_keys"
    __table_args__ = (
        CheckConstraint(
            "algorithm IN ('ed25519')", name="algorithm"
        ),
        {"schema": SCHEMA_NAME},
    )

    key_id: Mapped[str] = mapped_column(String, primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False
    )
    public_key_pem: Mapped[str] = mapped_column(String, nullable=False)
    algorithm: Mapped[str] = mapped_column(
        String, nullable=False, server_default=text("'ed25519'")
    )
    activated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    deactivated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("TRUE")
    )
