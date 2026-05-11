"""Replay Vault snapshotter + reconstructor (CP-12.4).

The snapshotter is the gateway-side entry point: given a live
decision context, it captures everything into a ReplayBundle,
encrypts it with the tenant's AES key, writes the ciphertext to the
BundleStore, and indexes the audit_id -> storage_key mapping so
later replay-by-audit_id lookups work.

The reconstructor is the inverse: given an audit_id + tenant key,
fetch the ciphertext, decrypt, return the ReplayBundle.

Phase-0 keeps the audit_id index in-memory (a dict on the Snapshotter
instance). CP-12.6 will move this to a Postgres table (the
verixa_replay.bundle_index schema from CP-3) so the index survives
process restarts. The Snapshotter accepts an injectable
``AuditIndex`` Protocol so the swap is a one-line change.

Two important separations:

  1. **Snapshotter knows about the tenant key resolver**; the store
     does not. This means a store implementation never sees a key
     and never sees plaintext. Useful for auditing the store's
     network boundary.

  2. **Snapshot is fire-and-forget at the gateway level**: the
     gateway's hot path returns the GovernResponse first; the
     snapshot happens in a background task. CP-12.5 (gateway wiring)
     adds the fire-and-forget plumbing. CP-12.4 (this) builds the
     snapshotter that the background task calls.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Protocol

from verixa_runtime.crypto.aes_gcm import AesGcmKey
from verixa_runtime.replay.bundle import (
    PolicyEvaluationRecord,
    ReplayBundle,
    TriadReviewRecord,
)
from verixa_runtime.replay.sealer import (
    EncryptedBundle,
    decrypt_bundle,
    encrypt_bundle,
)
from verixa_runtime.replay.store import BundleNotFound, BundleStore

# Callable that resolves a tenant_id to its AES-256 data-encryption
# key. Production: pulls from Vault transit. Tests: a dict lookup.
TenantKeyResolver = Callable[[uuid.UUID], AesGcmKey]


class AuditIndex(Protocol):
    """Maps audit_id -> storage_key.

    Phase-0 implementations: InMemoryAuditIndex. CP-12.6:
    PostgresAuditIndex backed by verixa_replay.bundle_index.
    """

    async def put(
        self, audit_id: uuid.UUID, storage_key: str
    ) -> None:  # pragma: no cover -- Protocol method body
        # Records the audit_id -> storage_key mapping. Idempotent on
        # exact-duplicate (same audit_id mapping to same storage_key);
        # raises AuditIndexConflict if audit_id already maps to a
        # different storage_key (would indicate a re-snapshot of the
        # same decision with different content, which is a bug).
        ...

    async def get(
        self, audit_id: uuid.UUID
    ) -> str:  # pragma: no cover -- Protocol method body
        # Returns the storage_key. Raises AuditIndexMiss if unknown.
        ...


class AuditIndexConflict(RuntimeError):
    """Raised when an audit_id is re-indexed to a different storage_key."""


class AuditIndexMiss(KeyError):
    """Raised by AuditIndex.get when audit_id is unknown."""


class InMemoryAuditIndex:
    """Dict-backed AuditIndex for tests and the offline demo."""

    def __init__(self) -> None:
        self._items: dict[uuid.UUID, str] = {}
        self._lock = asyncio.Lock()

    async def put(self, audit_id: uuid.UUID, storage_key: str) -> None:
        async with self._lock:
            existing = self._items.get(audit_id)
            if existing is None:
                self._items[audit_id] = storage_key
                return
            if existing == storage_key:
                return  # idempotent re-index
            raise AuditIndexConflict(
                f"audit_id {audit_id} already indexed to "
                f"storage_key={existing!r}, refusing to overwrite "
                f"with {storage_key!r}"
            )

    async def get(self, audit_id: uuid.UUID) -> str:
        async with self._lock:
            try:
                return self._items[audit_id]
            except KeyError as e:
                raise AuditIndexMiss(
                    f"no index entry for audit_id={audit_id}"
                ) from e


@dataclass(frozen=True, slots=True)
class SnapshotInputs:
    """Everything the snapshotter needs to capture one decision.

    Caller supplies typed inputs from the gateway hot path; the
    snapshotter assembles them into a ReplayBundle. Keeping this as
    a frozen dataclass means the caller can't accidentally mutate
    the inputs between two snapshot calls.
    """

    audit_id: uuid.UUID
    tenant_id: uuid.UUID
    decision: str  # "allow" / "deny" / "escalate"
    risk_score: float
    request_envelope: dict[str, Any]
    retrieved_documents: tuple[tuple[str, str], ...] = field(
        default_factory=tuple
    )
    tool_io: tuple[dict[str, Any], ...] = field(default_factory=tuple)
    policy_evaluations: tuple[PolicyEvaluationRecord, ...] = field(
        default_factory=tuple
    )
    triad_review: TriadReviewRecord | None = None


@dataclass(frozen=True, slots=True)
class SnapshotResult:
    """What the snapshotter returns to the gateway.

    The audit_id is echoed back so the caller can log it; the
    storage_key lets the caller construct a replay URL without
    a second lookup; the encrypted bundle is included so callers
    can do their own additional persistence if needed.
    """

    audit_id: uuid.UUID
    storage_key: str
    encrypted: EncryptedBundle


class Snapshotter:
    """Captures live decisions into encrypted replay bundles.

    Construction injects: the BundleStore (where ciphertexts live),
    the AuditIndex (audit_id -> storage_key), and a
    TenantKeyResolver (tenant_id -> AesGcmKey). All three are
    Protocol-typed so production can swap in MinIO + Postgres +
    Vault without changing this class.
    """

    def __init__(
        self,
        *,
        store: BundleStore,
        index: AuditIndex,
        key_resolver: TenantKeyResolver,
    ) -> None:
        self._store = store
        self._index = index
        self._key_resolver = key_resolver

    async def snapshot(
        self,
        inputs: SnapshotInputs,
        *,
        timestamp_unix_ns: int | None = None,
    ) -> SnapshotResult:
        """Capture, encrypt, store, index. Returns the SnapshotResult.

        If ``timestamp_unix_ns`` is None, uses time.time_ns(); pass
        an explicit value for deterministic tests.
        """
        ts = (
            timestamp_unix_ns
            if timestamp_unix_ns is not None
            else time.time_ns()
        )
        bundle = ReplayBundle(
            audit_id=inputs.audit_id,
            tenant_id=inputs.tenant_id,
            decision=inputs.decision,
            risk_score=inputs.risk_score,
            request_envelope=inputs.request_envelope,
            retrieved_documents=inputs.retrieved_documents,
            tool_io=inputs.tool_io,
            policy_evaluations=inputs.policy_evaluations,
            triad_review=inputs.triad_review,
            timestamp_unix_ns=ts,
        )
        key = self._key_resolver(inputs.tenant_id)
        encrypted = encrypt_bundle(bundle, key)
        # Order matters: store FIRST so the index never points at a
        # missing key. If put fails the index stays clean; if index
        # fails the store has an orphan we can GC later (the
        # AuditIndexConflict path).
        await self._store.put(encrypted)
        await self._index.put(inputs.audit_id, encrypted.storage_key)
        return SnapshotResult(
            audit_id=inputs.audit_id,
            storage_key=encrypted.storage_key,
            encrypted=encrypted,
        )


class Reconstructor:
    """Fetches and decrypts a previously-snapshotted bundle."""

    def __init__(
        self,
        *,
        store: BundleStore,
        index: AuditIndex,
        key_resolver: TenantKeyResolver,
    ) -> None:
        self._store = store
        self._index = index
        self._key_resolver = key_resolver

    async def reconstruct(self, audit_id: uuid.UUID) -> ReplayBundle:
        """audit_id -> ReplayBundle.

        Raises AuditIndexMiss if no index entry exists,
        BundleNotFound if the index points at a key that's been
        deleted from the store, or AesGcmDecryptionError if the
        ciphertext fails to authenticate (wrong key, tamper).
        """
        storage_key = await self._index.get(audit_id)
        encrypted = await self._store.get(storage_key)
        key = self._key_resolver(encrypted.tenant_id)
        return decrypt_bundle(encrypted, key)


__all__ = [
    "AuditIndex",
    "AuditIndexConflict",
    "AuditIndexMiss",
    "BundleNotFound",
    "InMemoryAuditIndex",
    "Reconstructor",
    "SnapshotInputs",
    "SnapshotResult",
    "Snapshotter",
    "TenantKeyResolver",
]
