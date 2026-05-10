"""POST /v1/runtime/govern — primary governed-action endpoint.

Phase 0 stub pipeline:

  1. Pydantic validates the request envelope (CP-6.1).
  2. A deterministic stub decision function returns allow/deny/escalate
     based on simple rules over the request (full risk + policy + triad
     in CP-8/9/10).
  3. The endpoint allocates a fresh audit_id (UUID4) and returns the
     response.

The stub decision function is exposed as `decide_phase0` so CP-9 can
keep it as a fallback while wiring the real decision router.

Phase 0 deliberately does NOT yet:
  - Persist to the audit ledger (CP-12 wires DB + emit + persist)
  - Invoke triad review (CP-10)
  - Invoke OPA (CP-8)
  - Score risk (CP-9)

These all add additional inputs to `decide_phase0` and additional fields
to the response envelope without breaking the on-the-wire shape.
"""

from __future__ import annotations

import time
import uuid

from fastapi import APIRouter

from verixa_runtime.gateway.envelopes import (
    Decision,
    GovernRequest,
    GovernResponse,
    PolicyAppliedResult,
    PolicyResult,
    RiskClassification,
)


router = APIRouter(prefix="/v1/runtime", tags=["runtime"])


# Threshold constants — placeholder values; CP-9 risk engine produces
# real scores from a real model. Phase 0 returns a deterministic stub
# based on action-type + tool-name only, so integration partners can
# wire the call site end-to-end without waiting for the full pipeline.
_DENY_TOOLS = frozenset({"shutdown_production", "delete_all_users"})
_ESCALATE_TOOLS = frozenset({"transfer_funds", "send_external_email"})


def decide_phase0(req: GovernRequest) -> GovernResponse:
    """Deterministic Phase 0 stub decision.

    Decision rules:
      - tool_name in deny-list           → deny  (risk 0.95, critical)
      - tool_name in escalate-list       → escalate (risk 0.65, high,
                                            triad_invoked=true)
      - everything else                  → allow  (risk 0.10, low)

    These thresholds are placeholder; CP-9 replaces this whole function
    with the real risk + decision router.
    """
    audit_id = uuid.uuid4()
    started = time.monotonic()
    tool = (req.action.tool_name or "").lower()

    if tool in _DENY_TOOLS:
        elapsed_ms = int((time.monotonic() - started) * 1000)
        return GovernResponse(
            decision=Decision.DENY,
            audit_id=audit_id,
            risk_score=0.95,
            risk_classification=RiskClassification.CRITICAL,
            latency_ms=elapsed_ms,
            reason="hard_policy_breach",
            policy_id="phase0.stub.deny_list",
            policy_message=(
                f"Tool '{tool}' is on the Phase 0 hard-deny stub list."
            ),
            remediation_suggestion=(
                "Phase 0 stub blocks this tool unconditionally. "
                "Wait for CP-8 OPA wiring or use a different tool."
            ),
        )

    if tool in _ESCALATE_TOOLS:
        elapsed_ms = int((time.monotonic() - started) * 1000)
        return GovernResponse(
            decision=Decision.ESCALATE,
            audit_id=audit_id,
            risk_score=0.65,
            risk_classification=RiskClassification.HIGH,
            latency_ms=elapsed_ms,
            triad_invoked=True,
            triad_consensus="phase0_stub_no_consensus",
            escalation_target="human_review",
            escalation_id=uuid.uuid4(),
            estimated_review_time_minutes=15,
            status_check_url=f"/v1/runtime/escalation/{audit_id}",
            policies_applied=[
                PolicyAppliedResult(
                    id="phase0.stub.escalate_list",
                    result=PolicyResult.ABSTAIN,
                )
            ],
        )

    elapsed_ms = int((time.monotonic() - started) * 1000)
    return GovernResponse(
        decision=Decision.ALLOW,
        audit_id=audit_id,
        risk_score=0.10,
        risk_classification=RiskClassification.LOW,
        latency_ms=elapsed_ms,
        triad_invoked=False,
        policies_applied=[
            PolicyAppliedResult(
                id="phase0.stub.default_allow",
                result=PolicyResult.PASS,
            )
        ],
    )


@router.post("/govern", response_model=GovernResponse)
def govern(req: GovernRequest) -> GovernResponse:
    """Govern a candidate action.

    Phase 0 returns a deterministic stub decision; CP-8/9/10 wire the
    real policy engine, risk engine, and triad-review pipeline.
    """
    return decide_phase0(req)
