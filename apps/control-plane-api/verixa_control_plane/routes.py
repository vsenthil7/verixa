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

from fastapi import APIRouter, FastAPI, Header, Query
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel
from verixa_runtime.crypto.aes_gcm import AesGcmKey, generate_key
from verixa_runtime.crypto.ed25519 import Ed25519KeyPair, generate_keypair
from verixa_runtime.policy import (
    BundleNameInvalid,
    BundleNotFound,
    BundleServer,
    BundleUnsigned,
)
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
    WebhookDeliveryListResponse,
    WebhookDeliverySummary,
    WebhookSubscribeRequest,
    WebhookSubscriptionListResponse,
    WebhookSubscriptionSummary,
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
from verixa_control_plane.webhooks import (
    WebhookDispatcher,
    WebhookSubscription,
    WebhookSubscriptionInvalid,
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
    # CP-46: optional OPA bundle distribution server. None disables
    # the /v1/control/policy/bundles routes (the routes return 503 in
    # that case rather than 404 so operators can distinguish
    # "disabled" from "no such bundle").
    bundle_server: BundleServer | None = None
    # CP-49: optional outbound-webhook dispatcher. None disables the
    # /v1/control/webhooks routes (503). Phase-1 wires up the
    # InMemoryWebhookDispatcher + InMemory subscriptions store; Phase-1+
    # swaps for Postgres + AsyncRetryQueue.
    webhook_dispatcher: WebhookDispatcher | None = None


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

    # ---- Policy bundle distribution (CP-46) ---------------------------

    @router.get("/policy/bundles")
    async def bundles_list() -> JSONResponse:
        """List bundle names available for OPA pull."""
        if state.bundle_server is None:
            return JSONResponse(
                status_code=503,
                content={"error": "bundle server not configured"},
            )
        return JSONResponse(
            status_code=200,
            content={"bundles": state.bundle_server.list_bundles()},
        )

    @router.get("/policy/bundles/{name}")
    async def bundles_fetch(
        name: str,
        if_none_match: str | None = Header(default=None),
    ) -> Response:
        """Fetch a signed bundle as gzipped tar.

        Returns 200 with tar.gz body + ETag header on first fetch;
        304 if If-None-Match matches the current ETag (OPA cache hit).
        Returns 400 / 404 / 503 with JSON body for failure modes.
        """
        if state.bundle_server is None:
            return JSONResponse(
                status_code=503,
                content={"error": "bundle server not configured"},
            )
        try:
            artifact = state.bundle_server.serve(name)
        except BundleNameInvalid as e:
            return JSONResponse(
                status_code=400, content={"error": str(e)}
            )
        except BundleNotFound as e:
            return JSONResponse(
                status_code=404, content={"error": str(e)}
            )
        except BundleUnsigned as e:
            return JSONResponse(
                status_code=409, content={"error": str(e)}
            )
        # Strong-validator ETag match -> 304 Not Modified, no body.
        if if_none_match is not None and if_none_match == artifact.etag:
            return Response(
                status_code=304, headers={"ETag": artifact.etag}
            )
        return Response(
            status_code=200,
            content=artifact.tarball,
            media_type="application/gzip",
            headers={
                "ETag": artifact.etag,
                "X-Verixa-Bundle-Signing-Key-Id": (
                    artifact.signatures.signing_key_id
                ),
            },
        )

    # ---- Webhook subscriptions + deliveries (CP-49) -------------------

    @router.post("/webhooks/subscriptions")
    async def webhook_subscribe(
        req: WebhookSubscribeRequest,
    ) -> JSONResponse:
        """Create a new webhook subscription.

        201 on success; 400 on invalid URL / event types / signing key id;
        503 if dispatcher not configured.
        """
        if state.webhook_dispatcher is None:
            return JSONResponse(
                status_code=503,
                content={"error": "webhook dispatcher not configured"},
            )
        try:
            subscription = WebhookSubscription(
                subscription_id=uuid.uuid4(),
                tenant_id=req.tenant_id,
                url=req.url,
                event_types=frozenset(req.event_types),
                signing_key_id=req.signing_key_id,
                created_at=datetime.now(),
            )
        except WebhookSubscriptionInvalid as e:
            return JSONResponse(
                status_code=400,
                content={"error": "subscription_invalid", "message": str(e)},
            )
        await state.webhook_dispatcher.subscribe(subscription)
        return JSONResponse(
            status_code=201,
            content=WebhookSubscriptionSummary(
                subscription_id=subscription.subscription_id,
                tenant_id=subscription.tenant_id,
                url=subscription.url,
                event_types=sorted(subscription.event_types),
                signing_key_id=subscription.signing_key_id,
                created_at=subscription.created_at,
            ).model_dump(mode="json"),
        )

    @router.get("/webhooks/subscriptions")
    async def webhook_list(
        tenant_id: uuid.UUID | None = Query(default=None),  # noqa: B008
    ) -> JSONResponse:
        """List subscriptions, optionally filtered by tenant_id."""
        if state.webhook_dispatcher is None:
            return JSONResponse(
                status_code=503,
                content={"error": "webhook dispatcher not configured"},
            )
        subs = await state.webhook_dispatcher.list_subscriptions(
            tenant_id=tenant_id
        )
        body = WebhookSubscriptionListResponse(
            subscriptions=[
                WebhookSubscriptionSummary(
                    subscription_id=s.subscription_id,
                    tenant_id=s.tenant_id,
                    url=s.url,
                    event_types=sorted(s.event_types),
                    signing_key_id=s.signing_key_id,
                    created_at=s.created_at,
                )
                for s in subs
            ],
            total=len(subs),
        )
        return JSONResponse(status_code=200, content=body.model_dump(mode="json"))

    @router.get("/webhooks/deliveries")
    async def webhook_deliveries(
        limit: int = Query(default=50, ge=1, le=1000),
    ) -> JSONResponse:
        """Recent delivery forensics for SIEM correlation."""
        if state.webhook_dispatcher is None:
            return JSONResponse(
                status_code=503,
                content={"error": "webhook dispatcher not configured"},
            )
        attempts = await state.webhook_dispatcher.recent_deliveries(
            limit=limit
        )
        body = WebhookDeliveryListResponse(
            deliveries=[
                WebhookDeliverySummary(
                    attempt_id=a.attempt_id,
                    subscription_id=a.subscription_id,
                    event_id=a.event_id,
                    url=a.url,
                    status_code=a.status_code,
                    latency_ms=a.latency_ms,
                    attempted_at=a.attempted_at,
                    error=a.error,
                )
                for a in attempts
            ],
            total=len(attempts),
        )
        return JSONResponse(status_code=200, content=body.model_dump(mode="json"))

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
