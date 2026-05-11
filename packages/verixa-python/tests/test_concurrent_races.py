"""CP-38 negative test 8/10: race-condition + concurrent-write tests.

Anchored to NEGATIVE_TEST_PLAN gap "Race conditions / concurrent writes
to audit ledger".

The InMemoryAuditLedger and InMemoryAuditIndex both use `asyncio.Lock()`
to serialise concurrent access. These tests stress that promise with
asyncio.gather() hammering N parallel writes + reads, asserting:

  - Every appended entry is visible in the post-hammer query
  - No appended entry is lost or duplicated
  - Concurrent appends to the same key raise the typed conflict error,
    not a silent overwrite
  - Concurrent reads return consistent snapshots (no torn reads)

Attack model: in a multi-tenant Phase-1 production deployment, many
agents will call /govern concurrently from different processes. The
in-memory infrastructure must hold up under this. Phase 1 replaces
InMemory* with Postgres* / MinIO* implementations that have their
own concurrency stories; the Protocol contract MUST hold across both.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime, timedelta

import pytest

from verixa_control_plane.audit import (
    AuditLedgerEntry,
    InMemoryAuditLedger,
)
from verixa_runtime.crypto.aes_gcm import AesGcmKey, generate_key
from verixa_runtime.replay import (
    AuditIndexConflict,
    InMemoryAuditIndex,
    InMemoryBundleStore,
    Snapshotter,
)
from verixa_runtime.replay.snapshotter import SnapshotInputs


# ---------------------------------------------------------------------------
# InMemoryAuditLedger concurrent appends
# ---------------------------------------------------------------------------


def _make_entry(
    *, workflow_id: uuid.UUID, audit_id: uuid.UUID, ts: datetime
) -> AuditLedgerEntry:
    return AuditLedgerEntry(
        audit_id=audit_id,
        workflow_id=workflow_id,
        tenant_id=uuid.uuid4(),
        decision="allow",
        risk_score=0.1,
        risk_classification="low",
        triad_invoked=False,
        timestamp=ts,
    )


@pytest.mark.asyncio
async def test_audit_ledger_concurrent_100_appends_all_land() -> None:
    """100 concurrent append() calls. After gather completes, query MUST
    return all 100 entries. Zero dropped, zero duplicated."""
    ledger = InMemoryAuditLedger()
    wf = uuid.uuid4()
    base_ts = datetime.now(UTC)
    entries = [
        _make_entry(
            workflow_id=wf,
            audit_id=uuid.uuid4(),
            ts=base_ts + timedelta(milliseconds=i),
        )
        for i in range(100)
    ]

    # Fire all 100 appends concurrently.
    await asyncio.gather(*[ledger.append(e) for e in entries])

    # Query the workflow for the full time range; expect 100.
    got = await ledger.query(
        workflow_id=wf,
        from_timestamp=base_ts - timedelta(seconds=1),
        to_timestamp=base_ts + timedelta(seconds=10),
    )
    assert len(got) == 100, (
        f"concurrent appends lost or duplicated entries: got {len(got)}, "
        f"expected 100"
    )
    # All audit_ids present (no duplicate, no drop)
    got_ids = {e.audit_id for e in got}
    expected_ids = {e.audit_id for e in entries}
    assert got_ids == expected_ids


@pytest.mark.asyncio
async def test_audit_ledger_concurrent_appends_and_reads_consistent() -> None:
    """50 concurrent appends interleaved with 50 concurrent reads.
    Every read returns a consistent snapshot (no torn reads); final
    state has all 50 appends visible."""
    ledger = InMemoryAuditLedger()
    wf = uuid.uuid4()
    base_ts = datetime.now(UTC)
    entries = [
        _make_entry(
            workflow_id=wf,
            audit_id=uuid.uuid4(),
            ts=base_ts + timedelta(milliseconds=i),
        )
        for i in range(50)
    ]
    full_range = (
        base_ts - timedelta(seconds=1),
        base_ts + timedelta(seconds=10),
    )

    async def reader() -> list[AuditLedgerEntry]:
        return await ledger.query(
            workflow_id=wf,
            from_timestamp=full_range[0],
            to_timestamp=full_range[1],
        )

    tasks: list = []
    for entry in entries:
        tasks.append(ledger.append(entry))
        tasks.append(reader())

    results = await asyncio.gather(*tasks)

    # Final state: all 50 entries
    final = await reader()
    assert len(final) == 50

    # No reader returned more than 50 or threw an error (no torn read)
    reader_results = [r for r in results if isinstance(r, list)]
    for r in reader_results:
        assert isinstance(r, list)
        assert len(r) <= 50  # never more than final state
        # All entries in any read are well-formed
        for e in r:
            assert isinstance(e, AuditLedgerEntry)
            assert 0.0 <= e.risk_score <= 1.0


@pytest.mark.asyncio
async def test_audit_ledger_concurrent_queries_dont_block_each_other() -> None:
    """N concurrent query() calls on an empty ledger MUST all return
    quickly. The Lock is a serialiser, not a global pause."""
    ledger = InMemoryAuditLedger()
    wf = uuid.uuid4()
    now = datetime.now(UTC)

    async def reader() -> list[AuditLedgerEntry]:
        return await ledger.query(
            workflow_id=wf,
            from_timestamp=now - timedelta(seconds=1),
            to_timestamp=now + timedelta(seconds=1),
        )

    results = await asyncio.gather(*[reader() for _ in range(20)])
    for r in results:
        assert r == []


@pytest.mark.asyncio
async def test_audit_ledger_concurrent_appends_preserve_each_workflow() -> None:
    """Concurrent appends across 3 different workflows: each workflow's
    query returns only its own entries, no cross-talk."""
    ledger = InMemoryAuditLedger()
    wf_a = uuid.uuid4()
    wf_b = uuid.uuid4()
    wf_c = uuid.uuid4()
    base_ts = datetime.now(UTC)

    entries_a = [
        _make_entry(
            workflow_id=wf_a,
            audit_id=uuid.uuid4(),
            ts=base_ts + timedelta(milliseconds=i),
        )
        for i in range(20)
    ]
    entries_b = [
        _make_entry(
            workflow_id=wf_b,
            audit_id=uuid.uuid4(),
            ts=base_ts + timedelta(milliseconds=i + 100),
        )
        for i in range(20)
    ]
    entries_c = [
        _make_entry(
            workflow_id=wf_c,
            audit_id=uuid.uuid4(),
            ts=base_ts + timedelta(milliseconds=i + 200),
        )
        for i in range(20)
    ]

    all_entries = entries_a + entries_b + entries_c
    await asyncio.gather(*[ledger.append(e) for e in all_entries])

    rng = (
        base_ts - timedelta(seconds=1),
        base_ts + timedelta(seconds=10),
    )
    got_a = await ledger.query(
        workflow_id=wf_a, from_timestamp=rng[0], to_timestamp=rng[1]
    )
    got_b = await ledger.query(
        workflow_id=wf_b, from_timestamp=rng[0], to_timestamp=rng[1]
    )
    got_c = await ledger.query(
        workflow_id=wf_c, from_timestamp=rng[0], to_timestamp=rng[1]
    )

    assert len(got_a) == 20
    assert len(got_b) == 20
    assert len(got_c) == 20

    # No cross-talk
    assert all(e.workflow_id == wf_a for e in got_a)
    assert all(e.workflow_id == wf_b for e in got_b)
    assert all(e.workflow_id == wf_c for e in got_c)


# ---------------------------------------------------------------------------
# InMemoryAuditIndex conflict detection under concurrent re-index
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_audit_index_idempotent_under_repeated_put_same_key() -> None:
    """Putting the same (audit_id, storage_key) pair 10 times concurrently
    MUST be idempotent. The lock serialises; same-key re-puts are no-ops."""
    index = InMemoryAuditIndex()
    audit_id = uuid.uuid4()
    storage_key = "a" * 64

    # 10 identical puts in parallel
    await asyncio.gather(
        *[index.put(audit_id, storage_key) for _ in range(10)]
    )

    # Get returns the consistent value
    got = await index.get(audit_id)
    assert got == storage_key


@pytest.mark.asyncio
async def test_audit_index_rejects_conflicting_put_to_same_audit_id() -> None:
    """Two different storage_keys for the same audit_id MUST raise
    AuditIndexConflict. This prevents the "re-snapshot of same decision
    with different content" silent overwrite bug.

    Cannot reliably hit in parallel (the lock serialises), so we test
    sequential put followed by put-with-different-key."""
    index = InMemoryAuditIndex()
    audit_id = uuid.uuid4()
    await index.put(audit_id, "a" * 64)

    with pytest.raises(AuditIndexConflict, match="already indexed"):
        await index.put(audit_id, "b" * 64)


# ---------------------------------------------------------------------------
# Snapshotter concurrent snapshots
# ---------------------------------------------------------------------------


_TENANT = uuid.UUID("aaaaaaaa-7777-7777-7777-aaaaaaaaaaaa")


@pytest.fixture
def snapshot_system() -> Snapshotter:
    """Snapshotter with InMemory backing for race tests."""
    bundle_store = InMemoryBundleStore()
    audit_index = InMemoryAuditIndex()
    tenant_key = generate_key()

    def key_resolver(tid: uuid.UUID) -> AesGcmKey:
        return tenant_key

    return Snapshotter(
        store=bundle_store, index=audit_index, key_resolver=key_resolver
    )


@pytest.mark.asyncio
async def test_snapshotter_50_concurrent_distinct_snapshots(
    snapshot_system: Snapshotter,
) -> None:
    """50 concurrent snapshot() calls with DISTINCT audit_ids MUST all
    succeed without raising. Store and index hold up under the load."""
    snapshotter = snapshot_system
    inputs = [
        SnapshotInputs(
            audit_id=uuid.uuid4(),
            tenant_id=_TENANT,
            decision="allow",
            risk_score=0.1,
            request_envelope={"i": i},
        )
        for i in range(50)
    ]

    results = await asyncio.gather(
        *[snapshotter.snapshot(inp) for inp in inputs]
    )
    assert len(results) == 50
    # Every result has a unique storage_key (random nonce per encrypt
    # means same plaintext gets different ciphertexts; different
    # inputs give different storage_keys too).
    storage_keys = {r.storage_key for r in results}
    assert len(storage_keys) == 50


@pytest.mark.asyncio
async def test_snapshotter_concurrent_same_audit_id_one_wins(
    snapshot_system: Snapshotter,
) -> None:
    """Two concurrent snapshots with the SAME audit_id but DIFFERENT
    content MUST not both succeed. The audit-index conflict detection
    catches it; one raises AuditIndexConflict.

    Note: AES-GCM uses random nonces so two encrypts of the same
    plaintext produce different ciphertexts -> different storage_keys
    -> the index's same-key idempotency check does NOT save us here.
    The conflict check on differing storage_keys is the defence."""
    snapshotter = snapshot_system
    shared_audit_id = uuid.uuid4()

    async def attempt(content_value: int) -> str | type:
        try:
            r = await snapshotter.snapshot(
                SnapshotInputs(
                    audit_id=shared_audit_id,
                    tenant_id=_TENANT,
                    decision="allow",
                    risk_score=0.1,
                    request_envelope={"content": content_value},
                )
            )
            return r.storage_key
        except AuditIndexConflict:
            return AuditIndexConflict

    results = await asyncio.gather(
        attempt(1), attempt(2), return_exceptions=False
    )
    # At least one MUST be AuditIndexConflict (the loser); the other
    # is the winning storage_key. Both should not be successful.
    success_count = sum(1 for r in results if isinstance(r, str))
    conflict_count = sum(1 for r in results if r is AuditIndexConflict)
    assert success_count == 1, (
        f"expected 1 winner, got {success_count} successes "
        f"and {conflict_count} conflicts"
    )
    assert conflict_count == 1
