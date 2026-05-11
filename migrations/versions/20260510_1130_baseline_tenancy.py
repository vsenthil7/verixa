"""CP-3.1 baseline + tenancy schema

Revision ID: 20260510_1130_baseline_tenancy
Revises:
Create Date: 2026-05-10 11:30:00 UK

Creates the `verixa_tenancy` Postgres schema and the `tenants` table.
This is the genesis migration — every later schema FK-references back
to `verixa_tenancy.tenants.tenant_id` either via real FK (Phase 1) or
via UUID equality + RLS (Phase 0).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20260510_1130_baseline_tenancy"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS verixa_tenancy")

    op.create_table(
        "tenants",
        sa.Column(
            "tenant_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("display_name", sa.String(256), nullable=False),
        sa.Column("slug", sa.String(64), nullable=False, unique=True),
        sa.Column(
            "deployment_tier",
            sa.String(32),
            nullable=False,
            server_default=sa.text("'tier_2'"),
        ),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("TRUE"),
        ),
        sa.Column(
            "metadata_json",
            sa.dialects.postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        schema="verixa_tenancy",
    )


def downgrade() -> None:
    op.drop_table("tenants", schema="verixa_tenancy")
    op.execute("DROP SCHEMA IF EXISTS verixa_tenancy CASCADE")
