"""Verixa review schema (`verixa_review`) — triad reviews + human reviews.

Per docs/06_data_model/DATA_MODEL.md §7.

The triad_reviews table carries the columns for the hash-commit-and-reveal
protocol that CP-10 (Triad Review Engine) implements:
  Commit phase: each reviewer commits SHA-256(verdict || nonce) to the
                ledger BEFORE any verdict is revealed.
  Reveal phase: the actual verdict + nonce are stored, and consumers can
                verify commit_hash == sha256(verdict || nonce).

This makes the triad protocol independently auditable: a tampered reveal
would not match its earlier commit.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Index,
    Integer,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from verixa_runtime.db import Base

SCHEMA_NAME = "verixa_review"


class TriadReview(Base):
    """One Triad Review Engine record per audit_id.

    See docs/05_api/API_SPECIFICATION.md and CP-10 implementation for the
    commit-and-reveal protocol that populates these columns.
    """

    __tablename__ = "triad_reviews"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "audit_id", name="tenant_audit"
        ),
        {"schema": SCHEMA_NAME},
    )

    triad_review_id: Mapped[uuid.UUID] = mapped_column(
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
    workflow_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False
    )
    invoked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("NOW()"),
    )
    revealed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Reviewer model identities (FK-by-UUID to verixa_registry.models).
    reviewer_a_model_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False
    )
    reviewer_b_model_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False
    )
    reviewer_c_model_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False
    )

    # Commit phase ----------------------------------------------------------
    reviewer_a_commit_hash: Mapped[str] = mapped_column(
        String, nullable=False
    )
    reviewer_b_commit_hash: Mapped[str] = mapped_column(
        String, nullable=False
    )
    reviewer_c_commit_hash: Mapped[str] = mapped_column(
        String, nullable=False
    )
    commit_completed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    # Reveal phase (nullable until reveal completes) ------------------------
    reviewer_a_verdict: Mapped[str | None] = mapped_column(
        String, nullable=True
    )
    reviewer_a_reasoning: Mapped[str | None] = mapped_column(
        String, nullable=True
    )
    reviewer_a_nonce: Mapped[str | None] = mapped_column(
        String, nullable=True
    )
    reviewer_b_verdict: Mapped[str | None] = mapped_column(
        String, nullable=True
    )
    reviewer_b_reasoning: Mapped[str | None] = mapped_column(
        String, nullable=True
    )
    reviewer_b_nonce: Mapped[str | None] = mapped_column(
        String, nullable=True
    )
    reviewer_c_verdict: Mapped[str | None] = mapped_column(
        String, nullable=True
    )
    reviewer_c_reasoning: Mapped[str | None] = mapped_column(
        String, nullable=True
    )
    reviewer_c_nonce: Mapped[str | None] = mapped_column(
        String, nullable=True
    )

    # Consensus -------------------------------------------------------------
    consensus: Mapped[str | None] = mapped_column(String, nullable=True)
    consensus_reason: Mapped[str | None] = mapped_column(
        String, nullable=True
    )

    total_latency_ms: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )


class HumanReview(Base):
    """One Human Review Console record per escalation."""

    __tablename__ = "human_reviews"
    __table_args__ = (
        CheckConstraint(
            "decision IN ('approve', 'deny', 'request_more_info')",
            name="decision",
        ),
        Index(
            "idx_human_reviews_tenant_status",
            "tenant_id",
            "decided_at",
            postgresql_where=text("decided_at IS NULL"),
        ),
        {"schema": SCHEMA_NAME},
    )

    human_review_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    escalation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False
    )
    audit_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False
    )
    queued_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("NOW()"),
    )
    assigned_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    decided_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    reviewer_identity: Mapped[str | None] = mapped_column(
        String, nullable=True
    )
    reviewer_role: Mapped[str | None] = mapped_column(String, nullable=True)
    decision: Mapped[str | None] = mapped_column(String, nullable=True)
    decision_notes: Mapped[str | None] = mapped_column(String, nullable=True)
    review_duration_ms: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )
    sla_target_minutes: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )
    sla_breached: Mapped[bool] = mapped_column(
        nullable=False, server_default=text("FALSE")
    )
