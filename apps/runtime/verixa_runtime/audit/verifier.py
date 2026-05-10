"""Audit-ledger verifier — full-chain walk for offline integrity check.

Walks a list of `PersistedAuditEntry` rows (read from
`verixa_audit.audit_entries` joined with `verixa_audit.signing_keys` to
attach the public key bytes) and confirms:

  1. The list is non-empty and indexed contiguously from sequence_number 0.
  2. Every entry's `hash_chain_prev` matches the previous entry's
     `hash_chain_self` (or `compute_genesis_prev(tenant_id)` for seq 0).
  3. Every entry's `hash_chain_self` matches a canonical recompute over
     the entry's content fields.
  4. Every entry's `signature` verifies under the supplied `public_key`
     over `hash_chain_self`.
  5. The entry's `tenant_id` matches the verification context.

Failure modes (each raise `AuditVerificationError` with a precise message):

  - empty input
  - tenant_id mismatch on any entry
  - sequence-number gap (must be 0, 1, 2, ...)
  - prev-hash mismatch (chain split or tampered prev field)
  - self-hash mismatch (tampered content field anywhere)
  - signature mismatch (tampered signature, wrong key, tampered self_hash)

This module is pure: no DB, no network. It's used by the offline
`audit_verify` CLI (CP-5.3) and by the runtime emitter as a
post-emit-then-read sanity check.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from verixa_runtime.crypto.ed25519 import Ed25519SignatureError
from verixa_runtime.crypto.ed25519 import verify as ed25519_verify
from verixa_runtime.crypto.hash_chain import (
    HashChainEntry,
    compute_genesis_prev,
    compute_self_hash,
)


class AuditVerificationError(ValueError):
    """Raised when the audit-chain walk detects integrity failure."""


@dataclass(frozen=True, slots=True)
class PersistedAuditEntry:
    """A row read back from `verixa_audit.audit_entries` for verification.

    Mirrors the integrity-critical columns of `AuditEmitRecord` plus the
    public-key bytes the verifier needs to check the signature. Caller
    joins audit_entries → signing_keys to produce these.
    """

    tenant_id: uuid.UUID
    sequence_number: int
    event_time: datetime
    workflow_id: uuid.UUID
    agent_id: uuid.UUID
    action_type: str
    decision: str
    risk_score: Decimal
    snapshot_hash: bytes
    hash_chain_prev: bytes
    hash_chain_self: bytes
    signature: bytes
    signing_key_id: str
    public_key: bytes  # joined from verixa_audit.signing_keys


def verify_audit_chain(
    entries: list[PersistedAuditEntry], tenant_id: uuid.UUID
) -> None:
    """Walk the persisted chain. Raise `AuditVerificationError` on any failure.

    Returns None on success. Empty input is rejected (an empty audit
    chain is meaningless; callers wanting to handle that case should
    do their own length check before calling).
    """
    if not isinstance(tenant_id, uuid.UUID):
        raise AuditVerificationError(
            f"tenant_id must be uuid.UUID, got {type(tenant_id).__name__}"
        )
    if not entries:
        raise AuditVerificationError("audit chain is empty")

    expected_prev = compute_genesis_prev(tenant_id)
    for index, entry in enumerate(entries):
        # 1. Tenant context
        if entry.tenant_id != tenant_id:
            raise AuditVerificationError(
                f"tenant mismatch at sequence_number={entry.sequence_number}: "
                f"expected {tenant_id}, got {entry.tenant_id}"
            )

        # 2. Sequence number
        if entry.sequence_number != index:
            raise AuditVerificationError(
                f"sequence gap at position {index}: expected "
                f"sequence_number={index}, got {entry.sequence_number}"
            )

        # 3. Predecessor hash
        if entry.hash_chain_prev != expected_prev:
            raise AuditVerificationError(
                f"prev-hash mismatch at sequence_number={entry.sequence_number}"
            )

        # 4. Self-hash recompute
        chain_entry = HashChainEntry(
            sequence_number=entry.sequence_number,
            event_time=entry.event_time,
            workflow_id=entry.workflow_id,
            agent_id=entry.agent_id,
            action_type=entry.action_type,
            decision=entry.decision,
            risk_score=entry.risk_score,
            snapshot_hash=entry.snapshot_hash,
            hash_chain_prev=entry.hash_chain_prev,
        )
        recomputed_self = compute_self_hash(chain_entry)
        if recomputed_self != entry.hash_chain_self:
            raise AuditVerificationError(
                f"self-hash mismatch at sequence_number={entry.sequence_number}"
            )

        # 5. Signature
        try:
            ed25519_verify(
                entry.public_key, entry.hash_chain_self, entry.signature
            )
        except Ed25519SignatureError as e:
            raise AuditVerificationError(
                f"signature verification failed at "
                f"sequence_number={entry.sequence_number}"
            ) from e

        # Advance the chain
        expected_prev = entry.hash_chain_self
