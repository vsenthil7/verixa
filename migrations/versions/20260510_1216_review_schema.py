"""CP-3.6 review schema (triad_reviews + human_reviews)

Revision ID: 20260510_1216_review_schema
Revises: 20260510_1214_replay_schema
Create Date: 2026-05-10 12:16:00 UK
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260510_1216_review_schema"
down_revision: str | None = "20260510_1214_replay_schema"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS verixa_review")

    op.create_table(
        "triad_reviews",
        sa.Column(
            "triad_review_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "audit_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "tenant_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "workflow_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "invoked_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column("revealed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "reviewer_a_model_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "reviewer_b_model_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "reviewer_c_model_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column("reviewer_a_commit_hash", sa.String(), nullable=False),
        sa.Column("reviewer_b_commit_hash", sa.String(), nullable=False),
        sa.Column("reviewer_c_commit_hash", sa.String(), nullable=False),
        sa.Column(
            "commit_completed_at", sa.DateTime(timezone=True), nullable=False
        ),
        sa.Column("reviewer_a_verdict", sa.String(), nullable=True),
        sa.Column("reviewer_a_reasoning", sa.String(), nullable=True),
        sa.Column("reviewer_a_nonce", sa.String(), nullable=True),
        sa.Column("reviewer_b_verdict", sa.String(), nullable=True),
        sa.Column("reviewer_b_reasoning", sa.String(), nullable=True),
        sa.Column("reviewer_b_nonce", sa.String(), nullable=True),
        sa.Column("reviewer_c_verdict", sa.String(), nullable=True),
        sa.Column("reviewer_c_reasoning", sa.String(), nullable=True),
        sa.Column("reviewer_c_nonce", sa.String(), nullable=True),
        sa.Column("consensus", sa.String(), nullable=True),
        sa.Column("consensus_reason", sa.String(), nullable=True),
        sa.Column("total_latency_ms", sa.Integer(), nullable=True),
        sa.UniqueConstraint(
            "tenant_id",
            "audit_id",
            name="uq_triad_reviews_tenant_audit",
        ),
        schema="verixa_review",
    )

    op.create_table(
        "human_reviews",
        sa.Column(
            "human_review_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "escalation_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "audit_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "tenant_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "queued_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column("assigned_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reviewer_identity", sa.String(), nullable=True),
        sa.Column("reviewer_role", sa.String(), nullable=True),
        sa.Column("decision", sa.String(), nullable=True),
        sa.Column("decision_notes", sa.String(), nullable=True),
        sa.Column("review_duration_ms", sa.Integer(), nullable=True),
        sa.Column("sla_target_minutes", sa.Integer(), nullable=True),
        sa.Column(
            "sla_breached",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("FALSE"),
        ),
        sa.CheckConstraint(
            "decision IN ('approve', 'deny', 'request_more_info')",
            name="ck_human_reviews_decision",
        ),
        schema="verixa_review",
    )
    op.create_index(
        "idx_human_reviews_tenant_status",
        "human_reviews",
        ["tenant_id", "decided_at"],
        schema="verixa_review",
        postgresql_where=sa.text("decided_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_table("human_reviews", schema="verixa_review")
    op.drop_table("triad_reviews", schema="verixa_review")
    op.execute("DROP SCHEMA IF EXISTS verixa_review CASCADE")
