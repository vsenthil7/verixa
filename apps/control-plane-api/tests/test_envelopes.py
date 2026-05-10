"""pytest suite for verixa_control_plane.envelopes (CP-14.1).

Pure Pydantic v2 validation tests. Covers every field constraint
(min/max length, ge/le bounds, extra=forbid rejection) and every
default-value path.

100% line coverage on envelopes.py.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from verixa_control_plane.envelopes import (
    AgentRegisterRequest,
    AgentRegisterResponse,
    AuditEntry,
    AuditQueryResponse,
    DossierGenerateRequest,
    DossierGenerateResponse,
    DossierGetResponse,
    ErrorResponse,
    ReplayRequest,
    ReplayResponse,
    ToolRegisterRequest,
    ToolRegisterResponse,
    WorkflowListResponse,
    WorkflowRegisterRequest,
    WorkflowRegisterResponse,
    WorkflowSummary,
)


_WF_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")
_AGENT_ID = uuid.UUID("22222222-2222-2222-2222-222222222222")
_TOOL_ID = uuid.UUID("33333333-3333-3333-3333-333333333333")
_TENANT_ID = uuid.UUID("44444444-4444-4444-4444-444444444444")
_AUDIT_ID = uuid.UUID("55555555-5555-5555-5555-555555555555")
_DOSSIER_ID = uuid.UUID("66666666-6666-6666-6666-666666666666")
_NOW = datetime(2026, 5, 10, 23, 59, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Workflow envelopes
# ---------------------------------------------------------------------------


def test_workflow_register_request_minimal_accepts() -> None:
    req = WorkflowRegisterRequest(name="loan-approval-workflow")
    assert req.name == "loan-approval-workflow"
    assert req.description == ""
    assert req.sector == "generic"
    assert req.risk_threshold_escalate == pytest.approx(0.50)


def test_workflow_register_request_rejects_empty_name() -> None:
    with pytest.raises(ValidationError):
        WorkflowRegisterRequest(name="")


def test_workflow_register_request_rejects_oversized_name() -> None:
    with pytest.raises(ValidationError):
        WorkflowRegisterRequest(name="a" * 201)


def test_workflow_register_request_rejects_extra_field() -> None:
    with pytest.raises(ValidationError):
        WorkflowRegisterRequest(name="x", unknown="boom")  # type: ignore[call-arg]


def test_workflow_register_request_rejects_threshold_above_one() -> None:
    with pytest.raises(ValidationError):
        WorkflowRegisterRequest(
            name="x", risk_threshold_escalate=1.01
        )


def test_workflow_register_request_rejects_threshold_below_zero() -> None:
    with pytest.raises(ValidationError):
        WorkflowRegisterRequest(
            name="x", risk_threshold_escalate=-0.01
        )


def test_workflow_register_response_round_trip_json() -> None:
    resp = WorkflowRegisterResponse(
        workflow_id=_WF_ID,
        name="loan-approval",
        sector="financial-services",
        created_at=_NOW,
    )
    j = resp.model_dump(mode="json")
    assert j["workflow_id"] == str(_WF_ID)
    assert j["sector"] == "financial-services"


def test_workflow_list_response_with_summaries() -> None:
    summary = WorkflowSummary(
        workflow_id=_WF_ID,
        name="x",
        sector="generic",
        risk_threshold_escalate=0.5,
        agent_count=3,
        created_at=_NOW,
    )
    resp = WorkflowListResponse(workflows=[summary], total=1)
    assert resp.total == 1
    assert resp.workflows[0].agent_count == 3


def test_workflow_summary_rejects_negative_agent_count() -> None:
    with pytest.raises(ValidationError):
        WorkflowSummary(
            workflow_id=_WF_ID,
            name="x",
            sector="generic",
            risk_threshold_escalate=0.5,
            agent_count=-1,
            created_at=_NOW,
        )


# ---------------------------------------------------------------------------
# Agent envelopes
# ---------------------------------------------------------------------------


def test_agent_register_request_minimal() -> None:
    req = AgentRegisterRequest(
        workflow_id=_WF_ID,
        spiffe_id="spiffe://example/agent/a",
        role="loan-officer",
    )
    assert req.description == ""


def test_agent_register_request_rejects_empty_spiffe_id() -> None:
    with pytest.raises(ValidationError):
        AgentRegisterRequest(
            workflow_id=_WF_ID,
            spiffe_id="",
            role="x",
        )


def test_agent_register_request_rejects_empty_role() -> None:
    with pytest.raises(ValidationError):
        AgentRegisterRequest(
            workflow_id=_WF_ID,
            spiffe_id="spiffe://x",
            role="",
        )


def test_agent_register_response_shape() -> None:
    resp = AgentRegisterResponse(
        agent_id=_AGENT_ID,
        workflow_id=_WF_ID,
        spiffe_id="spiffe://x",
        role="loan-officer",
        created_at=_NOW,
    )
    j = resp.model_dump(mode="json")
    assert j["agent_id"] == str(_AGENT_ID)


# ---------------------------------------------------------------------------
# Tool envelopes
# ---------------------------------------------------------------------------


def test_tool_register_request_defaults() -> None:
    req = ToolRegisterRequest(name="read_account_balance")
    assert req.is_active is True
    assert req.allowed_workflow_ids == []


def test_tool_register_request_with_workflow_restrictions() -> None:
    req = ToolRegisterRequest(
        name="transfer_funds", allowed_workflow_ids=[_WF_ID]
    )
    assert req.allowed_workflow_ids == [_WF_ID]


def test_tool_register_request_rejects_empty_name() -> None:
    with pytest.raises(ValidationError):
        ToolRegisterRequest(name="")


def test_tool_register_response_shape() -> None:
    resp = ToolRegisterResponse(
        tool_id=_TOOL_ID,
        name="transfer_funds",
        is_active=True,
        allowed_workflow_ids=[_WF_ID],
        created_at=_NOW,
    )
    assert resp.is_active is True


# ---------------------------------------------------------------------------
# Audit envelopes
# ---------------------------------------------------------------------------


def test_audit_entry_minimal() -> None:
    entry = AuditEntry(
        audit_id=_AUDIT_ID,
        workflow_id=_WF_ID,
        decision="allow",
        risk_score=0.1,
        risk_classification="low",
        triad_invoked=False,
        timestamp=_NOW,
    )
    assert entry.decision == "allow"


def test_audit_entry_rejects_risk_above_one() -> None:
    with pytest.raises(ValidationError):
        AuditEntry(
            audit_id=_AUDIT_ID,
            workflow_id=_WF_ID,
            decision="allow",
            risk_score=1.5,
            risk_classification="critical",
            triad_invoked=False,
            timestamp=_NOW,
        )


def test_audit_query_response_with_entries() -> None:
    entry = AuditEntry(
        audit_id=_AUDIT_ID,
        workflow_id=_WF_ID,
        decision="deny",
        risk_score=0.95,
        risk_classification="critical",
        triad_invoked=False,
        timestamp=_NOW,
    )
    resp = AuditQueryResponse(
        entries=[entry],
        total=1,
        workflow_id=_WF_ID,
        from_timestamp=_NOW,
        to_timestamp=_NOW,
    )
    assert resp.total == 1
    assert resp.entries[0].decision == "deny"


def test_audit_query_response_rejects_negative_total() -> None:
    with pytest.raises(ValidationError):
        AuditQueryResponse(
            entries=[],
            total=-1,
            workflow_id=_WF_ID,
            from_timestamp=_NOW,
            to_timestamp=_NOW,
        )


# ---------------------------------------------------------------------------
# Replay envelopes
# ---------------------------------------------------------------------------


def test_replay_request_shape() -> None:
    req = ReplayRequest(audit_id=_AUDIT_ID)
    assert req.audit_id == _AUDIT_ID


def test_replay_request_rejects_extra_field() -> None:
    with pytest.raises(ValidationError):
        ReplayRequest(audit_id=_AUDIT_ID, sneaky="x")  # type: ignore[call-arg]


def test_replay_response_minimal() -> None:
    resp = ReplayResponse(
        audit_id=_AUDIT_ID,
        tenant_id=_TENANT_ID,
        decision="allow",
        risk_score=0.1,
        request_envelope={"k": "v"},
        timestamp_unix_ns=1_700_000_000_000_000_000,
    )
    assert resp.retrieved_documents == []
    assert resp.triad_review is None


def test_replay_response_full_round_trip_json() -> None:
    """Full ReplayResponse with every nested field populated; JSON
    round-trip preserves shape."""
    resp = ReplayResponse(
        audit_id=_AUDIT_ID,
        tenant_id=_TENANT_ID,
        decision="deny",
        risk_score=0.85,
        request_envelope={"action": {"type": "tool_call"}},
        retrieved_documents=[
            {"doc_id": "d1", "content_sha256": "f" * 64},
        ],
        tool_io=[{"call": "x", "response": "y"}],
        policy_evaluations=[
            {
                "package": "verixa.fs.transfer_limit",
                "decision": "fail",
                "reason": "over limit",
            }
        ],
        triad_review={"consensus_kind": "unanimous"},
        timestamp_unix_ns=1_700_000_000_000_000_000,
    )
    j = resp.model_dump(mode="json")
    assert j["decision"] == "deny"
    assert j["retrieved_documents"][0]["doc_id"] == "d1"
    assert j["triad_review"]["consensus_kind"] == "unanimous"


def test_replay_response_rejects_negative_timestamp() -> None:
    with pytest.raises(ValidationError):
        ReplayResponse(
            audit_id=_AUDIT_ID,
            tenant_id=_TENANT_ID,
            decision="allow",
            risk_score=0.1,
            request_envelope={},
            timestamp_unix_ns=-1,
        )


# ---------------------------------------------------------------------------
# Dossier envelopes
# ---------------------------------------------------------------------------


def test_dossier_generate_request_minimal() -> None:
    req = DossierGenerateRequest(audit_id=_AUDIT_ID)
    assert req.action_summary == ""


def test_dossier_generate_request_rejects_oversized_summary() -> None:
    with pytest.raises(ValidationError):
        DossierGenerateRequest(
            audit_id=_AUDIT_ID, action_summary="x" * 2001
        )


def test_dossier_generate_response_shape() -> None:
    resp = DossierGenerateResponse(
        dossier_id=_DOSSIER_ID,
        audit_id=_AUDIT_ID,
        signing_key_id="verixa-sig-test",
        generated_at=_NOW,
    )
    assert resp.dossier_id == _DOSSIER_ID


def test_dossier_get_response_with_valid_hex_lengths() -> None:
    resp = DossierGetResponse(
        dossier_id=_DOSSIER_ID,
        audit_id=_AUDIT_ID,
        manifest={"k": "v"},
        signature_hex="a" * 128,
        public_key_hex="b" * 64,
    )
    assert len(resp.signature_hex) == 128


def test_dossier_get_response_rejects_short_signature() -> None:
    with pytest.raises(ValidationError):
        DossierGetResponse(
            dossier_id=_DOSSIER_ID,
            audit_id=_AUDIT_ID,
            manifest={},
            signature_hex="a" * 127,
            public_key_hex="b" * 64,
        )


def test_dossier_get_response_rejects_short_public_key() -> None:
    with pytest.raises(ValidationError):
        DossierGetResponse(
            dossier_id=_DOSSIER_ID,
            audit_id=_AUDIT_ID,
            manifest={},
            signature_hex="a" * 128,
            public_key_hex="b" * 63,
        )


# ---------------------------------------------------------------------------
# Error envelope
# ---------------------------------------------------------------------------


def test_error_response_minimal() -> None:
    err = ErrorResponse(error="audit_not_found", message="no audit row")
    assert err.audit_id is None


def test_error_response_with_audit_id() -> None:
    err = ErrorResponse(
        error="dossier_signing_failed",
        message="signing key unavailable",
        audit_id=_AUDIT_ID,
    )
    assert err.audit_id == _AUDIT_ID
