"""pytest suite for verixa_control_plane.audit (CP-14.3).

Covers AuditLedgerEntry invariants, InMemoryAuditLedger query
semantics (workflow filter, time-range filter, sort order),
handle_audit_query happy + error paths.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest

from verixa_control_plane.audit import (
    AuditLedgerEntry,
    InMemoryAuditLedger,
    handle_audit_query,
)
from verixa_control_plane.envelopes import (
    AuditQueryResponse,
    ErrorResponse,
)


_WF_A = uuid.UUID("a1111111-1111-1111-1111-111111111111")
_WF_B = uuid.UUID("b2222222-2222-2222-2222-222222222222")
_TENANT = uuid.UUID("cccc3333-3333-3333-3333-333333333333")
_T_BASE = datetime(2026, 5, 10, 12, 0, tzinfo=timezone.utc)


def _entry(
    *,
    audit_id: uuid.UUID | None = None,
    workflow_id: uuid.UUID = _WF_A,
    decision: str = "allow",
    risk_score: float = 0.1,
    risk_classification: str = "low",
    triad_invoked: bool = False,
    timestamp: datetime | None = None,
) -> AuditLedgerEntry:
    return AuditLedgerEntry(
        audit_id=audit_id or uuid.uuid4(),
        workflow_id=workflow_id,
        tenant_id=_TENANT,
        decision=decision,
        risk_score=risk_score,
        risk_classification=risk_classification,
        triad_invoked=triad_invoked,
        timestamp=timestamp or _T_BASE,
    )


# ---------------------------------------------------------------------------
# AuditLedgerEntry invariants
# ---------------------------------------------------------------------------


def test_entry_rejects_unknown_decision() -> None:
    with pytest.raises(ValueError, match="decision"):
        _entry(decision="maybe")


def test_entry_rejects_risk_below_zero() -> None:
    with pytest.raises(ValueError, match="risk_score"):
        _entry(risk_score=-0.01)


def test_entry_rejects_risk_above_one() -> None:
    with pytest.raises(ValueError, match="risk_score"):
        _entry(risk_score=1.5)


def test_entry_rejects_unknown_classification() -> None:
    with pytest.raises(ValueError, match="risk_classification"):
        _entry(risk_classification="cosmic")


def test_entry_accepts_minimal() -> None:
    e = _entry()
    assert e.decision == "allow"
    assert e.workflow_id == _WF_A


# ---------------------------------------------------------------------------
# InMemoryAuditLedger query semantics
# ---------------------------------------------------------------------------


async def test_query_empty_ledger_returns_empty_list() -> None:
    ledger = InMemoryAuditLedger()
    result = await ledger.query(
        workflow_id=_WF_A,
        from_timestamp=_T_BASE,
        to_timestamp=_T_BASE + timedelta(hours=1),
    )
    assert result == []


async def test_query_filters_by_workflow() -> None:
    ledger = InMemoryAuditLedger()
    await ledger.append(_entry(workflow_id=_WF_A, timestamp=_T_BASE))
    await ledger.append(_entry(workflow_id=_WF_B, timestamp=_T_BASE))
    result = await ledger.query(
        workflow_id=_WF_A,
        from_timestamp=_T_BASE,
        to_timestamp=_T_BASE + timedelta(hours=1),
    )
    assert len(result) == 1
    assert result[0].workflow_id == _WF_A


async def test_query_filters_by_time_range() -> None:
    """Entries outside the window must be excluded; boundary inclusive."""
    ledger = InMemoryAuditLedger()
    too_early = _T_BASE - timedelta(minutes=10)
    in_window_start = _T_BASE
    in_window_end = _T_BASE + timedelta(hours=1)
    too_late = _T_BASE + timedelta(hours=2)
    await ledger.append(_entry(timestamp=too_early))
    await ledger.append(_entry(timestamp=in_window_start))
    await ledger.append(_entry(timestamp=in_window_end))
    await ledger.append(_entry(timestamp=too_late))
    result = await ledger.query(
        workflow_id=_WF_A,
        from_timestamp=in_window_start,
        to_timestamp=in_window_end,
    )
    # Both boundary entries included.
    assert len(result) == 2


async def test_query_returns_ascending_timestamp_order() -> None:
    """Entries appended out of order are sorted on query."""
    ledger = InMemoryAuditLedger()
    t1 = _T_BASE
    t2 = _T_BASE + timedelta(minutes=30)
    t3 = _T_BASE + timedelta(hours=1)
    # Append out of order.
    await ledger.append(_entry(timestamp=t2))
    await ledger.append(_entry(timestamp=t1))
    await ledger.append(_entry(timestamp=t3))
    result = await ledger.query(
        workflow_id=_WF_A,
        from_timestamp=t1,
        to_timestamp=t3,
    )
    assert [e.timestamp for e in result] == [t1, t2, t3]


# ---------------------------------------------------------------------------
# handle_audit_query
# ---------------------------------------------------------------------------


async def test_handle_audit_query_success_returns_200_and_envelope() -> None:
    ledger = InMemoryAuditLedger()
    audit_id = uuid.uuid4()
    await ledger.append(
        _entry(audit_id=audit_id, decision="deny",
               risk_score=0.85, risk_classification="critical",
               triad_invoked=True, timestamp=_T_BASE)
    )
    status, body = await handle_audit_query(
        workflow_id=_WF_A,
        from_timestamp=_T_BASE - timedelta(minutes=1),
        to_timestamp=_T_BASE + timedelta(minutes=1),
        audit_ledger=ledger,
    )
    assert status == 200
    assert isinstance(body, AuditQueryResponse)
    assert body.total == 1
    assert body.entries[0].audit_id == audit_id
    assert body.entries[0].decision == "deny"
    assert body.entries[0].risk_classification == "critical"
    assert body.entries[0].triad_invoked is True
    # Query params echoed back.
    assert body.workflow_id == _WF_A


async def test_handle_audit_query_empty_result_returns_200() -> None:
    ledger = InMemoryAuditLedger()
    status, body = await handle_audit_query(
        workflow_id=_WF_A,
        from_timestamp=_T_BASE,
        to_timestamp=_T_BASE + timedelta(hours=1),
        audit_ledger=ledger,
    )
    assert status == 200
    assert isinstance(body, AuditQueryResponse)
    assert body.total == 0
    assert body.entries == []


async def test_handle_audit_query_inverted_range_returns_400() -> None:
    """from_timestamp > to_timestamp must be rejected with 400."""
    ledger = InMemoryAuditLedger()
    status, body = await handle_audit_query(
        workflow_id=_WF_A,
        from_timestamp=_T_BASE + timedelta(hours=1),  # later
        to_timestamp=_T_BASE,  # earlier
        audit_ledger=ledger,
    )
    assert status == 400
    assert isinstance(body, ErrorResponse)
    assert body.error == "invalid_time_range"


async def test_handle_audit_query_equal_timestamps_accepted() -> None:
    """from == to is a valid (zero-duration) range."""
    ledger = InMemoryAuditLedger()
    await ledger.append(_entry(timestamp=_T_BASE))
    status, body = await handle_audit_query(
        workflow_id=_WF_A,
        from_timestamp=_T_BASE,
        to_timestamp=_T_BASE,
        audit_ledger=ledger,
    )
    assert status == 200
    assert isinstance(body, AuditQueryResponse)
    assert body.total == 1
