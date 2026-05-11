"""pytest suite for verixa_runtime.replay.snapshotter (CP-12.4).

Covers Snapshotter + Reconstructor round-trip + each exception
branch on the AuditIndex, plus the snapshotter's choice to call
store.put before index.put (a partial-failure invariant).
"""

from __future__ import annotations

import uuid

import pytest
from verixa_runtime.crypto.aes_gcm import AesGcmKey, generate_key
from verixa_runtime.replay import (
    AuditIndexConflict,
    AuditIndexMiss,
    BundleNotFound,
    InMemoryAuditIndex,
    InMemoryBundleStore,
    PolicyEvaluationRecord,
    Reconstructor,
    SnapshotInputs,
    Snapshotter,
    TriadReviewRecord,
)

_TENANT_ID = uuid.UUID("12121212-1212-1212-1212-121212121212")
_AUDIT_ID = uuid.UUID("34343434-3434-3434-3434-343434343434")
_FIXED_TS = 1_700_000_000_000_000_000


def _inputs(**overrides) -> SnapshotInputs:  # type: ignore[no-untyped-def]
    defaults: dict[str, object] = {
        "audit_id": _AUDIT_ID,
        "tenant_id": _TENANT_ID,
        "decision": "allow",
        "risk_score": 0.1,
        "request_envelope": {"k": "v"},
    }
    defaults.update(overrides)
    return SnapshotInputs(**defaults)  # type: ignore[arg-type]


def _resolver_for(
    keys: dict[uuid.UUID, AesGcmKey],
):
    def _resolve(tenant_id: uuid.UUID) -> AesGcmKey:
        return keys[tenant_id]

    return _resolve


# ---------------------------------------------------------------------------
# Snapshotter happy paths
# ---------------------------------------------------------------------------


async def test_snapshot_minimal_round_trips_via_reconstructor() -> None:
    key = generate_key()
    store = InMemoryBundleStore()
    index = InMemoryAuditIndex()
    resolver = _resolver_for({_TENANT_ID: key})
    snapshotter = Snapshotter(
        store=store, index=index, key_resolver=resolver
    )
    reconstructor = Reconstructor(
        store=store, index=index, key_resolver=resolver
    )
    result = await snapshotter.snapshot(_inputs(), timestamp_unix_ns=_FIXED_TS)
    assert result.audit_id == _AUDIT_ID
    assert len(result.storage_key) == 64
    # Pull it back.
    recovered = await reconstructor.reconstruct(_AUDIT_ID)
    assert recovered.audit_id == _AUDIT_ID
    assert recovered.tenant_id == _TENANT_ID
    assert recovered.decision == "allow"
    assert recovered.risk_score == pytest.approx(0.1)
    assert recovered.timestamp_unix_ns == _FIXED_TS
    assert recovered.request_envelope == {"k": "v"}


async def test_snapshot_full_decision_context_round_trips() -> None:
    """Snapshot with retrieved_documents + tool_io + policy_evaluations
    + triad_review; round-trip must preserve every field."""
    key = generate_key()
    store = InMemoryBundleStore()
    index = InMemoryAuditIndex()
    resolver = _resolver_for({_TENANT_ID: key})
    snapshotter = Snapshotter(
        store=store, index=index, key_resolver=resolver
    )
    reconstructor = Reconstructor(
        store=store, index=index, key_resolver=resolver
    )

    triad = TriadReviewRecord(
        consensus_kind="majority",
        agreed_decision="allow",
        verdicts=(
            ("reviewer_a", "allow", 0.9, "ok"),
            ("reviewer_b", "allow", 0.8, "fine"),
            ("reviewer_c", "deny", 0.7, "nope"),
        ),
        commitments=(
            ("reviewer_a", "a" * 64),
            ("reviewer_b", "b" * 64),
            ("reviewer_c", "c" * 64),
        ),
    )
    policy_evals = (
        PolicyEvaluationRecord(
            package="verixa.fs.transfer_limit",
            decision="pass",
            reason="under limit",
        ),
    )
    inputs = _inputs(
        retrieved_documents=(("doc_001", "f" * 64),),
        tool_io=({"call": "x", "response": "y"},),
        policy_evaluations=policy_evals,
        triad_review=triad,
    )
    await snapshotter.snapshot(inputs, timestamp_unix_ns=_FIXED_TS)
    recovered = await reconstructor.reconstruct(_AUDIT_ID)
    assert recovered.retrieved_documents == (("doc_001", "f" * 64),)
    assert recovered.tool_io == ({"call": "x", "response": "y"},)
    assert len(recovered.policy_evaluations) == 1
    assert recovered.policy_evaluations[0].package == (
        "verixa.fs.transfer_limit"
    )
    assert recovered.triad_review is not None
    assert recovered.triad_review.consensus_kind == "majority"


async def test_snapshot_uses_time_time_ns_when_timestamp_none() -> None:
    """No explicit timestamp -> snapshotter calls time.time_ns().

    We can't assert an exact value, but we can assert it's within a
    reasonable window of "now"."""
    import time as time_mod

    key = generate_key()
    store = InMemoryBundleStore()
    index = InMemoryAuditIndex()
    resolver = _resolver_for({_TENANT_ID: key})
    snapshotter = Snapshotter(
        store=store, index=index, key_resolver=resolver
    )
    reconstructor = Reconstructor(
        store=store, index=index, key_resolver=resolver
    )
    before = time_mod.time_ns()
    await snapshotter.snapshot(_inputs())  # timestamp_unix_ns=None branch
    after = time_mod.time_ns()
    recovered = await reconstructor.reconstruct(_AUDIT_ID)
    assert before <= recovered.timestamp_unix_ns <= after


async def test_snapshot_indexes_audit_id_to_storage_key() -> None:
    """After snapshot, index.get(audit_id) returns the same key the
    snapshotter put in the store."""
    key = generate_key()
    store = InMemoryBundleStore()
    index = InMemoryAuditIndex()
    resolver = _resolver_for({_TENANT_ID: key})
    snapshotter = Snapshotter(
        store=store, index=index, key_resolver=resolver
    )
    result = await snapshotter.snapshot(_inputs(), timestamp_unix_ns=_FIXED_TS)
    looked_up = await index.get(_AUDIT_ID)
    assert looked_up == result.storage_key
    # And the store has it.
    assert await store.exists(result.storage_key) is True


# ---------------------------------------------------------------------------
# Reconstructor failure modes
# ---------------------------------------------------------------------------


async def test_reconstruct_unknown_audit_id_raises_audit_index_miss() -> None:
    key = generate_key()
    store = InMemoryBundleStore()
    index = InMemoryAuditIndex()
    resolver = _resolver_for({_TENANT_ID: key})
    reconstructor = Reconstructor(
        store=store, index=index, key_resolver=resolver
    )
    with pytest.raises(AuditIndexMiss):
        await reconstructor.reconstruct(uuid.uuid4())


async def test_reconstruct_after_store_delete_raises_bundle_not_found() -> None:
    """Index points at a key the store no longer has -- physical
    deletion happened (or someone GC'd the orphan path).  The
    reconstructor surfaces BundleNotFound."""
    key = generate_key()
    store = InMemoryBundleStore()
    index = InMemoryAuditIndex()
    resolver = _resolver_for({_TENANT_ID: key})
    snapshotter = Snapshotter(
        store=store, index=index, key_resolver=resolver
    )
    reconstructor = Reconstructor(
        store=store, index=index, key_resolver=resolver
    )
    result = await snapshotter.snapshot(_inputs(), timestamp_unix_ns=_FIXED_TS)
    # Now physically delete the ciphertext.
    await store.delete(result.storage_key)
    with pytest.raises(BundleNotFound):
        await reconstructor.reconstruct(_AUDIT_ID)


# ---------------------------------------------------------------------------
# AuditIndex semantics
# ---------------------------------------------------------------------------


async def test_audit_index_idempotent_re_put_with_same_storage_key() -> None:
    index = InMemoryAuditIndex()
    await index.put(_AUDIT_ID, "0" * 64)
    await index.put(_AUDIT_ID, "0" * 64)  # same key, no-op
    assert await index.get(_AUDIT_ID) == "0" * 64


async def test_audit_index_conflict_on_different_storage_key() -> None:
    """Same audit_id, different storage_key -> AuditIndexConflict.

    Means the same decision was snapshotted twice with different
    content; that's a programmer error worth raising."""
    index = InMemoryAuditIndex()
    await index.put(_AUDIT_ID, "0" * 64)
    with pytest.raises(AuditIndexConflict, match="audit_id"):
        await index.put(_AUDIT_ID, "1" * 64)


async def test_audit_index_get_unknown_raises_audit_index_miss() -> None:
    index = InMemoryAuditIndex()
    with pytest.raises(AuditIndexMiss, match="audit_id"):
        await index.get(uuid.uuid4())


# ---------------------------------------------------------------------------
# Multi-tenant isolation
# ---------------------------------------------------------------------------


async def test_reconstruct_uses_correct_tenant_key() -> None:
    """Two tenants snapshot at the same time; each can reconstruct
    its own bundle but not the other's (other's key fails auth)."""
    from verixa_runtime.crypto.aes_gcm import AesGcmDecryptionError

    tenant_a = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
    tenant_b = uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
    audit_a = uuid.UUID("11111111-1111-1111-1111-111111111111")
    audit_b = uuid.UUID("22222222-2222-2222-2222-222222222222")
    key_a = generate_key()
    key_b = generate_key()
    store = InMemoryBundleStore()
    index = InMemoryAuditIndex()
    resolver_correct = _resolver_for({tenant_a: key_a, tenant_b: key_b})

    snap = Snapshotter(
        store=store, index=index, key_resolver=resolver_correct
    )
    await snap.snapshot(
        _inputs(audit_id=audit_a, tenant_id=tenant_a),
        timestamp_unix_ns=_FIXED_TS,
    )
    await snap.snapshot(
        _inputs(audit_id=audit_b, tenant_id=tenant_b),
        timestamp_unix_ns=_FIXED_TS,
    )

    # Correct resolver: both reconstruct fine.
    rec_correct = Reconstructor(
        store=store, index=index, key_resolver=resolver_correct
    )
    assert (await rec_correct.reconstruct(audit_a)).tenant_id == tenant_a
    assert (await rec_correct.reconstruct(audit_b)).tenant_id == tenant_b

    # WRONG resolver: hands back key_b for tenant_a.
    resolver_swapped = _resolver_for({tenant_a: key_b, tenant_b: key_a})
    rec_wrong = Reconstructor(
        store=store, index=index, key_resolver=resolver_swapped
    )
    with pytest.raises(AesGcmDecryptionError):
        await rec_wrong.reconstruct(audit_a)
