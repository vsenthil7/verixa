"""pytest suite for verixa_runtime.risk.router (CP-9.1).

Pure-function tests -- no I/O, no fixtures-with-Docker. Covers every
branch in the decision pipeline:

  - R1 firewall deny (allowlist OR arg_bounds) -> DENY
  - R2 any policy fail -> DENY with first-fail surfaced
  - R3 any policy abstain (no fails) -> ESCALATE
  - R4 all pass -> ALLOW
  - Risk score weights + cap at 1.0
  - Risk classification thresholds
  - policies_applied trace ordering
"""

from __future__ import annotations

import uuid

import pytest

from verixa_runtime.firewall.allowlist import (
    CODE_TOOL_NOT_REGISTERED,
    CODE_WORKFLOW_NOT_PERMITTED,
    FirewallDecision,
    FirewallVerdict,
)
from verixa_runtime.firewall.arg_bounds import (
    CODE_ARG_RANGE,
)
from verixa_runtime.gateway.envelopes import (
    AgentIdentity,
    Decision,
    GovernAction,
    GovernContext,
    GovernRequest,
    PolicyResult,
    RiskClassification,
)
from verixa_runtime.policy.client import (
    PolicyDecision,
    PolicyDecisionKind,
)
from verixa_runtime.risk.router import (
    RISK_ABSTAIN_WEIGHT,
    RISK_FAIL_WEIGHT,
    RISK_FIREWALL_DENY_WEIGHT,
    RISK_MAX,
    RISK_THRESHOLD_CRITICAL,
    RISK_THRESHOLD_HIGH,
    RISK_THRESHOLD_MEDIUM,
    RouterInputs,
    classify_risk,
    compute_risk,
    route_decision,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _request(tool_name: str = "transfer_funds") -> GovernRequest:
    return GovernRequest(
        agent_identity=AgentIdentity(
            spiffe_id="spiffe://example/agent/x",
            role="loan-officer",
            workflow_id=uuid.UUID("11111111-1111-1111-1111-111111111111"),
        ),
        action=GovernAction(
            type="tool_call",
            tool_name=tool_name,
            arguments={"amount": 5000, "currency": "GBP"},
        ),
        context=GovernContext(
            prompt_hash="b" * 64,
            model_version="qwen3-72b",
        ),
        trace_id="t-1",
    )


def _allow_verdict() -> FirewallVerdict:
    return FirewallVerdict(
        decision=FirewallDecision.ALLOW,
        reason="ok",
    )


def _deny_verdict(code: str, reason: str = "blocked") -> FirewallVerdict:
    return FirewallVerdict(
        decision=FirewallDecision.DENY, reason=reason, code=code
    )


def _policy_pass(reason: str = "") -> PolicyDecision:
    return PolicyDecision(decision=PolicyDecisionKind.PASS, reason=reason)


def _policy_fail(reason: str = "limit exceeded") -> PolicyDecision:
    return PolicyDecision(decision=PolicyDecisionKind.FAIL, reason=reason)


def _policy_abstain(reason: str = "no opinion") -> PolicyDecision:
    return PolicyDecision(decision=PolicyDecisionKind.ABSTAIN, reason=reason)


# ---------------------------------------------------------------------------
# Constants smoke
# ---------------------------------------------------------------------------


def test_risk_weights_documented_values() -> None:
    """Constants match the documented design (so changes to weights
    deliberately fail this test rather than silently shift thresholds)."""
    assert RISK_FAIL_WEIGHT == 0.30
    assert RISK_ABSTAIN_WEIGHT == 0.10
    assert RISK_FIREWALL_DENY_WEIGHT == 0.50
    assert RISK_MAX == 1.0
    assert RISK_THRESHOLD_CRITICAL == 0.80
    assert RISK_THRESHOLD_HIGH == 0.50
    assert RISK_THRESHOLD_MEDIUM == 0.20


# ---------------------------------------------------------------------------
# compute_risk -- weights + capping
# ---------------------------------------------------------------------------


def test_compute_risk_all_clear_is_zero() -> None:
    inputs = RouterInputs(
        request=_request(),
        allowlist_verdict=_allow_verdict(),
        arg_bounds_verdict=_allow_verdict(),
        policy_decisions=(("verixa.fs.x", _policy_pass()),),
    )
    assert compute_risk(inputs) == 0.0


def test_compute_risk_one_fail() -> None:
    inputs = RouterInputs(
        request=_request(),
        allowlist_verdict=_allow_verdict(),
        arg_bounds_verdict=_allow_verdict(),
        policy_decisions=(("verixa.fs.x", _policy_fail()),),
    )
    assert compute_risk(inputs) == pytest.approx(RISK_FAIL_WEIGHT)


def test_compute_risk_one_abstain() -> None:
    inputs = RouterInputs(
        request=_request(),
        allowlist_verdict=_allow_verdict(),
        arg_bounds_verdict=_allow_verdict(),
        policy_decisions=(("verixa.fs.x", _policy_abstain()),),
    )
    assert compute_risk(inputs) == pytest.approx(RISK_ABSTAIN_WEIGHT)


def test_compute_risk_firewall_allowlist_deny() -> None:
    inputs = RouterInputs(
        request=_request(),
        allowlist_verdict=_deny_verdict(CODE_TOOL_NOT_REGISTERED),
        arg_bounds_verdict=_allow_verdict(),
    )
    assert compute_risk(inputs) == pytest.approx(RISK_FIREWALL_DENY_WEIGHT)


def test_compute_risk_firewall_arg_bounds_deny() -> None:
    inputs = RouterInputs(
        request=_request(),
        allowlist_verdict=_allow_verdict(),
        arg_bounds_verdict=_deny_verdict(CODE_ARG_RANGE),
    )
    assert compute_risk(inputs) == pytest.approx(RISK_FIREWALL_DENY_WEIGHT)


def test_compute_risk_both_firewalls_deny() -> None:
    inputs = RouterInputs(
        request=_request(),
        allowlist_verdict=_deny_verdict(CODE_TOOL_NOT_REGISTERED),
        arg_bounds_verdict=_deny_verdict(CODE_ARG_RANGE),
    )
    # Two firewall denies = 1.0 capped
    assert compute_risk(inputs) == pytest.approx(RISK_MAX)


def test_compute_risk_caps_at_max() -> None:
    """5 fails would otherwise total 1.50; must cap at 1.0."""
    inputs = RouterInputs(
        request=_request(),
        allowlist_verdict=_allow_verdict(),
        arg_bounds_verdict=_allow_verdict(),
        policy_decisions=tuple(
            (f"verixa.x.p{i}", _policy_fail()) for i in range(5)
        ),
    )
    assert compute_risk(inputs) == RISK_MAX


def test_compute_risk_mixed_fail_and_abstain() -> None:
    inputs = RouterInputs(
        request=_request(),
        allowlist_verdict=_allow_verdict(),
        arg_bounds_verdict=_allow_verdict(),
        policy_decisions=(
            ("verixa.fs.a", _policy_fail()),
            ("verixa.fs.b", _policy_abstain()),
        ),
    )
    assert compute_risk(inputs) == pytest.approx(
        RISK_FAIL_WEIGHT + RISK_ABSTAIN_WEIGHT
    )


# ---------------------------------------------------------------------------
# classify_risk -- thresholds
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "score,expected",
    [
        (0.0, RiskClassification.LOW),
        (0.10, RiskClassification.LOW),
        (0.19, RiskClassification.LOW),
        (0.20, RiskClassification.MEDIUM),
        (0.49, RiskClassification.MEDIUM),
        (0.50, RiskClassification.HIGH),
        (0.79, RiskClassification.HIGH),
        (0.80, RiskClassification.CRITICAL),
        (1.00, RiskClassification.CRITICAL),
    ],
)
def test_classify_risk_thresholds(score: float, expected: RiskClassification) -> None:
    assert classify_risk(score) == expected


# ---------------------------------------------------------------------------
# route_decision -- R1 firewall deny path
# ---------------------------------------------------------------------------


def test_route_r1_allowlist_deny_returns_deny() -> None:
    inputs = RouterInputs(
        request=_request(tool_name="shutdown_production"),
        allowlist_verdict=_deny_verdict(
            CODE_TOOL_NOT_REGISTERED, "tool not registered"
        ),
        arg_bounds_verdict=_allow_verdict(),
    )
    response = route_decision(inputs)
    assert response.decision == Decision.DENY
    assert response.reason == "firewall_denied"
    assert response.policy_id == CODE_TOOL_NOT_REGISTERED
    assert "tool not registered" in response.policy_message
    assert response.triad_invoked is False
    assert response.remediation_suggestion is not None


def test_route_r1_arg_bounds_deny_returns_deny() -> None:
    inputs = RouterInputs(
        request=_request(),
        allowlist_verdict=_allow_verdict(),
        arg_bounds_verdict=_deny_verdict(
            CODE_ARG_RANGE, "amount above maximum"
        ),
    )
    response = route_decision(inputs)
    assert response.decision == Decision.DENY
    assert response.policy_id == CODE_ARG_RANGE


def test_route_r1_skips_subsequent_policy_evaluation() -> None:
    """When firewall denies, OPA decisions don't change the outcome."""
    inputs = RouterInputs(
        request=_request(),
        allowlist_verdict=_deny_verdict(CODE_WORKFLOW_NOT_PERMITTED),
        arg_bounds_verdict=_allow_verdict(),
        # Even though OPA "passed", firewall deny wins
        policy_decisions=(
            ("verixa.fs.transfer_amount_limit", _policy_pass()),
            ("verixa.fs.beneficiary_verification", _policy_pass()),
        ),
    )
    response = route_decision(inputs)
    assert response.decision == Decision.DENY
    assert response.reason == "firewall_denied"


# ---------------------------------------------------------------------------
# route_decision -- R2 policy fail path
# ---------------------------------------------------------------------------


def test_route_r2_single_policy_fail_returns_deny() -> None:
    inputs = RouterInputs(
        request=_request(),
        allowlist_verdict=_allow_verdict(),
        arg_bounds_verdict=_allow_verdict(),
        policy_decisions=(
            (
                "verixa.fs.transfer_amount_limit",
                _policy_fail("amount 15000 exceeds limit 10000"),
            ),
        ),
    )
    response = route_decision(inputs)
    assert response.decision == Decision.DENY
    assert response.reason == "policy_fail"
    assert response.policy_id == "verixa.fs.transfer_amount_limit"
    assert response.policy_message is not None
    assert "exceeds limit" in response.policy_message


def test_route_r2_first_failing_policy_surfaced() -> None:
    """Multiple failing policies -> first-fail surfaces in policy_id."""
    inputs = RouterInputs(
        request=_request(),
        allowlist_verdict=_allow_verdict(),
        arg_bounds_verdict=_allow_verdict(),
        policy_decisions=(
            ("verixa.fs.policy_a", _policy_fail("first reason")),
            ("verixa.fs.policy_b", _policy_fail("second reason")),
        ),
    )
    response = route_decision(inputs)
    assert response.policy_id == "verixa.fs.policy_a"
    assert response.policy_message == "first reason"


def test_route_r2_pass_then_fail_picks_failing() -> None:
    inputs = RouterInputs(
        request=_request(),
        allowlist_verdict=_allow_verdict(),
        arg_bounds_verdict=_allow_verdict(),
        policy_decisions=(
            ("verixa.fs.passing", _policy_pass()),
            ("verixa.fs.failing", _policy_fail("blocked")),
        ),
    )
    response = route_decision(inputs)
    assert response.decision == Decision.DENY
    assert response.policy_id == "verixa.fs.failing"


# ---------------------------------------------------------------------------
# route_decision -- R3 abstain path
# ---------------------------------------------------------------------------


def test_route_r3_abstain_returns_escalate() -> None:
    inputs = RouterInputs(
        request=_request(),
        allowlist_verdict=_allow_verdict(),
        arg_bounds_verdict=_allow_verdict(),
        policy_decisions=(
            ("verixa.fs.transfer_amount_limit", _policy_pass()),
            ("verixa.x.unknown", _policy_abstain("undefined")),
        ),
    )
    response = route_decision(inputs)
    assert response.decision == Decision.ESCALATE
    assert response.reason == "policy_abstain"
    assert response.triad_invoked is True
    assert response.escalation_target == "human_review"
    assert response.escalation_id is not None
    assert response.estimated_review_time_minutes == 15
    assert response.status_check_url is not None
    assert str(response.escalation_id) in response.status_check_url


def test_route_r3_first_abstain_surfaced() -> None:
    inputs = RouterInputs(
        request=_request(),
        allowlist_verdict=_allow_verdict(),
        arg_bounds_verdict=_allow_verdict(),
        policy_decisions=(
            ("verixa.x.first", _policy_abstain("reason 1")),
            ("verixa.x.second", _policy_abstain("reason 2")),
        ),
    )
    response = route_decision(inputs)
    assert response.policy_id == "verixa.x.first"


def test_route_r3_fail_takes_precedence_over_abstain() -> None:
    """If both fail and abstain present, fail wins -> DENY not ESCALATE."""
    inputs = RouterInputs(
        request=_request(),
        allowlist_verdict=_allow_verdict(),
        arg_bounds_verdict=_allow_verdict(),
        policy_decisions=(
            ("verixa.x.abstainer", _policy_abstain()),
            ("verixa.x.failer", _policy_fail("real fail")),
        ),
    )
    response = route_decision(inputs)
    assert response.decision == Decision.DENY


# ---------------------------------------------------------------------------
# route_decision -- R4 allow path
# ---------------------------------------------------------------------------


def test_route_r4_all_pass_returns_allow() -> None:
    inputs = RouterInputs(
        request=_request(),
        allowlist_verdict=_allow_verdict(),
        arg_bounds_verdict=_allow_verdict(),
        policy_decisions=(
            ("verixa.fs.transfer_amount_limit", _policy_pass()),
            ("verixa.fs.beneficiary_verification", _policy_pass()),
        ),
    )
    response = route_decision(inputs)
    assert response.decision == Decision.ALLOW
    assert response.reason is None
    assert response.policy_id is None
    assert response.triad_invoked is False
    assert response.risk_classification == RiskClassification.LOW
    assert response.risk_score == 0.0


def test_route_r4_no_policies_evaluated_returns_allow() -> None:
    """If neither firewall denies and no policies were evaluated (e.g.
    a non-tool_call action), the router still allows."""
    inputs = RouterInputs(
        request=_request(),
        allowlist_verdict=_allow_verdict(),
        arg_bounds_verdict=_allow_verdict(),
        policy_decisions=(),
    )
    response = route_decision(inputs)
    assert response.decision == Decision.ALLOW


# ---------------------------------------------------------------------------
# Common output invariants
# ---------------------------------------------------------------------------


def test_route_emits_unique_audit_id_per_call() -> None:
    inputs = RouterInputs(
        request=_request(),
        allowlist_verdict=_allow_verdict(),
        arg_bounds_verdict=_allow_verdict(),
    )
    a = route_decision(inputs)
    b = route_decision(inputs)
    assert a.audit_id != b.audit_id


def test_route_emits_unique_escalation_id_per_call() -> None:
    inputs = RouterInputs(
        request=_request(),
        allowlist_verdict=_allow_verdict(),
        arg_bounds_verdict=_allow_verdict(),
        policy_decisions=(("verixa.x", _policy_abstain()),),
    )
    a = route_decision(inputs)
    b = route_decision(inputs)
    assert a.escalation_id != b.escalation_id


def test_route_latency_is_non_negative() -> None:
    inputs = RouterInputs(
        request=_request(),
        allowlist_verdict=_allow_verdict(),
        arg_bounds_verdict=_allow_verdict(),
    )
    assert route_decision(inputs).latency_ms >= 0


def test_route_policies_applied_includes_firewall_entries() -> None:
    """Both firewall steps should appear as policy_applied entries."""
    inputs = RouterInputs(
        request=_request(),
        allowlist_verdict=_allow_verdict(),
        arg_bounds_verdict=_allow_verdict(),
        policy_decisions=(("verixa.fs.x", _policy_pass()),),
    )
    response = route_decision(inputs)
    ids = [pa.id for pa in response.policies_applied]
    assert "firewall.allowlist" in ids
    assert "firewall.arg_bounds" in ids
    assert "verixa.fs.x" in ids


def test_route_policies_applied_marks_failing_firewall() -> None:
    inputs = RouterInputs(
        request=_request(),
        allowlist_verdict=_deny_verdict(CODE_TOOL_NOT_REGISTERED),
        arg_bounds_verdict=_allow_verdict(),
    )
    response = route_decision(inputs)
    by_id = {pa.id: pa.result for pa in response.policies_applied}
    # Firewall verdict surfaced under its stable code, not 'firewall.allowlist'
    assert by_id[CODE_TOOL_NOT_REGISTERED] == PolicyResult.FAIL


def test_route_policies_applied_marks_abstaining_policy() -> None:
    inputs = RouterInputs(
        request=_request(),
        allowlist_verdict=_allow_verdict(),
        arg_bounds_verdict=_allow_verdict(),
        policy_decisions=(("verixa.x.unknown", _policy_abstain()),),
    )
    response = route_decision(inputs)
    by_id = {pa.id: pa.result for pa in response.policies_applied}
    assert by_id["verixa.x.unknown"] == PolicyResult.ABSTAIN


# ---------------------------------------------------------------------------
# RouterInputs frozen + reexports
# ---------------------------------------------------------------------------


def test_router_inputs_is_frozen() -> None:
    inputs = RouterInputs(
        request=_request(),
        allowlist_verdict=_allow_verdict(),
        arg_bounds_verdict=_allow_verdict(),
    )
    with pytest.raises((AttributeError, Exception)):
        inputs.allowlist_verdict = _deny_verdict("x")  # type: ignore[misc]


def test_risk_package_reexports() -> None:
    from verixa_runtime import risk

    for name in (
        "RouterInputs",
        "classify_risk",
        "compute_risk",
        "route_decision",
    ):
        assert hasattr(risk, name), f"risk package missing {name}"
