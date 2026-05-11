"""CP-48 tests for verixa_control_plane.webhooks -- SIEM/ITSM webhook delivery.

Anchored to Phase-1 carry-forward "webhook event API". Covers:
  - Event allowlist validation
  - Subscription URL + event-type + signing-key-id validation
  - Subscribe + list (with tenant filter)
  - Dispatch happy path (signing + headers + body bytes)
  - Dispatch matching logic (tenant + event_type both must match)
  - Dispatch failure recording (HTTP error + transport error)
  - Signature verifies under the dispatcher's public key (Ed25519 round-trip)
  - Recent-deliveries ring buffer + bounded growth
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import Any

import pytest
from verixa_control_plane.webhooks import (
    InMemoryWebhookDispatcher,
    WebhookDispatcher,
    WebhookEvent,
    WebhookEventInvalid,
    WebhookSubscription,
    WebhookSubscriptionInvalid,
)
from verixa_runtime.crypto.ed25519 import (
    Ed25519SignatureError,
    generate_keypair,
    verify,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


_TENANT_A = uuid.UUID("aaaaaaaa-1111-1111-1111-aaaaaaaaaaaa")
_TENANT_B = uuid.UUID("bbbbbbbb-2222-2222-2222-bbbbbbbbbbbb")


def _make_event(
    *,
    event_type: str = "audit.decision.recorded",
    tenant_id: uuid.UUID = _TENANT_A,
    payload: dict[str, Any] | None = None,
) -> WebhookEvent:
    return WebhookEvent(
        event_id=uuid.uuid4(),
        event_type=event_type,
        tenant_id=tenant_id,
        payload=payload or {"audit_id": str(uuid.uuid4()), "decision": "allow"},
        timestamp=datetime(2026, 5, 11, 17, 0, 0, tzinfo=UTC),
    )


def _make_sub(
    *,
    tenant_id: uuid.UUID = _TENANT_A,
    url: str = "https://customer.example.com/webhook",
    event_types: frozenset[str] = frozenset({"audit.decision.recorded"}),
    signing_key_id: str = "verixa-sig-test",
    created_at: datetime | None = None,
) -> WebhookSubscription:
    return WebhookSubscription(
        subscription_id=uuid.uuid4(),
        tenant_id=tenant_id,
        url=url,
        event_types=event_types,
        signing_key_id=signing_key_id,
        created_at=created_at or datetime(2026, 5, 11, 17, 0, 0, tzinfo=UTC),
    )


class _FakePoster:
    """Records every (url, body, headers) it's posted; returns configurable
    status + latency. By default returns (202, 12) ms."""

    def __init__(
        self,
        *,
        status: int = 202,
        latency_ms: int = 12,
        raise_exc: Exception | None = None,
    ) -> None:
        self.status = status
        self.latency_ms = latency_ms
        self.raise_exc = raise_exc
        self.calls: list[tuple[str, bytes, dict[str, str]]] = []

    async def __call__(
        self, url: str, body: bytes, headers: dict[str, str]
    ) -> tuple[int, int]:
        self.calls.append((url, body, headers))
        if self.raise_exc is not None:
            raise self.raise_exc
        return self.status, self.latency_ms


@pytest.fixture
def keypair():
    return generate_keypair()


@pytest.fixture
def dispatcher(keypair) -> tuple[InMemoryWebhookDispatcher, _FakePoster]:
    poster = _FakePoster()
    d = InMemoryWebhookDispatcher(keypair=keypair, http_poster=poster)
    return d, poster


# ---------------------------------------------------------------------------
# WebhookEvent validation
# ---------------------------------------------------------------------------


def test_webhook_event_accepts_known_type() -> None:
    e = _make_event(event_type="audit.decision.recorded")
    assert e.event_type == "audit.decision.recorded"


def test_webhook_event_rejects_unknown_type() -> None:
    with pytest.raises(WebhookEventInvalid, match="not in allowlist"):
        _make_event(event_type="custom.thing")


def test_webhook_event_rejects_empty_type() -> None:
    with pytest.raises(WebhookEventInvalid):
        _make_event(event_type="")


# ---------------------------------------------------------------------------
# WebhookSubscription validation
# ---------------------------------------------------------------------------


def test_subscription_accepts_valid_url() -> None:
    sub = _make_sub(url="https://customer.example.com/path/to/hook")
    assert sub.url == "https://customer.example.com/path/to/hook"


def test_subscription_rejects_http_scheme() -> None:
    with pytest.raises(WebhookSubscriptionInvalid, match="https://"):
        _make_sub(url="http://customer.example.com/webhook")


def test_subscription_rejects_no_scheme() -> None:
    with pytest.raises(WebhookSubscriptionInvalid):
        _make_sub(url="customer.example.com/webhook")


def test_subscription_rejects_javascript_scheme() -> None:
    with pytest.raises(WebhookSubscriptionInvalid):
        _make_sub(url="javascript:alert(1)")


def test_subscription_rejects_empty_event_types() -> None:
    with pytest.raises(WebhookSubscriptionInvalid, match="at least one"):
        _make_sub(event_types=frozenset())


def test_subscription_rejects_unknown_event_type() -> None:
    with pytest.raises(WebhookSubscriptionInvalid, match="unknown types"):
        _make_sub(event_types=frozenset({"made.up.event"}))


def test_subscription_rejects_bad_signing_key_id() -> None:
    with pytest.raises(WebhookSubscriptionInvalid, match="verixa-sig-"):
        _make_sub(signing_key_id="my-key")


def test_subscription_accepts_url_with_port() -> None:
    sub = _make_sub(url="https://internal.example.com:8443/wh")
    assert ":8443" in sub.url


# ---------------------------------------------------------------------------
# subscribe + list_subscriptions
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_subscribe_stores_subscription(dispatcher) -> None:
    d, _ = dispatcher
    s = _make_sub()
    await d.subscribe(s)
    subs = await d.list_subscriptions()
    assert len(subs) == 1
    assert subs[0].subscription_id == s.subscription_id


@pytest.mark.asyncio
async def test_list_subscriptions_filters_by_tenant(dispatcher) -> None:
    d, _ = dispatcher
    sa = _make_sub(tenant_id=_TENANT_A)
    sb = _make_sub(tenant_id=_TENANT_B)
    await d.subscribe(sa)
    await d.subscribe(sb)
    subs_a = await d.list_subscriptions(tenant_id=_TENANT_A)
    assert len(subs_a) == 1
    assert subs_a[0].tenant_id == _TENANT_A
    subs_b = await d.list_subscriptions(tenant_id=_TENANT_B)
    assert len(subs_b) == 1


@pytest.mark.asyncio
async def test_list_subscriptions_no_filter_returns_all(dispatcher) -> None:
    d, _ = dispatcher
    await d.subscribe(_make_sub(tenant_id=_TENANT_A))
    await d.subscribe(_make_sub(tenant_id=_TENANT_B))
    subs = await d.list_subscriptions()
    assert len(subs) == 2


@pytest.mark.asyncio
async def test_subscribe_overwrites_same_id(dispatcher) -> None:
    """Re-subscribing with the same id replaces the previous record."""
    d, _ = dispatcher
    sid = uuid.uuid4()
    s1 = WebhookSubscription(
        subscription_id=sid,
        tenant_id=_TENANT_A,
        url="https://old.example.com/webhook",
        event_types=frozenset({"audit.decision.recorded"}),
        signing_key_id="verixa-sig-test",
        created_at=datetime(2026, 5, 11, 17, 0, 0, tzinfo=UTC),
    )
    s2 = WebhookSubscription(
        subscription_id=sid,
        tenant_id=_TENANT_A,
        url="https://new.example.com/webhook",
        event_types=frozenset({"audit.decision.recorded"}),
        signing_key_id="verixa-sig-test",
        created_at=datetime(2026, 5, 11, 17, 5, 0, tzinfo=UTC),
    )
    await d.subscribe(s1)
    await d.subscribe(s2)
    subs = await d.list_subscriptions()
    assert len(subs) == 1
    assert subs[0].url == "https://new.example.com/webhook"


# ---------------------------------------------------------------------------
# dispatch -- happy path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_dispatch_posts_to_matching_subscription(dispatcher) -> None:
    d, poster = dispatcher
    s = _make_sub()
    await d.subscribe(s)
    e = _make_event()
    attempts = await d.dispatch(e)
    assert len(attempts) == 1
    assert attempts[0].status_code == 202
    assert len(poster.calls) == 1
    url, body, headers = poster.calls[0]
    assert url == s.url
    # Body is canonical JSON
    parsed = json.loads(body)
    assert parsed["event_id"] == str(e.event_id)
    assert parsed["event_type"] == "audit.decision.recorded"
    # Headers include the signature + key-id + public-key + subscription-id
    assert headers["X-Verixa-Signing-Key-Id"] == "verixa-sig-test"
    assert len(headers["X-Verixa-Signature"]) == 128  # 64 bytes hex
    assert len(headers["X-Verixa-Public-Key"]) == 64  # 32 bytes hex
    assert headers["X-Verixa-Subscription-Id"] == str(s.subscription_id)
    assert headers["Content-Type"] == "application/json"


@pytest.mark.asyncio
async def test_dispatch_signature_verifies_under_dispatcher_public_key(
    dispatcher, keypair
) -> None:
    """The signature in the X-Verixa-Signature header MUST verify against
    the public key in X-Verixa-Public-Key over the request body bytes."""
    d, poster = dispatcher
    await d.subscribe(_make_sub())
    e = _make_event()
    await d.dispatch(e)
    _, body, headers = poster.calls[0]
    signature = bytes.fromhex(headers["X-Verixa-Signature"])
    public_key = bytes.fromhex(headers["X-Verixa-Public-Key"])
    # MUST verify; raises Ed25519SignatureError on tamper
    verify(public_key, body, signature)
    # The public key in the header is the dispatcher's
    assert public_key == keypair.public_key


@pytest.mark.asyncio
async def test_dispatch_signature_rejects_tampered_body(
    dispatcher,
) -> None:
    """Tampering the body bytes makes the signature fail to verify --
    proves the signature is over what we think it is."""
    d, poster = dispatcher
    await d.subscribe(_make_sub())
    await d.dispatch(_make_event())
    _, body, headers = poster.calls[0]
    signature = bytes.fromhex(headers["X-Verixa-Signature"])
    public_key = bytes.fromhex(headers["X-Verixa-Public-Key"])
    tampered = body[:-1] + bytes([body[-1] ^ 0x01])
    with pytest.raises(Ed25519SignatureError):
        verify(public_key, tampered, signature)


@pytest.mark.asyncio
async def test_dispatch_records_delivery_in_recent_buffer(
    dispatcher,
) -> None:
    d, _ = dispatcher
    await d.subscribe(_make_sub())
    await d.dispatch(_make_event())
    recent = await d.recent_deliveries()
    assert len(recent) == 1


# ---------------------------------------------------------------------------
# dispatch -- matching logic
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_dispatch_skips_subscriptions_for_other_tenant(
    dispatcher,
) -> None:
    d, poster = dispatcher
    await d.subscribe(_make_sub(tenant_id=_TENANT_B))
    e = _make_event(tenant_id=_TENANT_A)
    attempts = await d.dispatch(e)
    assert attempts == []
    assert poster.calls == []


@pytest.mark.asyncio
async def test_dispatch_skips_subscriptions_for_other_event_type(
    dispatcher,
) -> None:
    d, poster = dispatcher
    await d.subscribe(
        _make_sub(event_types=frozenset({"audit.dossier.generated"}))
    )
    e = _make_event(event_type="audit.decision.recorded")
    attempts = await d.dispatch(e)
    assert attempts == []
    assert poster.calls == []


@pytest.mark.asyncio
async def test_dispatch_to_multiple_matching_subscriptions(
    dispatcher,
) -> None:
    d, poster = dispatcher
    s1 = _make_sub(url="https://customer1.example.com/wh")
    s2 = _make_sub(url="https://customer2.example.com/wh")
    await d.subscribe(s1)
    await d.subscribe(s2)
    attempts = await d.dispatch(_make_event())
    assert len(attempts) == 2
    assert len(poster.calls) == 2
    urls = {c[0] for c in poster.calls}
    assert urls == {s1.url, s2.url}


# ---------------------------------------------------------------------------
# dispatch -- failure recording
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_dispatch_records_http_error_status(keypair) -> None:
    poster = _FakePoster(status=500, latency_ms=200)
    d = InMemoryWebhookDispatcher(keypair=keypair, http_poster=poster)
    await d.subscribe(_make_sub())
    attempts = await d.dispatch(_make_event())
    assert len(attempts) == 1
    assert attempts[0].status_code == 500
    assert attempts[0].latency_ms == 200
    assert attempts[0].error is None  # HTTP error is not a transport error


@pytest.mark.asyncio
async def test_dispatch_records_transport_exception(keypair) -> None:
    poster = _FakePoster(raise_exc=ConnectionError("dns failed"))
    d = InMemoryWebhookDispatcher(keypair=keypair, http_poster=poster)
    await d.subscribe(_make_sub())
    attempts = await d.dispatch(_make_event())
    assert len(attempts) == 1
    assert attempts[0].status_code == -1
    assert attempts[0].latency_ms == 0
    assert "ConnectionError" in attempts[0].error
    assert "dns failed" in attempts[0].error


# ---------------------------------------------------------------------------
# recent_deliveries
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_recent_deliveries_default_limit_50(dispatcher) -> None:
    d, _ = dispatcher
    await d.subscribe(_make_sub())
    for _ in range(60):
        await d.dispatch(_make_event())
    recent = await d.recent_deliveries()
    assert len(recent) == 50


@pytest.mark.asyncio
async def test_recent_deliveries_custom_limit(dispatcher) -> None:
    d, _ = dispatcher
    await d.subscribe(_make_sub())
    for _ in range(10):
        await d.dispatch(_make_event())
    recent = await d.recent_deliveries(limit=5)
    assert len(recent) == 5


@pytest.mark.asyncio
async def test_recent_deliveries_limit_zero_returns_empty(
    dispatcher,
) -> None:
    d, _ = dispatcher
    await d.subscribe(_make_sub())
    await d.dispatch(_make_event())
    assert await d.recent_deliveries(limit=0) == []


@pytest.mark.asyncio
async def test_recent_deliveries_negative_limit_returns_empty(
    dispatcher,
) -> None:
    d, _ = dispatcher
    assert await d.recent_deliveries(limit=-1) == []


@pytest.mark.asyncio
async def test_recent_deliveries_bounded_to_1000(dispatcher) -> None:
    """The internal ring buffer caps at 1000 deliveries to bound memory."""
    d, _ = dispatcher
    await d.subscribe(_make_sub())
    # Dispatch more than the buffer can hold
    for _ in range(1200):
        await d.dispatch(_make_event())
    recent = await d.recent_deliveries(limit=2000)
    assert len(recent) == 1000


# ---------------------------------------------------------------------------
# Protocol conformance
# ---------------------------------------------------------------------------


def test_in_memory_dispatcher_satisfies_protocol(keypair) -> None:
    async def _noop(url, body, headers):  # noqa: ARG001
        return 200, 5

    d: WebhookDispatcher = InMemoryWebhookDispatcher(
        keypair=keypair, http_poster=_noop
    )
    assert hasattr(d, "subscribe")
    assert hasattr(d, "list_subscriptions")
    assert hasattr(d, "dispatch")
    assert hasattr(d, "recent_deliveries")
