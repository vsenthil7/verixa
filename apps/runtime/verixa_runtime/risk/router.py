"""Pure-function risk scorer + decision router (CP-9.1).

See ``verixa_runtime.risk.__init__`` for the design overview. This
module is the implementation; it has no I/O dependencies (no HTTP, no
DB, no Redis). The gateway layer in CP-9.2 wires it up by:

  1. Calling firewall.evaluate_allowlist + evaluate_argument_bounds
  2. Calling policy CachedPolicyClient.evaluate(...) for each applicable
     policy package
  3. Building a RouterInputs(...) and calling route_decision(...)

The router returns a fully-populated GovernResponse including audit_id,
latency_ms placeholder (gateway substitutes the real number), and
policy/risk fields shaped per docs/08_api_specification A7 2.1.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Final

from verixa_runtime.firewall.allowlist import (
    FirewallDecision,
    FirewallVerdict,
)
from verixa_runtime.gateway.envelopes import (
    Decision,
    GovernRequest,
    GovernResponse,
    PolicyAppliedResult,
    PolicyResult,
    RiskClassification,
)
from verixa_runtime.policy.client import (
    PolicyDecision,
    PolicyDecisionKind,
)


# Risk score weights -- documented in __init__.py; constants here
# so they're testable.
RISK_FAIL_WEIGHT: Final[float] = 0.30
RISK_ABSTAIN_WEIGHT: Final[float] = 0.10
RISK_FIREWALL_DENY_WEIGHT: Final[float] = 0.50
RISK_MAX: Final[float] = 1.0

# Classification thresholds
RISK_THRESHOLD_CRITICAL: Final[float] = 0.80
RISK_THRESHOLD_HIGH: Final[float] = 0.50
RISK_THRESHOLD_MEDIUM: Final[float] = 0.20


@dataclass(frozen=True, slots=True)
class RouterInputs:
    """Pre-computed inputs the router needs to make a decision.

    Each entry in ``policy_decisions`` is keyed by the OPA package
    name (e.g. ``verixa.fs.transfer_amount_limit``) so the router can
    surface which policies passed/failed when emitting policy_applied.
    """

    request: GovernRequest
    allowlist_verdict: FirewallVerdict
    arg_bounds_verdict: FirewallVerdict
    policy_decisions: tuple[tuple[str, PolicyDecision], ...] = field(
        default_factory=tuple
    )


def compute_risk(inputs: RouterInputs) -> float:
    """Pure risk score: 0.0 (safe) to 1.0 (critical), capped at RISK_MAX."""
    score = 0.0
    if inputs.allowlist_verdict.decision == FirewallDecision.DENY:
        score += RISK_FIREWALL_DENY_WEIGHT
    if inputs.arg_bounds_verdict.decision == FirewallDecision.DENY:
        score += RISK_FIREWALL_DENY_WEIGHT
    for _, pd in inputs.policy_decisions:
        if pd.decision == PolicyDecisionKind.FAIL:
            score += RISK_FAIL_WEIGHT
        elif pd.decision == PolicyDecisionKind.ABSTAIN:
            score += RISK_ABSTAIN_WEIGHT
    return min(score, RISK_MAX)


def classify_risk(score: float) -> RiskClassification:
    """Bucket a numeric risk score into a categorical classification."""
    if score >= RISK_THRESHOLD_CRITICAL:
        return RiskClassification.CRITICAL
    if score >= RISK_THRESHOLD_HIGH:
        return RiskClassification.HIGH
    if score >= RISK_THRESHOLD_MEDIUM:
        return RiskClassification.MEDIUM
    return RiskClassification.LOW


def _firewall_verdict_to_policy_applied(
    name: str, verdict: FirewallVerdict
) -> PolicyAppliedResult:
    """Render a firewall verdict as a policy_applied entry for the response.

    The PolicyAppliedResult envelope (CP-6.1) carries only id + result.
    The verdict's free-text reason flows into the response-level
    policy_message field on the failing-verdict path; we don't lose
    information.
    """
    if verdict.decision == FirewallDecision.ALLOW:
        return PolicyAppliedResult(
            id=f"firewall.{name}",
            result=PolicyResult.PASS,
        )
    return PolicyAppliedResult(
        id=verdict.code or f"firewall.{name}",
        result=PolicyResult.FAIL,
    )


def _policy_decision_to_applied(
    package: str, pd: PolicyDecision
) -> PolicyAppliedResult:
    """Render an OPA decision as a policy_applied entry."""
    result = {
        PolicyDecisionKind.PASS: PolicyResult.PASS,
        PolicyDecisionKind.FAIL: PolicyResult.FAIL,
        PolicyDecisionKind.ABSTAIN: PolicyResult.ABSTAIN,
    }[pd.decision]
    return PolicyAppliedResult(id=package, result=result)


def _build_policies_applied(
    inputs: RouterInputs,
) -> list[PolicyAppliedResult]:
    """Combined firewall + OPA verdicts in evaluation order."""
    out: list[PolicyAppliedResult] = [
        _firewall_verdict_to_policy_applied(
            "allowlist", inputs.allowlist_verdict
        ),
        _firewall_verdict_to_policy_applied(
            "arg_bounds", inputs.arg_bounds_verdict
        ),
    ]
    for pkg, pd in inputs.policy_decisions:
        out.append(_policy_decision_to_applied(pkg, pd))
    return out


def route_decision(inputs: RouterInputs) -> GovernResponse:
    """Run the decision pipeline. Pure -- no I/O.

    The gateway endpoint (CP-9.2) computes the firewall verdicts +
    policy decisions and passes them in. This function decides the
    final allow/deny/escalate, builds the policies_applied trace,
    computes the risk score + classification, and emits a complete
    GovernResponse.
    """
    started = time.monotonic()
    policies_applied = _build_policies_applied(inputs)
    risk_score = compute_risk(inputs)
    risk_class = classify_risk(risk_score)
    audit_id = uuid.uuid4()
    latency_ms = int((time.monotonic() - started) * 1000)

    # R1: firewall deny terminates immediately.
    fw_denied = (
        inputs.allowlist_verdict.decision == FirewallDecision.DENY
        or inputs.arg_bounds_verdict.decision == FirewallDecision.DENY
    )
    if fw_denied:
        # Pick the first denying verdict for the customer-facing message.
        denying = (
            inputs.allowlist_verdict
            if inputs.allowlist_verdict.decision == FirewallDecision.DENY
            else inputs.arg_bounds_verdict
        )
        return GovernResponse(
            decision=Decision.DENY,
            risk_classification=risk_class,
            risk_score=risk_score,
            triad_invoked=False,
            audit_id=audit_id,
            latency_ms=latency_ms,
            reason="firewall_denied",
            policy_id=denying.code,
            policy_message=denying.reason,
            policies_applied=policies_applied,
            remediation_suggestion=(
                "Adjust the tool call to satisfy the firewall constraints; "
                "see policy_message for the specific rule."
            ),
        )

    # R2: any policy FAIL -> DENY with first-fail reason.
    failing_packages = [
        (pkg, pd)
        for pkg, pd in inputs.policy_decisions
        if pd.decision == PolicyDecisionKind.FAIL
    ]
    if failing_packages:
        first_pkg, first_pd = failing_packages[0]
        return GovernResponse(
            decision=Decision.DENY,
            risk_classification=risk_class,
            risk_score=risk_score,
            triad_invoked=False,
            audit_id=audit_id,
            latency_ms=latency_ms,
            reason="policy_fail",
            policy_id=first_pkg,
            policy_message=first_pd.reason or None,
            policies_applied=policies_applied,
            remediation_suggestion=(
                "Reframe the request to comply with the policies marked "
                "FAIL in policies_applied."
            ),
        )

    # R3: any policy ABSTAIN -> ESCALATE.
    abstaining = [
        (pkg, pd)
        for pkg, pd in inputs.policy_decisions
        if pd.decision == PolicyDecisionKind.ABSTAIN
    ]
    if abstaining:
        first_pkg, first_pd = abstaining[0]
        escalation_id = uuid.uuid4()
        return GovernResponse(
            decision=Decision.ESCALATE,
            risk_classification=risk_class,
            risk_score=risk_score,
            triad_invoked=True,
            audit_id=audit_id,
            latency_ms=latency_ms,
            reason="policy_abstain",
            policy_id=first_pkg,
            policy_message=first_pd.reason or None,
            policies_applied=policies_applied,
            escalation_target="human_review",
            escalation_id=escalation_id,
            estimated_review_time_minutes=15,
            status_check_url=f"/v1/runtime/escalation/{escalation_id}",
            remediation_suggestion=(
                "One or more policies could not produce an opinion; a "
                "human reviewer will inspect this request."
            ),
        )

    # R4: all clear -> ALLOW.
    return GovernResponse(
        decision=Decision.ALLOW,
        risk_classification=risk_class,
        risk_score=risk_score,
        triad_invoked=False,
        audit_id=audit_id,
        latency_ms=latency_ms,
        policies_applied=policies_applied,
    )
