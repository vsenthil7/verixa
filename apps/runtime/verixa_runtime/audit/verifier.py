"""Audit-ledger verifier — CP-5.2 will implement the full-chain walk.

CP-5.1 ships only the public types so the package's __init__ can import
them; the actual `verify_audit_chain` walk lands in CP-5.2 with the
full hash-chain + signature verification logic and tests.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal


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
    entries: list[PersistedAuditEntry],
    tenant_id: uuid.UUID,  # noqa: ARG001 — used in CP-5.2
) -> None:  # pragma: no cover  (placeholder; CP-5.2 implements)
    """Walk the persisted chain. Implemented in CP-5.2."""
    raise NotImplementedError(
        "verify_audit_chain lands in CP-5.2; CP-5.1 ships emitter only"
    )
