"""pytest suite for CP-3.2 — registry schema.

Structural validation of the four registry ORM models + the migration.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
MIGRATION_FILE = (
    REPO_ROOT / "migrations" / "versions" / "20260510_1138_registry_schema.py"
)


def _load_migration() -> Any:
    spec = importlib.util.spec_from_file_location(
        "registry_migration", MIGRATION_FILE
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ---------------------------------------------------------------------------
# Migration shape
# ---------------------------------------------------------------------------


def test_registry_migration_chains_to_baseline() -> None:
    m = _load_migration()
    assert m.revision == "20260510_1138_registry_schema"
    assert m.down_revision == "20260510_1130_baseline_tenancy"


def test_registry_migration_has_upgrade_and_downgrade() -> None:
    m = _load_migration()
    assert callable(m.upgrade)
    assert callable(m.downgrade)


# ---------------------------------------------------------------------------
# ORM models registered
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "qualified_table",
    [
        "verixa_registry.agents",
        "verixa_registry.workflows",
        "verixa_registry.tools",
        "verixa_registry.models",
    ],
)
def test_registry_table_in_metadata(qualified_table: str) -> None:
    from verixa_runtime.db import metadata

    assert qualified_table in metadata.tables, (
        f"missing {qualified_table}; have {sorted(metadata.tables)}"
    )


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------


def test_agent_columns_match_spec() -> None:
    from verixa_runtime.db.registry import Agent

    cols = {c.name for c in Agent.__table__.columns}
    expected = {
        "agent_id",
        "spiffe_id",
        "display_name",
        "role",
        "workflow_ids",
        "primary_model",
        "primary_model_hash",
        "sdk_version",
        "risk_baseline",
        "metadata_json",
        "is_active",
        "registered_at",
        "deactivated_at",
        "created_by",
        "tenant_id",
    }
    assert expected.issubset(cols), f"missing: {expected - cols}"


def test_agent_spiffe_id_is_unique() -> None:
    from verixa_runtime.db.registry import Agent

    assert Agent.__table__.c.spiffe_id.unique


# ---------------------------------------------------------------------------
# Workflow
# ---------------------------------------------------------------------------


def test_workflow_columns_match_spec() -> None:
    from verixa_runtime.db.registry import Workflow

    cols = {c.name for c in Workflow.__table__.columns}
    expected = {
        "workflow_id",
        "name",
        "description",
        "risk_classification",
        "sector",
        "compliance_packs",
        "triad_policy_id",
        "escalation_policy_id",
        "retention_tier",
        "is_active",
        "created_at",
        "updated_at",
        "created_by",
        "tenant_id",
    }
    assert expected.issubset(cols), f"missing: {expected - cols}"


def test_workflow_has_risk_classification_check_constraint() -> None:
    from verixa_runtime.db.registry import Workflow

    constraints = [
        c
        for c in Workflow.__table__.constraints
        if c.__class__.__name__ == "CheckConstraint"
    ]
    sources = " ".join(str(c.sqltext) for c in constraints)
    for level in ("low", "medium", "high", "critical"):
        assert level in sources


# ---------------------------------------------------------------------------
# Tool
# ---------------------------------------------------------------------------


def test_tool_columns_match_spec() -> None:
    from verixa_runtime.db.registry import Tool

    cols = {c.name for c in Tool.__table__.columns}
    expected = {
        "tool_id",
        "name",
        "schema",
        "risk_baseline",
        "sensitive_arguments",
        "allowed_workflow_ids",
        "is_active",
        "created_at",
        "tenant_id",
    }
    assert expected.issubset(cols), f"missing: {expected - cols}"


def test_tool_has_unique_tenant_name_constraint() -> None:
    from verixa_runtime.db.registry import Tool

    uniques = [
        c
        for c in Tool.__table__.constraints
        if c.__class__.__name__ == "UniqueConstraint"
    ]
    cols_seen = {tuple(c.name for c in u.columns) for u in uniques}
    assert ("tenant_id", "name") in cols_seen or {
        "tenant_id",
        "name",
    } in [set(t) for t in cols_seen]


# ---------------------------------------------------------------------------
# Model
# ---------------------------------------------------------------------------


def test_model_columns_match_spec() -> None:
    from verixa_runtime.db.registry import Model

    cols = {c.name for c in Model.__table__.columns}
    expected = {
        "model_id",
        "name",
        "family",
        "version_hash",
        "role",
        "deployment_target",
        "quantisation",
        "full_precision",
        "parameters_billion",
        "metadata_json",
        "is_active",
        "registered_at",
        "tenant_id",
    }
    assert expected.issubset(cols), f"missing: {expected - cols}"


def test_model_role_check_constraint() -> None:
    from verixa_runtime.db.registry import Model

    constraints = [
        c
        for c in Model.__table__.constraints
        if c.__class__.__name__ == "CheckConstraint"
    ]
    sources = " ".join(str(c.sqltext) for c in constraints)
    for role in ("primary", "reviewer", "verifier"):
        assert role in sources
