"""pytest suite for verixa_runtime.audit.emitter.

Coverage discipline: 100% line + branch on emitter.py.
The verifier.py module is a CP-5.1 placeholder (function body raises
NotImplementedError + has `pragma: no cover`); CP-5.2 will replace it
with the real walk and its own tests.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from verixa_runtime.audit.emitter import (
    AuditEmitInput,
    AuditEmitRecord,
    AuditEmitterError,
    emit_audit_record,
)
from verixa_runtime.crypto.ed25519 import verify as ed25519_verify
from verixa_runtime.crypto.hash_chain import (
    HashChainEntry,
    compute_genesis_prev,
    compute_self_hash,
)
from verixa_runtime.crypto.key_bootstrap import bootstrap_tenant

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def tenant_id() -> uuid.UUID:
    return uuid.UUID("11111111-1111-1111-1111-111111111111")


@pytest.fixture(scope="module")
def bundle(tenant_id: uuid.UUID):
    return bootstrap_tenant(tenant_id)


@pytest.fixture
def base_input(tenant_id, bundle) -> AuditEmitInput:
    return AuditEmitInput(
        tenant_id=tenant_id,
        sequence_number=0,
        event_time=datetime(2026, 5, 10, 12, 0, 0, tzinfo=UTC),
        workflow_id=uuid.UUID("22222222-2222-2222-2222-222222222222"),
        agent_id=uuid.UUID("33333333-3333-3333-3333-333333333333"),
        action_type="tool_call",
        decision="allow",
        risk_score=Decimal("0.250"),
        snapshot_hash=b"\xaa" * 32,
        signing_private_key=bundle.signing_keypair.private_key,
        signing_key_id=bundle.signing_key_id,
        prev_self_hash=None,
    )


# ---------------------------------------------------------------------------
# AuditEmitInput validation
# ---------------------------------------------------------------------------


def test_input_rejects_non_uuid_tenant(bundle) -> None:
    with pytest.raises(AuditEmitterError, match="tenant_id"):
        AuditEmitInput(
            tenant_id="not-uuid",  # type: ignore[arg-type]
            sequence_number=0,
            event_time=datetime.now(tz=UTC),
            workflow_id=uuid.uuid4(),
            agent_id=uuid.uuid4(),
            action_type="x",
            decision="allow",
            risk_score=Decimal("0.5"),
            snapshot_hash=b"\x00" * 32,
            signing_private_key=bundle.signing_keypair.private_key,
            signing_key_id=bundle.signing_key_id,
        )


def test_input_rejects_negative_sequence(base_input: AuditEmitInput) -> None:
    with pytest.raises(AuditEmitterError, match="non-negative"):
        AuditEmitInput(
            tenant_id=base_input.tenant_id,
            sequence_number=-1,
            event_time=base_input.event_time,
            workflow_id=base_input.workflow_id,
            agent_id=base_input.agent_id,
            action_type=base_input.action_type,
            decision=base_input.decision,
            risk_score=base_input.risk_score,
            snapshot_hash=base_input.snapshot_hash,
            signing_private_key=base_input.signing_private_key,
            signing_key_id=base_input.signing_key_id,
        )


def test_input_rejects_empty_action_type(base_input: AuditEmitInput) -> None:
    with pytest.raises(AuditEmitterError, match="action_type"):
        AuditEmitInput(
            tenant_id=base_input.tenant_id,
            sequence_number=0,
            event_time=base_input.event_time,
            workflow_id=base_input.workflow_id,
            agent_id=base_input.agent_id,
            action_type="",
            decision=base_input.decision,
            risk_score=base_input.risk_score,
            snapshot_hash=base_input.snapshot_hash,
            signing_private_key=base_input.signing_private_key,
            signing_key_id=base_input.signing_key_id,
        )


def test_input_rejects_unknown_decision(base_input: AuditEmitInput) -> None:
    with pytest.raises(AuditEmitterError, match="decision must be one of"):
        AuditEmitInput(
            tenant_id=base_input.tenant_id,
            sequence_number=0,
            event_time=base_input.event_time,
            workflow_id=base_input.workflow_id,
            agent_id=base_input.agent_id,
            action_type="x",
            decision="approved-by-vibes",
            risk_score=base_input.risk_score,
            snapshot_hash=base_input.snapshot_hash,
            signing_private_key=base_input.signing_private_key,
            signing_key_id=base_input.signing_key_id,
        )


@pytest.mark.parametrize("decision", ["allow", "deny", "escalate", "pending"])
def test_input_accepts_valid_decisions(
    base_input: AuditEmitInput, decision: str
) -> None:
    AuditEmitInput(
        tenant_id=base_input.tenant_id,
        sequence_number=0,
        event_time=base_input.event_time,
        workflow_id=base_input.workflow_id,
        agent_id=base_input.agent_id,
        action_type="x",
        decision=decision,
        risk_score=base_input.risk_score,
        snapshot_hash=base_input.snapshot_hash,
        signing_private_key=base_input.signing_private_key,
        signing_key_id=base_input.signing_key_id,
    )  # must not raise


@pytest.mark.parametrize(
    "bad_score", [Decimal("-0.001"), Decimal("1.001"), Decimal("2")]
)
def test_input_rejects_out_of_range_risk(
    base_input: AuditEmitInput, bad_score: Decimal
) -> None:
    with pytest.raises(AuditEmitterError, match="risk_score must be in"):
        AuditEmitInput(
            tenant_id=base_input.tenant_id,
            sequence_number=0,
            event_time=base_input.event_time,
            workflow_id=base_input.workflow_id,
            agent_id=base_input.agent_id,
            action_type="x",
            decision="allow",
            risk_score=bad_score,
            snapshot_hash=base_input.snapshot_hash,
            signing_private_key=base_input.signing_private_key,
            signing_key_id=base_input.signing_key_id,
        )


def test_input_rejects_wrong_snapshot_hash_length(
    base_input: AuditEmitInput,
) -> None:
    with pytest.raises(AuditEmitterError, match="snapshot_hash must be 32"):
        AuditEmitInput(
            tenant_id=base_input.tenant_id,
            sequence_number=0,
            event_time=base_input.event_time,
            workflow_id=base_input.workflow_id,
            agent_id=base_input.agent_id,
            action_type="x",
            decision="allow",
            risk_score=Decimal("0.5"),
            snapshot_hash=b"\x00" * 16,
            signing_private_key=base_input.signing_private_key,
            signing_key_id=base_input.signing_key_id,
        )


def test_input_rejects_wrong_private_key_length(
    base_input: AuditEmitInput,
) -> None:
    with pytest.raises(
        AuditEmitterError, match="signing_private_key must be 32"
    ):
        AuditEmitInput(
            tenant_id=base_input.tenant_id,
            sequence_number=0,
            event_time=base_input.event_time,
            workflow_id=base_input.workflow_id,
            agent_id=base_input.agent_id,
            action_type="x",
            decision="allow",
            risk_score=Decimal("0.5"),
            snapshot_hash=base_input.snapshot_hash,
            signing_private_key=b"\x00" * 16,
            signing_key_id=base_input.signing_key_id,
        )


def test_input_rejects_bad_signing_key_id_prefix(
    base_input: AuditEmitInput,
) -> None:
    with pytest.raises(AuditEmitterError, match="must start with 'verixa-sig-'"):
        AuditEmitInput(
            tenant_id=base_input.tenant_id,
            sequence_number=0,
            event_time=base_input.event_time,
            workflow_id=base_input.workflow_id,
            agent_id=base_input.agent_id,
            action_type="x",
            decision="allow",
            risk_score=Decimal("0.5"),
            snapshot_hash=base_input.snapshot_hash,
            signing_private_key=base_input.signing_private_key,
            signing_key_id="some-other-prefix-abc",
        )


def test_input_genesis_with_prev_hash_rejected(
    base_input: AuditEmitInput,
) -> None:
    with pytest.raises(AuditEmitterError, match="genesis row"):
        AuditEmitInput(
            tenant_id=base_input.tenant_id,
            sequence_number=0,
            event_time=base_input.event_time,
            workflow_id=base_input.workflow_id,
            agent_id=base_input.agent_id,
            action_type="x",
            decision="allow",
            risk_score=Decimal("0.5"),
            snapshot_hash=base_input.snapshot_hash,
            signing_private_key=base_input.signing_private_key,
            signing_key_id=base_input.signing_key_id,
            prev_self_hash=b"\x00" * 32,
        )


def test_input_non_genesis_without_prev_hash_rejected(
    base_input: AuditEmitInput,
) -> None:
    with pytest.raises(AuditEmitterError, match="non-genesis"):
        AuditEmitInput(
            tenant_id=base_input.tenant_id,
            sequence_number=1,
            event_time=base_input.event_time,
            workflow_id=base_input.workflow_id,
            agent_id=base_input.agent_id,
            action_type="x",
            decision="allow",
            risk_score=Decimal("0.5"),
            snapshot_hash=base_input.snapshot_hash,
            signing_private_key=base_input.signing_private_key,
            signing_key_id=base_input.signing_key_id,
            prev_self_hash=None,
        )


def test_input_rejects_wrong_prev_hash_length(base_input: AuditEmitInput) -> None:
    with pytest.raises(AuditEmitterError, match="prev_self_hash must be 32"):
        AuditEmitInput(
            tenant_id=base_input.tenant_id,
            sequence_number=1,
            event_time=base_input.event_time,
            workflow_id=base_input.workflow_id,
            agent_id=base_input.agent_id,
            action_type="x",
            decision="allow",
            risk_score=Decimal("0.5"),
            snapshot_hash=base_input.snapshot_hash,
            signing_private_key=base_input.signing_private_key,
            signing_key_id=base_input.signing_key_id,
            prev_self_hash=b"\x00" * 16,
        )


# ---------------------------------------------------------------------------
# emit_audit_record — happy path
# ---------------------------------------------------------------------------


def test_emit_genesis_returns_well_formed_record(
    base_input: AuditEmitInput, bundle, tenant_id: uuid.UUID
) -> None:
    rec = emit_audit_record(base_input)
    assert isinstance(rec, AuditEmitRecord)
    assert rec.tenant_id == tenant_id
    assert rec.sequence_number == 0
    assert len(rec.hash_chain_prev) == 32
    assert len(rec.hash_chain_self) == 32
    assert len(rec.signature) == 64
    assert rec.signing_key_id == bundle.signing_key_id


def test_emit_genesis_uses_correct_genesis_prev(
    base_input: AuditEmitInput, tenant_id: uuid.UUID
) -> None:
    rec = emit_audit_record(base_input)
    assert rec.hash_chain_prev == compute_genesis_prev(tenant_id)


def test_emit_self_hash_matches_canonical(base_input: AuditEmitInput) -> None:
    rec = emit_audit_record(base_input)
    expected = compute_self_hash(
        HashChainEntry(
            sequence_number=base_input.sequence_number,
            event_time=base_input.event_time,
            workflow_id=base_input.workflow_id,
            agent_id=base_input.agent_id,
            action_type=base_input.action_type,
            decision=base_input.decision,
            risk_score=base_input.risk_score,
            snapshot_hash=base_input.snapshot_hash,
            hash_chain_prev=rec.hash_chain_prev,
        )
    )
    assert rec.hash_chain_self == expected


def test_emit_signature_verifies_under_bundle_public_key(
    base_input: AuditEmitInput, bundle
) -> None:
    rec = emit_audit_record(base_input)
    # Must not raise
    ed25519_verify(bundle.public_key, rec.hash_chain_self, rec.signature)


def test_emit_is_deterministic_given_identical_inputs(
    base_input: AuditEmitInput,
) -> None:
    a = emit_audit_record(base_input)
    b = emit_audit_record(base_input)
    assert a == b


def test_emit_non_genesis_uses_supplied_prev(
    base_input: AuditEmitInput, bundle, tenant_id: uuid.UUID
) -> None:
    # Emit genesis first
    genesis = emit_audit_record(base_input)
    # Now seq 1 with the genesis self-hash as prev
    seq1_input = AuditEmitInput(
        tenant_id=tenant_id,
        sequence_number=1,
        event_time=base_input.event_time,
        workflow_id=base_input.workflow_id,
        agent_id=base_input.agent_id,
        action_type=base_input.action_type,
        decision="deny",
        risk_score=Decimal("0.900"),
        snapshot_hash=b"\xbb" * 32,
        signing_private_key=bundle.signing_keypair.private_key,
        signing_key_id=bundle.signing_key_id,
        prev_self_hash=genesis.hash_chain_self,
    )
    rec = emit_audit_record(seq1_input)
    assert rec.sequence_number == 1
    assert rec.hash_chain_prev == genesis.hash_chain_self
    # Signature must verify too
    ed25519_verify(bundle.public_key, rec.hash_chain_self, rec.signature)


def test_emit_chain_of_three_links_correctly(
    base_input: AuditEmitInput, bundle, tenant_id: uuid.UUID
) -> None:
    """Three consecutive emits must form a valid chain."""
    chain: list[AuditEmitRecord] = []
    prev: bytes | None = None
    for seq in range(3):
        emit_in = AuditEmitInput(
            tenant_id=tenant_id,
            sequence_number=seq,
            event_time=base_input.event_time,
            workflow_id=base_input.workflow_id,
            agent_id=base_input.agent_id,
            action_type=base_input.action_type,
            decision=base_input.decision,
            risk_score=Decimal("0.5"),
            snapshot_hash=bytes([seq]) * 32,
            signing_private_key=bundle.signing_keypair.private_key,
            signing_key_id=bundle.signing_key_id,
            prev_self_hash=prev,
        )
        rec = emit_audit_record(emit_in)
        chain.append(rec)
        prev = rec.hash_chain_self

    assert chain[0].hash_chain_prev == compute_genesis_prev(tenant_id)
    assert chain[1].hash_chain_prev == chain[0].hash_chain_self
    assert chain[2].hash_chain_prev == chain[1].hash_chain_self
    for rec in chain:
        ed25519_verify(bundle.public_key, rec.hash_chain_self, rec.signature)


# ---------------------------------------------------------------------------
# Public-API surface
# ---------------------------------------------------------------------------


def test_audit_package_reexports() -> None:
    from verixa_runtime import audit

    for name in (
        "AuditEmitInput",
        "AuditEmitRecord",
        "AuditEmitterError",
        "emit_audit_record",
        "AuditVerificationError",
        "PersistedAuditEntry",
        "verify_audit_chain",
    ):
        assert hasattr(audit, name), f"audit package missing {name}"
