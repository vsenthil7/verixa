"""pytest suite for verixa_control_plane.demo_seed (CP-16).

Smoke + integration tests:
  - The seed runs to completion without raising
  - Every entity surfaces in the in-memory stores
  - The pre-generated dossier verifies offline
  - The seed result IDs match what the HTTP endpoints would return
"""

from __future__ import annotations

import uuid
from datetime import UTC

import pytest
from fastapi.testclient import TestClient
from verixa_control_plane.demo_seed import (
    DemoSeedResult,
    seed_financial_services_demo,
)
from verixa_control_plane.routes import (
    build_default_state,
    create_app_with_state,
)
from verixa_runtime.dossier import verify_signed_dossier


async def test_seed_runs_to_completion() -> None:
    state = build_default_state()
    result = await seed_financial_services_demo(state)
    assert isinstance(result, DemoSeedResult)


async def test_seed_creates_one_workflow_with_one_agent() -> None:
    state = build_default_state()
    result = await seed_financial_services_demo(state)
    workflows = await state.workflow_registry.list_all()
    assert len(workflows) == 1
    assert workflows[0].workflow_id == result.workflow_id
    assert workflows[0].sector == "financial-services"
    # And the workflow has 1 agent attached.
    assert await state.workflow_registry.count_agents(result.workflow_id) == 1


async def test_seed_creates_four_tools() -> None:
    state = build_default_state()
    result = await seed_financial_services_demo(state)
    assert len(result.tool_ids) == 4


async def test_seed_creates_three_audit_entries() -> None:
    """Each of the three decisions lands in both the snapshotter
    (for replay) and the audit ledger (for query)."""
    from datetime import datetime

    state = build_default_state()
    result = await seed_financial_services_demo(state)
    # Query all three across a wide window.
    all_entries = await state.audit_ledger.query(
        workflow_id=result.workflow_id,
        from_timestamp=datetime(2026, 1, 1, tzinfo=UTC),
        to_timestamp=datetime(2026, 12, 31, tzinfo=UTC),
    )
    assert len(all_entries) == 3
    decisions = {e.decision for e in all_entries}
    assert decisions == {"allow", "deny"}  # two allows + one deny
    classifications = {e.risk_classification for e in all_entries}
    assert classifications == {"low", "medium", "critical"}


async def test_seed_audit_b_is_the_triad_decision() -> None:
    """Decision B is the medium-risk transfer with triad MAJORITY ALLOW.
    Verify by replaying the bundle and inspecting triad_review."""
    state = build_default_state()
    result = await seed_financial_services_demo(state)
    audit_b = result.audit_ids[1]
    bundle = await state.reconstructor.reconstruct(audit_b)
    assert bundle.decision == "allow"
    assert bundle.risk_score == pytest.approx(0.42)
    assert bundle.triad_review is not None
    assert bundle.triad_review.consensus_kind == "majority"
    assert bundle.triad_review.agreed_decision == "allow"
    assert len(bundle.triad_review.verdicts) == 3


async def test_seed_audit_c_is_the_policy_deny() -> None:
    """Decision C is the high-risk USD 95,000 transfer that policy-fails."""
    state = build_default_state()
    result = await seed_financial_services_demo(state)
    audit_c = result.audit_ids[2]
    bundle = await state.reconstructor.reconstruct(audit_c)
    assert bundle.decision == "deny"
    assert bundle.risk_score == pytest.approx(0.88)
    assert bundle.triad_review is None  # firewall/policy denial short-circuits
    # Both policy evaluations are fail.
    assert len(bundle.policy_evaluations) == 2
    assert all(p.decision == "fail" for p in bundle.policy_evaluations)


async def test_seed_pre_generated_dossier_verifies_offline() -> None:
    """The pre-generated SignedDossier for decision B passes
    verify_signed_dossier without further info -- proves the seed
    produces a real, valid evidence pack ready to hand to an auditor."""
    state = build_default_state()
    result = await seed_financial_services_demo(state)
    signed = await state.dossier_store.get(result.dossier_id)
    verify_signed_dossier(signed)  # must NOT raise
    # And the dossier is for decision B (the triad one).
    assert signed.manifest.audit_id == result.audit_ids[1]


async def test_seed_with_explicit_tenant_id() -> None:
    """Caller can pin tenant_id; the seed uses it everywhere."""
    state = build_default_state()
    custom_tid = uuid.UUID("99999999-8888-7777-6666-555555555555")
    result = await seed_financial_services_demo(state, tenant_id=custom_tid)
    assert result.tenant_id == custom_tid
    # Confirm the snapshots carry the custom tenant_id.
    bundle = await state.reconstructor.reconstruct(result.audit_ids[0])
    assert bundle.tenant_id == custom_tid


# ---------------------------------------------------------------------------
# Full HTTP-level smoke: seed + serve + auditor flow
# ---------------------------------------------------------------------------


def test_seeded_app_serves_demo_via_http() -> None:
    """Build the app with a seeded state; hit every demo URL through
    TestClient; everything works without any operator action."""
    import asyncio

    state = build_default_state()
    result = asyncio.run(seed_financial_services_demo(state))
    app = create_app_with_state(state)
    client = TestClient(app)

    # List workflows: 1 entry, agent_count=1.
    r = client.get("/v1/control/workflows")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 1
    assert body["workflows"][0]["agent_count"] == 1

    # Replay decision B (the triad one).
    r = client.post(
        "/v1/control/replay",
        json={"audit_id": str(result.audit_ids[1])},
    )
    assert r.status_code == 200
    rep = r.json()
    assert rep["decision"] == "allow"
    assert rep["triad_review"]["consensus_kind"] == "majority"

    # Fetch the pre-generated dossier.
    r = client.get(f"/v1/control/dossier/{result.dossier_id}")
    assert r.status_code == 200
    dos = r.json()
    assert dos["audit_id"] == str(result.audit_ids[1])
    assert len(dos["signature_hex"]) == 128
