"""pytest suite for CP-3.5 — replay schema (replay_index)."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]
MIGRATION_FILE = (
    REPO_ROOT / "migrations" / "versions" / "20260510_1214_replay_schema.py"
)


def _load_migration() -> Any:
    spec = importlib.util.spec_from_file_location("replay_migration", MIGRATION_FILE)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_replay_migration_chains_to_audit() -> None:
    m = _load_migration()
    assert m.revision == "20260510_1214_replay_schema"
    assert m.down_revision == "20260510_1212_audit_schema"


def test_replay_migration_callable() -> None:
    m = _load_migration()
    assert callable(m.upgrade)
    assert callable(m.downgrade)


def test_replay_index_table_in_metadata() -> None:
    from verixa_runtime.db import metadata

    assert "verixa_replay.replay_index" in metadata.tables


def test_replay_index_columns_match_spec() -> None:
    from verixa_runtime.db.replay import ReplayIndex

    cols = {c.name for c in ReplayIndex.__table__.columns}
    expected = {
        "replay_id",
        "audit_id",
        "tenant_id",
        "object_key",
        "object_store_url",
        "bundle_hash",
        "encryption_key_id",
        "bundle_size_bytes",
        "retention_tier",
        "expires_at",
        "created_at",
    }
    assert expected.issubset(cols), f"missing: {expected - cols}"


def test_replay_index_retention_tier_check() -> None:
    from verixa_runtime.db.replay import ReplayIndex

    constraints = [
        c
        for c in ReplayIndex.__table__.constraints
        if c.__class__.__name__ == "CheckConstraint"
    ]
    sources = " ".join(str(c.sqltext) for c in constraints)
    for tier in ("hot", "warm", "cold"):
        assert tier in sources


def test_replay_index_unique_tenant_audit() -> None:
    """One replay row per audit entry — chain integrity."""
    from verixa_runtime.db.replay import ReplayIndex

    uniques = [
        c
        for c in ReplayIndex.__table__.constraints
        if c.__class__.__name__ == "UniqueConstraint"
    ]
    found = {tuple(c.name for c in u.columns) for u in uniques}
    assert any(set(cols) == {"tenant_id", "audit_id"} for cols in found)


def test_replay_index_required_columns_not_null() -> None:
    """object_key, bundle_hash, encryption_key_id must be NOT NULL."""
    from verixa_runtime.db.replay import ReplayIndex

    for required in (
        "audit_id",
        "tenant_id",
        "object_key",
        "object_store_url",
        "bundle_hash",
        "encryption_key_id",
        "retention_tier",
    ):
        assert ReplayIndex.__table__.c[required].nullable is False, (
            f"{required} must be NOT NULL"
        )


def test_replay_index_indexes_present() -> None:
    from verixa_runtime.db.replay import ReplayIndex

    index_names = {idx.name for idx in ReplayIndex.__table__.indexes}
    expected = {"idx_replay_audit", "idx_replay_retention"}
    assert expected.issubset(index_names)
