"""CP-49 -- HTTP integration tests for /v1/control/webhooks/* routes.

Mirrors the CP-46 BundleServer wiring tests. Uses FastAPI TestClient against
a real wired-up app. The webhook_dispatcher is supplied via a fixture that
injects a fake HTTP poster so tests don't make real network calls.
"""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from verixa_control_plane.routes import (
    build_default_state,
    create_app_with_state,
)
from verixa_control_plane.webhooks import InMemoryWebhookDispatcher
from verixa_runtime.crypto.ed25519 import generate_keypair

_TENANT_A = uuid.UUID("aaaaaaaa-1111-1111-1111-aaaaaaaaaaaa")
_TENANT_B = uuid.UUID("bbbbbbbb-2222-2222-2222-bbbbbbbbbbbb")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


class _FakePoster:
    def __init__(self) -> None:
        self.calls: list[tuple[str, bytes, dict[str, str]]] = []

    async def __call__(
        self, url: str, body: bytes, headers: dict[str, str]
    ) -> tuple[int, int]:
        self.calls.append((url, body, headers))
        return 202, 7


@pytest.fixture
def client_with_dispatcher() -> tuple[TestClient, _FakePoster]:
    state = build_default_state()
    poster = _FakePoster()
    state.webhook_dispatcher = InMemoryWebhookDispatcher(
        keypair=generate_keypair(), http_poster=poster
    )
    app = create_app_with_state(state)
    return TestClient(app), poster


@pytest.fixture
def client_no_dispatcher() -> TestClient:
    """Client with webhook_dispatcher=None -- all routes return 503."""
    state = build_default_state()
    app = create_app_with_state(state)
    return TestClient(app)


# ---------------------------------------------------------------------------
# POST /webhooks/subscriptions
# ---------------------------------------------------------------------------


def test_subscribe_happy_path(client_with_dispatcher) -> None:
    client, _ = client_with_dispatcher
    r = client.post(
        "/v1/control/webhooks/subscriptions",
        json={
            "tenant_id": str(_TENANT_A),
            "url": "https://customer.example.com/webhook",
            "event_types": ["audit.decision.recorded"],
            "signing_key_id": "verixa-sig-prod",
        },
    )
    assert r.status_code == 201
    body = r.json()
    assert body["tenant_id"] == str(_TENANT_A)
    assert body["url"] == "https://customer.example.com/webhook"
    assert body["event_types"] == ["audit.decision.recorded"]
    assert body["signing_key_id"] == "verixa-sig-prod"
    assert uuid.UUID(body["subscription_id"])  # valid UUID
    assert body["created_at"]  # ISO timestamp present


def test_subscribe_rejects_http_url(client_with_dispatcher) -> None:
    client, _ = client_with_dispatcher
    r = client.post(
        "/v1/control/webhooks/subscriptions",
        json={
            "tenant_id": str(_TENANT_A),
            "url": "http://customer.example.com/webhook",
            "event_types": ["audit.decision.recorded"],
            "signing_key_id": "verixa-sig-prod",
        },
    )
    assert r.status_code == 400
    body = r.json()
    assert body["error"] == "subscription_invalid"
    assert "https://" in body["message"]


def test_subscribe_rejects_unknown_event_type(client_with_dispatcher) -> None:
    client, _ = client_with_dispatcher
    r = client.post(
        "/v1/control/webhooks/subscriptions",
        json={
            "tenant_id": str(_TENANT_A),
            "url": "https://customer.example.com/wh",
            "event_types": ["not.an.event"],
            "signing_key_id": "verixa-sig-prod",
        },
    )
    assert r.status_code == 400
    assert "unknown types" in r.json()["message"]


def test_subscribe_rejects_bad_signing_key_id(client_with_dispatcher) -> None:
    """A 12+ char signing_key_id that fails the verixa-sig- prefix check
    passes envelope validation (min_length=12) but is rejected at the
    runtime WebhookSubscription.__post_init__ -> 400 from the route."""
    client, _ = client_with_dispatcher
    r = client.post(
        "/v1/control/webhooks/subscriptions",
        json={
            "tenant_id": str(_TENANT_A),
            "url": "https://customer.example.com/wh",
            "event_types": ["audit.decision.recorded"],
            "signing_key_id": "my-custom-key-id",
        },
    )
    assert r.status_code == 400
    assert "verixa-sig-" in r.json()["message"]


def test_subscribe_rejects_too_short_signing_key_id(
    client_with_dispatcher,
) -> None:
    """Envelope-level rejection: signing_key_id < 12 chars -> 422."""
    client, _ = client_with_dispatcher
    r = client.post(
        "/v1/control/webhooks/subscriptions",
        json={
            "tenant_id": str(_TENANT_A),
            "url": "https://customer.example.com/wh",
            "event_types": ["audit.decision.recorded"],
            "signing_key_id": "my-key",
        },
    )
    assert r.status_code == 422


def test_subscribe_rejects_empty_event_types(client_with_dispatcher) -> None:
    client, _ = client_with_dispatcher
    r = client.post(
        "/v1/control/webhooks/subscriptions",
        json={
            "tenant_id": str(_TENANT_A),
            "url": "https://customer.example.com/wh",
            "event_types": [],
            "signing_key_id": "verixa-sig-prod",
        },
    )
    # Pydantic catches the min_length=1 violation -> 422
    assert r.status_code == 422


def test_subscribe_503_when_disabled(client_no_dispatcher) -> None:
    r = client_no_dispatcher.post(
        "/v1/control/webhooks/subscriptions",
        json={
            "tenant_id": str(_TENANT_A),
            "url": "https://customer.example.com/wh",
            "event_types": ["audit.decision.recorded"],
            "signing_key_id": "verixa-sig-prod",
        },
    )
    assert r.status_code == 503


# ---------------------------------------------------------------------------
# GET /webhooks/subscriptions
# ---------------------------------------------------------------------------


def test_list_subscriptions_empty(client_with_dispatcher) -> None:
    client, _ = client_with_dispatcher
    r = client.get("/v1/control/webhooks/subscriptions")
    assert r.status_code == 200
    body = r.json()
    assert body["subscriptions"] == []
    assert body["total"] == 0


def test_list_subscriptions_returns_created(client_with_dispatcher) -> None:
    client, _ = client_with_dispatcher
    # Create two subscriptions for different tenants
    client.post(
        "/v1/control/webhooks/subscriptions",
        json={
            "tenant_id": str(_TENANT_A),
            "url": "https://a.example.com/wh",
            "event_types": ["audit.decision.recorded"],
            "signing_key_id": "verixa-sig-prod",
        },
    )
    client.post(
        "/v1/control/webhooks/subscriptions",
        json={
            "tenant_id": str(_TENANT_B),
            "url": "https://b.example.com/wh",
            "event_types": ["audit.dossier.generated"],
            "signing_key_id": "verixa-sig-prod",
        },
    )
    r = client.get("/v1/control/webhooks/subscriptions")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 2
    assert len(body["subscriptions"]) == 2


def test_list_subscriptions_filters_by_tenant(client_with_dispatcher) -> None:
    client, _ = client_with_dispatcher
    client.post(
        "/v1/control/webhooks/subscriptions",
        json={
            "tenant_id": str(_TENANT_A),
            "url": "https://a.example.com/wh",
            "event_types": ["audit.decision.recorded"],
            "signing_key_id": "verixa-sig-prod",
        },
    )
    client.post(
        "/v1/control/webhooks/subscriptions",
        json={
            "tenant_id": str(_TENANT_B),
            "url": "https://b.example.com/wh",
            "event_types": ["audit.decision.recorded"],
            "signing_key_id": "verixa-sig-prod",
        },
    )
    r = client.get(
        f"/v1/control/webhooks/subscriptions?tenant_id={_TENANT_A}"
    )
    body = r.json()
    assert body["total"] == 1
    assert body["subscriptions"][0]["tenant_id"] == str(_TENANT_A)


def test_list_subscriptions_503_when_disabled(
    client_no_dispatcher,
) -> None:
    r = client_no_dispatcher.get("/v1/control/webhooks/subscriptions")
    assert r.status_code == 503


# ---------------------------------------------------------------------------
# GET /webhooks/deliveries
# ---------------------------------------------------------------------------


def test_deliveries_empty_when_no_events_dispatched(
    client_with_dispatcher,
) -> None:
    client, _ = client_with_dispatcher
    r = client.get("/v1/control/webhooks/deliveries")
    assert r.status_code == 200
    body = r.json()
    assert body["deliveries"] == []
    assert body["total"] == 0


@pytest.mark.asyncio
async def test_deliveries_returns_after_dispatch(
    client_with_dispatcher,
) -> None:
    """Subscribe via HTTP, then dispatch an event programmatically,
    then read deliveries via HTTP. Tests the full dispatcher loop."""
    client, poster = client_with_dispatcher
    # Subscribe via the HTTP route
    sub_resp = client.post(
        "/v1/control/webhooks/subscriptions",
        json={
            "tenant_id": str(_TENANT_A),
            "url": "https://customer.example.com/wh",
            "event_types": ["audit.decision.recorded"],
            "signing_key_id": "verixa-sig-prod",
        },
    )
    assert sub_resp.status_code == 201

    # Dispatch an event by reaching into the dispatcher
    # (no HTTP route dispatches; that's the gateway's job)
    from datetime import UTC, datetime

    from verixa_control_plane.webhooks import WebhookEvent

    state = client.app.state.cp
    event = WebhookEvent(
        event_id=uuid.uuid4(),
        event_type="audit.decision.recorded",
        tenant_id=_TENANT_A,
        payload={"audit_id": str(uuid.uuid4()), "decision": "allow"},
        timestamp=datetime.now(UTC),
    )
    attempts = await state.webhook_dispatcher.dispatch(event)
    assert len(attempts) == 1
    assert len(poster.calls) == 1

    # Read back via HTTP
    r = client.get("/v1/control/webhooks/deliveries")
    body = r.json()
    assert body["total"] == 1
    delivery = body["deliveries"][0]
    assert delivery["status_code"] == 202
    assert delivery["url"] == "https://customer.example.com/wh"
    assert delivery["error"] is None


def test_deliveries_respects_limit(client_with_dispatcher) -> None:
    client, _ = client_with_dispatcher
    r = client.get("/v1/control/webhooks/deliveries?limit=10")
    assert r.status_code == 200


def test_deliveries_rejects_zero_limit(client_with_dispatcher) -> None:
    """Pydantic ge=1 constraint rejects limit=0."""
    client, _ = client_with_dispatcher
    r = client.get("/v1/control/webhooks/deliveries?limit=0")
    assert r.status_code == 422


def test_deliveries_rejects_oversized_limit(client_with_dispatcher) -> None:
    """Pydantic le=1000 constraint rejects limit=1001."""
    client, _ = client_with_dispatcher
    r = client.get("/v1/control/webhooks/deliveries?limit=1001")
    assert r.status_code == 422


def test_deliveries_503_when_disabled(client_no_dispatcher) -> None:
    r = client_no_dispatcher.get("/v1/control/webhooks/deliveries")
    assert r.status_code == 503


# ---------------------------------------------------------------------------
# OpenAPI surface
# ---------------------------------------------------------------------------


def test_openapi_includes_webhook_routes(
    client_with_dispatcher,
) -> None:
    client, _ = client_with_dispatcher
    spec = client.get("/openapi.json").json()
    paths = spec["paths"]
    assert "/v1/control/webhooks/subscriptions" in paths
    assert "/v1/control/webhooks/deliveries" in paths
