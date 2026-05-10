"""pytest suite for verixa_runtime.replay.store (CP-12.3).

Covers InMemoryBundleStore happy paths + every exception branch +
the Protocol-typing smoke check.
"""

from __future__ import annotations

import asyncio
import uuid

import pytest

from verixa_runtime.crypto.aes_gcm import (
    AesGcmCiphertext,
    generate_key,
)
from verixa_runtime.replay import (
    BundleConflict,
    BundleNotFound,
    BundleStore,
    EncryptedBundle,
    InMemoryBundleStore,
    ReplayBundle,
    encrypt_bundle,
)


_TENANT_ID = uuid.UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
_AUDIT_ID = uuid.UUID("11111111-2222-3333-4444-555555555555")


def _bundle_for(audit_id: uuid.UUID | None = None) -> ReplayBundle:
    return ReplayBundle(
        audit_id=audit_id or _AUDIT_ID,
        tenant_id=_TENANT_ID,
        decision="allow",
        risk_score=0.05,
        request_envelope={"x": 1},
        timestamp_unix_ns=1_700_000_000_000_000_000,
    )


def _encrypted(audit_id: uuid.UUID | None = None) -> EncryptedBundle:
    return encrypt_bundle(_bundle_for(audit_id), generate_key())


# ---------------------------------------------------------------------------
# put / get / exists / delete happy paths
# ---------------------------------------------------------------------------


async def test_put_returns_storage_key() -> None:
    store = InMemoryBundleStore()
    eb = _encrypted()
    key = await store.put(eb)
    assert key == eb.storage_key


async def test_get_returns_previously_put_bundle() -> None:
    store = InMemoryBundleStore()
    eb = _encrypted()
    await store.put(eb)
    got = await store.get(eb.storage_key)
    # Same object retrieved.
    assert got.storage_key == eb.storage_key
    assert got.tenant_id == eb.tenant_id
    assert got.audit_id == eb.audit_id


async def test_exists_true_after_put() -> None:
    store = InMemoryBundleStore()
    eb = _encrypted()
    assert await store.exists(eb.storage_key) is False
    await store.put(eb)
    assert await store.exists(eb.storage_key) is True


async def test_delete_removes_bundle() -> None:
    store = InMemoryBundleStore()
    eb = _encrypted()
    await store.put(eb)
    assert await store.exists(eb.storage_key) is True
    await store.delete(eb.storage_key)
    assert await store.exists(eb.storage_key) is False


# ---------------------------------------------------------------------------
# Exception branches
# ---------------------------------------------------------------------------


async def test_get_missing_raises_bundle_not_found() -> None:
    store = InMemoryBundleStore()
    with pytest.raises(BundleNotFound, match="storage_key"):
        await store.get("0" * 64)


async def test_delete_missing_raises_bundle_not_found() -> None:
    """Delete on absent key surfaces loudly rather than silently
    succeeding -- caller asked to remove something that wasn't
    there, that's a bug worth knowing about."""
    store = InMemoryBundleStore()
    with pytest.raises(BundleNotFound, match="storage_key"):
        await store.delete("0" * 64)


async def test_put_idempotent_on_byte_identical_re_put() -> None:
    """Re-putting the exact same EncryptedBundle is a no-op, not an
    error. Snapshot-then-retry must not fail just because the first
    attempt succeeded."""
    store = InMemoryBundleStore()
    eb = _encrypted()
    k1 = await store.put(eb)
    k2 = await store.put(eb)
    assert k1 == k2
    # Only one entry in the store.
    assert len(store._snapshot_keys()) == 1


async def test_put_conflict_on_different_bytes_under_same_key() -> None:
    """Forge an EncryptedBundle that claims an existing storage_key
    but carries different ciphertext bytes; put must raise
    BundleConflict.

    This simulates a content-address-derivation bug (or, vanishingly
    unlikely, a SHA-256 collision). The point is to surface it loudly
    not silently overwrite.
    """
    store = InMemoryBundleStore()
    eb_real = _encrypted()
    await store.put(eb_real)
    # Build a different EncryptedBundle that lies about its storage_key.
    eb_different = _encrypted(audit_id=uuid.uuid4())
    forged = EncryptedBundle(
        ciphertext=eb_different.ciphertext,
        storage_key=eb_real.storage_key,  # same key, different bytes
        tenant_id=eb_different.tenant_id,
        audit_id=eb_different.audit_id,
    )
    with pytest.raises(BundleConflict, match="different ciphertext"):
        await store.put(forged)


# ---------------------------------------------------------------------------
# Concurrency: asyncio.Lock serialises concurrent ops
# ---------------------------------------------------------------------------


async def test_concurrent_puts_are_serialised() -> None:
    """Fire many puts concurrently; the lock keeps state consistent."""
    store = InMemoryBundleStore()
    bundles = [_encrypted(audit_id=uuid.uuid4()) for _ in range(20)]
    keys = await asyncio.gather(*(store.put(b) for b in bundles))
    assert set(keys) == {b.storage_key for b in bundles}
    assert len(store._snapshot_keys()) == 20


# ---------------------------------------------------------------------------
# Protocol structural typing (smoke)
# ---------------------------------------------------------------------------


def test_in_memory_store_satisfies_bundle_store_protocol() -> None:
    """InMemoryBundleStore is structurally assignable to BundleStore."""
    s: BundleStore = InMemoryBundleStore()
    # The type assertion above is the meaningful check; the assert
    # below is a runtime smoke so the test isn't a pure type-check.
    assert hasattr(s, "put")
    assert hasattr(s, "get")
    assert hasattr(s, "exists")
    assert hasattr(s, "delete")
