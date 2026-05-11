"""CP-48 -- Outbound webhook event API for SIEM/ITSM delivery.

Closes Phase-1 carry-forward "webhook event API for customer SIEM/ITSM
delivery with signing". Customers running Splunk / Elastic / ServiceNow
expect Verixa to push audit + decision events to a webhook endpoint
they control. Each delivery carries an Ed25519 signature so the receiver
can verify authenticity offline (same key infrastructure as CP-43
policy_sign + CP-45 BundleServer).

Phase-0 (this commit) ships:

  - ``WebhookEvent``       frozen dataclass: event_id + event_type +
                           tenant_id + payload + timestamp
  - ``WebhookSubscription`` frozen dataclass: subscription_id + URL +
                           event-type filter + signing_key_id +
                           created_at
  - ``WebhookDeliveryAttempt`` frozen dataclass: attempt result for
                           SIEM forensics (status / latency / error)
  - ``WebhookDispatcher``  Protocol: subscribe + dispatch + list +
                           recent_deliveries
  - ``InMemoryWebhookDispatcher`` reference implementation: stores
    subscriptions in a dict, dispatches synchronously by invoking
    an injected ``HttpPoster`` callable; signs each delivery with
    the matched subscription's keypair and records the attempt.

Phase-1+ adds:
  - PostgresWebhookSubscriptions store
  - AsyncRetryQueue with exponential backoff (1s/4s/16s/64s/256s,
    5 attempts then dead-letter)
  - Per-tenant rate limits + circuit breaker for unhealthy receivers
  - Replay-attack defence: receiver verifies the event_id has not
    been seen recently (Verixa includes event_id in the signed
    payload so this is a receiver-side responsibility)

Receiver verification protocol (documented for customer integration):

  1. Read the ``X-Verixa-Signature`` header (Ed25519 hex, 128 chars)
  2. Read the ``X-Verixa-Signing-Key-Id`` header (e.g. verixa-sig-prod)
  3. Read the ``X-Verixa-Public-Key`` header (Ed25519 hex, 64 chars)
  4. Verify ``ed25519_verify(public_key, request_body_bytes, signature)``
  5. Reject if verification fails -- do NOT trust the payload otherwise

The public key travels in-band on the first delivery; receivers should
pin the key on first receipt and reject deliveries that change the key
without an out-of-band key-rotation announcement.
"""

from __future__ import annotations

import asyncio
import json
import re
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Final, Protocol

from verixa_runtime.crypto.ed25519 import (
    Ed25519KeyPair,
)
from verixa_runtime.crypto.ed25519 import (
    sign as ed25519_sign,
)

# Allowlist for event types -- prevents typos from silently breaking
# downstream SIEM rules. Add new types here as Phase-1+ work needs them.
_EVENT_TYPES: Final[frozenset[str]] = frozenset({
    "audit.decision.recorded",
    "audit.dossier.generated",
    "audit.replay.requested",
    "policy.bundle.published",
    "policy.bundle.signing_failed",
    "triad.consensus.reached",
    "triad.consensus.failed",
    "system.health.degraded",
})

# Allowlist pattern for subscription URLs. Customer URLs are HTTPS only
# (defence-in-depth -- HTTP can be intercepted); IP literals + localhost
# allowed for development. Length caps prevent silly inputs.
_URL_RE: Final = re.compile(
    r"^https://[a-zA-Z0-9][a-zA-Z0-9._-]{0,253}(:[0-9]{1,5})?(/[a-zA-Z0-9._\-/?&=%~]{0,1024})?$"
)


class WebhookError(RuntimeError):
    """Base for webhook-subsystem failures."""


class WebhookSubscriptionInvalid(WebhookError):
    """Subscription URL or event-type filter is invalid."""


class WebhookEventInvalid(WebhookError):
    """Event payload is malformed or event_type is unknown."""


@dataclass(frozen=True, slots=True)
class WebhookEvent:
    """One event the dispatcher will deliver to matching subscriptions."""

    event_id: uuid.UUID
    event_type: str
    tenant_id: uuid.UUID
    payload: dict[str, Any]
    timestamp: datetime

    def __post_init__(self) -> None:
        if self.event_type not in _EVENT_TYPES:
            raise WebhookEventInvalid(
                f"event_type {self.event_type!r} not in allowlist; "
                f"add to _EVENT_TYPES first"
            )


@dataclass(frozen=True, slots=True)
class WebhookSubscription:
    """One customer subscription. event_types is a non-empty subset of
    _EVENT_TYPES; an empty set is explicitly rejected (no-op subscription
    would just consume DB capacity and confuse audit trails)."""

    subscription_id: uuid.UUID
    tenant_id: uuid.UUID
    url: str
    event_types: frozenset[str]
    signing_key_id: str
    created_at: datetime

    def __post_init__(self) -> None:
        if not _URL_RE.match(self.url):
            raise WebhookSubscriptionInvalid(
                f"url {self.url!r} must be https:// with a valid host"
            )
        if not self.event_types:
            raise WebhookSubscriptionInvalid(
                "event_types must contain at least one event type"
            )
        unknown = self.event_types - _EVENT_TYPES
        if unknown:
            raise WebhookSubscriptionInvalid(
                f"event_types contains unknown types: {sorted(unknown)}"
            )
        if not self.signing_key_id.startswith("verixa-sig-"):
            raise WebhookSubscriptionInvalid(
                f"signing_key_id must start with 'verixa-sig-'; "
                f"got {self.signing_key_id!r}"
            )


@dataclass(frozen=True, slots=True)
class WebhookDeliveryAttempt:
    """Forensic record of one delivery attempt."""

    attempt_id: uuid.UUID
    subscription_id: uuid.UUID
    event_id: uuid.UUID
    url: str
    status_code: int  # HTTP status from receiver; -1 on transport failure
    latency_ms: int
    attempted_at: datetime
    error: str | None = None


# Type alias for the HTTP-poster callable. Returns (status_code, latency_ms).
# Implementations may wrap httpx / requests / aiohttp. Tests inject a fake.
HttpPoster = Callable[
    [str, bytes, dict[str, str]], Awaitable[tuple[int, int]]
]


class WebhookDispatcher(Protocol):
    """Async surface for managing subscriptions + dispatching events."""

    async def subscribe(
        self, subscription: WebhookSubscription
    ) -> None:  # pragma: no cover -- Protocol body
        ...

    async def list_subscriptions(
        self, *, tenant_id: uuid.UUID | None = None
    ) -> list[WebhookSubscription]:  # pragma: no cover
        ...

    async def dispatch(
        self, event: WebhookEvent
    ) -> list[WebhookDeliveryAttempt]:  # pragma: no cover
        ...

    async def recent_deliveries(
        self, *, limit: int = 50
    ) -> list[WebhookDeliveryAttempt]:  # pragma: no cover
        ...


class InMemoryWebhookDispatcher:
    """Reference dispatcher: signs payloads, posts via an injected callable,
    records attempts in a bounded ring buffer for forensics.

    The dispatcher is constructed with a single Ed25519 keypair; production
    will resolve a per-subscription key from Vault transit. Phase-0
    single-keypair is acceptable because the subscription model already
    carries a signing_key_id that production can use as the Vault key
    selector.
    """

    _MAX_RECENT_DELIVERIES = 1000

    def __init__(
        self,
        *,
        keypair: Ed25519KeyPair,
        http_poster: HttpPoster,
    ) -> None:
        self._keypair = keypair
        self._http_poster = http_poster
        self._subs: dict[uuid.UUID, WebhookSubscription] = {}
        self._recent: list[WebhookDeliveryAttempt] = []
        self._lock = asyncio.Lock()

    async def subscribe(
        self, subscription: WebhookSubscription
    ) -> None:
        async with self._lock:
            self._subs[subscription.subscription_id] = subscription

    async def list_subscriptions(
        self, *, tenant_id: uuid.UUID | None = None
    ) -> list[WebhookSubscription]:
        async with self._lock:
            subs = list(self._subs.values())
        if tenant_id is not None:
            subs = [s for s in subs if s.tenant_id == tenant_id]
        return sorted(subs, key=lambda s: s.created_at)

    def _match(
        self, event: WebhookEvent
    ) -> list[WebhookSubscription]:
        # Caller holds the lock; this is a pure filter.
        return [
            s for s in self._subs.values()
            if s.tenant_id == event.tenant_id
            and event.event_type in s.event_types
        ]

    def _build_payload(self, event: WebhookEvent) -> bytes:
        """Canonical JSON bytes that get signed + posted."""
        body = {
            "event_id": str(event.event_id),
            "event_type": event.event_type,
            "tenant_id": str(event.tenant_id),
            "payload": event.payload,
            "timestamp": event.timestamp.strftime(
                "%Y-%m-%dT%H:%M:%S.%fZ"
            ),
        }
        return json.dumps(body, sort_keys=True, separators=(",", ":")).encode(
            "utf-8"
        )

    def _build_headers(
        self,
        *,
        signature: bytes,
        subscription: WebhookSubscription,
    ) -> dict[str, str]:
        return {
            "Content-Type": "application/json",
            "User-Agent": "verixa-webhook/1.0",
            "X-Verixa-Signature": signature.hex(),
            "X-Verixa-Signing-Key-Id": subscription.signing_key_id,
            "X-Verixa-Public-Key": self._keypair.public_key.hex(),
            "X-Verixa-Subscription-Id": str(subscription.subscription_id),
        }

    async def dispatch(
        self, event: WebhookEvent
    ) -> list[WebhookDeliveryAttempt]:
        async with self._lock:
            matched = self._match(event)
        attempts: list[WebhookDeliveryAttempt] = []
        payload_bytes = self._build_payload(event)
        signature = ed25519_sign(
            self._keypair.private_key, payload_bytes
        )
        for sub in matched:
            headers = self._build_headers(
                signature=signature, subscription=sub
            )
            try:
                status_code, latency_ms = await self._http_poster(
                    sub.url, payload_bytes, headers
                )
                error: str | None = None
            except Exception as exc:  # noqa: BLE001 -- intentional broad catch
                status_code = -1
                latency_ms = 0
                error = f"{type(exc).__name__}: {exc}"
            attempt = WebhookDeliveryAttempt(
                attempt_id=uuid.uuid4(),
                subscription_id=sub.subscription_id,
                event_id=event.event_id,
                url=sub.url,
                status_code=status_code,
                latency_ms=latency_ms,
                attempted_at=datetime.now(UTC),
                error=error,
            )
            attempts.append(attempt)
        async with self._lock:
            self._recent.extend(attempts)
            # Bounded ring buffer
            if len(self._recent) > self._MAX_RECENT_DELIVERIES:
                self._recent = self._recent[-self._MAX_RECENT_DELIVERIES:]
        return attempts

    async def recent_deliveries(
        self, *, limit: int = 50
    ) -> list[WebhookDeliveryAttempt]:
        if limit <= 0:
            return []
        async with self._lock:
            return list(self._recent[-limit:])


__all__ = [
    "HttpPoster",
    "InMemoryWebhookDispatcher",
    "WebhookDeliveryAttempt",
    "WebhookDispatcher",
    "WebhookError",
    "WebhookEvent",
    "WebhookEventInvalid",
    "WebhookSubscription",
    "WebhookSubscriptionInvalid",
]
