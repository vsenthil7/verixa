"""CP-61 tests for verixa.envelopes -- typed response dataclasses.

Anchored to the v0.4.0 roadmap promise in CHANGELOG: customers can opt
into typed return values instead of plain ``dict[str, Any]``. This
commit ships the 3 most-used envelopes:

  - WorkflowRegisterResponse
  - WorkflowSummary + WorkflowListResponse
  - AuditEntry + AuditQueryResponse

Tests cover:

  - Positive: valid payloads parse correctly + every field populates
  - Type errors: non-string UUID, non-string datetime, wrong types
  - Missing required fields: each raises InvalidEnvelopeError with the
    field name in the message so customers can debug server-shape bugs
  - Forward-compat: extra fields are IGNORED (server can add fields)
  - Datetime invariants: naive datetimes rejected (Verixa requires TZ)
  - List parsing: nested AuditEntry / WorkflowSummary errors bubble up
  - Frozen + slotted: dataclasses are immutable + memory-efficient
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta, timezone

import pytest
from verixa.envelopes import (
    AuditEntry,
    AuditQueryResponse,
    InvalidEnvelopeError,
    WorkflowListResponse,
    WorkflowRegisterResponse,
    WorkflowSummary,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _workflow_register_payload(**overrides) -> dict:
    payload = {
        "workflow_id": str(uuid.uuid4()),
        "name": "payments-flow",
        "description": "customer payment authorisation",
        "owner_tenant_id": str(uuid.uuid4()),
        "created_at": datetime.now(UTC).isoformat(),
    }
    payload.update(overrides)
    return payload


def _audit_entry_payload(**overrides) -> dict:
    payload = {
        "audit_id": str(uuid.uuid4()),
        "workflow_id": str(uuid.uuid4()),
        "timestamp": datetime.now(UTC).isoformat(),
        "event_type": "decision.recorded",
        "payload": {"decision": "approve", "confidence": 0.97},
        "signature": "ed25519:" + "a" * 128,
    }
    payload.update(overrides)
    return payload


# ---------------------------------------------------------------------------
# WorkflowRegisterResponse -- positive cases
# ---------------------------------------------------------------------------


def test_workflow_register_response_parses_minimal() -> None:
    payload = _workflow_register_payload()
    parsed = WorkflowRegisterResponse.from_dict(payload)
    assert parsed.name == "payments-flow"
    assert parsed.description == "customer payment authorisation"
    assert isinstance(parsed.workflow_id, uuid.UUID)
    assert isinstance(parsed.owner_tenant_id, uuid.UUID)
    assert isinstance(parsed.created_at, datetime)
    assert parsed.created_at.tzinfo is not None


def test_workflow_register_response_accepts_none_description() -> None:
    payload = _workflow_register_payload(description=None)
    parsed = WorkflowRegisterResponse.from_dict(payload)
    assert parsed.description is None


def test_workflow_register_response_accepts_missing_description_key() -> None:
    """description is optional -- missing key is the same as None."""
    payload = _workflow_register_payload()
    del payload["description"]
    parsed = WorkflowRegisterResponse.from_dict(payload)
    assert parsed.description is None


def test_workflow_register_response_ignores_extra_fields() -> None:
    """Server can add new optional fields; SDK forward-compat means
    extra fields are silently ignored, not rejected."""
    payload = _workflow_register_payload(future_field="ignored", extra=42)
    parsed = WorkflowRegisterResponse.from_dict(payload)
    assert parsed.name == "payments-flow"


def test_workflow_register_response_is_frozen() -> None:
    """The dataclass is frozen so customer code cannot accidentally
    mutate a parsed response and confuse downstream code."""
    payload = _workflow_register_payload()
    parsed = WorkflowRegisterResponse.from_dict(payload)
    with pytest.raises((AttributeError, TypeError)):
        parsed.name = "mutated"  # type: ignore[misc]


def test_workflow_register_response_uses_slots() -> None:
    """Frozen dataclasses still allow attribute-creation by default;
    slots=True locks it down and saves memory for high-volume usage."""
    payload = _workflow_register_payload()
    parsed = WorkflowRegisterResponse.from_dict(payload)
    with pytest.raises((AttributeError, TypeError)):
        parsed.new_field = "not allowed"  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# WorkflowRegisterResponse -- error cases
# ---------------------------------------------------------------------------


def test_workflow_register_response_rejects_non_dict() -> None:
    with pytest.raises(InvalidEnvelopeError, match="expected dict"):
        WorkflowRegisterResponse.from_dict([])  # type: ignore[arg-type]
    with pytest.raises(InvalidEnvelopeError, match="expected dict"):
        WorkflowRegisterResponse.from_dict("not a dict")  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "missing_key",
    ["workflow_id", "name", "owner_tenant_id", "created_at"],
)
def test_workflow_register_response_rejects_missing_required(missing_key: str) -> None:
    payload = _workflow_register_payload()
    del payload[missing_key]
    with pytest.raises(InvalidEnvelopeError, match=f"field {missing_key}"):
        WorkflowRegisterResponse.from_dict(payload)


def test_workflow_register_response_rejects_invalid_uuid() -> None:
    payload = _workflow_register_payload(workflow_id="not-a-uuid")
    with pytest.raises(InvalidEnvelopeError, match="not a valid UUID"):
        WorkflowRegisterResponse.from_dict(payload)


def test_workflow_register_response_rejects_non_string_uuid() -> None:
    payload = _workflow_register_payload(workflow_id=12345)
    with pytest.raises(InvalidEnvelopeError, match="expected uuid string"):
        WorkflowRegisterResponse.from_dict(payload)


def test_workflow_register_response_accepts_uuid_object() -> None:
    """Passing an already-parsed UUID is fine (server lib may pre-parse)."""
    wf_uuid = uuid.uuid4()
    payload = _workflow_register_payload(workflow_id=wf_uuid)
    parsed = WorkflowRegisterResponse.from_dict(payload)
    assert parsed.workflow_id == wf_uuid


def test_workflow_register_response_rejects_naive_datetime() -> None:
    """Verixa requires every timestamp be TZ-aware. A naive datetime
    string is a server bug and must be loud."""
    naive = datetime(2026, 5, 11, 17, 30, 0).isoformat()  # no tzinfo
    payload = _workflow_register_payload(created_at=naive)
    with pytest.raises(InvalidEnvelopeError, match="naive"):
        WorkflowRegisterResponse.from_dict(payload)


def test_workflow_register_response_accepts_z_suffix_datetime() -> None:
    """ISO-8601 with Z suffix (UTC) MUST parse (Python 3.11+ supports)."""
    payload = _workflow_register_payload(
        created_at="2026-05-11T17:30:00+00:00"
    )
    parsed = WorkflowRegisterResponse.from_dict(payload)
    assert parsed.created_at.tzinfo is not None


def test_workflow_register_response_accepts_offset_datetime() -> None:
    """ISO-8601 with explicit offset (+01:00 etc.) MUST also parse."""
    payload = _workflow_register_payload(
        created_at="2026-05-11T18:30:00+01:00"
    )
    parsed = WorkflowRegisterResponse.from_dict(payload)
    assert parsed.created_at.tzinfo == timezone(timedelta(hours=1))


def test_workflow_register_response_rejects_invalid_datetime_string() -> None:
    payload = _workflow_register_payload(created_at="last Tuesday")
    with pytest.raises(InvalidEnvelopeError, match="ISO-8601"):
        WorkflowRegisterResponse.from_dict(payload)


def test_workflow_register_response_rejects_non_string_datetime() -> None:
    payload = _workflow_register_payload(created_at=1234567890)
    with pytest.raises(InvalidEnvelopeError, match="expected ISO-8601 string"):
        WorkflowRegisterResponse.from_dict(payload)


def test_workflow_register_response_accepts_datetime_object() -> None:
    """A pre-parsed datetime is accepted as long as it's TZ-aware."""
    now = datetime.now(UTC)
    payload = _workflow_register_payload(created_at=now)
    parsed = WorkflowRegisterResponse.from_dict(payload)
    assert parsed.created_at == now


def test_workflow_register_response_rejects_naive_datetime_object() -> None:
    naive = datetime(2026, 5, 11, 17, 30, 0)  # no tzinfo
    payload = _workflow_register_payload(created_at=naive)
    with pytest.raises(InvalidEnvelopeError, match="naive"):
        WorkflowRegisterResponse.from_dict(payload)


def test_workflow_register_response_rejects_non_string_name() -> None:
    payload = _workflow_register_payload(name=42)
    with pytest.raises(InvalidEnvelopeError, match="field name: expected string"):
        WorkflowRegisterResponse.from_dict(payload)


def test_workflow_register_response_rejects_non_string_description() -> None:
    """description is Optional[str] but must be str-or-None, not int."""
    payload = _workflow_register_payload(description=42)
    with pytest.raises(InvalidEnvelopeError, match="field description"):
        WorkflowRegisterResponse.from_dict(payload)


# ---------------------------------------------------------------------------
# WorkflowSummary + WorkflowListResponse
# ---------------------------------------------------------------------------


def test_workflow_summary_parses() -> None:
    payload = _workflow_register_payload()
    parsed = WorkflowSummary.from_dict(payload)
    assert parsed.name == "payments-flow"


def test_workflow_summary_rejects_non_dict() -> None:
    with pytest.raises(InvalidEnvelopeError, match="expected dict"):
        WorkflowSummary.from_dict("oops")  # type: ignore[arg-type]


def test_workflow_summary_accepts_missing_description_key() -> None:
    payload = _workflow_register_payload()
    del payload["description"]
    parsed = WorkflowSummary.from_dict(payload)
    assert parsed.description is None


def test_workflow_list_response_parses_empty() -> None:
    parsed = WorkflowListResponse.from_dict({"workflows": [], "total": 0})
    assert parsed.workflows == ()
    assert parsed.total == 0


def test_workflow_list_response_parses_multiple() -> None:
    items = [_workflow_register_payload() for _ in range(3)]
    parsed = WorkflowListResponse.from_dict({"workflows": items, "total": 3})
    assert len(parsed.workflows) == 3
    assert parsed.total == 3
    assert all(isinstance(w, WorkflowSummary) for w in parsed.workflows)


def test_workflow_list_response_returns_tuple_not_list() -> None:
    """Tuple is immutable; customers cannot accidentally mutate the
    parsed list back into the underlying SDK state."""
    parsed = WorkflowListResponse.from_dict({"workflows": [], "total": 0})
    assert isinstance(parsed.workflows, tuple)


def test_workflow_list_response_rejects_non_dict() -> None:
    with pytest.raises(InvalidEnvelopeError, match="expected dict"):
        WorkflowListResponse.from_dict("x")  # type: ignore[arg-type]


def test_workflow_list_response_rejects_missing_workflows_field() -> None:
    with pytest.raises(InvalidEnvelopeError, match="field workflows"):
        WorkflowListResponse.from_dict({"total": 0})


def test_workflow_list_response_rejects_workflows_not_list() -> None:
    with pytest.raises(InvalidEnvelopeError, match="field workflows: expected list"):
        WorkflowListResponse.from_dict({"workflows": "not-a-list", "total": 0})


def test_workflow_list_response_rejects_missing_total() -> None:
    with pytest.raises(InvalidEnvelopeError, match="field total"):
        WorkflowListResponse.from_dict({"workflows": []})


def test_workflow_list_response_rejects_bool_total() -> None:
    """bool is a subclass of int in Python; reject explicitly so True/
    False cannot be silently coerced into 1/0 totals."""
    with pytest.raises(InvalidEnvelopeError, match="field total: expected int"):
        WorkflowListResponse.from_dict({"workflows": [], "total": True})


def test_workflow_list_response_bubbles_inner_error() -> None:
    """An invalid workflow inside the list raises InvalidEnvelopeError
    so customers know WHICH entry failed (not a silent partial parse)."""
    bad = _workflow_register_payload()
    del bad["name"]
    with pytest.raises(InvalidEnvelopeError, match="field name"):
        WorkflowListResponse.from_dict({"workflows": [bad], "total": 1})


# ---------------------------------------------------------------------------
# AuditEntry + AuditQueryResponse
# ---------------------------------------------------------------------------


def test_audit_entry_parses() -> None:
    payload = _audit_entry_payload()
    parsed = AuditEntry.from_dict(payload)
    assert parsed.event_type == "decision.recorded"
    assert parsed.payload == {"decision": "approve", "confidence": 0.97}
    assert parsed.signature.startswith("ed25519:")


def test_audit_entry_rejects_non_dict() -> None:
    with pytest.raises(InvalidEnvelopeError, match="expected dict"):
        AuditEntry.from_dict(42)  # type: ignore[arg-type]


def test_audit_entry_rejects_non_dict_payload() -> None:
    """payload must be a dict (server-side guarantee); if the server
    sends a string the SDK must catch it loudly."""
    payload = _audit_entry_payload(payload="not-a-dict")
    with pytest.raises(InvalidEnvelopeError, match="field payload: expected dict"):
        AuditEntry.from_dict(payload)


@pytest.mark.parametrize(
    "missing_key",
    ["audit_id", "workflow_id", "timestamp", "event_type", "payload", "signature"],
)
def test_audit_entry_rejects_missing_required(missing_key: str) -> None:
    payload = _audit_entry_payload()
    del payload[missing_key]
    with pytest.raises(InvalidEnvelopeError, match=f"field {missing_key}"):
        AuditEntry.from_dict(payload)


def test_audit_query_response_parses() -> None:
    items = [_audit_entry_payload() for _ in range(2)]
    parsed = AuditQueryResponse.from_dict({"entries": items, "total": 2})
    assert len(parsed.entries) == 2
    assert isinstance(parsed.entries, tuple)
    assert all(isinstance(e, AuditEntry) for e in parsed.entries)


def test_audit_query_response_rejects_non_dict() -> None:
    with pytest.raises(InvalidEnvelopeError, match="expected dict"):
        AuditQueryResponse.from_dict("oops")  # type: ignore[arg-type]


def test_audit_query_response_rejects_missing_entries() -> None:
    with pytest.raises(InvalidEnvelopeError, match="field entries"):
        AuditQueryResponse.from_dict({"total": 0})


def test_audit_query_response_rejects_entries_not_list() -> None:
    with pytest.raises(InvalidEnvelopeError, match="field entries: expected list"):
        AuditQueryResponse.from_dict({"entries": {}, "total": 0})


def test_audit_query_response_bubbles_inner_error() -> None:
    bad = _audit_entry_payload()
    del bad["timestamp"]
    with pytest.raises(InvalidEnvelopeError, match="field timestamp"):
        AuditQueryResponse.from_dict({"entries": [bad], "total": 1})


# ---------------------------------------------------------------------------
# Exception hierarchy
# ---------------------------------------------------------------------------


def test_invalid_envelope_error_is_value_error() -> None:
    """For backwards-compat with code that catches ValueError, the
    parser error subclasses ValueError."""
    assert issubclass(InvalidEnvelopeError, ValueError)


# ---------------------------------------------------------------------------
# Top-level re-export
# ---------------------------------------------------------------------------


def test_envelopes_reexported_from_top_level_verixa() -> None:
    """Customers do `from verixa import WorkflowRegisterResponse` etc;
    these must be in verixa.__all__ so wildcard imports work."""
    import verixa

    for name in (
        "AuditEntry",
        "AuditQueryResponse",
        "InvalidEnvelopeError",
        "WorkflowListResponse",
        "WorkflowRegisterResponse",
        "WorkflowSummary",
    ):
        assert name in verixa.__all__, f"{name} missing from verixa.__all__"
        assert hasattr(verixa, name), f"{name} not importable from verixa"
