"""pytest suite for CP-3.3 — policy schema (policies, policy_test_fixtures)."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
MIGRATION_FILE = (
    REPO_ROOT / "migrations" / "versions" / "20260510_1147_policy_schema.py"
)


def _load_migration() -> Any:
    spec = importlib.util.spec_from_file_location("policy_migration", MIGRATION_FILE)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_policy_migration_chains_to_registry() -> None:
    m = _load_migration()
    assert m.revision == "20260510_1147_policy_schema"
    assert m.down_revision == "20260510_1138_registry_schema"


def test_policy_migration_has_upgrade_and_downgrade() -> None:
    m = _load_migration()
    assert callable(m.upgrade)
    assert callable(m.downgrade)


@pytest.mark.parametrize(
    "qualified",
    ["verixa_policy.policies", "verixa_policy.policy_test_fixtures"],
)
def test_policy_table_in_metadata(qualified: str) -> None:
    from verixa_runtime.db import metadata

    assert qualified in metadata.tables


def test_policy_columns_match_spec() -> None:
    from verixa_runtime.db.policy import Policy

    cols = {c.name for c in Policy.__table__.columns}
    expected = {
        "policy_id",
        "name",
        "description",
        "rego_source",
        "rego_compiled_hash",
        "version",
        "is_active",
        "compliance_pack",
        "regulatory_mappings",
        "created_at",
        "created_by",
        "tenant_id",
    }
    assert expected.issubset(cols), f"missing: {expected - cols}"


def test_policy_unique_tenant_name_version() -> None:
    from verixa_runtime.db.policy import Policy

    uniques = [
        c
        for c in Policy.__table__.constraints
        if c.__class__.__name__ == "UniqueConstraint"
    ]
    found_cols = {tuple(c.name for c in u.columns) for u in uniques}
    assert any(
        set(cols) == {"tenant_id", "name", "version"} for cols in found_cols
    )


def test_policy_test_fixture_columns() -> None:
    from verixa_runtime.db.policy import PolicyTestFixture

    cols = {c.name for c in PolicyTestFixture.__table__.columns}
    expected = {
        "fixture_id",
        "policy_id",
        "name",
        "input_payload",
        "expected_result",
        "expected_reason",
        "created_at",
        "tenant_id",
    }
    assert expected.issubset(cols), f"missing: {expected - cols}"


def test_policy_test_fixture_expected_result_check() -> None:
    from verixa_runtime.db.policy import PolicyTestFixture

    constraints = [
        c
        for c in PolicyTestFixture.__table__.constraints
        if c.__class__.__name__ == "CheckConstraint"
    ]
    sources = " ".join(str(c.sqltext) for c in constraints)
    for outcome in ("pass", "fail", "abstain"):
        assert outcome in sources


def test_policy_test_fixture_fk_to_policies() -> None:
    from verixa_runtime.db.policy import PolicyTestFixture

    fks = [
        fk
        for col in PolicyTestFixture.__table__.columns
        for fk in col.foreign_keys
    ]
    targets = {fk.target_fullname for fk in fks}
    assert "verixa_policy.policies.policy_id" in targets
