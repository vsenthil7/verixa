"""CP-42 baseline load test: sustained-rate audit-ledger volume.

Anchored to NEGATIVE_TEST_PLAN gap "Resource exhaustion (10k simultaneous
govern calls)". The Phase 0 in-memory infrastructure cannot meaningfully
simulate the production target of 500 decisions/sec/replica — but it CAN
prove the infrastructure does not silently drop work under high-volume
concurrent load.

Three baseline scenarios:

  1. **Audit ledger high-concurrency append:** 1000 concurrent appends
     to InMemoryAuditLedger using asyncio.gather. Asserts all 1000 land
     and complete in under 5 seconds. This is 4x what CP-38 covered
     (CP-38 was 100 concurrent appends as a correctness check; this is
     1000 as a volume check).

  2. **Snapshotter high-concurrency burst:** 200 concurrent Snapshotter
     calls. Asserts all 200 complete, every storage_key is unique, and
     the burst settles in under 10 seconds.

  3. **Mixed read+write pressure:** 500 appends interleaved with 500
     reads on the same workflow's audit ledger. Asserts every read
     returns a valid snapshot (no torn reads), final state has all
     500 appends, total runtime under 10 seconds.

These tests intentionally don't fit in the regular pytest suite — they
take seconds rather than milliseconds, and the noise on small-sample
correctness can mask real performance regressions. Run them explicitly
from load-tests/.

NOT a substitute for production load testing with Postgres + MinIO +
SPIFFE + Vault; Phase 1 will add those. This is the Phase-0-honesty
baseline that proves the in-memory contract does not silently drop work.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from verixa_control_plane.audit import (
    AuditLedgerEntry,
    InMemoryAuditLedger,
)
from verixa_runtime.crypto.aes_gcm import AesGcmKey, generate_key
from verixa_runtime.replay import (
    InMemoryAuditIndex,
    InMemoryBundleStore,
    Snapshotter,
)
from verixa_runtime.replay.snapshotter import SnapshotInputs

_TENANT = uuid.UUID("aaaaaaaa-8888-8888-8888-aaaaaaaaaaaa")


def _make_entry(
    *, workflow_id: uuid.UUID, audit_id: uuid.UUID, ts: datetime
) -> AuditLedgerEntry:
    return AuditLedgerEntry(
        audit_id=audit_id,
        workflow_id=workflow_id,
        tenant_id=_TENANT,
        decision="allow",
        risk_score=0.1,
        risk_classification="low",
        triad_invoked=False,
        timestamp=ts,
    )


# ---------------------------------------------------------------------------
# Scenario 1 — Audit ledger high-concurrency append (1000 in parallel)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_audit_ledger_1000_concurrent_appends() -> None:
    """1000 concurrent append() calls. All MUST land; runtime < 5 seconds.

    This is 4x CP-38's correctness check; here we measure volume."""
    ledger = InMemoryAuditLedger()
    wf = uuid.uuid4()
    base_ts = datetime.now(UTC)
    entries = [
        _make_entry(
            workflow_id=wf,
            audit_id=uuid.uuid4(),
            ts=base_ts + timedelta(milliseconds=i),
        )
        for i in range(1000)
    ]

    t0 = time.perf_counter()
    await asyncio.gather(*[ledger.append(e) for e in entries])
    elapsed = time.perf_counter() - t0

    # All entries present, no drops or duplicates
    got = await ledger.query(
        workflow_id=wf,
        from_timestamp=base_ts - timedelta(seconds=1),
        to_timestamp=base_ts + timedelta(seconds=10),
    )
    assert len(got) == 1000, (
        f"1000 concurrent appends produced {len(got)} entries; lost or "
        f"duplicated under load"
    )
    # Performance budget: 5 seconds is generous; real-world is < 1 second
    # on a developer laptop. If this blows out, something has regressed.
    assert elapsed < 5.0, (
        f"1000 concurrent appends took {elapsed:.2f}s; budget is 5s"
    )


# ---------------------------------------------------------------------------
# Scenario 2 — Snapshotter burst (200 in parallel)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_snapshotter_200_concurrent_burst() -> None:
    """200 concurrent snapshot() calls with distinct audit_ids. All
    complete in under 10 seconds, every storage_key unique.

    Snapshotter does crypto work (AES-GCM encrypt + SHA-256), so it's
    slower per-op than the audit-ledger append. 200 is the right size
    for an in-memory burst test."""
    bundle_store = InMemoryBundleStore()
    audit_index = InMemoryAuditIndex()
    tenant_key = generate_key()

    def key_resolver(tid: uuid.UUID) -> AesGcmKey:
        return tenant_key

    snapshotter = Snapshotter(
        store=bundle_store, index=audit_index, key_resolver=key_resolver
    )

    inputs = [
        SnapshotInputs(
            audit_id=uuid.uuid4(),
            tenant_id=_TENANT,
            decision="allow",
            risk_score=0.1,
            request_envelope={"burst_i": i},
        )
        for i in range(200)
    ]

    t0 = time.perf_counter()
    results = await asyncio.gather(
        *[snapshotter.snapshot(inp) for inp in inputs]
    )
    elapsed = time.perf_counter() - t0

    assert len(results) == 200
    storage_keys = {r.storage_key for r in results}
    assert len(storage_keys) == 200, (
        f"snapshotter produced {len(storage_keys)} distinct storage_keys "
        f"from 200 distinct snapshots; collision under load is impossible "
        f"under AES-GCM random-nonce, so this is a serious bug"
    )
    assert elapsed < 10.0, (
        f"200 concurrent snapshots took {elapsed:.2f}s; budget is 10s"
    )


# ---------------------------------------------------------------------------
# Scenario 3 — Mixed read+write pressure (500 appends + 500 reads)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_audit_ledger_mixed_read_write_under_load() -> None:
    """500 appends interleaved with 500 reads on the same workflow.
    Every read returns a valid snapshot (no torn reads); final state
    has all 500 appends; total runtime under 10 seconds.

    This stresses the asyncio.Lock contract under realistic mixed
    operator + runtime pressure: operator dashboards poll while
    runtime writes new decisions."""
    ledger = InMemoryAuditLedger()
    wf = uuid.uuid4()
    base_ts = datetime.now(UTC)
    full_range = (
        base_ts - timedelta(seconds=1),
        base_ts + timedelta(seconds=10),
    )

    entries = [
        _make_entry(
            workflow_id=wf,
            audit_id=uuid.uuid4(),
            ts=base_ts + timedelta(milliseconds=i),
        )
        for i in range(500)
    ]

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

    t0 = time.perf_counter()
    results = await asyncio.gather(*tasks)
    elapsed = time.perf_counter() - t0

    # Final-state assertion: all 500 entries present
    final = await reader()
    assert len(final) == 500

    # Every reader returned a coherent snapshot (no torn reads)
    reader_results = [r for r in results if isinstance(r, list)]
    for r in reader_results:
        assert 0 <= len(r) <= 500
        for e in r:
            assert isinstance(e, AuditLedgerEntry)
            assert 0.0 <= e.risk_score <= 1.0

    # Performance budget
    assert elapsed < 10.0, (
        f"500 mixed read+write ops took {elapsed:.2f}s; budget is 10s"
    )
