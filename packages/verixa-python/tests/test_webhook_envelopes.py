"""CP-64 tests for Webhook envelope dataclasses -- completes typed-response surface.

The 4 webhook envelopes mirror the server-side WebhookSubscriptionSummary +
WebhookSubscriptionListResponse + WebhookDeliverySummary +
WebhookDeliveryListResponse. After this commit, every server-side
response envelope is typed in the Python SDK.

Tests mirror the CP-61/CP-62/CP-63 pattern:
  - Positive parses for each envelope
  - Missing required fields raise InvalidEnvelopeError(field=name)
  - Invalid types rejected
  - Collections returned as tuples (immutable)
  - Forward-compat: extra fields ignored
  - Optional error field on WebhookDeliverySummary tested both ways
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from verixa.envelopes import (
    InvalidEnvelopeError,
    WebhookDeliveryListResponse,
    WebhookDeliverySummary,
    WebhookSubscriptionListResponse,
    WebhookSubscriptionSummary,
)


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _subscription_payload(**overrides) -> dict:
    payload = {
        "subscription_id": str(uuid.uuid4()),
        "tenant_id": str(uuid.uuid4()),
        "url": "https://acme.example.com/webhooks/verixa",
        "event_types": ["decision.recorded", "dossier.generated"],
        "signing_key_id": "verixa-sig-prod-acme",
        "created_at": _now(),
    }
    payload.update(overrides)
    return payload


def _delivery_payload(**overrides) -> dict:
    payload = {
        "attempt_id": str(uuid.uuid4()),
        "subscription_id": str(uuid.uuid4()),
        "event_id": str(uuid.uuid4()),
        "url": "https://acme.example.com/webhooks/verixa",
        "status_code": 200,
        "latency_ms": 42,
        "attempted_at": _now(),
        "error": None,
    }
    payload.update(overrides)
    return payload


# ---------------------------------------------------------------------------
# WebhookSubscriptionSummary
# ---------------------------------------------------------------------------


def test_subscription_summary_parses() -> None:
    parsed = WebhookSubscriptionSummary.from_dict(_subscription_payload())
    assert parsed.event_types == ("decision.recorded", "dossier.generated")
    assert isinstance(parsed.event_types, tuple)
    assert parsed.signing_key_id == "verixa-sig-prod-acme"
    assert isinstance(parsed.created_at, datetime)


def test_subscription_summary_event_types_returns_tuple() -> None:
    """Immutability: customer cannot mutate the parsed list back into
    SDK state."""
    parsed = WebhookSubscriptionSummary.from_dict(_subscription_payload())
    assert isinstance(parsed.event_types, tuple)


def test_subscription_summary_ignores_extra_fields() -> None:
    parsed = WebhookSubscriptionSummary.from_dict(
        _subscription_payload(future_field=42)
    )
    assert parsed.signing_key_id == "verixa-sig-prod-acme"


def test_subscription_summary_is_frozen() -> None:
    parsed = WebhookSubscriptionSummary.from_dict(_subscription_payload())
    with pytest.raises((AttributeError, TypeError)):
        parsed.url = "mutated"  # type: ignore[misc]


def test_subscription_summary_rejects_non_dict() -> None:
    with pytest.raises(InvalidEnvelopeError, match="expected dict"):
        WebhookSubscriptionSummary.from_dict("oops")  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "missing_key",
    [
        "subscription_id",
        "tenant_id",
        "url",
        "event_types",
        "signing_key_id",
        "created_at",
    ],
)
def test_subscription_summary_rejects_missing_required(missing_key: str) -> None:
    payload = _subscription_payload()
    del payload[missing_key]
    with pytest.raises(InvalidEnvelopeError, match=f"field {missing_key}"):
        WebhookSubscriptionSummary.from_dict(payload)


def test_subscription_summary_rejects_non_list_event_types() -> None:
    payload = _subscription_payload(event_types="not-a-list")
    with pytest.raises(InvalidEnvelopeError, match="expected list of strings"):
        WebhookSubscriptionSummary.from_dict(payload)


def test_subscription_summary_rejects_non_string_in_event_types() -> None:
    payload = _subscription_payload(event_types=["ok", 42, "ok2"])
    with pytest.raises(
        InvalidEnvelopeError, match=r"event_types\[1\]: expected string"
    ):
        WebhookSubscriptionSummary.from_dict(payload)


def test_subscription_summary_accepts_empty_event_types() -> None:
    """Server-side has a min_length=1 constraint but the SDK parser
    accepts empty for forward-compat; validation happens server-side."""
    parsed = WebhookSubscriptionSummary.from_dict(
        _subscription_payload(event_types=[])
    )
    assert parsed.event_types == ()


# ---------------------------------------------------------------------------
# WebhookSubscriptionListResponse
# ---------------------------------------------------------------------------


def test_subscription_list_parses_empty() -> None:
    parsed = WebhookSubscriptionListResponse.from_dict({
        "subscriptions": [],
        "total": 0,
    })
    assert parsed.subscriptions == ()
    assert parsed.total == 0


def test_subscription_list_parses_multiple() -> None:
    items = [_subscription_payload() for _ in range(3)]
    parsed = WebhookSubscriptionListResponse.from_dict({
        "subscriptions": items,
        "total": 3,
    })
    assert len(parsed.subscriptions) == 3
    assert all(
        isinstance(s, WebhookSubscriptionSummary)
        for s in parsed.subscriptions
    )


def test_subscription_list_returns_tuple() -> None:
    parsed = WebhookSubscriptionListResponse.from_dict({
        "subscriptions": [],
        "total": 0,
    })
    assert isinstance(parsed.subscriptions, tuple)


def test_subscription_list_rejects_non_dict() -> None:
    with pytest.raises(InvalidEnvelopeError, match="expected dict"):
        WebhookSubscriptionListResponse.from_dict("oops")  # type: ignore[arg-type]


def test_subscription_list_rejects_missing_subscriptions() -> None:
    with pytest.raises(InvalidEnvelopeError, match="field subscriptions"):
        WebhookSubscriptionListResponse.from_dict({"total": 0})


def test_subscription_list_rejects_non_list_subscriptions() -> None:
    with pytest.raises(
        InvalidEnvelopeError, match="field subscriptions: expected list"
    ):
        WebhookSubscriptionListResponse.from_dict({
            "subscriptions": "not-a-list",
            "total": 0,
        })


def test_subscription_list_bubbles_inner_error() -> None:
    """An invalid subscription inside the list raises with the field name."""
    bad = _subscription_payload()
    del bad["url"]
    with pytest.raises(InvalidEnvelopeError, match="field url"):
        WebhookSubscriptionListResponse.from_dict({
            "subscriptions": [bad],
            "total": 1,
        })


# ---------------------------------------------------------------------------
# WebhookDeliverySummary
# ---------------------------------------------------------------------------


def test_delivery_summary_parses_successful() -> None:
    """Successful delivery: status 200, error=None."""
    parsed = WebhookDeliverySummary.from_dict(_delivery_payload())
    assert parsed.status_code == 200
    assert parsed.latency_ms == 42
    assert parsed.error is None


def test_delivery_summary_parses_failed_with_error() -> None:
    """Failed delivery: non-2xx + error message."""
    parsed = WebhookDeliverySummary.from_dict(_delivery_payload(
        status_code=500,
        latency_ms=5000,
        error="HTTP 500 internal server error",
    ))
    assert parsed.status_code == 500
    assert parsed.error == "HTTP 500 internal server error"


def test_delivery_summary_omitting_error_key_yields_none() -> None:
    """Server may omit the error key entirely (vs sending null)."""
    payload = _delivery_payload()
    del payload["error"]
    parsed = WebhookDeliverySummary.from_dict(payload)
    assert parsed.error is None


def test_delivery_summary_rejects_non_string_error() -> None:
    """error is Optional[str] -- if present must be string-or-None."""
    payload = _delivery_payload(error=42)
    with pytest.raises(InvalidEnvelopeError, match="field error: expected string"):
        WebhookDeliverySummary.from_dict(payload)


def test_delivery_summary_rejects_bool_for_status_code() -> None:
    payload = _delivery_payload(status_code=True)
    with pytest.raises(InvalidEnvelopeError, match="field status_code: expected int"):
        WebhookDeliverySummary.from_dict(payload)


def test_delivery_summary_rejects_bool_for_latency() -> None:
    payload = _delivery_payload(latency_ms=False)
    with pytest.raises(InvalidEnvelopeError, match="field latency_ms: expected int"):
        WebhookDeliverySummary.from_dict(payload)


def test_delivery_summary_ignores_extra_fields() -> None:
    parsed = WebhookDeliverySummary.from_dict(_delivery_payload(future_field=42))
    assert parsed.status_code == 200


def test_delivery_summary_is_frozen() -> None:
    parsed = WebhookDeliverySummary.from_dict(_delivery_payload())
    with pytest.raises((AttributeError, TypeError)):
        parsed.status_code = 999  # type: ignore[misc]


def test_delivery_summary_rejects_non_dict() -> None:
    with pytest.raises(InvalidEnvelopeError, match="expected dict"):
        WebhookDeliverySummary.from_dict(42)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "missing_key",
    [
        "attempt_id",
        "subscription_id",
        "event_id",
        "url",
        "status_code",
        "latency_ms",
        "attempted_at",
    ],
)
def test_delivery_summary_rejects_missing_required(missing_key: str) -> None:
    """error is optional; the other 7 are required."""
    payload = _delivery_payload()
    del payload[missing_key]
    with pytest.raises(InvalidEnvelopeError, match=f"field {missing_key}"):
        WebhookDeliverySummary.from_dict(payload)


# ---------------------------------------------------------------------------
# WebhookDeliveryListResponse
# ---------------------------------------------------------------------------


def test_delivery_list_parses_empty() -> None:
    parsed = WebhookDeliveryListResponse.from_dict({
        "deliveries": [],
        "total": 0,
    })
    assert parsed.deliveries == ()
    assert parsed.total == 0


def test_delivery_list_parses_multiple() -> None:
    items = [_delivery_payload() for _ in range(2)]
    parsed = WebhookDeliveryListResponse.from_dict({
        "deliveries": items,
        "total": 2,
    })
    assert len(parsed.deliveries) == 2
    assert all(isinstance(d, WebhookDeliverySummary) for d in parsed.deliveries)


def test_delivery_list_returns_tuple() -> None:
    parsed = WebhookDeliveryListResponse.from_dict({
        "deliveries": [],
        "total": 0,
    })
    assert isinstance(parsed.deliveries, tuple)


def test_delivery_list_rejects_non_dict() -> None:
    with pytest.raises(InvalidEnvelopeError, match="expected dict"):
        WebhookDeliveryListResponse.from_dict("oops")  # type: ignore[arg-type]


def test_delivery_list_rejects_missing_deliveries() -> None:
    with pytest.raises(InvalidEnvelopeError, match="field deliveries"):
        WebhookDeliveryListResponse.from_dict({"total": 0})


def test_delivery_list_rejects_non_list_deliveries() -> None:
    with pytest.raises(
        InvalidEnvelopeError, match="field deliveries: expected list"
    ):
        WebhookDeliveryListResponse.from_dict({
            "deliveries": {},
            "total": 0,
        })


def test_delivery_list_bubbles_inner_error() -> None:
    bad = _delivery_payload()
    del bad["url"]
    with pytest.raises(InvalidEnvelopeError, match="field url"):
        WebhookDeliveryListResponse.from_dict({
            "deliveries": [bad],
            "total": 1,
        })


# ---------------------------------------------------------------------------
# Top-level re-export
# ---------------------------------------------------------------------------


def test_webhook_envelopes_reexported_from_top_level() -> None:
    import verixa

    for name in (
        "WebhookSubscriptionSummary",
        "WebhookSubscriptionListResponse",
        "WebhookDeliverySummary",
        "WebhookDeliveryListResponse",
    ):
        assert name in verixa.__all__, f"{name} missing from verixa.__all__"
        assert hasattr(verixa, name), f"{name} not importable from verixa"


def test_typed_response_surface_is_complete() -> None:
    """CP-64 milestone: every server-side response envelope has a
    Python SDK dataclass mirror. Count the envelopes."""
    import verixa

    expected_envelopes = {
        # Workflow (3)
        "WorkflowRegisterResponse",
        "WorkflowSummary",
        "WorkflowListResponse",
        # Audit (2)
        "AuditEntry",
        "AuditQueryResponse",
        # Registry (2)
        "AgentRegisterResponse",
        "ToolRegisterResponse",
        # Replay (1)
        "ReplayResponse",
        # Dossier (2)
        "DossierGenerateResponse",
        "DossierGetResponse",
        # Webhook (4) -- completes the set with CP-64
        "WebhookSubscriptionSummary",
        "WebhookSubscriptionListResponse",
        "WebhookDeliverySummary",
        "WebhookDeliveryListResponse",
    }
    for name in expected_envelopes:
        assert name in verixa.__all__, f"{name} missing"
    assert len(expected_envelopes) == 14
