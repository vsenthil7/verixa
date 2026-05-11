"""Phase-0 demo seed data (CP-16).

Pre-loads a ControlPlaneState with a realistic financial-services
scenario so the demo shows something more compelling than empty
registries.

Scenario: a small US community bank using Verixa to govern its
loan-approval workflow. One workflow, one agent (a loan officer's
AI assistant), four tools, three historical decisions across the
risk spectrum, one pre-generated signed dossier.

Usage:

  state = build_default_state()
  await seed_financial_services_demo(state)
  app = create_app_with_state(state)

The seed function is async because every collaborator (registries,
ledger, snapshotter, dossier store) is async. It is idempotent
ONLY in the sense that re-running it produces fresh IDs each time;
it does NOT detect existing data and skip -- callers must seed at
most once per state.

This is demo data, NOT production fixtures: timestamps are pinned
to a fixed window in May 2026 so the demo always looks the same;
amounts and customer names are illustrative.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime

from verixa_runtime.replay.bundle import (
    PolicyEvaluationRecord,
    TriadReviewRecord,
)
from verixa_runtime.replay.snapshotter import SnapshotInputs

from verixa_control_plane.audit import AuditLedgerEntry
from verixa_control_plane.envelopes import (
    AgentRegisterRequest,
    DossierGenerateRequest,
    ToolRegisterRequest,
    WorkflowRegisterRequest,
)
from verixa_control_plane.handlers import handle_dossier_generate
from verixa_control_plane.registry import (
    handle_agent_register,
    handle_tool_register,
    handle_workflow_register,
)
from verixa_control_plane.routes import ControlPlaneState

# Pinned timestamps so the demo always shows the same audit history.
_T0 = datetime(2026, 5, 10, 9, 15, tzinfo=UTC)
_T1 = datetime(2026, 5, 10, 11, 42, tzinfo=UTC)
_T2 = datetime(2026, 5, 10, 14, 3, tzinfo=UTC)


@dataclass(frozen=True)
class DemoSeedResult:
    """Handles to every entity the seed function created.

    Callers (tests, demo scripts, UI bootstrap) use this to surface
    the same audit_ids and dossier_id the seed put in the system,
    so demo URLs and screenshots remain stable.
    """

    workflow_id: uuid.UUID
    agent_id: uuid.UUID
    tenant_id: uuid.UUID
    audit_ids: tuple[uuid.UUID, uuid.UUID, uuid.UUID]
    dossier_id: uuid.UUID
    tool_ids: tuple[uuid.UUID, ...] = field(default_factory=tuple)


async def seed_financial_services_demo(
    state: ControlPlaneState,
    *,
    tenant_id: uuid.UUID | None = None,
) -> DemoSeedResult:
    """Pre-load ``state`` with the loan-approval demo scenario.

    Returns a DemoSeedResult carrying the IDs the seed minted so
    callers can build deep links.
    """
    tenant_id = tenant_id or uuid.UUID("11111111-2222-3333-4444-555555555555")

    # ------------------------------------------------------------------
    # 1. Workflow
    # ------------------------------------------------------------------
    _, wf_resp = await handle_workflow_register(
        WorkflowRegisterRequest(
            name="Loan Approval Workflow",
            description=(
                "Small-business loan applications under USD 50,000 "
                "auto-routed through credit checks and approved by "
                "an AI loan officer; over-limit applications "
                "escalate to triad review."
            ),
            sector="financial-services",
            risk_threshold_escalate=0.40,
        ),
        workflow_registry=state.workflow_registry,
        now=_T0,
    )
    workflow_id = wf_resp.workflow_id

    # ------------------------------------------------------------------
    # 2. Agent
    # ------------------------------------------------------------------
    _, agent_resp = await handle_agent_register(
        AgentRegisterRequest(
            workflow_id=workflow_id,
            spiffe_id="spiffe://example-bank.com/loan-officer-agent-001",
            role="loan-officer",
            description=(
                "AI loan-officer assistant for the small-business "
                "lending desk."
            ),
        ),
        workflow_registry=state.workflow_registry,
        agent_registry=state.agent_registry,
        now=_T0,
    )
    agent_id = agent_resp.agent_id

    # ------------------------------------------------------------------
    # 3. Tools
    # ------------------------------------------------------------------
    tool_ids: list[uuid.UUID] = []
    for tool_req in [
        ToolRegisterRequest(
            name="read_account_balance",
            description="Read-only: customer account balance lookup.",
        ),
        ToolRegisterRequest(
            name="lookup_customer",
            description="Read-only: customer profile and KYC status lookup.",
        ),
        ToolRegisterRequest(
            name="transfer_funds",
            description="Transfer funds between accounts (high-risk).",
            allowed_workflow_ids=[workflow_id],
        ),
        ToolRegisterRequest(
            name="submit_payment",
            description="Submit an outbound payment instruction (high-risk).",
            allowed_workflow_ids=[workflow_id],
        ),
    ]:
        _, tool_resp = await handle_tool_register(
            tool_req,
            workflow_registry=state.workflow_registry,
            tool_registry=state.tool_registry,
            now=_T0,
        )
        tool_ids.append(tool_resp.tool_id)

    # ------------------------------------------------------------------
    # 4. Three historical decisions (different risk profiles)
    # ------------------------------------------------------------------

    # Decision A: low-risk lookup, ALLOW
    audit_a = uuid.uuid4()
    await state.snapshotter.snapshot(
        SnapshotInputs(
            audit_id=audit_a,
            tenant_id=tenant_id,
            decision="allow",
            risk_score=0.05,
            request_envelope={
                "action": {
                    "type": "tool_call",
                    "tool_name": "lookup_customer",
                    "arguments": {"customer_id": "C-10042"},
                },
                "workflow_id": str(workflow_id),
                "role": "loan-officer",
            },
        ),
        timestamp_unix_ns=int(_T0.timestamp() * 1_000_000_000),
    )
    await state.audit_ledger.append(
        AuditLedgerEntry(
            audit_id=audit_a,
            workflow_id=workflow_id,
            tenant_id=tenant_id,
            decision="allow",
            risk_score=0.05,
            risk_classification="low",
            triad_invoked=False,
            timestamp=_T0,
        )
    )

    # Decision B: medium-risk transfer, ESCALATE -> ALLOW via triad MAJORITY
    audit_b = uuid.uuid4()
    triad_b = TriadReviewRecord(
        consensus_kind="majority",
        agreed_decision="allow",
        verdicts=(
            ("reviewer_a", "allow", 0.85,
             "Customer is in good standing; KYC complete; amount within profile."),
            ("reviewer_b", "allow", 0.78,
             "Transfer pattern consistent with normal business flow."),
            ("reviewer_c", "escalate", 0.65,
             "Amount above prior 90-day average; flag for human spot-check."),
        ),
        commitments=(
            ("reviewer_a", "a" * 64),
            ("reviewer_b", "b" * 64),
            ("reviewer_c", "c" * 64),
        ),
    )
    await state.snapshotter.snapshot(
        SnapshotInputs(
            audit_id=audit_b,
            tenant_id=tenant_id,
            decision="allow",
            risk_score=0.42,
            request_envelope={
                "action": {
                    "type": "tool_call",
                    "tool_name": "transfer_funds",
                    "arguments": {
                        "from_account": "BANK-0042",
                        "to_account": "VENDOR-9981",
                        "amount_usd": 12500,
                    },
                },
                "workflow_id": str(workflow_id),
                "role": "loan-officer",
            },
            policy_evaluations=(
                PolicyEvaluationRecord(
                    package="verixa.fs.transfer_limit",
                    decision="pass",
                    reason="USD 12,500 within USD 50,000 workflow limit",
                ),
                PolicyEvaluationRecord(
                    package="verixa.fs.beneficiary_verification",
                    decision="pass",
                    reason="VENDOR-9981 is on the approved beneficiary list",
                ),
            ),
            triad_review=triad_b,
        ),
        timestamp_unix_ns=int(_T1.timestamp() * 1_000_000_000),
    )
    await state.audit_ledger.append(
        AuditLedgerEntry(
            audit_id=audit_b,
            workflow_id=workflow_id,
            tenant_id=tenant_id,
            decision="allow",
            risk_score=0.42,
            risk_classification="medium",
            triad_invoked=True,
            timestamp=_T1,
        )
    )

    # Decision C: high-risk transfer, DENY via policy_fail
    audit_c = uuid.uuid4()
    await state.snapshotter.snapshot(
        SnapshotInputs(
            audit_id=audit_c,
            tenant_id=tenant_id,
            decision="deny",
            risk_score=0.88,
            request_envelope={
                "action": {
                    "type": "tool_call",
                    "tool_name": "transfer_funds",
                    "arguments": {
                        "from_account": "BANK-0042",
                        "to_account": "UNKNOWN-7724",
                        "amount_usd": 95000,
                    },
                },
                "workflow_id": str(workflow_id),
                "role": "loan-officer",
            },
            policy_evaluations=(
                PolicyEvaluationRecord(
                    package="verixa.fs.transfer_limit",
                    decision="fail",
                    reason=(
                        "USD 95,000 exceeds USD 50,000 workflow limit"
                    ),
                ),
                PolicyEvaluationRecord(
                    package="verixa.fs.beneficiary_verification",
                    decision="fail",
                    reason=(
                        "UNKNOWN-7724 is not on the approved beneficiary list"
                    ),
                ),
            ),
        ),
        timestamp_unix_ns=int(_T2.timestamp() * 1_000_000_000),
    )
    await state.audit_ledger.append(
        AuditLedgerEntry(
            audit_id=audit_c,
            workflow_id=workflow_id,
            tenant_id=tenant_id,
            decision="deny",
            risk_score=0.88,
            risk_classification="critical",
            triad_invoked=False,
            timestamp=_T2,
        )
    )

    # ------------------------------------------------------------------
    # 5. Pre-generate the signed dossier for decision B (the interesting one)
    # ------------------------------------------------------------------
    _, gen_resp = await handle_dossier_generate(
        DossierGenerateRequest(
            audit_id=audit_b,
            action_summary=(
                "Loan officer approved USD 12,500 vendor transfer; "
                "triad MAJORITY allow with reviewer_c dissent flagging "
                "above-average amount."
            ),
        ),
        reconstructor=state.reconstructor,
        dossier_store=state.dossier_store,
        signing_keypair=state.signing_keypair,
        signing_key_id=state.signing_key_id,
        generated_at_unix_ns=int(_T1.timestamp() * 1_000_000_000) + 60_000_000_000,
    )

    return DemoSeedResult(
        workflow_id=workflow_id,
        agent_id=agent_id,
        tenant_id=tenant_id,
        audit_ids=(audit_a, audit_b, audit_c),
        dossier_id=gen_resp.dossier_id,
        tool_ids=tuple(tool_ids),
    )


__all__ = [
    "DemoSeedResult",
    "seed_financial_services_demo",
]
