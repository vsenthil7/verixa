"""CP-30 negative test 2/5: replay-attack edges on bundle deserialisation.

Anchored to UC-09 (replay vault), BR-04 (replay-vault snapshot integrity),
NEGATIVE_TEST_PLAN section 5 (replay attacks).

A "replay attack" in the Verixa context means an attacker takes a
previously-sealed bundle (or a bundle they've intercepted) and tries
to inject it back into the verifier as though it were a fresh
decision. The defences are: schema_version match, required-field
match, audit_id uniqueness (caller-enforced), and the seal layer
(AES-256-GCM tag in test_replay_sealer.py).

This file tests the bundle-deserialiser layer specifically:

  - reusing a valid bundle bytes string MUST round-trip identically
    (no hidden state)
  - tampering ANY single field MUST fail deserialise OR produce a
    bundle whose canonicalisation does NOT match the original (caller
    detects mismatch)
  - swapping in a different audit_id MUST produce a different
    canonicalisation (so the seal verifier rejects it as bound to a
    different audit_id)
  - reusing the same canonical bytes against a different tenant_id
    (constructed in caller code) MUST produce different bytes and
    therefore a different commitment hash
  - dropping a required field after canonical serialisation MUST be
    rejected at deserialise time, not silently accepted

Adversarial framing: these tests model an attacker who has captured
a known-good bundle (e.g. for a previously-ALLOWed transfer) and
attempts to re-present it for a different audit, tenant, or to
strip a field that flags the decision as DENY.
"""

from __future__ import annotations

import json
import uuid

import pytest
from verixa_runtime.replay import (
    BUNDLE_SCHEMA_VERSION,
    PolicyEvaluationRecord,
    ReplayBundle,
    TriadReviewRecord,
    canonicalise_bundle,
    deserialise_bundle,
)

_AUDIT_ID_ORIG = uuid.UUID("11111111-1111-1111-1111-111111111111")
_AUDIT_ID_NEW = uuid.UUID("22222222-2222-2222-2222-222222222222")
_TENANT_ID_ORIG = uuid.UUID("33333333-3333-3333-3333-333333333333")
_TENANT_ID_NEW = uuid.UUID("44444444-4444-4444-4444-444444444444")


def _bundle(
    audit_id: uuid.UUID = _AUDIT_ID_ORIG,
    tenant_id: uuid.UUID = _TENANT_ID_ORIG,
    decision: str = "allow",
) -> ReplayBundle:
    return ReplayBundle(
        audit_id=audit_id,
        tenant_id=tenant_id,
        decision=decision,
        risk_score=0.1,
        request_envelope={"action": {"type": "tool_call"}},
        timestamp_unix_ns=1_700_000_000_000_000_000,
    )


# ---------------------------------------------------------------------------
# Identity / determinism (positive baselines for the negative tests)
# ---------------------------------------------------------------------------


def test_same_bundle_canonicalises_to_same_bytes() -> None:
    """Determinism baseline: two structurally-identical bundles MUST
    produce byte-identical canonical output. If this ever changes, an
    attacker could craft a 'looks-same-but-different-bytes' bundle and
    break the seal."""
    b1 = _bundle()
    b2 = _bundle()
    assert canonicalise_bundle(b1) == canonicalise_bundle(b2)


def test_round_trip_preserves_all_fields() -> None:
    """Round-trip identity baseline: deserialise(canonicalise(b)) MUST
    preserve every safety-critical field. An attacker who mutates
    bytes in transit must not be able to land a bundle that
    deserialises differently than it canonicalised."""
    b = _bundle()
    bytes_out = canonicalise_bundle(b)
    b2 = deserialise_bundle(bytes_out)
    assert b2.audit_id == b.audit_id
    assert b2.tenant_id == b.tenant_id
    assert b2.decision == b.decision
    assert b2.risk_score == pytest.approx(b.risk_score)


# ---------------------------------------------------------------------------
# Replay-attack scenarios
# ---------------------------------------------------------------------------


def test_swapping_audit_id_changes_canonical_bytes() -> None:
    """Take a known-good ALLOW bundle, swap in a different audit_id,
    canonicalise. The new bytes MUST be different. The seal (computed
    over canonical bytes) will then mismatch the original signature
    so a downstream verifier rejects the replay."""
    b1 = _bundle(audit_id=_AUDIT_ID_ORIG)
    b2 = _bundle(audit_id=_AUDIT_ID_NEW)
    assert canonicalise_bundle(b1) != canonicalise_bundle(b2)


def test_swapping_tenant_id_changes_canonical_bytes() -> None:
    """Replay across tenants: attacker takes tenant A's ALLOW bundle
    and rewrites tenant_id to tenant B. Canonical bytes diverge so
    seal verification fails. Defence against cross-tenant replay."""
    b1 = _bundle(tenant_id=_TENANT_ID_ORIG)
    b2 = _bundle(tenant_id=_TENANT_ID_NEW)
    assert canonicalise_bundle(b1) != canonicalise_bundle(b2)


def test_flipping_decision_changes_canonical_bytes() -> None:
    """Attacker flips DENY -> ALLOW on a captured bundle. Canonical
    bytes diverge; seal verifier rejects."""
    b_deny = _bundle(decision="deny")
    b_allow = _bundle(decision="allow")
    assert canonicalise_bundle(b_deny) != canonicalise_bundle(b_allow)


def test_dropping_required_field_after_serialisation_rejected() -> None:
    """Attacker takes valid JSON, drops 'risk_score', re-serialises.
    Deserialise MUST reject with a 'missing required fields' error."""
    b = _bundle()
    parsed = json.loads(canonicalise_bundle(b))
    del parsed["risk_score"]
    tampered = json.dumps(parsed).encode("utf-8")
    with pytest.raises(ValueError, match="missing required fields"):
        deserialise_bundle(tampered)


def test_downgrading_schema_version_rejected() -> None:
    """Attacker tries to downgrade schema_version to a value an old
    verifier accepts. Deserialise MUST reject any version not equal
    to the current BUNDLE_SCHEMA_VERSION."""
    b = _bundle()
    parsed = json.loads(canonicalise_bundle(b))
    parsed["schema_version"] = BUNDLE_SCHEMA_VERSION + 99
    tampered = json.dumps(parsed).encode("utf-8")
    with pytest.raises(ValueError, match="unsupported schema_version"):
        deserialise_bundle(tampered)


def test_upgrading_schema_version_rejected() -> None:
    """And forward attempts: an attacker who knows a future bundle
    format exists tries to land a future-version bundle through the
    current verifier."""
    b = _bundle()
    parsed = json.loads(canonicalise_bundle(b))
    parsed["schema_version"] = -1
    tampered = json.dumps(parsed).encode("utf-8")
    with pytest.raises(ValueError, match="unsupported schema_version"):
        deserialise_bundle(tampered)


def test_replaying_with_swapped_triad_record_changes_bytes() -> None:
    """Attacker reuses a bundle but swaps in a DIFFERENT triad record
    that previously approved a different action. Canonical bytes
    diverge -> seal fails. This is the cross-decision triad replay
    defence."""
    triad_a = TriadReviewRecord(
        consensus_kind="unanimous",
        agreed_decision="allow",
        verdicts=(
            ("reviewer_a", "allow", 0.9, "a-ok"),
            ("reviewer_b", "allow", 0.9, "b-ok"),
            ("reviewer_c", "allow", 0.9, "c-ok"),
        ),
        commitments=(
            ("reviewer_a", "1" * 64),
            ("reviewer_b", "2" * 64),
            ("reviewer_c", "3" * 64),
        ),
    )
    triad_b = TriadReviewRecord(
        consensus_kind="majority",
        agreed_decision="allow",
        verdicts=(
            ("reviewer_a", "allow", 0.9, "a-ok"),
            ("reviewer_b", "allow", 0.9, "b-ok"),
            ("reviewer_c", "deny", 0.7, "c-deny"),
        ),
        commitments=(
            ("reviewer_a", "1" * 64),
            ("reviewer_b", "2" * 64),
            ("reviewer_c", "9" * 64),
        ),
    )
    b1 = ReplayBundle(
        audit_id=_AUDIT_ID_ORIG,
        tenant_id=_TENANT_ID_ORIG,
        decision="allow",
        risk_score=0.5,
        request_envelope={"a": 1},
        timestamp_unix_ns=1_700_000_000_000_000_000,
        triad_review=triad_a,
    )
    b2 = ReplayBundle(
        audit_id=_AUDIT_ID_ORIG,
        tenant_id=_TENANT_ID_ORIG,
        decision="allow",
        risk_score=0.5,
        request_envelope={"a": 1},
        timestamp_unix_ns=1_700_000_000_000_000_000,
        triad_review=triad_b,
    )
    assert canonicalise_bundle(b1) != canonicalise_bundle(b2)


def test_policy_eval_substitution_changes_bytes() -> None:
    """Attacker swaps a 'fail' policy evaluation for a 'pass' one.
    Canonical bytes diverge -> seal fails."""
    fail_eval = PolicyEvaluationRecord(
        package="verixa.fs.transfer_limit", decision="fail", reason="over"
    )
    pass_eval = PolicyEvaluationRecord(
        package="verixa.fs.transfer_limit", decision="pass", reason="under"
    )
    b1 = ReplayBundle(
        audit_id=_AUDIT_ID_ORIG,
        tenant_id=_TENANT_ID_ORIG,
        decision="deny",
        risk_score=0.9,
        request_envelope={"a": 1},
        timestamp_unix_ns=1_700_000_000_000_000_000,
        policy_evaluations=(fail_eval,),
    )
    b2 = ReplayBundle(
        audit_id=_AUDIT_ID_ORIG,
        tenant_id=_TENANT_ID_ORIG,
        decision="deny",
        risk_score=0.9,
        request_envelope={"a": 1},
        timestamp_unix_ns=1_700_000_000_000_000_000,
        policy_evaluations=(pass_eval,),
    )
    assert canonicalise_bundle(b1) != canonicalise_bundle(b2)
