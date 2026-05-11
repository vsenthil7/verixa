"""CP-3.4 audit ledger schema (audit_entries + signing_keys)

Revision ID: 20260510_1212_audit_schema
Revises: 20260510_1147_policy_schema
Create Date: 2026-05-10 12:12:00 UK

Hash-chained, Ed25519-signed, append-only. The most important schema
in Verixa.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260510_1212_audit_schema"
down_revision: str | None = "20260510_1147_policy_schema"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS verixa_audit")

    op.create_table(
        "audit_entries",
        sa.Column(
            "audit_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "tenant_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column("sequence_number", sa.BigInteger(), nullable=False),
        sa.Column("event_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "workflow_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "agent_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column("action_type", sa.String(), nullable=False),
        sa.Column("tool_name", sa.String(), nullable=True),
        sa.Column("decision", sa.String(), nullable=False),
        sa.Column("reason", sa.String(), nullable=True),
        sa.Column("risk_score", sa.Numeric(4, 3), nullable=True),
        sa.Column("risk_classification", sa.String(), nullable=True),
        sa.Column(
            "triad_invoked",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("FALSE"),
        ),
        sa.Column(
            "triad_review_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
        sa.Column("hash_chain_prev", sa.String(), nullable=True),
        sa.Column("hash_chain_self", sa.String(), nullable=False),
        sa.Column("signature", sa.String(), nullable=False),
        sa.Column("signing_key_id", sa.String(), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("request_id", sa.String(), nullable=True),
        sa.Column("trace_id", sa.String(), nullable=True),
        sa.Column(
            "policies_applied",
            sa.dialects.postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.CheckConstraint(
            "decision IN ('allow', 'deny', 'escalate', 'pending')",
            name="ck_audit_entries_decision",
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "sequence_number",
            name="uq_audit_entries_tenant_sequence",
        ),
        schema="verixa_audit",
    )
    op.create_index(
        "idx_audit_tenant_time",
        "audit_entries",
        ["tenant_id", sa.text("event_time DESC")],
        schema="verixa_audit",
    )
    op.create_index(
        "idx_audit_workflow",
        "audit_entries",
        ["tenant_id", "workflow_id", sa.text("event_time DESC")],
        schema="verixa_audit",
    )
    op.create_index(
        "idx_audit_agent",
        "audit_entries",
        ["tenant_id", "agent_id", sa.text("event_time DESC")],
        schema="verixa_audit",
    )
    op.create_index(
        "idx_audit_decision",
        "audit_entries",
        ["tenant_id", "decision"],
        schema="verixa_audit",
    )
    op.create_index(
        "idx_audit_risk_high",
        "audit_entries",
        ["tenant_id", sa.text("event_time DESC")],
        schema="verixa_audit",
        postgresql_where=sa.text("risk_classification = 'high'"),
    )

    op.create_table(
        "signing_keys",
        sa.Column("key_id", sa.String(), primary_key=True),
        sa.Column(
            "tenant_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column("public_key_pem", sa.String(), nullable=False),
        sa.Column(
            "algorithm",
            sa.String(),
            nullable=False,
            server_default=sa.text("'ed25519'"),
        ),
        sa.Column(
            "activated_at", sa.DateTime(timezone=True), nullable=False
        ),
        sa.Column(
            "deactivated_at", sa.DateTime(timezone=True), nullable=True
        ),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("TRUE"),
        ),
        sa.CheckConstraint(
            "algorithm IN ('ed25519')",
            name="ck_signing_keys_algorithm",
        ),
        schema="verixa_audit",
    )


def downgrade() -> None:
    op.drop_table("signing_keys", schema="verixa_audit")
    op.drop_table("audit_entries", schema="verixa_audit")
    op.execute("DROP SCHEMA IF EXISTS verixa_audit CASCADE")
