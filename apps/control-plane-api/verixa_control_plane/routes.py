"""Control Plane FastAPI route wiring (CP-14.5).

Wraps the CP-14.2/14.3/14.4 handlers into HTTP routes. Each route
pulls its collaborators from app.state via FastAPI's dependency
system, calls the handler, and translates the (status, envelope)
tuple into a JSONResponse with the right status code.

App-state container holds in-memory implementations for Phase-0:

  - WorkflowRegistry / AgentRegistry / ToolRegistry
  - AuditLedger
  - BundleStore + AuditIndex + TenantKeyResolver (replay)
  - Snapshotter + Reconstructor wired around the three above
  - DossierStore
  - Signing keypair + signing_key_id

Phase-1 swaps the registries / ledger / dossier-store for Postgres
and the bundle-store for MinIO; the route wiring stays unchanged
because every collaborator is Protocol-typed.

This module exports ``build_control_plane_router(state)`` which
returns a FastAPI ``APIRouter`` that can be mounted under any
prefix. ``create_app_with_state(state)`` is a convenience factory
that builds the full FastAPI app (operational endpoints from
``app.py`` plus the control-plane router under ``/v1/control``).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime

from fastapi import APIRouter, FastAPI, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from verixa_runtime.crypto.aes_gcm import AesGcmKey, generate_key
from verixa_runtime.crypto.ed25519 import Ed25519KeyPair, generate_keypair
from verixa_runtime.replay import (
    InMemoryAuditIndex,
    InMemoryBundleStore,
    Reconstructor,
    Snapshotter,
)

from verixa_control_plane.app import create_app
from verixa_control_plane.audit import (
    AuditLedger,
    InMemoryAuditLedger,
    handle_audit_query,
)
from verixa_control_plane.envelopes import (
    AgentRegisterRequest,
    DossierGenerateRequest,
    ReplayRequest,
    ToolRegisterRequest,
    WorkflowRegisterRequest,
)
from verixa_control_plane.handlers import (
    DossierStore,
    InMemoryDossierStore,
    handle_dossier_generate,
    handle_dossier_get,
    handle_replay,
)
from verixa_control_plane.registry import (
    AgentRegistry,
    InMemoryAgentRegistry,
    InMemoryToolRegistry,
    InMemoryWorkflowRegistry,
    ToolRegistry,
    WorkflowRegistry,
    handle_agent_register,
    handle_tool_register,
    handle_workflow_list,
    handle_workflow_register,
)

# ---------------------------------------------------------------------------
# App-state container
# ---------------------------------------------------------------------------


@dataclass
class ControlPlaneState:
    """Bundle of every collaborator a Control Plane route needs.

    Constructed once at app boot; passed into routes via dependency
    injection so handlers stay testable without a live FastAPI loop.
    """

    workflow_registry: WorkflowRegistry
    agent_registry: AgentRegistry
    tool_registry: ToolRegistry
    audit_ledger: AuditLedger
    reconstructor: Reconstructor
    dossier_store: DossierStore
    signing_keypair: Ed25519KeyPair
    signing_key_id: str
    # Held for test fixtures that need to seed via the snapshotter.
    snapshotter: Snapshotter = field(repr=False)
    # Held so tests can introspect/seed without going through the API.
    _tenant_keys: dict[uuid.UUID, AesGcmKey] = field(
        default_factory=dict, repr=False
    )


def build_default_state(
    *,
    signing_key_id: str = "verixa-sig-dev",
) -> ControlPlaneState:
    """Build a Phase-0 in-memory ControlPlaneState.

    Production calls a different builder that wires Postgres + Vault
    + MinIO; the FastAPI route surface is identical.
    """
    # Replay collaborators -- store + index + key resolver, plus a
    # shared tenant key for the Phase-0 demo (single-tenant).
    bundle_store = InMemoryBundleStore()
    audit_index = InMemoryAuditIndex()
    tenant_keys: dict[uuid.UUID, AesGcmKey] = {}

    def key_resolver(tid: uuid.UUID) -> AesGcmKey:
        if tid not in tenant_keys:
            tenant_keys[tid] = generate_key()
        return tenant_keys[tid]

    snapshotter = Snapshotter(
        store=bundle_store, index=audit_index, key_resolver=key_resolver
    )
    reconstructor = Reconstructor(
        store=bundle_store, index=audit_index, key_resolver=key_resolver
    )

    # Registry collaborators -- and wire the agent registry into the
    # workflow registry so list_all can report agent counts.
    wf_reg = InMemoryWorkflowRegistry()
    agent_reg = InMemoryAgentRegistry()
    wf_reg._agent_registry = agent_reg  # noqa: SLF001 -- intended wire-up

    return ControlPlaneState(
        workflow_registry=wf_reg,
        agent_registry=agent_reg,
        tool_registry=InMemoryToolRegistry(),
        audit_ledger=InMemoryAuditLedger(),
        reconstructor=reconstructor,
        dossier_store=InMemoryDossierStore(),
        signing_keypair=generate_keypair(),
        signing_key_id=signing_key_id,
        snapshotter=snapshotter,
        _tenant_keys=tenant_keys,
    )


# ---------------------------------------------------------------------------
# Helper: tuple -> JSONResponse
# ---------------------------------------------------------------------------


def _to_json_response(
    pair: tuple[int, BaseModel],
) -> JSONResponse:
    """Translate (status, envelope) into a FastAPI JSONResponse.

    Uses model_dump(mode='json') so UUIDs render as strings and
    datetimes as ISO-8601 (Pydantic v2 default).
    """
    status, body = pair
    return JSONResponse(
        status_code=status, content=body.model_dump(mode="json")
    )


# ---------------------------------------------------------------------------
# Router builder
# ---------------------------------------------------------------------------


def build_control_plane_router(state: ControlPlaneState) -> APIRouter:
    """Build the APIRouter that mounts under /v1/control."""
    router = APIRouter(prefix="/v1/control", tags=["control-plane"])

    # ---- Registry -----------------------------------------------------

    @router.post("/workflows")
    async def workflows_register(req: WorkflowRegisterRequest) -> JSONResponse:
        return _to_json_response(
            await handle_workflow_register(
                req, workflow_registry=state.workflow_registry
            )
        )

    @router.get("/workflows")
    async def workflows_list() -> JSONResponse:
        return _to_json_response(
            await handle_workflow_list(
                workflow_registry=state.workflow_registry
            )
        )

    @router.post("/agents")
    async def agents_register(req: AgentRegisterRequest) -> JSONResponse:
        return _to_json_response(
            await handle_agent_register(
                req,
                workflow_registry=state.workflow_registry,
                agent_registry=state.agent_registry,
            )
        )

    @router.post("/tools")
    async def tools_register(req: ToolRegisterRequest) -> JSONResponse:
        return _to_json_response(
            await handle_tool_register(
                req,
                workflow_registry=state.workflow_registry,
                tool_registry=state.tool_registry,
            )
        )

    # ---- Audit --------------------------------------------------------

    @router.get("/audit")
    async def audit_query(
        workflow_id: uuid.UUID = Query(...),  # noqa: B008
        from_timestamp: datetime = Query(..., alias="from"),  # noqa: B008
        to_timestamp: datetime = Query(..., alias="to"),  # noqa: B008
    ) -> JSONResponse:
        return _to_json_response(
            await handle_audit_query(
                workflow_id=workflow_id,
                from_timestamp=from_timestamp,
                to_timestamp=to_timestamp,
                audit_ledger=state.audit_ledger,
            )
        )

    # ---- Replay -------------------------------------------------------

    @router.post("/replay")
    async def replay(req: ReplayRequest) -> JSONResponse:
        return _to_json_response(
            await handle_replay(
                req, reconstructor=state.reconstructor
            )
        )

    # ---- Dossier ------------------------------------------------------

    @router.post("/dossier")
    async def dossier_generate(
        req: DossierGenerateRequest,
    ) -> JSONResponse:
        return _to_json_response(
            await handle_dossier_generate(
                req,
                reconstructor=state.reconstructor,
                dossier_store=state.dossier_store,
                signing_keypair=state.signing_keypair,
                signing_key_id=state.signing_key_id,
            )
        )

    @router.get("/dossier/{dossier_id}")
    async def dossier_get(dossier_id: uuid.UUID) -> JSONResponse:
        return _to_json_response(
            await handle_dossier_get(
                dossier_id, dossier_store=state.dossier_store
            )
        )

    return router


def create_app_with_state(
    state: ControlPlaneState | None = None,
) -> FastAPI:
    """Convenience factory: full FastAPI app + control-plane routes."""
    app = create_app()
    if state is None:
        state = build_default_state()
    app.state.cp = state
    app.include_router(build_control_plane_router(state))
    return app


__all__ = [
    "ControlPlaneState",
    "build_control_plane_router",
    "build_default_state",
    "create_app_with_state",
]
