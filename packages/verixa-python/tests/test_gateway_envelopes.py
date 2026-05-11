"""pytest suite for verixa_runtime.gateway.envelopes (CP-6.1).

100% line + branch coverage on the envelope module. Validates request
parsing for the happy path + every constraint violation, plus response
shape for all three decision variants.
"""

from __future__ import annotations

import uuid

import pytest
from pydantic import ValidationError
from verixa_runtime.gateway.envelopes import (
    AgentIdentity,
    Decision,
    GovernAction,
    GovernContext,
    GovernRequest,
    GovernResponse,
    PolicyAppliedResult,
    PolicyResult,
    RetrievedDocument,
    RiskClassification,
)

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


def test_decision_values() -> None:
    assert Decision.ALLOW.value == "allow"
    assert Decision.DENY.value == "deny"
    assert Decision.ESCALATE.value == "escalate"


def test_risk_classification_values() -> None:
    assert {r.value for r in RiskClassification} == {
        "low", "medium", "high", "critical"
    }


def test_policy_result_values() -> None:
    assert {r.value for r in PolicyResult} == {"pass", "fail", "abstain"}


# ---------------------------------------------------------------------------
# AgentIdentity
# ---------------------------------------------------------------------------


def _wf_id() -> uuid.UUID:
    return uuid.UUID("22222222-2222-2222-2222-222222222222")


def test_agent_identity_happy() -> None:
    a = AgentIdentity(
        spiffe_id="spiffe://example/agent/x",
        role="loan-officer",
        workflow_id=_wf_id(),
    )
    assert a.role == "loan-officer"
    assert a.workflow_id == _wf_id()


def test_agent_identity_rejects_extra_field() -> None:
    with pytest.raises(ValidationError):
        AgentIdentity(
            spiffe_id="spiffe://x",
            role="r",
            workflow_id=_wf_id(),
            unknown_field="boom",  # type: ignore[call-arg]
        )


def test_agent_identity_rejects_empty_spiffe() -> None:
    with pytest.raises(ValidationError):
        AgentIdentity(spiffe_id="", role="r", workflow_id=_wf_id())


def test_agent_identity_rejects_empty_role() -> None:
    with pytest.raises(ValidationError):
        AgentIdentity(spiffe_id="x", role="", workflow_id=_wf_id())


# ---------------------------------------------------------------------------
# GovernAction
# ---------------------------------------------------------------------------


def test_govern_action_default_arguments_is_empty_dict() -> None:
    act = GovernAction(type="tool_call", tool_name="t")
    assert act.arguments == {}


@pytest.mark.parametrize(
    "kind",
    ["tool_call", "model_invocation", "data_access", "external_api"],
)
def test_govern_action_accepts_all_known_types(kind: str) -> None:
    act = GovernAction.model_validate({"type": kind, "tool_name": "x"})
    assert act.type == kind


def test_govern_action_rejects_unknown_type() -> None:
    with pytest.raises(ValidationError):
        GovernAction.model_validate({"type": "telepathy"})


# ---------------------------------------------------------------------------
# RetrievedDocument
# ---------------------------------------------------------------------------


def test_retrieved_document_happy() -> None:
    rd = RetrievedDocument(doc_id="doc_001", hash="a" * 64)
    assert rd.doc_id == "doc_001"


def test_retrieved_document_rejects_short_hash() -> None:
    with pytest.raises(ValidationError):
        RetrievedDocument(doc_id="x", hash="ab")


def test_retrieved_document_rejects_non_hex_hash() -> None:
    with pytest.raises(ValidationError):
        RetrievedDocument(doc_id="x", hash="z" * 64)


# ---------------------------------------------------------------------------
# GovernContext
# ---------------------------------------------------------------------------


def test_govern_context_happy() -> None:
    ctx = GovernContext(
        prompt_hash="b" * 64,
        retrieved_documents=[
            RetrievedDocument(doc_id="d1", hash="c" * 64),
        ],
        model_version="qwen3-72b@2025-12-01",
        reasoning_chain_summary="brief reasoning",
        workflow_state="pending",
    )
    assert len(ctx.retrieved_documents) == 1


def test_govern_context_default_empty_documents() -> None:
    ctx = GovernContext(prompt_hash="b" * 64, model_version="m")
    assert ctx.retrieved_documents == []


def test_govern_context_rejects_short_prompt_hash() -> None:
    with pytest.raises(ValidationError):
        GovernContext(prompt_hash="ab", model_version="m")


# ---------------------------------------------------------------------------
# GovernRequest — full happy + invalid
# ---------------------------------------------------------------------------


def _full_request() -> GovernRequest:
    return GovernRequest(
        agent_identity=AgentIdentity(
            spiffe_id="spiffe://x", role="r", workflow_id=_wf_id()
        ),
        action=GovernAction(type="tool_call", tool_name="transfer_funds"),
        context=GovernContext(prompt_hash="b" * 64, model_version="m"),
        trace_id="01HW...",
    )


def test_govern_request_happy() -> None:
    req = _full_request()
    assert req.action.tool_name == "transfer_funds"
    assert req.trace_id == "01HW..."


def test_govern_request_rejects_extra_top_level_field() -> None:
    with pytest.raises(ValidationError):
        GovernRequest.model_validate(
            {
                "agent_identity": {
                    "spiffe_id": "x",
                    "role": "r",
                    "workflow_id": str(_wf_id()),
                },
                "action": {"type": "tool_call"},
                "context": {"prompt_hash": "b" * 64, "model_version": "m"},
                "trace_id": "t",
                "extra": "boom",
            }
        )


def test_govern_request_rejects_empty_trace_id() -> None:
    with pytest.raises(ValidationError):
        GovernRequest(
            agent_identity=AgentIdentity(
                spiffe_id="x", role="r", workflow_id=_wf_id()
            ),
            action=GovernAction(type="tool_call"),
            context=GovernContext(prompt_hash="b" * 64, model_version="m"),
            trace_id="",
        )


# ---------------------------------------------------------------------------
# GovernResponse — three decision variants
# ---------------------------------------------------------------------------


def test_response_allow_minimum_fields() -> None:
    resp = GovernResponse(
        decision=Decision.ALLOW,
        audit_id=uuid.uuid4(),
        risk_score=0.23,
        risk_classification=RiskClassification.LOW,
        latency_ms=38,
        policies_applied=[
            PolicyAppliedResult(
                id="fs.transfer.amount_limit_v3",
                result=PolicyResult.PASS,
            )
        ],
        triad_invoked=False,
    )
    assert resp.decision == Decision.ALLOW
    assert resp.policies_applied[0].result == PolicyResult.PASS


def test_response_deny_with_remediation() -> None:
    resp = GovernResponse(
        decision=Decision.DENY,
        audit_id=uuid.uuid4(),
        risk_score=0.91,
        risk_classification=RiskClassification.HIGH,
        latency_ms=42,
        reason="hard_policy_breach",
        policy_id="fs.transfer.amount_limit_v3",
        policy_message="Transfer £15000 exceeds role limit £10000",
        remediation_suggestion="Escalate or split below £10000",
    )
    assert resp.decision == Decision.DENY
    assert resp.reason == "hard_policy_breach"


def test_response_escalate_with_status_url() -> None:
    resp = GovernResponse(
        decision=Decision.ESCALATE,
        audit_id=uuid.uuid4(),
        risk_score=0.78,
        risk_classification=RiskClassification.HIGH,
        latency_ms=847,
        triad_invoked=True,
        triad_consensus="2_safe_1_unsafe",
        escalation_target="human_review",
        escalation_id=uuid.uuid4(),
        estimated_review_time_minutes=15,
        status_check_url="/v1/runtime/escalation/esc_01J0",
    )
    assert resp.decision == Decision.ESCALATE
    assert resp.triad_invoked is True


@pytest.mark.parametrize("bad", [-0.001, 1.001, 2.0])
def test_response_rejects_out_of_range_risk(bad: float) -> None:
    with pytest.raises(ValidationError):
        GovernResponse(
            decision=Decision.ALLOW,
            audit_id=uuid.uuid4(),
            risk_score=bad,
            risk_classification=RiskClassification.LOW,
            latency_ms=10,
        )


def test_response_rejects_negative_latency() -> None:
    with pytest.raises(ValidationError):
        GovernResponse(
            decision=Decision.ALLOW,
            audit_id=uuid.uuid4(),
            risk_score=0.1,
            risk_classification=RiskClassification.LOW,
            latency_ms=-1,
        )


def test_response_policies_applied_none_coerced_to_empty_list() -> None:
    resp = GovernResponse.model_validate(
        {
            "decision": "allow",
            "audit_id": str(uuid.uuid4()),
            "risk_score": 0.1,
            "risk_classification": "low",
            "latency_ms": 10,
            "policies_applied": None,
        }
    )
    assert resp.policies_applied == []


# ---------------------------------------------------------------------------
# Public API surface
# ---------------------------------------------------------------------------


def test_gateway_package_reexports() -> None:
    from verixa_runtime import gateway

    for name in (
        "AgentIdentity",
        "Decision",
        "GovernAction",
        "GovernContext",
        "GovernRequest",
        "GovernResponse",
        "PolicyResult",
        "RiskClassification",
    ):
        assert hasattr(gateway, name), f"gateway package missing {name}"
