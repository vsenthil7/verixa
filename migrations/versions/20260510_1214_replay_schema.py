"""CP-3.5 replay schema (replay_index)

Revision ID: 20260510_1214_replay_schema
Revises: 20260510_1212_audit_schema
Create Date: 2026-05-10 12:14:00 UK
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260510_1214_replay_schema"
down_revision: str | None = "20260510_1212_audit_schema"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS verixa_replay")

    op.create_table(
        "replay_index",
        sa.Column(
            "replay_id",
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
        sa.Column("object_key", sa.String(), nullable=False),
        sa.Column("object_store_url", sa.String(), nullable=False),
        sa.Column("bundle_hash", sa.String(), nullable=False),
        sa.Column("encryption_key_id", sa.String(), nullable=False),
        sa.Column("bundle_size_bytes", sa.BigInteger(), nullable=True),
        sa.Column("retention_tier", sa.String(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.CheckConstraint(
            "retention_tier IN ('hot', 'warm', 'cold')",
            name="ck_replay_index_retention_tier",
        ),
        sa.UniqueConstraint(
            "tenant_id", "audit_id", name="uq_replay_index_tenant_audit"
        ),
        schema="verixa_replay",
    )
    op.create_index(
        "idx_replay_audit",
        "replay_index",
        ["audit_id"],
        schema="verixa_replay",
    )
    op.create_index(
        "idx_replay_retention",
        "replay_index",
        ["tenant_id", "retention_tier", "expires_at"],
        schema="verixa_replay",
    )


def downgrade() -> None:
    op.drop_table("replay_index", schema="verixa_replay")
    op.execute("DROP SCHEMA IF EXISTS verixa_replay CASCADE")
