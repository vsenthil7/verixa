"""Integration tests for the wired Control Plane FastAPI app (CP-14.5).

Hits real HTTP routes via FastAPI's TestClient. Every endpoint is
exercised at least once happy-path + at least one error path, plus
an end-to-end flow that goes through register -> snapshot (via the
state.snapshotter back-door so we don't need a runtime gateway in
this test) -> audit-query -> replay -> dossier-generate -> dossier-get
-> offline-verify.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from verixa_runtime.dossier import SignedDossier, verify_signed_dossier
from verixa_runtime.dossier.manifest import DossierManifest
from verixa_runtime.replay.snapshotter import SnapshotInputs

from verixa_control_plane.audit import AuditLedgerEntry
from verixa_control_plane.routes import (
    build_default_state,
    create_app_with_state,
)


def _client() -> tuple[TestClient, "ControlPlaneStateType"]:  # type: ignore[name-defined]
    state = build_default_state()
    app = create_app_with_state(state)
    return TestClient(app), state


# ---------------------------------------------------------------------------
# Operational endpoints still work after we mount the router
# ---------------------------------------------------------------------------


def test_healthz_still_works() -> None:
    client, _ = _client()
    r = client.get("/healthz")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_openapi_includes_control_plane_routes() -> None:
    """The generated OpenAPI schema lists every /v1/control/* path."""
    client, _ = _client()
    spec = client.get("/openapi.json").json()
    paths = spec["paths"]
    assert "/v1/control/workflows" in paths
    assert "/v1/control/agents" in paths
    assert "/v1/control/tools" in paths
    assert "/v1/control/audit" in paths
    assert "/v1/control/replay" in paths
    assert "/v1/control/dossier" in paths
    assert "/v1/control/dossier/{dossier_id}" in paths


def test_create_app_with_state_default_path() -> None:
    """create_app_with_state(None) -- the default-state branch.

    Exercises the ``if state is None: state = build_default_state()``
    path. Confirms the resulting app responds on /healthz and has
    the control-plane routes attached."""
    app = create_app_with_state()  # no state -> default
    client = TestClient(app)
    assert client.get("/healthz").status_code == 200
    # Empty workflow list confirms the wired-up state has an
    # empty in-memory registry attached.
    r = client.get("/v1/control/workflows")
    assert r.status_code == 200
    assert r.json()["total"] == 0


# ---------------------------------------------------------------------------
# Workflow endpoints
# ---------------------------------------------------------------------------


def test_post_workflows_creates_and_get_lists() -> None:
    client, _ = _client()
    # POST create
    r = client.post(
        "/v1/control/workflows",
        json={
            "name": "loan-approval",
            "sector": "financial-services",
            "risk_threshold_escalate": 0.4,
        },
    )
    assert r.status_code == 200
    workflow_id = r.json()["workflow_id"]
    # GET list reflects the new row
    r2 = client.get("/v1/control/workflows")
    assert r2.status_code == 200
    body = r2.json()
    assert body["total"] == 1
    assert body["workflows"][0]["workflow_id"] == workflow_id
    assert body["workflows"][0]["agent_count"] == 0


def test_post_workflows_rejects_empty_name() -> None:
    client, _ = _client()
    r = client.post("/v1/control/workflows", json={"name": ""})
    assert r.status_code == 422  # FastAPI/Pydantic validation


# ---------------------------------------------------------------------------
# Agent endpoints
# ---------------------------------------------------------------------------


def test_post_agents_success() -> None:
    client, _ = _client()
    wf = client.post(
        "/v1/control/workflows", json={"name": "wf"}
    ).json()
    r = client.post(
        "/v1/control/agents",
        json={
            "workflow_id": wf["workflow_id"],
            "spiffe_id": "spiffe://example/agent/a",
            "role": "loan-officer",
        },
    )
    assert r.status_code == 200
    assert r.json()["workflow_id"] == wf["workflow_id"]


def test_post_agents_unknown_workflow_returns_404() -> None:
    client, _ = _client()
    r = client.post(
        "/v1/control/agents",
        json={
            "workflow_id": str(uuid.uuid4()),
            "spiffe_id": "spiffe://x",
            "role": "x",
        },
    )
    assert r.status_code == 404
    assert r.json()["error"] == "workflow_not_found"


# ---------------------------------------------------------------------------
# Tool endpoints
# ---------------------------------------------------------------------------


def test_post_tools_with_no_restriction() -> None:
    client, _ = _client()
    r = client.post(
        "/v1/control/tools", json={"name": "read_account_balance"}
    )
    assert r.status_code == 200
    assert r.json()["allowed_workflow_ids"] == []


def test_post_tools_with_unknown_workflow_returns_400() -> None:
    client, _ = _client()
    r = client.post(
        "/v1/control/tools",
        json={
            "name": "transfer_funds",
            "allowed_workflow_ids": [str(uuid.uuid4())],
        },
    )
    assert r.status_code == 400
    assert r.json()["error"] == "invalid_workflow_reference"


# ---------------------------------------------------------------------------
# Replay endpoint (needs a seeded snapshot)
# ---------------------------------------------------------------------------


async def _seed_one_audit(state, *, workflow_id, tenant_id, audit_id, decision="allow"):
    await state.snapshotter.snapshot(
        SnapshotInputs(
            audit_id=audit_id,
            tenant_id=tenant_id,
            decision=decision,
            risk_score=0.1,
            request_envelope={
                "action": {
                    "type": "tool_call",
                    "tool_name": "transfer_funds",
                },
                "workflow_id": str(workflow_id),
            },
        )
    )


def test_post_replay_returns_seeded_bundle() -> None:
    import asyncio

    client, state = _client()
    wf_id = uuid.uuid4()
    tenant_id = uuid.uuid4()
    audit_id = uuid.uuid4()
    asyncio.run(
        _seed_one_audit(
            state, workflow_id=wf_id, tenant_id=tenant_id, audit_id=audit_id
        )
    )
    r = client.post(
        "/v1/control/replay", json={"audit_id": str(audit_id)}
    )
    assert r.status_code == 200
    body = r.json()
    assert body["audit_id"] == str(audit_id)
    assert body["tenant_id"] == str(tenant_id)
    assert body["decision"] == "allow"


def test_post_replay_unknown_audit_returns_404() -> None:
    client, _ = _client()
    r = client.post(
        "/v1/control/replay", json={"audit_id": str(uuid.uuid4())}
    )
    assert r.status_code == 404
    assert r.json()["error"] == "audit_not_found"


# ---------------------------------------------------------------------------
# Audit endpoint (needs a seeded ledger)
# ---------------------------------------------------------------------------


def test_get_audit_returns_seeded_entries() -> None:
    import asyncio

    client, state = _client()
    wf_id = uuid.uuid4()
    now = datetime.now(timezone.utc)

    async def seed():
        await state.audit_ledger.append(
            AuditLedgerEntry(
                audit_id=uuid.uuid4(),
                workflow_id=wf_id,
                tenant_id=uuid.uuid4(),
                decision="deny",
                risk_score=0.9,
                risk_classification="critical",
                triad_invoked=True,
                timestamp=now,
            )
        )

    asyncio.run(seed())
    r = client.get(
        "/v1/control/audit",
        params={
            "workflow_id": str(wf_id),
            "from": (now - timedelta(minutes=1)).isoformat(),
            "to": (now + timedelta(minutes=1)).isoformat(),
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 1
    assert body["entries"][0]["decision"] == "deny"
    assert body["entries"][0]["risk_classification"] == "critical"
    assert body["entries"][0]["triad_invoked"] is True


def test_get_audit_inverted_range_returns_400() -> None:
    client, _ = _client()
    now = datetime.now(timezone.utc)
    r = client.get(
        "/v1/control/audit",
        params={
            "workflow_id": str(uuid.uuid4()),
            "from": (now + timedelta(hours=1)).isoformat(),
            "to": now.isoformat(),
        },
    )
    assert r.status_code == 400
    assert r.json()["error"] == "invalid_time_range"


# ---------------------------------------------------------------------------
# Dossier endpoints + end-to-end trust anchor
# ---------------------------------------------------------------------------


def test_dossier_generate_and_get_round_trip() -> None:
    import asyncio

    client, state = _client()
    wf_id = uuid.uuid4()
    tenant_id = uuid.uuid4()
    audit_id = uuid.uuid4()
    asyncio.run(
        _seed_one_audit(
            state, workflow_id=wf_id, tenant_id=tenant_id, audit_id=audit_id
        )
    )
    # Generate
    gen = client.post(
        "/v1/control/dossier",
        json={
            "audit_id": str(audit_id),
            "action_summary": "transfer_funds approved by loan officer",
        },
    )
    assert gen.status_code == 200
    dossier_id = gen.json()["dossier_id"]
    # Get
    got = client.get(f"/v1/control/dossier/{dossier_id}")
    assert got.status_code == 200
    body = got.json()
    assert body["audit_id"] == str(audit_id)
    assert len(body["signature_hex"]) == 128
    assert len(body["public_key_hex"]) == 64


def test_dossier_get_unknown_returns_404() -> None:
    client, _ = _client()
    r = client.get(f"/v1/control/dossier/{uuid.uuid4()}")
    assert r.status_code == 404
    assert r.json()["error"] == "dossier_not_found"


def test_end_to_end_trust_anchor_via_http() -> None:
    """Full operator+auditor flow through real HTTP:

      1. Operator registers a workflow + agent + tool.
      2. (Behind the scenes the runtime would call snapshot.
         We do it here via the snapshotter on the shared state.)
      3. Operator queries the audit log -- finds the decision.
         (We seed the ledger by hand because the runtime gateway
         doesn't write to it yet -- that's Phase-1 wiring.)
      4. Operator generates a dossier via POST /v1/control/dossier.
      5. Auditor fetches GET /v1/control/dossier/{id}.
      6. Auditor reconstructs a SignedDossier locally from the JSON
         and runs verify_signed_dossier -- must NOT raise.

    This is the proof Verixa actually works for the demo scenario.
    """
    import asyncio

    client, state = _client()

    # Step 1: register workflow/agent/tool via HTTP.
    wf = client.post(
        "/v1/control/workflows",
        json={"name": "loan-approval", "sector": "financial-services"},
    ).json()
    workflow_id = uuid.UUID(wf["workflow_id"])
    client.post(
        "/v1/control/agents",
        json={
            "workflow_id": wf["workflow_id"],
            "spiffe_id": "spiffe://example/loan-officer-1",
            "role": "loan-officer",
        },
    )
    client.post(
        "/v1/control/tools",
        json={
            "name": "transfer_funds",
            "allowed_workflow_ids": [wf["workflow_id"]],
        },
    )

    # Step 2: simulate a runtime decision by seeding the snapshot
    # + audit ledger on the shared state.
    tenant_id = uuid.uuid4()
    audit_id = uuid.uuid4()
    now = datetime.now(timezone.utc)

    async def seed():
        await state.snapshotter.snapshot(
            SnapshotInputs(
                audit_id=audit_id,
                tenant_id=tenant_id,
                decision="allow",
                risk_score=0.15,
                request_envelope={
                    "action": {
                        "type": "tool_call",
                        "tool_name": "transfer_funds",
                    },
                    "workflow_id": str(workflow_id),
                },
            )
        )
        await state.audit_ledger.append(
            AuditLedgerEntry(
                audit_id=audit_id,
                workflow_id=workflow_id,
                tenant_id=tenant_id,
                decision="allow",
                risk_score=0.15,
                risk_classification="low",
                triad_invoked=False,
                timestamp=now,
            )
        )

    asyncio.run(seed())

    # Step 3: operator queries audit -- finds the decision.
    audit_resp = client.get(
        "/v1/control/audit",
        params={
            "workflow_id": str(workflow_id),
            "from": (now - timedelta(minutes=1)).isoformat(),
            "to": (now + timedelta(minutes=1)).isoformat(),
        },
    )
    assert audit_resp.status_code == 200
    assert audit_resp.json()["total"] == 1

    # Step 4: operator generates dossier.
    gen_resp = client.post(
        "/v1/control/dossier",
        json={
            "audit_id": str(audit_id),
            "action_summary": "loan officer transfer 5000 USD approved",
        },
    )
    assert gen_resp.status_code == 200
    dossier_id = gen_resp.json()["dossier_id"]

    # Step 5: auditor fetches the dossier.
    get_resp = client.get(f"/v1/control/dossier/{dossier_id}")
    assert get_resp.status_code == 200
    body = get_resp.json()

    # Step 6: auditor verifies OFFLINE using only the JSON payload.
    # Reconstruct the SignedDossier locally.
    m = body["manifest"]
    manifest = DossierManifest(
        audit_id=uuid.UUID(m["audit_id"]),
        tenant_id=uuid.UUID(m["tenant_id"]),
        generated_at_unix_ns=m["generated_at_unix_ns"],
        decision=m["decision"],
        risk_score=m["risk_score"],
        risk_classification=m["risk_classification"],
        action_summary=m["action_summary"],
        policy_evaluations=tuple(
            (p["package"], p["decision"], p["reason"])
            for p in m["policy_evaluations"]
        ),
        triad_consensus=m["triad_consensus"],
        triad_agreed_decision=m["triad_agreed_decision"],
        triad_dissenters=tuple(m["triad_dissenters"]),
        retrieved_documents=tuple(
            (d["doc_id"], d["content_sha256"])
            for d in m["retrieved_documents"]
        ),
        replay_storage_key=m["replay_storage_key"],
        signing_key_id=m["signing_key_id"],
    )
    signed = SignedDossier(
        manifest=manifest,
        signature_hex=body["signature_hex"],
        public_key_hex=body["public_key_hex"],
    )
    verify_signed_dossier(signed)  # MUST NOT raise -- this is the trust anchor
