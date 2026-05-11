"""CP-61/CP-62 tests for verixa.envelopes -- typed response dataclasses.

Anchored to the v0.4.0 roadmap promise in CHANGELOG: customers can opt
into typed return values instead of plain ``dict[str, Any]``.

CP-61 shipped Workflow + Audit envelopes; CP-62 corrects the server-shape
mismatch in CP-61 (Workflow had description+owner_tenant_id but server
emits sector; Audit had event_type+payload+signature but server emits
decision+risk_score+risk_classification+triad_invoked) and adds Agent +
Tool envelopes.

Tests cover:

  - Positive: valid payloads parse correctly + every field populates
  - Type errors: non-string UUID, non-string datetime, wrong types
  - Missing required fields: each raises InvalidEnvelopeError with the
    field name in the message so customers can debug server-shape bugs
  - Forward-compat: extra fields are IGNORED (server can add fields)
  - Datetime invariants: naive datetimes rejected (Verixa requires TZ)
  - bool-as-int rejection: True/False cannot silently coerce to 1/0
  - List parsing: nested AuditEntry / WorkflowSummary errors bubble up
  - allowed_workflow_ids: tuple-not-list (immutable, parsed per-element)
  - Frozen + slotted: dataclasses are immutable + memory-efficient

The fixture helpers MATCH the server-side envelopes.py wire format
exactly (CP-62 corrected mismatch).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta, timezone

import pytest
from verixa.envelopes import (
    AgentRegisterResponse,
    AuditEntry,
    AuditQueryResponse,
    InvalidEnvelopeError,
    ToolRegisterResponse,
    WorkflowListResponse,
    WorkflowRegisterResponse,
    WorkflowSummary,
)

# ---------------------------------------------------------------------------
# Fixtures (match server-side envelopes.py wire format)
# ---------------------------------------------------------------------------


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _workflow_register_payload(**overrides) -> dict:
    payload = {
        "workflow_id": str(uuid.uuid4()),
        "name": "payments-flow",
        "sector": "financial-services",
        "created_at": _now(),
    }
    payload.update(overrides)
    return payload


def _workflow_summary_payload(**overrides) -> dict:
    payload = {
        "workflow_id": str(uuid.uuid4()),
        "name": "payments-flow",
        "sector": "financial-services",
        "risk_threshold_escalate": 0.5,
        "agent_count": 3,
        "created_at": _now(),
    }
    payload.update(overrides)
    return payload


def _audit_entry_payload(**overrides) -> dict:
    payload = {
        "audit_id": str(uuid.uuid4()),
        "workflow_id": str(uuid.uuid4()),
        "decision": "allow",
        "risk_score": 0.12,
        "risk_classification": "low",
        "triad_invoked": False,
        "timestamp": _now(),
    }
    payload.update(overrides)
    return payload


def _agent_register_payload(**overrides) -> dict:
    payload = {
        "agent_id": str(uuid.uuid4()),
        "workflow_id": str(uuid.uuid4()),
        "spiffe_id": "spiffe://verixa.local/prod/runtime-gateway/pod-1",
        "role": "gateway",
        "created_at": _now(),
    }
    payload.update(overrides)
    return payload


def _tool_register_payload(**overrides) -> dict:
    payload = {
        "tool_id": str(uuid.uuid4()),
        "name": "firewall-checker",
        "is_active": True,
        "allowed_workflow_ids": [],
        "created_at": _now(),
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
    assert parsed.sector == "financial-services"
    assert isinstance(parsed.workflow_id, uuid.UUID)
    assert isinstance(parsed.created_at, datetime)
    assert parsed.created_at.tzinfo is not None


def test_workflow_register_response_ignores_extra_fields() -> None:
    """Server can add new optional fields; SDK forward-compat means
    extra fields are silently ignored, not rejected."""
    payload = _workflow_register_payload(future_field="ignored", extra=42)
    parsed = WorkflowRegisterResponse.from_dict(payload)
    assert parsed.name == "payments-flow"


def test_workflow_register_response_is_frozen() -> None:
    payload = _workflow_register_payload()
    parsed = WorkflowRegisterResponse.from_dict(payload)
    with pytest.raises((AttributeError, TypeError)):
        parsed.name = "mutated"  # type: ignore[misc]


def test_workflow_register_response_uses_slots() -> None:
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
    ["workflow_id", "name", "sector", "created_at"],
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
    wf_uuid = uuid.uuid4()
    payload = _workflow_register_payload(workflow_id=wf_uuid)
    parsed = WorkflowRegisterResponse.from_dict(payload)
    assert parsed.workflow_id == wf_uuid


def test_workflow_register_response_rejects_naive_datetime() -> None:
    naive = datetime(2026, 5, 11, 17, 30, 0).isoformat()
    payload = _workflow_register_payload(created_at=naive)
    with pytest.raises(InvalidEnvelopeError, match="naive"):
        WorkflowRegisterResponse.from_dict(payload)


def test_workflow_register_response_accepts_offset_datetime() -> None:
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
    now = datetime.now(UTC)
    payload = _workflow_register_payload(created_at=now)
    parsed = WorkflowRegisterResponse.from_dict(payload)
    assert parsed.created_at == now


def test_workflow_register_response_rejects_naive_datetime_object() -> None:
    naive = datetime(2026, 5, 11, 17, 30, 0)
    payload = _workflow_register_payload(created_at=naive)
    with pytest.raises(InvalidEnvelopeError, match="naive"):
        WorkflowRegisterResponse.from_dict(payload)


def test_workflow_register_response_rejects_non_string_name() -> None:
    payload = _workflow_register_payload(name=42)
    with pytest.raises(InvalidEnvelopeError, match="field name: expected string"):
        WorkflowRegisterResponse.from_dict(payload)


def test_workflow_register_response_rejects_non_string_sector() -> None:
    payload = _workflow_register_payload(sector=42)
    with pytest.raises(InvalidEnvelopeError, match="field sector: expected string"):
        WorkflowRegisterResponse.from_dict(payload)


# ---------------------------------------------------------------------------
# WorkflowSummary + WorkflowListResponse
# ---------------------------------------------------------------------------


def test_workflow_summary_parses() -> None:
    parsed = WorkflowSummary.from_dict(_workflow_summary_payload())
    assert parsed.name == "payments-flow"
    assert parsed.sector == "financial-services"
    assert parsed.risk_threshold_escalate == 0.5
    assert parsed.agent_count == 3


def test_workflow_summary_accepts_int_for_risk_threshold() -> None:
    """0 and 1 are valid float scores but serialise as JSON ints
    sometimes; the float parser must accept int values."""
    payload = _workflow_summary_payload(risk_threshold_escalate=1)
    parsed = WorkflowSummary.from_dict(payload)
    assert parsed.risk_threshold_escalate == 1.0
    assert isinstance(parsed.risk_threshold_escalate, float)


def test_workflow_summary_rejects_bool_for_risk_threshold() -> None:
    """True/False would silently coerce to 1.0/0.0 via int -> float.
    Reject explicitly."""
    payload = _workflow_summary_payload(risk_threshold_escalate=True)
    with pytest.raises(InvalidEnvelopeError, match="expected number, got bool"):
        WorkflowSummary.from_dict(payload)


def test_workflow_summary_rejects_string_for_risk_threshold() -> None:
    payload = _workflow_summary_payload(risk_threshold_escalate="0.5")
    with pytest.raises(InvalidEnvelopeError, match="expected number"):
        WorkflowSummary.from_dict(payload)


def test_workflow_summary_rejects_bool_for_agent_count() -> None:
    payload = _workflow_summary_payload(agent_count=True)
    with pytest.raises(InvalidEnvelopeError, match="expected int"):
        WorkflowSummary.from_dict(payload)


def test_workflow_summary_rejects_non_dict() -> None:
    with pytest.raises(InvalidEnvelopeError, match="expected dict"):
        WorkflowSummary.from_dict("oops")  # type: ignore[arg-type]


def test_workflow_list_response_parses_empty() -> None:
    parsed = WorkflowListResponse.from_dict({"workflows": [], "total": 0})
    assert parsed.workflows == ()
    assert parsed.total == 0


def test_workflow_list_response_parses_multiple() -> None:
    items = [_workflow_summary_payload() for _ in range(3)]
    parsed = WorkflowListResponse.from_dict({"workflows": items, "total": 3})
    assert len(parsed.workflows) == 3
    assert parsed.total == 3
    assert all(isinstance(w, WorkflowSummary) for w in parsed.workflows)


def test_workflow_list_response_returns_tuple_not_list() -> None:
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
    with pytest.raises(InvalidEnvelopeError, match="field total: expected int"):
        WorkflowListResponse.from_dict({"workflows": [], "total": True})


def test_workflow_list_response_bubbles_inner_error() -> None:
    bad = _workflow_summary_payload()
    del bad["name"]
    with pytest.raises(InvalidEnvelopeError, match="field name"):
        WorkflowListResponse.from_dict({"workflows": [bad], "total": 1})


# ---------------------------------------------------------------------------
# AuditEntry + AuditQueryResponse
# ---------------------------------------------------------------------------


def test_audit_entry_parses() -> None:
    parsed = AuditEntry.from_dict(_audit_entry_payload())
    assert parsed.decision == "allow"
    assert parsed.risk_score == 0.12
    assert parsed.risk_classification == "low"
    assert parsed.triad_invoked is False
    assert isinstance(parsed.timestamp, datetime)


def test_audit_entry_accepts_triad_invoked_true() -> None:
    parsed = AuditEntry.from_dict(_audit_entry_payload(triad_invoked=True))
    assert parsed.triad_invoked is True


def test_audit_entry_rejects_bool_for_risk_score() -> None:
    """risk_score is a float in [0,1]; True/False would coerce to 1.0/0.0."""
    payload = _audit_entry_payload(risk_score=True)
    with pytest.raises(InvalidEnvelopeError, match="expected number, got bool"):
        AuditEntry.from_dict(payload)


def test_audit_entry_rejects_string_for_triad_invoked() -> None:
    """triad_invoked is strictly bool; reject 'true' / '1' / 1."""
    for bad_value in ("true", "1", 1):
        payload = _audit_entry_payload(triad_invoked=bad_value)
        with pytest.raises(InvalidEnvelopeError, match="expected bool"):
            AuditEntry.from_dict(payload)


def test_audit_entry_rejects_non_dict() -> None:
    with pytest.raises(InvalidEnvelopeError, match="expected dict"):
        AuditEntry.from_dict(42)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "missing_key",
    [
        "audit_id",
        "workflow_id",
        "decision",
        "risk_score",
        "risk_classification",
        "triad_invoked",
        "timestamp",
    ],
)
def test_audit_entry_rejects_missing_required(missing_key: str) -> None:
    payload = _audit_entry_payload()
    del payload[missing_key]
    with pytest.raises(InvalidEnvelopeError, match=f"field {missing_key}"):
        AuditEntry.from_dict(payload)


def test_audit_query_response_parses() -> None:
    workflow_id = str(uuid.uuid4())
    items = [_audit_entry_payload() for _ in range(2)]
    parsed = AuditQueryResponse.from_dict({
        "entries": items,
        "total": 2,
        "workflow_id": workflow_id,
        "from_timestamp": _now(),
        "to_timestamp": _now(),
    })
    assert len(parsed.entries) == 2
    assert isinstance(parsed.entries, tuple)
    assert all(isinstance(e, AuditEntry) for e in parsed.entries)
    assert parsed.workflow_id == uuid.UUID(workflow_id)
    assert isinstance(parsed.from_timestamp, datetime)
    assert isinstance(parsed.to_timestamp, datetime)


def test_audit_query_response_rejects_non_dict() -> None:
    with pytest.raises(InvalidEnvelopeError, match="expected dict"):
        AuditQueryResponse.from_dict("oops")  # type: ignore[arg-type]


def test_audit_query_response_rejects_missing_entries() -> None:
    with pytest.raises(InvalidEnvelopeError, match="field entries"):
        AuditQueryResponse.from_dict({
            "total": 0,
            "workflow_id": str(uuid.uuid4()),
            "from_timestamp": _now(),
            "to_timestamp": _now(),
        })


def test_audit_query_response_rejects_entries_not_list() -> None:
    with pytest.raises(InvalidEnvelopeError, match="field entries: expected list"):
        AuditQueryResponse.from_dict({
            "entries": {},
            "total": 0,
            "workflow_id": str(uuid.uuid4()),
            "from_timestamp": _now(),
            "to_timestamp": _now(),
        })


def test_audit_query_response_rejects_missing_workflow_id() -> None:
    with pytest.raises(InvalidEnvelopeError, match="field workflow_id"):
        AuditQueryResponse.from_dict({
            "entries": [],
            "total": 0,
            "from_timestamp": _now(),
            "to_timestamp": _now(),
        })


def test_audit_query_response_bubbles_inner_error() -> None:
    bad = _audit_entry_payload()
    del bad["timestamp"]
    with pytest.raises(InvalidEnvelopeError, match="field timestamp"):
        AuditQueryResponse.from_dict({
            "entries": [bad],
            "total": 1,
            "workflow_id": str(uuid.uuid4()),
            "from_timestamp": _now(),
            "to_timestamp": _now(),
        })


# ---------------------------------------------------------------------------
# AgentRegisterResponse (CP-62)
# ---------------------------------------------------------------------------


def test_agent_register_response_parses() -> None:
    parsed = AgentRegisterResponse.from_dict(_agent_register_payload())
    assert parsed.role == "gateway"
    assert parsed.spiffe_id.startswith("spiffe://verixa.local/")
    assert isinstance(parsed.agent_id, uuid.UUID)
    assert isinstance(parsed.workflow_id, uuid.UUID)
    assert isinstance(parsed.created_at, datetime)


def test_agent_register_response_ignores_extra_fields() -> None:
    parsed = AgentRegisterResponse.from_dict(
        _agent_register_payload(future_field=42)
    )
    assert parsed.role == "gateway"


def test_agent_register_response_is_frozen() -> None:
    parsed = AgentRegisterResponse.from_dict(_agent_register_payload())
    with pytest.raises((AttributeError, TypeError)):
        parsed.role = "mutated"  # type: ignore[misc]


def test_agent_register_response_rejects_non_dict() -> None:
    with pytest.raises(InvalidEnvelopeError, match="expected dict"):
        AgentRegisterResponse.from_dict(["x"])  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "missing_key",
    ["agent_id", "workflow_id", "spiffe_id", "role", "created_at"],
)
def test_agent_register_response_rejects_missing_required(missing_key: str) -> None:
    payload = _agent_register_payload()
    del payload[missing_key]
    with pytest.raises(InvalidEnvelopeError, match=f"field {missing_key}"):
        AgentRegisterResponse.from_dict(payload)


def test_agent_register_response_rejects_non_string_spiffe_id() -> None:
    payload = _agent_register_payload(spiffe_id=42)
    with pytest.raises(InvalidEnvelopeError, match="field spiffe_id"):
        AgentRegisterResponse.from_dict(payload)


def test_agent_register_response_rejects_invalid_uuid() -> None:
    payload = _agent_register_payload(agent_id="not-a-uuid")
    with pytest.raises(InvalidEnvelopeError, match="not a valid UUID"):
        AgentRegisterResponse.from_dict(payload)


# ---------------------------------------------------------------------------
# ToolRegisterResponse (CP-62)
# ---------------------------------------------------------------------------


def test_tool_register_response_parses_empty_allowed_workflows() -> None:
    """Empty allowed_workflow_ids means 'any workflow' per server-side
    docstring; parser MUST accept this case."""
    parsed = ToolRegisterResponse.from_dict(_tool_register_payload())
    assert parsed.name == "firewall-checker"
    assert parsed.is_active is True
    assert parsed.allowed_workflow_ids == ()
    assert isinstance(parsed.allowed_workflow_ids, tuple)


def test_tool_register_response_parses_with_workflows() -> None:
    wf1 = str(uuid.uuid4())
    wf2 = str(uuid.uuid4())
    parsed = ToolRegisterResponse.from_dict(
        _tool_register_payload(allowed_workflow_ids=[wf1, wf2])
    )
    assert len(parsed.allowed_workflow_ids) == 2
    assert all(isinstance(w, uuid.UUID) for w in parsed.allowed_workflow_ids)
    assert parsed.allowed_workflow_ids[0] == uuid.UUID(wf1)


def test_tool_register_response_returns_tuple_not_list() -> None:
    """Immutability: customer code cannot mutate the parsed list."""
    parsed = ToolRegisterResponse.from_dict(
        _tool_register_payload(allowed_workflow_ids=[str(uuid.uuid4())])
    )
    assert isinstance(parsed.allowed_workflow_ids, tuple)


def test_tool_register_response_rejects_non_list_allowed_workflows() -> None:
    payload = _tool_register_payload(allowed_workflow_ids="not-a-list")
    with pytest.raises(InvalidEnvelopeError, match="expected list of uuids"):
        ToolRegisterResponse.from_dict(payload)


def test_tool_register_response_rejects_invalid_uuid_in_list() -> None:
    """Per-element UUID validation: an invalid UUID in the list MUST
    surface with the index in the field name for debuggability."""
    payload = _tool_register_payload(
        allowed_workflow_ids=[str(uuid.uuid4()), "not-a-uuid"]
    )
    with pytest.raises(
        InvalidEnvelopeError, match=r"allowed_workflow_ids\[1\]"
    ):
        ToolRegisterResponse.from_dict(payload)


def test_tool_register_response_rejects_int_for_is_active() -> None:
    payload = _tool_register_payload(is_active=1)
    with pytest.raises(InvalidEnvelopeError, match="field is_active: expected bool"):
        ToolRegisterResponse.from_dict(payload)


def test_tool_register_response_accepts_is_active_false() -> None:
    parsed = ToolRegisterResponse.from_dict(_tool_register_payload(is_active=False))
    assert parsed.is_active is False


def test_tool_register_response_rejects_non_dict() -> None:
    with pytest.raises(InvalidEnvelopeError, match="expected dict"):
        ToolRegisterResponse.from_dict(42)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "missing_key",
    ["tool_id", "name", "is_active", "allowed_workflow_ids", "created_at"],
)
def test_tool_register_response_rejects_missing_required(missing_key: str) -> None:
    payload = _tool_register_payload()
    del payload[missing_key]
    with pytest.raises(InvalidEnvelopeError, match=f"field {missing_key}"):
        ToolRegisterResponse.from_dict(payload)


def test_tool_register_response_is_frozen() -> None:
    parsed = ToolRegisterResponse.from_dict(_tool_register_payload())
    with pytest.raises((AttributeError, TypeError)):
        parsed.name = "mutated"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Exception hierarchy
# ---------------------------------------------------------------------------


def test_invalid_envelope_error_is_value_error() -> None:
    assert issubclass(InvalidEnvelopeError, ValueError)


# ---------------------------------------------------------------------------
# Top-level re-export
# ---------------------------------------------------------------------------


def test_envelopes_reexported_from_top_level_verixa() -> None:
    """Customers do `from verixa import ...` for typed envelopes."""
    import verixa

    for name in (
        "AgentRegisterResponse",
        "AuditEntry",
        "AuditQueryResponse",
        "InvalidEnvelopeError",
        "ToolRegisterResponse",
        "WorkflowListResponse",
        "WorkflowRegisterResponse",
        "WorkflowSummary",
    ):
        assert name in verixa.__all__, f"{name} missing from verixa.__all__"
        assert hasattr(verixa, name), f"{name} not importable from verixa"
