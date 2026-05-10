"""Verixa audit-ledger emit + verify.

The audit ledger is the **single most important** persisted object in
Verixa. Every governed action lands as one row in
`verixa_audit.audit_entries` — append-only, hash-chained, Ed25519-signed.

This package separates concerns:

- `emitter`  — builds an `AuditEmitRecord` ready for the caller to persist
- `verifier` — walks a sequence of persisted rows confirming integrity

Neither module touches the DB directly. The caller (CP-6 Runtime
Gateway, CP-14 Control Plane API) is responsible for `INSERT` / `SELECT`.
That keeps the integrity logic pure-function, deterministic, and
trivially testable.
"""

from verixa_runtime.audit.emitter import (  # noqa: F401
    AuditEmitInput,
    AuditEmitRecord,
    AuditEmitterError,
    emit_audit_record,
)
from verixa_runtime.audit.verifier import (  # noqa: F401
    AuditVerificationError,
    PersistedAuditEntry,
    verify_audit_chain,
)

__all__ = [
    "AuditEmitInput",
    "AuditEmitRecord",
    "AuditEmitterError",
    "AuditVerificationError",
    "PersistedAuditEntry",
    "emit_audit_record",
    "verify_audit_chain",
]
