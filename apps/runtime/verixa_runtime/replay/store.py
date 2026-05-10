"""Replay Vault object-store interface (CP-12.3).

The Replay Vault writes encrypted bundles to an object store and
reads them back later. CP-12.4 (snapshotter / reconstructor) doesn't
care whether the backing store is MinIO, AWS S3, or an in-memory
dictionary -- it just calls put / get / exists / delete on a
``BundleStore``.

Phase-0 ships:
  - ``BundleStore`` -- Protocol type (structural typing) defining the
    surface the snapshotter uses.
  - ``InMemoryBundleStore`` -- dict-backed implementation for tests
    and the offline demo. Thread-safe via a single asyncio.Lock so
    concurrent put/get calls from multiple coroutines don't race.
  - ``BundleNotFound`` -- raised on get/delete for unknown keys.

CP-12.6 will add ``MinioBundleStore`` (real S3-compatible client) and
gate its tests behind testcontainers, following the same pattern as
CP-8.6 for Redis.

Two flavours of erasure:

  1. **Cryptographic erasure** (default for GDPR Article 17): zeroise
     the tenant's AES key in Vault. The encrypted bytes in the
     object store remain as audit artefacts but the plaintext is
     unrecoverable. Use this when an auditor still needs to know
     *that* a decision happened, just not *what* it decided.

  2. **Physical deletion**: ``BundleStore.delete`` removes the
     ciphertext bytes entirely. Use this when even the existence
     of the bundle must be erased (rare; usually mandated by court
     order).
"""

from __future__ import annotations

import asyncio
from typing import Protocol

from verixa_runtime.replay.sealer import EncryptedBundle


class BundleNotFound(KeyError):
    """Raised by get/delete when no bundle exists at the given key."""


class BundleStore(Protocol):
    """Pluggable backend for encrypted-bundle storage.

    Implementations: ``InMemoryBundleStore`` (tests, offline demo);
    ``MinioBundleStore`` (CP-12.6, real S3-compatible client).
    """

    async def put(
        self, bundle: EncryptedBundle
    ) -> str:  # pragma: no cover -- Protocol method body
        # Stores the bundle under its content-addressable
        # storage_key. Returns the key. Idempotent: storing a bundle
        # whose key already exists with byte-identical ciphertext is
        # a no-op. Raises BundleConflict if the key exists with
        # different bytes (would indicate a hash collision -- in
        # practice unreachable under SHA-256).
        ...

    async def get(
        self, storage_key: str
    ) -> EncryptedBundle:  # pragma: no cover -- Protocol method body
        # Retrieves the bundle. Raises BundleNotFound if absent.
        ...

    async def exists(
        self, storage_key: str
    ) -> bool:  # pragma: no cover -- Protocol method body
        # Cheap presence check. Implementations should avoid a full
        # fetch when the backend supports HEAD-style queries.
        ...

    async def delete(
        self, storage_key: str
    ) -> None:  # pragma: no cover -- Protocol method body
        # Physical deletion. Raises BundleNotFound if absent (the
        # caller asked to delete something that wasn't there;
        # surface that rather than silently succeed).
        ...


class BundleConflict(RuntimeError):
    """Raised on put when storage_key exists with different bytes.

    Under SHA-256 over a sufficiently entropic input this is
    cryptographically unreachable; surfacing it loudly defends
    against a bug in the content-address derivation rather than
    against a real collision.
    """


class InMemoryBundleStore:
    """Dict-backed BundleStore implementation.

    Used by tests + the offline demo. Thread-safe across coroutines
    via a single asyncio.Lock; the operations are short and the
    contention is low, so a single lock is fine.

    NOT process-safe: each Python process has its own dict. For
    multi-process replay (a real production workload) use the
    MinioBundleStore from CP-12.6.
    """

    def __init__(self) -> None:
        self._items: dict[str, EncryptedBundle] = {}
        self._lock = asyncio.Lock()

    async def put(self, bundle: EncryptedBundle) -> str:
        async with self._lock:
            existing = self._items.get(bundle.storage_key)
            if existing is not None:
                # Idempotent re-put of the exact same ciphertext is
                # fine -- snapshot-then-retry should not fail.
                if (
                    existing.ciphertext.nonce == bundle.ciphertext.nonce
                    and existing.ciphertext.ciphertext
                    == bundle.ciphertext.ciphertext
                    and existing.ciphertext.associated_data
                    == bundle.ciphertext.associated_data
                ):
                    return bundle.storage_key
                # Different bytes under the same key: hash collision
                # (or, far more likely, a bug). Surface loudly.
                raise BundleConflict(
                    f"storage_key {bundle.storage_key!r} already exists "
                    f"with different ciphertext bytes"
                )
            self._items[bundle.storage_key] = bundle
            return bundle.storage_key

    async def get(self, storage_key: str) -> EncryptedBundle:
        async with self._lock:
            try:
                return self._items[storage_key]
            except KeyError as e:
                raise BundleNotFound(
                    f"no bundle at storage_key={storage_key!r}"
                ) from e

    async def exists(self, storage_key: str) -> bool:
        async with self._lock:
            return storage_key in self._items

    async def delete(self, storage_key: str) -> None:
        async with self._lock:
            try:
                del self._items[storage_key]
            except KeyError as e:
                raise BundleNotFound(
                    f"no bundle at storage_key={storage_key!r}"
                ) from e

    # Test-helper -- NOT part of the BundleStore Protocol surface.
    # Tests use this to inspect store state without taking the lock
    # (safe because tests are single-threaded by default).
    def _snapshot_keys(self) -> list[str]:
        return list(self._items.keys())
