"""Verixa Replay Vault.

Snapshot-based replay (NOT bit-exact regeneration; compliance-language
hardening from page-1 brief). For every governed action, the Replay
Vault captures the **complete decision context** at the moment of
decision -- envelope, retrieved docs, tool I/O, policy evaluations,
triad verdicts, and the final decision -- encrypts the bundle with a
per-tenant AES-256-GCM key, and stores it in an object store keyed by
the SHA-256 of the encrypted bundle (content-addressable).

CP-12 sub-CPs:
  CP-12.1 -- replay bundle types + canonical serialisation (this).
  CP-12.2 -- AES-256-GCM encrypt/decrypt + content-addressable key.
  CP-12.3 -- object-store abstraction (Protocol + InMemoryStore).
  CP-12.4 -- snapshotter + reconstructor.
  CP-12.5 -- gateway wiring (snapshot on every governed action).
  CP-12.6 -- live MinIO testcontainer integration test (gated).

Phase-0 stores the hot tier only (working set, MinIO local); Phase 1
adds warm tier (S3) and cold tier (Glacier) with automatic
promotion/demotion. Per-subject erasure (GDPR Article 17) is handled
by key-zeroising the tenant's AES key for the affected subject,
making all bundles cryptographically unrecoverable -- the encrypted
bytes remain in the store as audit artefacts but their plaintext is
gone forever.
"""

from verixa_runtime.replay.bundle import (  # noqa: F401
    BUNDLE_SCHEMA_VERSION,
    PolicyEvaluationRecord,
    ReplayBundle,
    TriadReviewRecord,
    canonicalise_bundle,
    deserialise_bundle,
)
from verixa_runtime.replay.sealer import (  # noqa: F401
    STORAGE_KEY_HEX_LEN,
    AesGcmDecryptionError,
    EncryptedBundle,
    decrypt_bundle,
    encrypt_bundle,
)
from verixa_runtime.replay.store import (  # noqa: F401
    BundleConflict,
    BundleNotFound,
    BundleStore,
    InMemoryBundleStore,
)
from verixa_runtime.replay.snapshotter import (  # noqa: F401
    AuditIndex,
    AuditIndexConflict,
    AuditIndexMiss,
    InMemoryAuditIndex,
    Reconstructor,
    SnapshotInputs,
    SnapshotResult,
    Snapshotter,
    TenantKeyResolver,
)
from verixa_runtime.replay.minio_store import (  # noqa: F401
    MinioBundleStore,
)


__all__ = [
    "BUNDLE_SCHEMA_VERSION",
    "STORAGE_KEY_HEX_LEN",
    "AesGcmDecryptionError",
    "AuditIndex",
    "AuditIndexConflict",
    "AuditIndexMiss",
    "BundleConflict",
    "BundleNotFound",
    "BundleStore",
    "EncryptedBundle",
    "InMemoryAuditIndex",
    "InMemoryBundleStore",
    "MinioBundleStore",
    "PolicyEvaluationRecord",
    "Reconstructor",
    "ReplayBundle",
    "SnapshotInputs",
    "SnapshotResult",
    "Snapshotter",
    "TenantKeyResolver",
    "TriadReviewRecord",
    "canonicalise_bundle",
    "decrypt_bundle",
    "deserialise_bundle",
    "encrypt_bundle",
]
