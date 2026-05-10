"""Audit-ledger emit — produce a signed, hash-chained record.

Per docs/06_data_model/DATA_MODEL.md §5: every governed action emits a
single row into `verixa_audit.audit_entries` with fixed integrity columns:

  - sequence_number       : strictly monotonic per-tenant
  - hash_chain_prev       : the previous entry's hash_chain_self
                            (or compute_genesis_prev(tenant_id) for seq 0)
  - hash_chain_self       : sha256 over the canonical entry inputs
  - signature             : Ed25519 over hash_chain_self
  - signing_key_id        : which key signed this row

This module is **pure** — no DB I/O, no clock side-effect, no implicit
state. The caller passes the previous self-hash (from the most-recent
persisted row) and gets back a fully-formed `AuditEmitRecord` ready to
INSERT.

Idempotency: two `emit_audit_record(...)` calls with identical inputs
**including identical timestamps** produce identical hash chain self
values. Signature bytes will differ only in the (tiny) extent that
Ed25519 signatures are deterministic in libsodium (they are — Ed25519
is by definition deterministic — so signatures are identical too).

Public API:
  - `AuditEmitInput`       — frozen dataclass of required emit inputs
  - `AuditEmitRecord`      — frozen dataclass of the row ready to persist
  - `AuditEmitterError`    — raised on malformed input
  - `emit_audit_record`    — single entry point
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from verixa_runtime.crypto.ed25519 import sign as ed25519_sign
from verixa_runtime.crypto.hash_chain import (
    HashChainEntry,
    compute_genesis_prev,
    compute_self_hash,
)


class AuditEmitterError(ValueError):
    """Raised when emitter inputs are malformed."""


@dataclass(frozen=True, slots=True)
class AuditEmitInput:
    """All fields the emitter needs from the caller.

    Caller responsibilities:
      - Allocate `sequence_number` (per-tenant strictly monotonic counter;
        in production this comes from a Postgres advisory lock or a
        sequence; in tests, the caller increments).
      - Pass `prev_self_hash` from the most-recent persisted entry, or
        ``None`` for sequence_number == 0 (the emitter computes the
        genesis prev hash internally).
      - Pass a real Ed25519 private key + matching `signing_key_id`.
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
    signing_private_key: bytes
    signing_key_id: str
    # None means caller is asserting this is the genesis row (seq == 0).
    prev_self_hash: bytes | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.tenant_id, uuid.UUID):
            raise AuditEmitterError("tenant_id must be uuid.UUID")
        if self.sequence_number < 0:
            raise AuditEmitterError("sequence_number must be non-negative")
        if not self.action_type:
            raise AuditEmitterError("action_type must be a non-empty string")
        if self.decision not in ("allow", "deny", "escalate", "pending"):
            raise AuditEmitterError(
                "decision must be one of: allow, deny, escalate, pending; "
                f"got {self.decision!r}"
            )
        if not (Decimal("0") <= self.risk_score <= Decimal("1")):
            raise AuditEmitterError(
                f"risk_score must be in [0, 1], got {self.risk_score}"
            )
        if len(self.snapshot_hash) != 32:
            raise AuditEmitterError(
                f"snapshot_hash must be 32 bytes, got {len(self.snapshot_hash)}"
            )
        if len(self.signing_private_key) != 32:
            raise AuditEmitterError(
                "signing_private_key must be 32 bytes, "
                f"got {len(self.signing_private_key)}"
            )
        if not self.signing_key_id.startswith("verixa-sig-"):
            raise AuditEmitterError(
                "signing_key_id must start with 'verixa-sig-'"
            )
        if self.sequence_number == 0 and self.prev_self_hash is not None:
            raise AuditEmitterError(
                "genesis row (sequence_number=0) must have prev_self_hash=None"
            )
        if self.sequence_number > 0 and self.prev_self_hash is None:
            raise AuditEmitterError(
                "non-genesis row must supply prev_self_hash from previous entry"
            )
        if self.prev_self_hash is not None and len(self.prev_self_hash) != 32:
            raise AuditEmitterError(
                "prev_self_hash must be 32 bytes when supplied"
            )


@dataclass(frozen=True, slots=True)
class AuditEmitRecord:
    """An audit-ledger row, ready to INSERT into verixa_audit.audit_entries.

    Fields map 1:1 to the columns specified in DATA_MODEL.md §5.1 (the
    integrity-critical subset; non-critical fields like trace_id and
    request_id are caller-supplied at INSERT time).
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


def emit_audit_record(emit_input: AuditEmitInput) -> AuditEmitRecord:
    """Build a hash-chained, signed audit-ledger record.

    Pure function: same inputs → identical record bytes (including
    signature, since Ed25519 is deterministic).
    """
    # Compute the predecessor hash for this row.
    if emit_input.sequence_number == 0:
        prev_hash = compute_genesis_prev(emit_input.tenant_id)
    else:
        # Validated non-None by AuditEmitInput.__post_init__
        prev_hash = emit_input.prev_self_hash
        assert prev_hash is not None  # narrowing for type checker

    chain_entry = HashChainEntry(
        sequence_number=emit_input.sequence_number,
        event_time=emit_input.event_time,
        workflow_id=emit_input.workflow_id,
        agent_id=emit_input.agent_id,
        action_type=emit_input.action_type,
        decision=emit_input.decision,
        risk_score=emit_input.risk_score,
        snapshot_hash=emit_input.snapshot_hash,
        hash_chain_prev=prev_hash,
    )
    self_hash = compute_self_hash(chain_entry)
    signature = ed25519_sign(emit_input.signing_private_key, self_hash)

    return AuditEmitRecord(
        tenant_id=emit_input.tenant_id,
        sequence_number=emit_input.sequence_number,
        event_time=emit_input.event_time,
        workflow_id=emit_input.workflow_id,
        agent_id=emit_input.agent_id,
        action_type=emit_input.action_type,
        decision=emit_input.decision,
        risk_score=emit_input.risk_score,
        snapshot_hash=emit_input.snapshot_hash,
        hash_chain_prev=prev_hash,
        hash_chain_self=self_hash,
        signature=signature,
        signing_key_id=emit_input.signing_key_id,
    )
