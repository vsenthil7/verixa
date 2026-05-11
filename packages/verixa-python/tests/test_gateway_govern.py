"""pytest suite for verixa_runtime.gateway.govern (CP-6.2 + CP-6.4 + CP-9.2).

Three layers:

  1. Pure ``decide_phase0`` -- 9 unit tests pinning the legacy CP-6.2
     stub. CP-9.2 retains the function unchanged so these still pass.
  2. Pure ``decide_via_router`` -- CP-9.2 unit test that injects an
     ABSTAIN policy decision to prove R3 (escalate) is reachable
     without HTTP/OPA wiring (CP-12 supplies real OPA).
  3. Endpoint via FastAPI TestClient -- CP-9.2 dispatches via
     ``decide_via_router``. Registered tools (read_account_balance,
     transfer_funds, ...) return ALLOW; unregistered tools (e.g.
     shutdown_production) deny via firewall.tool_not_registered.

100% line + branch coverage on gateway/govern.py and gateway/__init__.py.
"""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from verixa_runtime.app import create_app
from verixa_runtime.gateway import (
    AgentIdentity,
    Decision,
    GovernAction,
    GovernContext,
    GovernRequest,
    PolicyResult,
    RiskClassification,
    decide_phase0,
    decide_via_router,
)
from verixa_runtime.policy.client import PolicyDecision, PolicyDecisionKind

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


TEST_API_KEY = "test-key-govern"
TEST_TENANT_ID = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaa01")


@pytest.fixture
def client() -> TestClient:
    app = create_app(api_keys={TEST_API_KEY: TEST_TENANT_ID})
    return TestClient(app)


@pytest.fixture
def auth_headers() -> dict[str, str]:
    return {"X-Verixa-API-Key": TEST_API_KEY}


def _wf_id() -> uuid.UUID:
    return uuid.UUID("22222222-2222-2222-2222-222222222222")


def _request_for_tool(tool_name: str | None) -> GovernRequest:
    action_kwargs: dict[str, object] = {"type": "tool_call"}
    if tool_name is not None:
        action_kwargs["tool_name"] = tool_name
    return GovernRequest(
        agent_identity=AgentIdentity(
            spiffe_id="spiffe://example/agent/x",
            role="loan-officer",
            workflow_id=_wf_id(),
        ),
        action=GovernAction(**action_kwargs),
        context=GovernContext(
            prompt_hash="b" * 64,
            model_version="qwen3-72b",
        ),
        trace_id="01HW",
    )


def _request_payload_for_tool(tool_name: str | None) -> dict:
    return {
        "agent_identity": {
            "spiffe_id": "spiffe://example/agent/x",
            "role": "loan-officer",
            "workflow_id": str(_wf_id()),
        },
        "action": {
            "type": "tool_call",
            **({"tool_name": tool_name} if tool_name is not None else {}),
        },
        "context": {
            "prompt_hash": "b" * 64,
            "model_version": "qwen3-72b",
        },
        "trace_id": "01HW",
    }


# ---------------------------------------------------------------------------
# decide_phase0 -- pure function (CP-6.2 legacy stub, retained unchanged)
# ---------------------------------------------------------------------------


def test_decide_phase0_default_allow() -> None:
    resp = decide_phase0(_request_for_tool("read_account_balance"))
    assert resp.decision == Decision.ALLOW
    assert resp.risk_classification == RiskClassification.LOW
    assert resp.risk_score == pytest.approx(0.10)
    assert resp.triad_invoked is False
    assert len(resp.policies_applied) == 1
    assert resp.policies_applied[0].id == "phase0.stub.default_allow"
    assert resp.policies_applied[0].result == PolicyResult.PASS


def test_decide_phase0_no_tool_name_defaults_to_allow() -> None:
    """Action with no tool_name falls into the default-allow branch."""
    resp = decide_phase0(_request_for_tool(None))
    assert resp.decision == Decision.ALLOW


def test_decide_phase0_deny_list() -> None:
    resp = decide_phase0(_request_for_tool("shutdown_production"))
    assert resp.decision == Decision.DENY
    assert resp.risk_classification == RiskClassification.CRITICAL
    assert resp.risk_score == pytest.approx(0.95)
    assert resp.reason == "hard_policy_breach"
    assert resp.policy_id == "phase0.stub.deny_list"
    assert resp.policy_message is not None
    assert "shutdown_production" in resp.policy_message
    assert resp.remediation_suggestion is not None


def test_decide_phase0_deny_list_second_entry() -> None:
    resp = decide_phase0(_request_for_tool("delete_all_users"))
    assert resp.decision == Decision.DENY


def test_decide_phase0_escalate_list() -> None:
    resp = decide_phase0(_request_for_tool("transfer_funds"))
    assert resp.decision == Decision.ESCALATE
    assert resp.risk_classification == RiskClassification.HIGH
    assert resp.risk_score == pytest.approx(0.65)
    assert resp.triad_invoked is True
    assert resp.escalation_target == "human_review"
    assert resp.escalation_id is not None
    assert resp.estimated_review_time_minutes == 15
    assert resp.status_check_url is not None
    assert resp.status_check_url.startswith("/v1/runtime/escalation/")
    assert len(resp.policies_applied) == 1
    assert resp.policies_applied[0].result == PolicyResult.ABSTAIN


def test_decide_phase0_escalate_list_second_entry() -> None:
    resp = decide_phase0(_request_for_tool("send_external_email"))
    assert resp.decision == Decision.ESCALATE


def test_decide_phase0_case_insensitive_match() -> None:
    """Tool name matching is case-insensitive (lowercase normalisation)."""
    resp = decide_phase0(_request_for_tool("SHUTDOWN_PRODUCTION"))
    assert resp.decision == Decision.DENY


def test_decide_phase0_returns_unique_audit_ids() -> None:
    a = decide_phase0(_request_for_tool("read_x"))
    b = decide_phase0(_request_for_tool("read_x"))
    assert a.audit_id != b.audit_id


def test_decide_phase0_latency_is_non_negative() -> None:
    resp = decide_phase0(_request_for_tool("read_x"))
    assert resp.latency_ms >= 0


# ---------------------------------------------------------------------------
# Endpoint wiring -- POST /v1/runtime/govern (CP-9.2 dispatches via router)
# ---------------------------------------------------------------------------


def test_endpoint_returns_200_for_valid_request(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    payload = _request_payload_for_tool("read_account_balance")
    r = client.post("/v1/runtime/govern", json=payload, headers=auth_headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["decision"] == "allow"
    assert body["risk_classification"] == "low"
    assert "audit_id" in body


def test_endpoint_deny_for_deny_list_tool(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """CP-9.2: unregistered tools deny via firewall.tool_not_registered.

    Previously (CP-6.2 stub) this denied with hard_policy_breach +
    phase0.stub.deny_list; the router now surfaces the stable firewall
    error code instead.
    """
    payload = _request_payload_for_tool("shutdown_production")
    r = client.post("/v1/runtime/govern", json=payload, headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["decision"] == "deny"
    assert body["reason"] == "firewall_denied"
    assert body["policy_id"] == "firewall.tool_not_registered"


def test_endpoint_registered_tool_no_policies_returns_allow(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """CP-9.2: registered tools with no policy_decisions ALLOW.

    transfer_funds used to escalate under the CP-6.2 stub (escalate-list
    membership) but is now a registered tool that passes the firewall
    cleanly; with empty policy_decisions the router returns ALLOW. Real
    escalation needs OPA ABSTAIN -- exercised in the unit test below.
    """
    payload = _request_payload_for_tool("transfer_funds")
    r = client.post("/v1/runtime/govern", json=payload, headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["decision"] == "allow"
    assert body["triad_invoked"] is False


def test_endpoint_escalate_via_injected_abstain() -> None:
    """CP-9.2: ESCALATE path is reachable when an ABSTAIN is injected.

    The HTTP endpoint can't inject policy_decisions in Phase 0 (CP-12
    will wire CachedPolicyClient), so this test calls decide_via_router
    directly -- proving the wiring is correct and the router's R3 path
    fires when OPA returns abstain on a registered tool.
    """
    req = _request_for_tool("transfer_funds")
    decisions = (
        (
            "verixa.x.unknown",
            PolicyDecision(
                decision=PolicyDecisionKind.ABSTAIN,
                reason="undefined",
            ),
        ),
    )
    resp = decide_via_router(req, policy_decisions=decisions)
    assert resp.decision == Decision.ESCALATE
    assert resp.triad_invoked is True
    assert resp.escalation_id is not None
    assert resp.policy_id == "verixa.x.unknown"


def test_endpoint_returns_422_for_missing_required_field(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    bad_payload = _request_payload_for_tool("read_x")
    del bad_payload["trace_id"]
    r = client.post(
        "/v1/runtime/govern", json=bad_payload, headers=auth_headers
    )
    assert r.status_code == 422


def test_endpoint_returns_422_for_extra_field(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    bad_payload = _request_payload_for_tool("read_x")
    bad_payload["extra_unknown"] = "boom"
    r = client.post(
        "/v1/runtime/govern", json=bad_payload, headers=auth_headers
    )
    assert r.status_code == 422


def test_endpoint_returns_422_for_short_prompt_hash(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    bad_payload = _request_payload_for_tool("read_x")
    bad_payload["context"]["prompt_hash"] = "ab"  # too short
    r = client.post(
        "/v1/runtime/govern", json=bad_payload, headers=auth_headers
    )
    assert r.status_code == 422


def test_operational_endpoints_still_work_after_router_mount(
    client: TestClient,
) -> None:
    """CP-2.5 health/version/metrics must not regress after mounting govern.

    Operational endpoints bypass auth, so no header needed.
    """
    assert client.get("/healthz").status_code == 200
    assert client.get("/readyz").status_code == 200
    assert client.get("/version").status_code == 200
    assert client.get("/metrics").status_code == 200


def test_openapi_schema_includes_govern_endpoint(client: TestClient) -> None:
    schema = client.get("/openapi.json").json()
    paths = schema["paths"]
    assert "/v1/runtime/govern" in paths
    assert "post" in paths["/v1/runtime/govern"]
