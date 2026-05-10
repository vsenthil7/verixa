"""CP-3.7 dossier schema (dossiers)

Revision ID: 20260510_1220_dossier_schema
Revises: 20260510_1216_review_schema
Create Date: 2026-05-10 12:20:00 UK
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260510_1220_dossier_schema"
down_revision: Union[str, None] = "20260510_1216_review_schema"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS verixa_dossier")

    op.create_table(
        "dossiers",
        sa.Column(
            "dossier_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "tenant_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "workflow_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
        sa.Column(
            "time_range_start", sa.DateTime(timezone=True), nullable=False
        ),
        sa.Column(
            "time_range_end", sa.DateTime(timezone=True), nullable=False
        ),
        sa.Column("regulator_target", sa.String(), nullable=True),
        sa.Column("template_version", sa.String(), nullable=False),
        sa.Column("pdf_object_key", sa.String(), nullable=False),
        sa.Column("json_object_key", sa.String(), nullable=False),
        sa.Column("hash_chain_proof", sa.String(), nullable=False),
        sa.Column(
            "summary", sa.dialects.postgresql.JSONB(), nullable=False
        ),
        sa.Column("generated_by", sa.String(), nullable=False),
        sa.Column(
            "generated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        schema="verixa_dossier",
    )


def downgrade() -> None:
    op.drop_table("dossiers", schema="verixa_dossier")
    op.execute("DROP SCHEMA IF EXISTS verixa_dossier CASCADE")
