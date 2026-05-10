"""POST /v1/runtime/govern -- primary governed-action endpoint.

CP-6.2 wired a deterministic stub (`decide_phase0`). CP-9.2 wires the
real risk + decision router (`decide_via_router`) alongside it; the
endpoint now dispatches via the router. `decide_phase0` is retained
unchanged so its CP-6.2 unit tests still pass (it is no longer reached
from the HTTP surface but stays exported for backward-compat).

Phase-0 deliberately still does NOT, even via the router:

  - Invoke OPA (CP-12 wires CachedPolicyClient at the gateway -- this
    commit passes ``policy_decisions=()`` so R3 abstain / R2 fail are
    only reachable via unit tests that inject decisions directly)
  - Persist to the audit ledger (CP-12)
  - Invoke triad review (CP-10)

The router itself supports all of the above; CP-9.2 just hasn't bolted
the I/O collaborators in. The on-the-wire envelope shapes (CP-6.1)
remain stable.
"""

from __future__ import annotations

import time
import uuid
from typing import Iterable

from fastapi import APIRouter

from verixa_runtime.firewall.allowlist import (
    ToolRegistryEntry,
    evaluate_allowlist,
)
from verixa_runtime.firewall.arg_bounds import evaluate_argument_bounds
from verixa_runtime.gateway.envelopes import (
    Decision,
    GovernRequest,
    GovernResponse,
    PolicyAppliedResult,
    PolicyResult,
    RiskClassification,
)
from verixa_runtime.policy.client import PolicyDecision
from verixa_runtime.risk.router import RouterInputs, route_decision
from verixa_runtime.triad.orchestrator import (
    TriadOrchestrator,
    consensus_to_decision,
)
from verixa_runtime.triad.protocol import VerdictDecision


router = APIRouter(prefix="/v1/runtime", tags=["runtime"])


# ---------------------------------------------------------------------------
# Legacy CP-6.2 stub (retained for backward-compat; tests still pin it)
# ---------------------------------------------------------------------------

_DENY_TOOLS = frozenset({"shutdown_production", "delete_all_users"})
_ESCALATE_TOOLS = frozenset({"transfer_funds", "send_external_email"})


def decide_phase0(req: GovernRequest) -> GovernResponse:
    """Deterministic Phase-0 stub decision (CP-6.2; retained).

    No longer reached from /v1/runtime/govern after CP-9.2; kept so the
    nine CP-6.2 unit tests continue to pass and so callers that imported
    it directly aren't broken.
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


# ---------------------------------------------------------------------------
# CP-9.2 -- real decision-router dispatch path
# ---------------------------------------------------------------------------


# Phase-0 hardcoded tool registry. Mirrors the seven tools the sample
# workflows use (CP-16 will replace this with a verixa_registry.tools
# database read once Alembic seeds the rows). All entries are active
# and unrestricted by workflow_id, so the allow-list only weeds out
# tools that aren't in the seven names listed here.
_PHASE0_TOOL_REGISTRY: tuple[ToolRegistryEntry, ...] = (
    ToolRegistryEntry(name="read_account_balance", is_active=True),
    ToolRegistryEntry(name="lookup_account", is_active=True),
    ToolRegistryEntry(name="lookup_customer", is_active=True),
    ToolRegistryEntry(name="read_user_profile", is_active=True),
    ToolRegistryEntry(name="transfer_funds", is_active=True),
    ToolRegistryEntry(name="send_external_email", is_active=True),
    ToolRegistryEntry(name="submit_payment", is_active=True),
)


def decide_via_router(
    req: GovernRequest,
    *,
    registry: list[ToolRegistryEntry] | None = None,
    policy_decisions: Iterable[tuple[str, PolicyDecision]] = (),
) -> GovernResponse:
    """Wire CP-7 firewall + CP-9.1 router into a single decision.

    Steps:
      1. Resolve registry -> default Phase-0 hardcoded list of 7 tools.
      2. Run firewall.evaluate_allowlist with the request's workflow_id.
      3. Run firewall.evaluate_argument_bounds with schema=None (the
         Phase-0 registry doesn't carry per-tool schemas yet; the
         arg_bounds layer treats schema=None as "skip" and returns
         ALLOW). CP-12 will surface the schema from the DB.
      4. Build RouterInputs with caller-supplied policy_decisions
         (empty by default; CP-12 wires CachedPolicyClient).
      5. Dispatch to risk.router.route_decision.

    Keyword-only ``registry`` and ``policy_decisions`` keep the call site
    clean and enable test injection without HTTP/OPA.
    """
    reg = list(registry) if registry is not None else list(_PHASE0_TOOL_REGISTRY)
    allowlist_verdict = evaluate_allowlist(
        req.action,
        req.agent_identity.workflow_id,
        reg,
    )
    arg_bounds_verdict = evaluate_argument_bounds(req.action, schema=None)
    inputs = RouterInputs(
        request=req,
        allowlist_verdict=allowlist_verdict,
        arg_bounds_verdict=arg_bounds_verdict,
        policy_decisions=tuple(policy_decisions),
    )
    return route_decision(inputs)


@router.post("/govern", response_model=GovernResponse)
def govern(req: GovernRequest) -> GovernResponse:
    """Govern a candidate action.

    CP-9.2: dispatches via ``decide_via_router`` (firewall + risk
    router). Until CP-12 wires real OPA, ``policy_decisions`` is empty,
    so only firewall outcomes can flip ALLOW to DENY at the HTTP level.
    Direct callers of ``decide_via_router`` (tests, CP-12) can inject
    policy decisions to exercise R2/R3 paths.

    CP-10.5: triad invocation is exposed via ``decide_via_router_with_triad``
    (async); the HTTP endpoint stays sync because no triad is wired in
    by default at Phase-0 (the orchestrator is constructed by callers
    that have an event loop and a live droplet, e.g. an async demo
    harness or CP-10.4 integration test).
    """
    return decide_via_router(req)


# ---------------------------------------------------------------------------
# CP-10.5 -- triad-aware decision (async; ESCALATE -> triad consensus)
# ---------------------------------------------------------------------------


async def decide_via_router_with_triad(
    req: GovernRequest,
    *,
    triad: TriadOrchestrator,
    registry: list[ToolRegistryEntry] | None = None,
    policy_decisions: Iterable[tuple[str, PolicyDecision]] = (),
) -> GovernResponse:
    """Run the sync router; if it ESCALATEs, invoke the triad and let
    the consensus decide.

    Workflow:
      1. Run ``decide_via_router`` synchronously to get the baseline
         response.
      2. If decision != ESCALATE, return the response unchanged --
         firewall denies and policy fails terminate immediately
         without triad cost.
      3. If decision == ESCALATE, await ``triad.run(audit_id=...)``,
         translate consensus to a VerdictDecision via
         ``consensus_to_decision``:
           - ALLOW or DENY: override the response with the triad's
             chosen decision; triad_invoked=True; triad_consensus =
             ConsensusKind.value ("unanimous"/"majority")
           - ESCALATE (SPLIT or INTEGRITY_FAILURE or genuine ESCALATE
             vote): leave the response as ESCALATE; surface
             triad_consensus = "split"/"integrity_failure"/"escalate"

    The triad's commitments are NOT yet persisted to the audit ledger
    here (CP-12 wires the audit emitter and passes it as the
    ``audit_emit`` kwarg into ``triad.run``). For now the function
    accepts triad as a kwarg so a test or demo harness can construct
    one with MockReviewer or live OpenAICompatReviewer instances.
    """
    base = decide_via_router(
        req, registry=registry, policy_decisions=policy_decisions
    )
    if base.decision != Decision.ESCALATE:
        return base
    outcome = await triad.run(
        audit_id=base.audit_id,
        governed_action_summary=_summarise_request_for_triad(req),
    )
    triad_decision = consensus_to_decision(outcome)
    triad_consensus_label = outcome.consensus.kind.value
    if triad_decision == VerdictDecision.ESCALATE:
        # Triad couldn't reach consensus or all three voted escalate;
        # leave the response as ESCALATE but surface the triad outcome.
        return base.model_copy(
            update={
                "triad_invoked": True,
                "triad_consensus": triad_consensus_label,
            }
        )
    # Triad reached consensus on ALLOW or DENY -> override.
    overridden_decision = (
        Decision.ALLOW
        if triad_decision == VerdictDecision.ALLOW
        else Decision.DENY
    )
    return base.model_copy(
        update={
            "decision": overridden_decision,
            "triad_invoked": True,
            "triad_consensus": triad_consensus_label,
        }
    )


def _summarise_request_for_triad(req: GovernRequest) -> str:
    """Render the GovernRequest into a short string for reviewer prompts.

    Phase-0 includes the bare minimum a reviewer needs to opine on the
    action: tool name, action type, and the workflow / agent role.
    Full action.arguments + retrieved-document context arrive in CP-11
    (Evidence Validator) and CP-12 (Replay Vault) where the reviewer
    can inspect the grounding evidence too.
    """
    return (
        f"action.type={req.action.type} "
        f"tool_name={req.action.tool_name or '<none>'} "
        f"role={req.agent_identity.role} "
        f"workflow_id={req.agent_identity.workflow_id}"
    )
