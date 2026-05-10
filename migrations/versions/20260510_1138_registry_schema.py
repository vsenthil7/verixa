"""CP-3.2 registry schema (agents, workflows, tools, models)

Revision ID: 20260510_1138_registry_schema
Revises: 20260510_1130_baseline_tenancy
Create Date: 2026-05-10 11:38:00 UK
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260510_1138_registry_schema"
down_revision: Union[str, None] = "20260510_1130_baseline_tenancy"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS verixa_registry")

    # ---- agents -----------------------------------------------------------
    op.create_table(
        "agents",
        sa.Column(
            "agent_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("spiffe_id", sa.String(), nullable=False, unique=True),
        sa.Column("display_name", sa.String(), nullable=False),
        sa.Column("role", sa.String(), nullable=False),
        sa.Column(
            "workflow_ids",
            sa.ARRAY(sa.dialects.postgresql.UUID(as_uuid=True)),
            nullable=False,
            server_default=sa.text("ARRAY[]::uuid[]"),
        ),
        sa.Column("primary_model", sa.String(), nullable=True),
        sa.Column("primary_model_hash", sa.String(), nullable=True),
        sa.Column("sdk_version", sa.String(), nullable=True),
        sa.Column(
            "risk_baseline",
            sa.Numeric(4, 3),
            nullable=False,
            server_default=sa.text("0.500"),
        ),
        sa.Column(
            "metadata_json",
            sa.dialects.postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("TRUE"),
        ),
        sa.Column(
            "registered_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column("deactivated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.String(), nullable=False),
        sa.Column(
            "tenant_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        schema="verixa_registry",
    )
    op.create_index(
        "idx_agents_tenant_active",
        "agents",
        ["tenant_id", "is_active"],
        schema="verixa_registry",
    )
    op.create_index(
        "idx_agents_spiffe", "agents", ["spiffe_id"], schema="verixa_registry"
    )

    # ---- workflows --------------------------------------------------------
    op.create_table(
        "workflows",
        sa.Column(
            "workflow_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("description", sa.String(), nullable=True),
        sa.Column("risk_classification", sa.String(), nullable=False),
        sa.Column("sector", sa.String(), nullable=False),
        sa.Column(
            "compliance_packs",
            sa.ARRAY(sa.String()),
            nullable=False,
            server_default=sa.text("ARRAY[]::text[]"),
        ),
        sa.Column(
            "triad_policy_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
        sa.Column(
            "escalation_policy_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
        sa.Column(
            "retention_tier",
            sa.String(),
            nullable=False,
            server_default=sa.text("'enterprise_production'"),
        ),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("TRUE"),
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
        sa.Column("created_by", sa.String(), nullable=False),
        sa.Column(
            "tenant_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.CheckConstraint(
            "risk_classification IN ('low', 'medium', 'high', 'critical')",
            name="ck_workflows_risk_classification",
        ),
        schema="verixa_registry",
    )
    op.create_index(
        "idx_workflows_tenant_active",
        "workflows",
        ["tenant_id", "is_active"],
        schema="verixa_registry",
    )
    op.create_index(
        "idx_workflows_sector",
        "workflows",
        ["sector"],
        schema="verixa_registry",
    )

    # ---- tools ------------------------------------------------------------
    op.create_table(
        "tools",
        sa.Column(
            "tool_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("schema", sa.dialects.postgresql.JSONB(), nullable=False),
        sa.Column(
            "risk_baseline",
            sa.Numeric(4, 3),
            nullable=False,
            server_default=sa.text("0.500"),
        ),
        sa.Column(
            "sensitive_arguments",
            sa.ARRAY(sa.String()),
            nullable=False,
            server_default=sa.text("ARRAY[]::text[]"),
        ),
        sa.Column(
            "allowed_workflow_ids",
            sa.ARRAY(sa.dialects.postgresql.UUID(as_uuid=True)),
            nullable=False,
            server_default=sa.text("ARRAY[]::uuid[]"),
        ),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("TRUE"),
        ),
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
        sa.UniqueConstraint(
            "tenant_id", "name", name="uq_tools_tenant_name"
        ),
        schema="verixa_registry",
    )

    # ---- models -----------------------------------------------------------
    op.create_table(
        "models",
        sa.Column(
            "model_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("family", sa.String(), nullable=False),
        sa.Column("version_hash", sa.String(), nullable=False),
        sa.Column("role", sa.String(), nullable=False),
        sa.Column("deployment_target", sa.String(), nullable=False),
        sa.Column("quantisation", sa.String(), nullable=True),
        sa.Column(
            "full_precision",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("FALSE"),
        ),
        sa.Column("parameters_billion", sa.Numeric(5, 1), nullable=True),
        sa.Column(
            "metadata_json",
            sa.dialects.postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("TRUE"),
        ),
        sa.Column(
            "registered_at",
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
            "role IN ('primary', 'reviewer', 'verifier')",
            name="ck_models_role",
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "name",
            "version_hash",
            name="uq_models_tenant_name_version",
        ),
        schema="verixa_registry",
    )


def downgrade() -> None:
    op.drop_table("models", schema="verixa_registry")
    op.drop_table("tools", schema="verixa_registry")
    op.drop_table("workflows", schema="verixa_registry")
    op.drop_table("agents", schema="verixa_registry")
    op.execute("DROP SCHEMA IF EXISTS verixa_registry CASCADE")
