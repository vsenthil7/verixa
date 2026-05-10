"""pytest suite for CP-3.4 — audit ledger schema (audit_entries, signing_keys).

The audit ledger is the single most important schema in Verixa.
Tests cover ORM model shape + migration shape + the cryptographic
columns that CP-4 + CP-5 will populate.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
MIGRATION_FILE = (
    REPO_ROOT / "migrations" / "versions" / "20260510_1212_audit_schema.py"
)


def _load_migration() -> Any:
    spec = importlib.util.spec_from_file_location("audit_migration", MIGRATION_FILE)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ---------------------------------------------------------------------------
# Migration shape
# ---------------------------------------------------------------------------


def test_audit_migration_chains_to_policy() -> None:
    m = _load_migration()
    assert m.revision == "20260510_1212_audit_schema"
    assert m.down_revision == "20260510_1147_policy_schema"


def test_audit_migration_has_upgrade_and_downgrade() -> None:
    m = _load_migration()
    assert callable(m.upgrade)
    assert callable(m.downgrade)


# ---------------------------------------------------------------------------
# Tables in metadata
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "qualified",
    ["verixa_audit.audit_entries", "verixa_audit.signing_keys"],
)
def test_audit_table_in_metadata(qualified: str) -> None:
    from verixa_runtime.db import metadata

    assert qualified in metadata.tables


# ---------------------------------------------------------------------------
# AuditEntry model
# ---------------------------------------------------------------------------


def test_audit_entry_columns_match_spec() -> None:
    from verixa_runtime.db.audit import AuditEntry

    cols = {c.name for c in AuditEntry.__table__.columns}
    expected = {
        "audit_id",
        "tenant_id",
        "sequence_number",
        "event_time",
        "workflow_id",
        "agent_id",
        "action_type",
        "tool_name",
        "decision",
        "reason",
        "risk_score",
        "risk_classification",
        "triad_invoked",
        "triad_review_id",
        "hash_chain_prev",
        "hash_chain_self",
        "signature",
        "signing_key_id",
        "latency_ms",
        "request_id",
        "trace_id",
        "policies_applied",
    }
    assert expected.issubset(cols), f"missing: {expected - cols}"


def test_audit_entry_decision_check_constraint() -> None:
    from verixa_runtime.db.audit import AuditEntry

    constraints = [
        c
        for c in AuditEntry.__table__.constraints
        if c.__class__.__name__ == "CheckConstraint"
    ]
    sources = " ".join(str(c.sqltext) for c in constraints)
    for d in ("allow", "deny", "escalate", "pending"):
        assert d in sources, f"decision value {d!r} not in CHECK"


def test_audit_entry_unique_tenant_sequence() -> None:
    """Sequence numbers must be unique per tenant — chain integrity."""
    from verixa_runtime.db.audit import AuditEntry

    uniques = [
        c
        for c in AuditEntry.__table__.constraints
        if c.__class__.__name__ == "UniqueConstraint"
    ]
    found = {tuple(c.name for c in u.columns) for u in uniques}
    assert any(
        set(cols) == {"tenant_id", "sequence_number"} for cols in found
    ), f"missing unique(tenant_id, sequence_number); have {found}"


def test_audit_entry_has_required_crypto_columns() -> None:
    """Hash chain + signature columns are NOT NULL — chain integrity."""
    from verixa_runtime.db.audit import AuditEntry

    table = AuditEntry.__table__
    # hash_chain_self, signature, signing_key_id, sequence_number are NOT NULL
    for required in (
        "hash_chain_self",
        "signature",
        "signing_key_id",
        "sequence_number",
        "tenant_id",
        "event_time",
    ):
        assert table.c[required].nullable is False, (
            f"{required} must be NOT NULL"
        )


def test_audit_entry_hash_chain_prev_is_nullable() -> None:
    """Genesis entry has no prior hash; subsequent entries must populate it."""
    from verixa_runtime.db.audit import AuditEntry

    assert AuditEntry.__table__.c.hash_chain_prev.nullable is True


def test_audit_entry_repr_includes_sequence_and_decision() -> None:
    from verixa_runtime.db.audit import AuditEntry

    e = AuditEntry()
    e.audit_id = "00000000-0000-0000-0000-000000000abc"
    e.sequence_number = 42
    e.decision = "allow"
    s = repr(e)
    assert "seq=42" in s
    assert "decision=allow" in s
    assert "00000000-0000-0000-0000-000000000abc" in s


def test_audit_entry_indexes_present() -> None:
    """Required indexes for hot-path queries (per spec)."""
    from verixa_runtime.db.audit import AuditEntry

    index_names = {idx.name for idx in AuditEntry.__table__.indexes}
    expected = {
        "idx_audit_tenant_time",
        "idx_audit_workflow",
        "idx_audit_agent",
        "idx_audit_decision",
        "idx_audit_risk_high",
    }
    assert expected.issubset(index_names), (
        f"missing indexes: {expected - index_names}"
    )


# ---------------------------------------------------------------------------
# SigningKey model
# ---------------------------------------------------------------------------


def test_signing_key_columns_match_spec() -> None:
    from verixa_runtime.db.audit import SigningKey

    cols = {c.name for c in SigningKey.__table__.columns}
    expected = {
        "key_id",
        "tenant_id",
        "public_key_pem",
        "algorithm",
        "activated_at",
        "deactivated_at",
        "is_active",
    }
    assert expected.issubset(cols), f"missing: {expected - cols}"


def test_signing_key_algorithm_check() -> None:
    """Phase 0 only allows ed25519. Phase 1+ may add post-quantum algorithms."""
    from verixa_runtime.db.audit import SigningKey

    constraints = [
        c
        for c in SigningKey.__table__.constraints
        if c.__class__.__name__ == "CheckConstraint"
    ]
    sources = " ".join(str(c.sqltext) for c in constraints)
    assert "ed25519" in sources


def test_signing_key_id_is_primary_key() -> None:
    from verixa_runtime.db.audit import SigningKey

    pk_cols = [c.name for c in SigningKey.__table__.primary_key]
    assert pk_cols == ["key_id"]


def test_signing_key_public_key_is_required() -> None:
    """Public key PEM must be present — required for offline verification."""
    from verixa_runtime.db.audit import SigningKey

    assert SigningKey.__table__.c.public_key_pem.nullable is False
