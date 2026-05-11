"""pytest suite for CP-5.4 — key-rotation continuity.

The audit ledger doc (docs/09_data_model A7 5.3) specifies that signing
keys are versioned. An audit chain can have entries signed by Key A
(rows 0..N) followed by entries signed by Key B (rows N+1..) — as long
as each entry's signature verifies under the public key for ITS OWN
signing_key_id.

These tests prove that:

  1. A two-key chain (rotation mid-stream) verifies end-to-end.
  2. A three-key chain (two rotations) verifies end-to-end.
  3. Tampering with a post-rotation signature is detected.
  4. Swapping a post-rotation entry's public_key with the pre-rotation
     key (a misattribution attack) is detected.
  5. The hash chain is unbroken across rotation (rotation does not
     reset the hash chain — that would be a chain-split bug).

These tests are intentionally test-code-only; CP-5.1 / 5.2 / 5.3 already
implement the production code that supports rotation. CP-5.4's
contribution is the proof that it works.
"""

from __future__ import annotations

import uuid
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
from verixa_runtime.crypto.key_bootstrap import (
    TenantKeyBundle,
    bootstrap_tenant,
)


# ---------------------------------------------------------------------------
# Fixtures + helpers
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def tenant_id() -> uuid.UUID:
    return uuid.UUID("dddddddd-dddd-dddd-dddd-dddddddddddd")


@pytest.fixture(scope="module")
def bundle_a(tenant_id: uuid.UUID) -> TenantKeyBundle:
    return bootstrap_tenant(tenant_id)


@pytest.fixture(scope="module")
def bundle_b(tenant_id: uuid.UUID) -> TenantKeyBundle:
    return bootstrap_tenant(tenant_id)


@pytest.fixture(scope="module")
def bundle_c(tenant_id: uuid.UUID) -> TenantKeyBundle:
    return bootstrap_tenant(tenant_id)


def _emit_with_bundle(
    *,
    tenant_id: uuid.UUID,
    bundle: TenantKeyBundle,
    sequence_number: int,
    prev_self_hash: bytes | None,
    snapshot_seed: int,
    base_time: datetime,
) -> AuditEmitRecord:
    """Helper: emit a single record under a specific bundle."""
    emit_in = AuditEmitInput(
        tenant_id=tenant_id,
        sequence_number=sequence_number,
        event_time=base_time,
        workflow_id=uuid.UUID("22222222-2222-2222-2222-222222222222"),
        agent_id=uuid.UUID("33333333-3333-3333-3333-333333333333"),
        action_type="tool_call",
        decision="allow",
        risk_score=Decimal("0.250"),
        snapshot_hash=bytes([snapshot_seed]) * 32,
        signing_private_key=bundle.signing_keypair.private_key,
        signing_key_id=bundle.signing_key_id,
        prev_self_hash=prev_self_hash,
    )
    return emit_audit_record(emit_in)


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


def _build_two_key_chain(
    tenant_id: uuid.UUID,
    bundle_a: TenantKeyBundle,
    bundle_b: TenantKeyBundle,
    *,
    pre_rotation_count: int,
    post_rotation_count: int,
) -> list[PersistedAuditEntry]:
    """Emit `pre_rotation_count` entries under bundle_a then
    `post_rotation_count` entries under bundle_b. Hash chain unbroken."""
    persisted: list[PersistedAuditEntry] = []
    base_time = datetime(2026, 5, 10, 12, 0, 0, tzinfo=timezone.utc)
    prev: bytes | None = None
    seq = 0

    # Pre-rotation: signed by Key A
    for _ in range(pre_rotation_count):
        rec = _emit_with_bundle(
            tenant_id=tenant_id,
            bundle=bundle_a,
            sequence_number=seq,
            prev_self_hash=prev,
            snapshot_seed=seq,
            base_time=base_time,
        )
        persisted.append(_to_persisted(rec, bundle_a.public_key))
        prev = rec.hash_chain_self
        seq += 1

    # Post-rotation: signed by Key B
    for _ in range(post_rotation_count):
        rec = _emit_with_bundle(
            tenant_id=tenant_id,
            bundle=bundle_b,
            sequence_number=seq,
            prev_self_hash=prev,
            snapshot_seed=seq,
            base_time=base_time,
        )
        persisted.append(_to_persisted(rec, bundle_b.public_key))
        prev = rec.hash_chain_self
        seq += 1

    return persisted


# ---------------------------------------------------------------------------
# Happy paths — rotation works
# ---------------------------------------------------------------------------


def test_two_key_chain_verifies_end_to_end(
    tenant_id: uuid.UUID,
    bundle_a: TenantKeyBundle,
    bundle_b: TenantKeyBundle,
) -> None:
    chain = _build_two_key_chain(
        tenant_id, bundle_a, bundle_b,
        pre_rotation_count=3, post_rotation_count=3,
    )
    verify_audit_chain(chain, tenant_id)  # must not raise


def test_two_key_chain_carries_two_distinct_signing_key_ids(
    tenant_id: uuid.UUID,
    bundle_a: TenantKeyBundle,
    bundle_b: TenantKeyBundle,
) -> None:
    chain = _build_two_key_chain(
        tenant_id, bundle_a, bundle_b,
        pre_rotation_count=2, post_rotation_count=2,
    )
    sig_ids = {entry.signing_key_id for entry in chain}
    assert sig_ids == {bundle_a.signing_key_id, bundle_b.signing_key_id}
    # Pre-rotation entries claim Key A; post-rotation claim Key B
    assert chain[0].signing_key_id == bundle_a.signing_key_id
    assert chain[1].signing_key_id == bundle_a.signing_key_id
    assert chain[2].signing_key_id == bundle_b.signing_key_id
    assert chain[3].signing_key_id == bundle_b.signing_key_id


def test_three_key_chain_verifies(
    tenant_id: uuid.UUID,
    bundle_a: TenantKeyBundle,
    bundle_b: TenantKeyBundle,
    bundle_c: TenantKeyBundle,
) -> None:
    """Two rotations: Key A -> Key B -> Key C. Hash chain unbroken."""
    persisted: list[PersistedAuditEntry] = []
    base_time = datetime(2026, 5, 10, 12, 0, 0, tzinfo=timezone.utc)
    prev: bytes | None = None
    seq = 0

    for bundle in (bundle_a, bundle_b, bundle_c):
        for _ in range(2):
            rec = _emit_with_bundle(
                tenant_id=tenant_id,
                bundle=bundle,
                sequence_number=seq,
                prev_self_hash=prev,
                snapshot_seed=seq,
                base_time=base_time,
            )
            persisted.append(_to_persisted(rec, bundle.public_key))
            prev = rec.hash_chain_self
            seq += 1

    verify_audit_chain(persisted, tenant_id)
    sig_ids_in_order = [p.signing_key_id for p in persisted]
    assert sig_ids_in_order == [
        bundle_a.signing_key_id,
        bundle_a.signing_key_id,
        bundle_b.signing_key_id,
        bundle_b.signing_key_id,
        bundle_c.signing_key_id,
        bundle_c.signing_key_id,
    ]


def test_hash_chain_unbroken_across_rotation(
    tenant_id: uuid.UUID,
    bundle_a: TenantKeyBundle,
    bundle_b: TenantKeyBundle,
) -> None:
    """The rotation must NOT reset the hash chain. Entry at the rotation
    boundary's hash_chain_prev is the previous entry's hash_chain_self."""
    chain = _build_two_key_chain(
        tenant_id, bundle_a, bundle_b,
        pre_rotation_count=3, post_rotation_count=2,
    )
    # Boundary entry: index 3 (first under Key B); its prev must be
    # index 2's self.
    assert chain[3].hash_chain_prev == chain[2].hash_chain_self
    # And its public_key must be Key B's, while index 2's was Key A's.
    assert chain[2].public_key == bundle_a.public_key
    assert chain[3].public_key == bundle_b.public_key


# ---------------------------------------------------------------------------
# Failure paths — rotation does not weaken the verifier
# ---------------------------------------------------------------------------


def test_post_rotation_signature_tamper_detected(
    tenant_id: uuid.UUID,
    bundle_a: TenantKeyBundle,
    bundle_b: TenantKeyBundle,
) -> None:
    chain = _build_two_key_chain(
        tenant_id, bundle_a, bundle_b,
        pre_rotation_count=2, post_rotation_count=2,
    )
    # Tamper a single bit of the post-rotation entry's signature
    bad_sig = bytearray(chain[3].signature)
    bad_sig[0] ^= 0x01
    chain[3] = replace(chain[3], signature=bytes(bad_sig))
    with pytest.raises(
        AuditVerificationError, match="signature verification failed"
    ):
        verify_audit_chain(chain, tenant_id)


def test_misattribution_attack_detected(
    tenant_id: uuid.UUID,
    bundle_a: TenantKeyBundle,
    bundle_b: TenantKeyBundle,
) -> None:
    """Misattribution: an attacker swaps the public_key on a post-rotation
    entry to claim Key A signed it. The signature won't verify under the
    wrong public key."""
    chain = _build_two_key_chain(
        tenant_id, bundle_a, bundle_b,
        pre_rotation_count=2, post_rotation_count=2,
    )
    # Entry 2 was signed by Key B but we relabel it as Key A.
    chain[2] = replace(
        chain[2],
        public_key=bundle_a.public_key,
        signing_key_id=bundle_a.signing_key_id,
    )
    with pytest.raises(
        AuditVerificationError, match="signature verification failed"
    ):
        verify_audit_chain(chain, tenant_id)


def test_post_rotation_self_hash_tamper_detected(
    tenant_id: uuid.UUID,
    bundle_a: TenantKeyBundle,
    bundle_b: TenantKeyBundle,
) -> None:
    chain = _build_two_key_chain(
        tenant_id, bundle_a, bundle_b,
        pre_rotation_count=2, post_rotation_count=2,
    )
    # Flip a content field on a post-rotation entry without recomputing
    chain[2] = replace(chain[2], decision="deny")
    with pytest.raises(AuditVerificationError, match="self-hash mismatch"):
        verify_audit_chain(chain, tenant_id)


def test_chain_split_at_rotation_boundary_detected(
    tenant_id: uuid.UUID,
    bundle_a: TenantKeyBundle,
    bundle_b: TenantKeyBundle,
) -> None:
    """If an attacker resets the hash chain at the rotation boundary, the
    verifier must catch it — rotation does NOT excuse a chain split."""
    chain = _build_two_key_chain(
        tenant_id, bundle_a, bundle_b,
        pre_rotation_count=2, post_rotation_count=2,
    )
    # Replace post-rotation prev with a fabricated value (chain split)
    chain[2] = replace(chain[2], hash_chain_prev=b"\xee" * 32)
    with pytest.raises(AuditVerificationError, match="prev-hash mismatch"):
        verify_audit_chain(chain, tenant_id)


# ---------------------------------------------------------------------------
# Bigger chain — stress the rotation invariants over many entries
# ---------------------------------------------------------------------------


def test_large_two_key_chain_verifies(
    tenant_id: uuid.UUID,
    bundle_a: TenantKeyBundle,
    bundle_b: TenantKeyBundle,
) -> None:
    chain = _build_two_key_chain(
        tenant_id, bundle_a, bundle_b,
        pre_rotation_count=15, post_rotation_count=15,
    )
    verify_audit_chain(chain, tenant_id)
    assert len(chain) == 30
