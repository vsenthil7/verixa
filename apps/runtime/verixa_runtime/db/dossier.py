"""Verixa dossier schema (`verixa_dossier`) — compliance evidence packs.

Per docs/09_data_model/DATA_MODEL.md §8.

A dossier is a generated compliance pack that bundles audit entries +
metadata into a PDF + machine-readable JSON. The `hash_chain_proof`
column captures the hash-chain anchor for the entries covered, so a
verifier can confirm the dossier corresponds to a verifiable range of
the underlying audit ledger without re-querying.

Phase 0 implements the per-decision pack only. Per-workflow / Annex IV
/ Article 72 packs come in Phase 1 (per docs/15_build_plan/BUILD_PLAN.md).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, String, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from verixa_runtime.db import Base

SCHEMA_NAME = "verixa_dossier"


class Dossier(Base):
    """Generated compliance dossier record."""

    __tablename__ = "dossiers"
    __table_args__ = ({"schema": SCHEMA_NAME},)

    dossier_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False
    )
    workflow_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    time_range_start: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    time_range_end: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    regulator_target: Mapped[str | None] = mapped_column(
        String, nullable=True
    )
    template_version: Mapped[str] = mapped_column(String, nullable=False)
    pdf_object_key: Mapped[str] = mapped_column(String, nullable=False)
    json_object_key: Mapped[str] = mapped_column(String, nullable=False)
    hash_chain_proof: Mapped[str] = mapped_column(String, nullable=False)
    summary: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    generated_by: Mapped[str] = mapped_column(String, nullable=False)
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("NOW()"),
    )
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
