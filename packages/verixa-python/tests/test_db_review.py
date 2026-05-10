"""pytest suite for CP-3.6 — review schema (triad_reviews + human_reviews).

Special focus: the commit-and-reveal columns of triad_reviews. Those
fields are the protocol Verixa CP-10 implements — every reviewer's
commit_hash MUST be NOT NULL (commit phase is mandatory), while
verdict/reasoning/nonce are nullable until reveal completes.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
MIGRATION_FILE = (
    REPO_ROOT / "migrations" / "versions" / "20260510_1216_review_schema.py"
)


def _load_migration() -> Any:
    spec = importlib.util.spec_from_file_location("review_migration", MIGRATION_FILE)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ---------------------------------------------------------------------------
# Migration shape
# ---------------------------------------------------------------------------


def test_review_migration_chains_to_replay() -> None:
    m = _load_migration()
    assert m.revision == "20260510_1216_review_schema"
    assert m.down_revision == "20260510_1214_replay_schema"


def test_review_migration_callable() -> None:
    m = _load_migration()
    assert callable(m.upgrade)
    assert callable(m.downgrade)


# ---------------------------------------------------------------------------
# Tables in metadata
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "qualified",
    ["verixa_review.triad_reviews", "verixa_review.human_reviews"],
)
def test_review_table_in_metadata(qualified: str) -> None:
    from verixa_runtime.db import metadata

    assert qualified in metadata.tables


# ---------------------------------------------------------------------------
# TriadReview: commit + reveal protocol columns
# ---------------------------------------------------------------------------


def test_triad_review_columns_match_spec() -> None:
    from verixa_runtime.db.review import TriadReview

    cols = {c.name for c in TriadReview.__table__.columns}
    expected = {
        "triad_review_id",
        "audit_id",
        "tenant_id",
        "workflow_id",
        "invoked_at",
        "revealed_at",
        "reviewer_a_model_id",
        "reviewer_b_model_id",
        "reviewer_c_model_id",
        "reviewer_a_commit_hash",
        "reviewer_b_commit_hash",
        "reviewer_c_commit_hash",
        "commit_completed_at",
        "reviewer_a_verdict",
        "reviewer_a_reasoning",
        "reviewer_a_nonce",
        "reviewer_b_verdict",
        "reviewer_b_reasoning",
        "reviewer_b_nonce",
        "reviewer_c_verdict",
        "reviewer_c_reasoning",
        "reviewer_c_nonce",
        "consensus",
        "consensus_reason",
        "total_latency_ms",
    }
    assert expected.issubset(cols), f"missing: {expected - cols}"


@pytest.mark.parametrize("reviewer", ["a", "b", "c"])
def test_triad_review_commit_hashes_are_required(reviewer: str) -> None:
    """Commit phase is mandatory — commit_hash columns are NOT NULL."""
    from verixa_runtime.db.review import TriadReview

    col = TriadReview.__table__.c[f"reviewer_{reviewer}_commit_hash"]
    assert col.nullable is False, (
        f"reviewer_{reviewer}_commit_hash must be NOT NULL"
    )


@pytest.mark.parametrize(
    "reveal_col",
    [
        "reviewer_a_verdict",
        "reviewer_a_nonce",
        "reviewer_b_verdict",
        "reviewer_b_nonce",
        "reviewer_c_verdict",
        "reviewer_c_nonce",
    ],
)
def test_triad_review_reveal_columns_are_nullable(reveal_col: str) -> None:
    """Reveal phase is post-commit — these columns are nullable until reveal."""
    from verixa_runtime.db.review import TriadReview

    col = TriadReview.__table__.c[reveal_col]
    assert col.nullable is True, f"{reveal_col} must be nullable until reveal"


def test_triad_review_unique_tenant_audit() -> None:
    """One triad per audit — chain integrity."""
    from verixa_runtime.db.review import TriadReview

    uniques = [
        c
        for c in TriadReview.__table__.constraints
        if c.__class__.__name__ == "UniqueConstraint"
    ]
    found = {tuple(c.name for c in u.columns) for u in uniques}
    assert any(set(cols) == {"tenant_id", "audit_id"} for cols in found)


# ---------------------------------------------------------------------------
# HumanReview
# ---------------------------------------------------------------------------


def test_human_review_columns_match_spec() -> None:
    from verixa_runtime.db.review import HumanReview

    cols = {c.name for c in HumanReview.__table__.columns}
    expected = {
        "human_review_id",
        "escalation_id",
        "audit_id",
        "tenant_id",
        "queued_at",
        "assigned_at",
        "decided_at",
        "reviewer_identity",
        "reviewer_role",
        "decision",
        "decision_notes",
        "review_duration_ms",
        "sla_target_minutes",
        "sla_breached",
    }
    assert expected.issubset(cols), f"missing: {expected - cols}"


def test_human_review_decision_check_constraint() -> None:
    from verixa_runtime.db.review import HumanReview

    constraints = [
        c
        for c in HumanReview.__table__.constraints
        if c.__class__.__name__ == "CheckConstraint"
    ]
    sources = " ".join(str(c.sqltext) for c in constraints)
    for d in ("approve", "deny", "request_more_info"):
        assert d in sources


def test_human_review_decision_is_nullable_until_decided() -> None:
    """`decision` is nullable while review is in queue/assigned states."""
    from verixa_runtime.db.review import HumanReview

    assert HumanReview.__table__.c.decision.nullable is True
    assert HumanReview.__table__.c.decided_at.nullable is True


def test_human_review_partial_index_for_open_queue() -> None:
    """idx_human_reviews_tenant_status filters decided_at IS NULL."""
    from verixa_runtime.db.review import HumanReview

    indexes = list(HumanReview.__table__.indexes)
    open_queue_idx = next(
        (i for i in indexes if i.name == "idx_human_reviews_tenant_status"),
        None,
    )
    assert open_queue_idx is not None
