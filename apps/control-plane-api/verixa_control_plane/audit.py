"""Control Plane audit-log query handler + ledger abstraction (CP-14.3).

The audit ledger records every governed decision: which workflow,
which agent, what the action was, what the decision was, what the
risk was, and whether the triad got invoked. This module defines
the operator-facing read surface.

The cryptographic audit ledger from CP-5 carries more (Ed25519
signatures, hash-chain links to detect tampering). The
``AuditLedger`` Protocol here exposes the **redacted operator view**
needed for filtering and display; the integrity layer stays in the
runtime where it belongs.

Phase-0 ships:
  - AuditLedger Protocol (async query)
  - AuditLedgerEntry frozen dataclass (the row type)
  - InMemoryAuditLedger for tests + offline demo
  - handle_audit_query handler

Phase-1 replaces InMemoryAuditLedger with PostgresAuditLedger
backed by verixa_audit.ledger_entries from the CP-3 schema, and
wires the gateway to write entries on every governed decision.
"""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from verixa_control_plane.envelopes import (
    AuditEntry,
    AuditQueryResponse,
    ErrorResponse,
)


@dataclass(frozen=True, slots=True)
class AuditLedgerEntry:
    """One row of the operator-facing audit view.

    Mirrors the AuditEntry envelope but lives in the runtime layer
    so the ledger implementation doesn't depend on the HTTP
    envelopes.
    """

    audit_id: uuid.UUID
    workflow_id: uuid.UUID
    tenant_id: uuid.UUID
    decision: str  # "allow" / "deny" / "escalate"
    risk_score: float
    risk_classification: str  # "low" / "medium" / "high" / "critical"
    triad_invoked: bool
    timestamp: datetime

    def __post_init__(self) -> None:
        if self.decision not in ("allow", "deny", "escalate"):
            raise ValueError(
                f"decision must be allow/deny/escalate; got {self.decision!r}"
            )
        if not 0.0 <= self.risk_score <= 1.0:
            raise ValueError(
                f"risk_score must be in [0.0, 1.0]; got {self.risk_score!r}"
            )
        if self.risk_classification not in (
            "low", "medium", "high", "critical"
        ):
            raise ValueError(
                f"risk_classification must be one of "
                f"low/medium/high/critical; got {self.risk_classification!r}"
            )


class AuditLedger(Protocol):
    """Async query surface for the operator-facing audit view.

    Phase-0: InMemoryAuditLedger. Phase-1: PostgresAuditLedger
    backed by verixa_audit.ledger_entries.
    """

    async def query(
        self,
        *,
        workflow_id: uuid.UUID,
        from_timestamp: datetime,
        to_timestamp: datetime,
    ) -> list[AuditLedgerEntry]:  # pragma: no cover -- Protocol body
        # Returns ledger entries matching the workflow + the closed
        # timestamp range [from, to], sorted by timestamp ascending.
        ...

    async def append(
        self, entry: AuditLedgerEntry
    ) -> None:  # pragma: no cover -- Protocol body
        # Records a new entry. Implementations may add integrity
        # checks (hash chain, signature) on top.
        ...


class InMemoryAuditLedger:
    """Dict-backed ledger for tests + offline demo.

    Entries are stored in a list to preserve insertion order; query
    filters by workflow + timestamp range and returns matches in
    ascending timestamp order.
    """

    def __init__(self) -> None:
        self._entries: list[AuditLedgerEntry] = []
        self._lock = asyncio.Lock()

    async def append(self, entry: AuditLedgerEntry) -> None:
        async with self._lock:
            self._entries.append(entry)

    async def query(
        self,
        *,
        workflow_id: uuid.UUID,
        from_timestamp: datetime,
        to_timestamp: datetime,
    ) -> list[AuditLedgerEntry]:
        async with self._lock:
            matches = [
                e for e in self._entries
                if e.workflow_id == workflow_id
                and from_timestamp <= e.timestamp <= to_timestamp
            ]
        return sorted(matches, key=lambda e: e.timestamp)


# ---------------------------------------------------------------------------
# Handler
# ---------------------------------------------------------------------------


async def handle_audit_query(
    *,
    workflow_id: uuid.UUID,
    from_timestamp: datetime,
    to_timestamp: datetime,
    audit_ledger: AuditLedger,
) -> tuple[int, AuditQueryResponse | ErrorResponse]:
    """GET /v1/control/audit?workflow_id=&from=&to= handler.

    Validates timestamp range (from <= to) and queries the ledger.
    Returns 400 if the range is inverted; 200 with the AuditQueryResponse
    otherwise.
    """
    if from_timestamp > to_timestamp:
        return 400, ErrorResponse(
            error="invalid_time_range",
            message=(
                f"from_timestamp {from_timestamp.isoformat()} is after "
                f"to_timestamp {to_timestamp.isoformat()}"
            ),
        )
    entries = await audit_ledger.query(
        workflow_id=workflow_id,
        from_timestamp=from_timestamp,
        to_timestamp=to_timestamp,
    )
    return 200, AuditQueryResponse(
        entries=[
            AuditEntry(
                audit_id=e.audit_id,
                workflow_id=e.workflow_id,
                decision=e.decision,
                risk_score=e.risk_score,
                risk_classification=e.risk_classification,
                triad_invoked=e.triad_invoked,
                timestamp=e.timestamp,
            )
            for e in entries
        ],
        total=len(entries),
        workflow_id=workflow_id,
        from_timestamp=from_timestamp,
        to_timestamp=to_timestamp,
    )


__all__ = [
    "AuditLedger",
    "AuditLedgerEntry",
    "InMemoryAuditLedger",
    "handle_audit_query",
]
