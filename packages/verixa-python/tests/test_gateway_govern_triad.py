"""pytest suite for decide_via_router_with_triad (CP-10.5).

Exercises the gateway integration of the triad orchestrator. Uses
MockReviewer factories from CP-10.2 (no live droplet) to drive the
orchestrator through every consensus outcome and assert the resulting
GovernResponse override.

Coverage target: 100% line + branch on the new code in
gateway/govern.py (decide_via_router_with_triad +
_summarise_request_for_triad).
"""

from __future__ import annotations

import uuid
from typing import Awaitable, Callable

import pytest

from verixa_runtime.gateway import (
    AgentIdentity,
    Decision,
    GovernAction,
    GovernContext,
    GovernRequest,
    decide_via_router_with_triad,
)
from verixa_runtime.policy.client import PolicyDecision, PolicyDecisionKind
from verixa_runtime.triad import (
    MockReviewer,
    ReviewerId,
    ReviewerVerdict,
    TriadOrchestrator,
    VerdictDecision,
)


_WF_ID = uuid.UUID("22222222-2222-2222-2222-222222222222")


def _request_for_tool(tool_name: str | None) -> GovernRequest:
    action_kwargs: dict[str, object] = {"type": "tool_call"}
    if tool_name is not None:
        action_kwargs["tool_name"] = tool_name
    return GovernRequest(
        agent_identity=AgentIdentity(
            spiffe_id="spiffe://example/agent/x",
            role="loan-officer",
            workflow_id=_WF_ID,
        ),
        action=GovernAction(**action_kwargs),
        context=GovernContext(
            prompt_hash="b" * 64,
            model_version="qwen3-0.6b",
        ),
        trace_id="01HW",
    )


def _factory_for(
    reviewer_id: ReviewerId, decision: VerdictDecision
) -> Callable[[uuid.UUID, str], Awaitable[ReviewerVerdict]]:
    async def _factory(audit_id: uuid.UUID, _summary: str) -> ReviewerVerdict:
        return ReviewerVerdict(
            reviewer_id=reviewer_id,
            decision=decision,
            confidence=0.9,
            reasoning=f"{reviewer_id.value}-{decision.value}",
            audit_id=audit_id,
        )

    return _factory


def _orchestrator_for(
    decisions: tuple[VerdictDecision, VerdictDecision, VerdictDecision],
) -> TriadOrchestrator:
    return TriadOrchestrator(
        reviewer_a=MockReviewer(
            _reviewer_id=ReviewerId.REVIEWER_A,
            factory=_factory_for(ReviewerId.REVIEWER_A, decisions[0]),
        ),
        reviewer_b=MockReviewer(
            _reviewer_id=ReviewerId.REVIEWER_B,
            factory=_factory_for(ReviewerId.REVIEWER_B, decisions[1]),
        ),
        reviewer_c=MockReviewer(
            _reviewer_id=ReviewerId.REVIEWER_C,
            factory=_factory_for(ReviewerId.REVIEWER_C, decisions[2]),
        ),
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


async def test_router_with_triad_allow_path_skips_triad() -> None:
    """Registered tool, no policies -> base ALLOW; triad must NOT run.

    Verify by passing a triad whose factories would crash if invoked
    (we'd see a non-ALLOW outcome). The bypass must short-circuit
    before triad.run.
    """

    async def boom(*_: object) -> ReviewerVerdict:
        raise AssertionError("triad must not be invoked on ALLOW path")

    triad = TriadOrchestrator(
        reviewer_a=MockReviewer(
            _reviewer_id=ReviewerId.REVIEWER_A, factory=boom
        ),
        reviewer_b=MockReviewer(
            _reviewer_id=ReviewerId.REVIEWER_B, factory=boom
        ),
        reviewer_c=MockReviewer(
            _reviewer_id=ReviewerId.REVIEWER_C, factory=boom
        ),
    )
    req = _request_for_tool("read_account_balance")
    resp = await decide_via_router_with_triad(req, triad=triad)
    assert resp.decision == Decision.ALLOW
    assert resp.triad_invoked is False


async def test_router_with_triad_deny_path_skips_triad() -> None:
    """Unregistered tool -> firewall DENY; triad must NOT run."""

    async def boom(*_: object) -> ReviewerVerdict:
        raise AssertionError("triad must not be invoked on DENY path")

    triad = TriadOrchestrator(
        reviewer_a=MockReviewer(
            _reviewer_id=ReviewerId.REVIEWER_A, factory=boom
        ),
        reviewer_b=MockReviewer(
            _reviewer_id=ReviewerId.REVIEWER_B, factory=boom
        ),
        reviewer_c=MockReviewer(
            _reviewer_id=ReviewerId.REVIEWER_C, factory=boom
        ),
    )
    req = _request_for_tool("shutdown_production")
    resp = await decide_via_router_with_triad(req, triad=triad)
    assert resp.decision == Decision.DENY
    assert resp.policy_id == "firewall.tool_not_registered"


async def test_router_with_triad_unanimous_allow_overrides_escalate() -> None:
    """Inject ABSTAIN policy -> base ESCALATE; triad UNANIMOUS ALLOW
    overrides to ALLOW with triad_invoked=True."""
    triad = _orchestrator_for(
        (VerdictDecision.ALLOW, VerdictDecision.ALLOW, VerdictDecision.ALLOW)
    )
    req = _request_for_tool("transfer_funds")
    decisions = (
        (
            "verixa.x.unknown",
            PolicyDecision(
                decision=PolicyDecisionKind.ABSTAIN, reason="undefined"
            ),
        ),
    )
    resp = await decide_via_router_with_triad(
        req, triad=triad, policy_decisions=decisions
    )
    assert resp.decision == Decision.ALLOW
    assert resp.triad_invoked is True
    assert resp.triad_consensus == "unanimous"


async def test_router_with_triad_majority_deny_overrides_escalate() -> None:
    """Triad MAJORITY DENY (B+C agree, A dissents) overrides to DENY."""
    triad = _orchestrator_for(
        (VerdictDecision.ALLOW, VerdictDecision.DENY, VerdictDecision.DENY)
    )
    req = _request_for_tool("transfer_funds")
    decisions = (
        (
            "verixa.x.unknown",
            PolicyDecision(
                decision=PolicyDecisionKind.ABSTAIN, reason="undefined"
            ),
        ),
    )
    resp = await decide_via_router_with_triad(
        req, triad=triad, policy_decisions=decisions
    )
    assert resp.decision == Decision.DENY
    assert resp.triad_invoked is True
    assert resp.triad_consensus == "majority"


async def test_router_with_triad_split_stays_escalate() -> None:
    """Triad SPLIT -> decision stays ESCALATE; triad_consensus='split'."""
    triad = _orchestrator_for(
        (
            VerdictDecision.ALLOW,
            VerdictDecision.DENY,
            VerdictDecision.ESCALATE,
        )
    )
    req = _request_for_tool("transfer_funds")
    decisions = (
        (
            "verixa.x.unknown",
            PolicyDecision(
                decision=PolicyDecisionKind.ABSTAIN, reason="undefined"
            ),
        ),
    )
    resp = await decide_via_router_with_triad(
        req, triad=triad, policy_decisions=decisions
    )
    assert resp.decision == Decision.ESCALATE
    assert resp.triad_invoked is True
    assert resp.triad_consensus == "split"


async def test_router_with_triad_unanimous_escalate_stays_escalate() -> None:
    """All three vote ESCALATE -> UNANIMOUS ESCALATE; gateway leaves
    decision as ESCALATE but flags triad_invoked=True and surfaces
    triad_consensus='unanimous'."""
    triad = _orchestrator_for(
        (
            VerdictDecision.ESCALATE,
            VerdictDecision.ESCALATE,
            VerdictDecision.ESCALATE,
        )
    )
    req = _request_for_tool("transfer_funds")
    decisions = (
        (
            "verixa.x.unknown",
            PolicyDecision(
                decision=PolicyDecisionKind.ABSTAIN, reason="undefined"
            ),
        ),
    )
    resp = await decide_via_router_with_triad(
        req, triad=triad, policy_decisions=decisions
    )
    assert resp.decision == Decision.ESCALATE
    assert resp.triad_invoked is True
    # Although the kind is UNANIMOUS, the agreed_decision is ESCALATE,
    # so the gateway keeps the response as ESCALATE.
    assert resp.triad_consensus == "unanimous"


async def test_router_with_triad_summary_includes_tool_and_role() -> None:
    """Smoke: the prompt the triad sees mentions tool + role.

    Capture the summary by intercepting via a factory that records it.
    """
    captured: dict[str, str] = {}

    async def recording_factory(
        audit_id: uuid.UUID, summary: str
    ) -> ReviewerVerdict:
        captured["summary"] = summary
        return ReviewerVerdict(
            reviewer_id=ReviewerId.REVIEWER_A,
            decision=VerdictDecision.ALLOW,
            confidence=1.0,
            reasoning="ok",
            audit_id=audit_id,
        )

    triad = TriadOrchestrator(
        reviewer_a=MockReviewer(
            _reviewer_id=ReviewerId.REVIEWER_A, factory=recording_factory
        ),
        reviewer_b=MockReviewer(
            _reviewer_id=ReviewerId.REVIEWER_B,
            factory=_factory_for(ReviewerId.REVIEWER_B, VerdictDecision.ALLOW),
        ),
        reviewer_c=MockReviewer(
            _reviewer_id=ReviewerId.REVIEWER_C,
            factory=_factory_for(ReviewerId.REVIEWER_C, VerdictDecision.ALLOW),
        ),
    )
    req = _request_for_tool("transfer_funds")
    decisions = (
        (
            "verixa.x.unknown",
            PolicyDecision(
                decision=PolicyDecisionKind.ABSTAIN, reason="undefined"
            ),
        ),
    )
    await decide_via_router_with_triad(
        req, triad=triad, policy_decisions=decisions
    )
    assert "transfer_funds" in captured["summary"]
    assert "loan-officer" in captured["summary"]
    assert str(_WF_ID) in captured["summary"]


async def test_router_with_triad_summary_handles_missing_tool_name() -> None:
    """When action has no tool_name, summary substitutes '<none>'.

    This path is exercised by triggering the firewall DENY (no tool
    name), but we want the summariser specifically -- so we build a
    request with tool_name=None and inject ABSTAIN to force ESCALATE
    before firewall has a chance to deny... actually, no_tool_name
    DENIES at the firewall (CODE_NO_TOOL_NAME), not ESCALATEs. So
    this branch is only reachable if the triad is invoked WITHOUT
    going through decide_via_router. We exercise it directly via
    the helper to keep coverage 100pct without contorting the
    request path.
    """
    from verixa_runtime.gateway.govern import _summarise_request_for_triad

    req = _request_for_tool(None)
    summary = _summarise_request_for_triad(req)
    assert "<none>" in summary
    assert "loan-officer" in summary
