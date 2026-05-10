"""pytest suite for verixa_runtime.audit.verifier.

Builds chains via the emitter (CP-5.1) and walks them via the verifier
(CP-5.2). Covers every failure path so the verifier hits 100% coverage.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from verixa_runtime.audit.emitter import (
    AuditEmitInput,
    AuditEmitRecord,
    emit_audit_record,
)
from verixa_runtime.audit.verifier import (
    AuditVerificationError,
    PersistedAuditEntry,
    verify_audit_chain,
)
from verixa_runtime.crypto.key_bootstrap import TenantKeyBundle, bootstrap_tenant


# ---------------------------------------------------------------------------
# Fixtures + helpers
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def tenant_id() -> uuid.UUID:
    return uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")


@pytest.fixture(scope="module")
def bundle(tenant_id: uuid.UUID) -> TenantKeyBundle:
    return bootstrap_tenant(tenant_id)


def _emit_chain(
    tenant_id: uuid.UUID, bundle: TenantKeyBundle, length: int
) -> list[AuditEmitRecord]:
    """Helper: emit a length-N valid chain."""
    records: list[AuditEmitRecord] = []
    prev: bytes | None = None
    base_time = datetime(2026, 5, 10, 12, 0, 0, tzinfo=timezone.utc)
    for seq in range(length):
        emit_in = AuditEmitInput(
            tenant_id=tenant_id,
            sequence_number=seq,
            event_time=base_time,
            workflow_id=uuid.UUID("22222222-2222-2222-2222-222222222222"),
            agent_id=uuid.UUID("33333333-3333-3333-3333-333333333333"),
            action_type="tool_call",
            decision="allow",
            risk_score=Decimal("0.250"),
            snapshot_hash=bytes([seq]) * 32,
            signing_private_key=bundle.signing_keypair.private_key,
            signing_key_id=bundle.signing_key_id,
            prev_self_hash=prev,
        )
        rec = emit_audit_record(emit_in)
        records.append(rec)
        prev = rec.hash_chain_self
    return records


def _to_persisted(
    rec: AuditEmitRecord, public_key: bytes
) -> PersistedAuditEntry:
    return PersistedAuditEntry(
        tenant_id=rec.tenant_id,
        sequence_number=rec.sequence_number,
        event_time=rec.event_time,
        workflow_id=rec.workflow_id,
        agent_id=rec.agent_id,
        action_type=rec.action_type,
        decision=rec.decision,
        risk_score=rec.risk_score,
        snapshot_hash=rec.snapshot_hash,
        hash_chain_prev=rec.hash_chain_prev,
        hash_chain_self=rec.hash_chain_self,
        signature=rec.signature,
        signing_key_id=rec.signing_key_id,
        public_key=public_key,
    )


@pytest.fixture
def chain_factory(
    tenant_id: uuid.UUID, bundle: TenantKeyBundle
) -> Callable[[int], list[PersistedAuditEntry]]:
    def _factory(length: int) -> list[PersistedAuditEntry]:
        return [
            _to_persisted(rec, bundle.public_key)
            for rec in _emit_chain(tenant_id, bundle, length)
        ]

    return _factory


# ---------------------------------------------------------------------------
# Happy paths
# ---------------------------------------------------------------------------


def test_verify_single_entry_chain_passes(
    chain_factory: Callable[[int], list[PersistedAuditEntry]],
    tenant_id: uuid.UUID,
) -> None:
    chain = chain_factory(1)
    verify_audit_chain(chain, tenant_id)  # must not raise


def test_verify_three_entry_chain_passes(
    chain_factory: Callable[[int], list[PersistedAuditEntry]],
    tenant_id: uuid.UUID,
) -> None:
    chain = chain_factory(3)
    verify_audit_chain(chain, tenant_id)


def test_verify_long_chain_passes(
    chain_factory: Callable[[int], list[PersistedAuditEntry]],
    tenant_id: uuid.UUID,
) -> None:
    chain = chain_factory(20)
    verify_audit_chain(chain, tenant_id)


# ---------------------------------------------------------------------------
# Failure paths
# ---------------------------------------------------------------------------


def test_verify_rejects_non_uuid_tenant(
    chain_factory: Callable[[int], list[PersistedAuditEntry]],
) -> None:
    chain = chain_factory(1)
    with pytest.raises(AuditVerificationError, match="tenant_id must be uuid"):
        verify_audit_chain(chain, "not-uuid")  # type: ignore[arg-type]


def test_verify_rejects_empty_chain(tenant_id: uuid.UUID) -> None:
    with pytest.raises(AuditVerificationError, match="empty"):
        verify_audit_chain([], tenant_id)


def test_verify_rejects_tenant_mismatch(
    chain_factory: Callable[[int], list[PersistedAuditEntry]],
    tenant_id: uuid.UUID,
) -> None:
    chain = chain_factory(1)
    other_tenant = uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
    with pytest.raises(AuditVerificationError, match="tenant mismatch"):
        verify_audit_chain(chain, other_tenant)


def test_verify_rejects_tenant_mismatch_within_chain(
    chain_factory: Callable[[int], list[PersistedAuditEntry]],
    tenant_id: uuid.UUID,
) -> None:
    chain = chain_factory(2)
    # Force an entry to claim a wrong tenant
    chain[1] = replace(
        chain[1], tenant_id=uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
    )
    with pytest.raises(AuditVerificationError, match="tenant mismatch"):
        verify_audit_chain(chain, tenant_id)


def test_verify_detects_sequence_gap(
    chain_factory: Callable[[int], list[PersistedAuditEntry]],
    tenant_id: uuid.UUID,
) -> None:
    chain = chain_factory(2)
    # Bump seq on entry 1 to a wrong value
    chain[1] = replace(chain[1], sequence_number=99)
    with pytest.raises(AuditVerificationError, match="sequence gap"):
        verify_audit_chain(chain, tenant_id)


def test_verify_detects_first_entry_not_seq_zero(
    chain_factory: Callable[[int], list[PersistedAuditEntry]],
    tenant_id: uuid.UUID,
) -> None:
    chain = chain_factory(1)
    chain[0] = replace(chain[0], sequence_number=5)
    with pytest.raises(AuditVerificationError, match="sequence gap"):
        verify_audit_chain(chain, tenant_id)


def test_verify_detects_wrong_genesis_prev(
    chain_factory: Callable[[int], list[PersistedAuditEntry]],
    tenant_id: uuid.UUID,
) -> None:
    chain = chain_factory(1)
    chain[0] = replace(chain[0], hash_chain_prev=b"\xff" * 32)
    with pytest.raises(AuditVerificationError, match="prev-hash mismatch"):
        verify_audit_chain(chain, tenant_id)


def test_verify_detects_chain_split_in_middle(
    chain_factory: Callable[[int], list[PersistedAuditEntry]],
    tenant_id: uuid.UUID,
) -> None:
    chain = chain_factory(3)
    # Tamper entry 2's prev so it no longer chains from entry 1
    chain[2] = replace(chain[2], hash_chain_prev=b"\xaa" * 32)
    with pytest.raises(AuditVerificationError, match="prev-hash mismatch"):
        verify_audit_chain(chain, tenant_id)


def test_verify_detects_self_hash_tamper(
    chain_factory: Callable[[int], list[PersistedAuditEntry]],
    tenant_id: uuid.UUID,
) -> None:
    chain = chain_factory(2)
    # Flip a content field on entry 1 without recomputing self-hash
    chain[1] = replace(chain[1], decision="deny")
    with pytest.raises(AuditVerificationError, match="self-hash mismatch"):
        verify_audit_chain(chain, tenant_id)


def test_verify_detects_signature_tamper(
    chain_factory: Callable[[int], list[PersistedAuditEntry]],
    tenant_id: uuid.UUID,
) -> None:
    chain = chain_factory(1)
    bad_sig = bytearray(chain[0].signature)
    bad_sig[0] ^= 0x01
    chain[0] = replace(chain[0], signature=bytes(bad_sig))
    with pytest.raises(
        AuditVerificationError, match="signature verification failed"
    ):
        verify_audit_chain(chain, tenant_id)


def test_verify_detects_wrong_public_key(
    chain_factory: Callable[[int], list[PersistedAuditEntry]],
    tenant_id: uuid.UUID,
) -> None:
    chain = chain_factory(1)
    other_bundle = bootstrap_tenant(tenant_id)
    chain[0] = replace(chain[0], public_key=other_bundle.public_key)
    with pytest.raises(
        AuditVerificationError, match="signature verification failed"
    ):
        verify_audit_chain(chain, tenant_id)
