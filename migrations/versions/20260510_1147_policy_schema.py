"""CP-3.3 policy schema (policies, policy_test_fixtures)

Revision ID: 20260510_1147_policy_schema
Revises: 20260510_1138_registry_schema
Create Date: 2026-05-10 11:47:00 UK
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260510_1147_policy_schema"
down_revision: str | None = "20260510_1138_registry_schema"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS verixa_policy")

    op.create_table(
        "policies",
        sa.Column(
            "policy_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("description", sa.String(), nullable=True),
        sa.Column("rego_source", sa.String(), nullable=False),
        sa.Column("rego_compiled_hash", sa.String(), nullable=False),
        sa.Column(
            "version",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("1"),
        ),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("TRUE"),
        ),
        sa.Column("compliance_pack", sa.String(), nullable=True),
        sa.Column(
            "regulatory_mappings",
            sa.dialects.postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column("created_by", sa.String(), nullable=False),
        sa.Column(
            "tenant_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "name",
            "version",
            name="uq_policies_tenant_name_version",
        ),
        schema="verixa_policy",
    )
    op.create_index(
        "idx_policies_tenant_active",
        "policies",
        ["tenant_id", "is_active"],
        schema="verixa_policy",
    )
    op.create_index(
        "idx_policies_pack",
        "policies",
        ["compliance_pack"],
        schema="verixa_policy",
    )

    op.create_table(
        "policy_test_fixtures",
        sa.Column(
            "fixture_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "policy_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("verixa_policy.policies.policy_id"),
            nullable=False,
        ),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column(
            "input_payload",
            sa.dialects.postgresql.JSONB(),
            nullable=False,
        ),
        sa.Column("expected_result", sa.String(), nullable=False),
        sa.Column("expected_reason", sa.String(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column(
            "tenant_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.CheckConstraint(
            "expected_result IN ('pass', 'fail', 'abstain')",
            name="ck_policy_test_fixtures_expected_result",
        ),
        schema="verixa_policy",
    )


def downgrade() -> None:
    op.drop_table("policy_test_fixtures", schema="verixa_policy")
    op.drop_table("policies", schema="verixa_policy")
    op.execute("DROP SCHEMA IF EXISTS verixa_policy CASCADE")
