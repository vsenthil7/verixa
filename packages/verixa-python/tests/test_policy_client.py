"""pytest suite for verixa_runtime.policy.client (CP-8.3).

OPA is not running in pytest. All HTTP traffic goes through
``httpx.MockTransport`` so the test suite is self-contained.
Live integration is exercised under the ``integration`` marker.
"""

from __future__ import annotations

from typing import Any

import httpx
import pytest

from verixa_runtime.policy import client as client_module
from verixa_runtime.policy.client import (
    OpaPolicyClient,
    PolicyClientError,
    PolicyDecision,
    PolicyDecisionKind,
    _package_to_url_path,
    _parse_opa_response,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_client_with_handler(handler) -> OpaPolicyClient:
    """Build an OpaPolicyClient whose AsyncClient uses a MockTransport."""
    transport = httpx.MockTransport(handler)
    real_async_client = httpx.AsyncClient

    def _patched_async_client(*args: Any, **kwargs: Any) -> httpx.AsyncClient:
        kwargs["transport"] = transport
        return real_async_client(*args, **kwargs)

    # Patch only inside the client module's import binding
    client_module.httpx = type(client_module.httpx)(client_module.httpx.__name__)
    client_module.httpx.AsyncClient = _patched_async_client
    client_module.httpx.HTTPError = httpx.HTTPError
    return OpaPolicyClient("http://opa:8181")


# ---------------------------------------------------------------------------
# Constants + URL composition
# ---------------------------------------------------------------------------


def test_decision_kind_values() -> None:
    assert {x.value for x in PolicyDecisionKind} == {"pass", "fail", "abstain"}


def test_package_to_url_path_simple() -> None:
    assert (
        _package_to_url_path("verixa.fs.transfer_amount_limit")
        == "verixa/fs/transfer_amount_limit"
    )


def test_package_to_url_path_two_segments() -> None:
    assert _package_to_url_path("verixa.x") == "verixa/x"


def test_package_to_url_path_rejects_empty() -> None:
    with pytest.raises(PolicyClientError, match="dotted Rego path"):
        _package_to_url_path("")


def test_package_to_url_path_rejects_no_dot() -> None:
    with pytest.raises(PolicyClientError, match="dotted Rego path"):
        _package_to_url_path("notdotted")


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------


def test_client_strips_trailing_slash() -> None:
    c = OpaPolicyClient("http://opa:8181/")
    assert c.base_url == "http://opa:8181"


def test_client_accepts_no_trailing_slash() -> None:
    c = OpaPolicyClient("http://opa:8181")
    assert c.base_url == "http://opa:8181"


def test_client_rejects_empty_base_url() -> None:
    with pytest.raises(ValueError, match="non-empty"):
        OpaPolicyClient("")


# ---------------------------------------------------------------------------
# _parse_opa_response (pure parser; covers branches not reachable via mock)
# ---------------------------------------------------------------------------


def test_parse_response_rejects_non_object() -> None:
    with pytest.raises(PolicyClientError, match="not a JSON object"):
        _parse_opa_response([1, 2, 3], "verixa.x")


def test_parse_response_missing_result_returns_abstain() -> None:
    """OPA convention: 200 with no `result` => path undefined => abstain."""
    decision = _parse_opa_response({}, "verixa.x")
    assert decision.decision == PolicyDecisionKind.ABSTAIN
    assert "no result" in decision.reason


def test_parse_response_result_not_object() -> None:
    with pytest.raises(PolicyClientError, match="not an object"):
        _parse_opa_response({"result": "scalar"}, "verixa.x")


def test_parse_response_missing_decision_field() -> None:
    with pytest.raises(PolicyClientError, match="missing 'decision'"):
        _parse_opa_response({"result": {"reason": "x"}}, "verixa.x")


def test_parse_response_unknown_decision_value() -> None:
    with pytest.raises(PolicyClientError, match="unknown decision"):
        _parse_opa_response(
            {"result": {"decision": "maybe"}}, "verixa.x"
        )


def test_parse_response_happy_path_pass() -> None:
    decision = _parse_opa_response(
        {"result": {"decision": "pass", "reason": ""}}, "verixa.x"
    )
    assert decision.decision == PolicyDecisionKind.PASS
    assert decision.reason == ""


def test_parse_response_happy_path_fail_with_extras() -> None:
    decision = _parse_opa_response(
        {
            "result": {
                "decision": "fail",
                "reason": "limit exceeded",
                "matched_pattern": "amount",
            }
        },
        "verixa.x",
    )
    assert decision.decision == PolicyDecisionKind.FAIL
    assert decision.reason == "limit exceeded"
    assert decision.raw["matched_pattern"] == "amount"


def test_parse_response_default_empty_reason() -> None:
    decision = _parse_opa_response(
        {"result": {"decision": "pass"}}, "verixa.x"
    )
    assert decision.reason == ""


# ---------------------------------------------------------------------------
# evaluate() via httpx.MockTransport
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_evaluate_happy_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    def _handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["body"] = request.content
        return httpx.Response(
            200,
            json={
                "result": {
                    "decision": "pass",
                    "reason": "",
                    "policy": "verixa.fs.transfer_amount_limit",
                }
            },
        )

    transport = httpx.MockTransport(_handler)
    real_async_client = httpx.AsyncClient

    def _patched_client(*args: Any, **kwargs: Any) -> httpx.AsyncClient:
        kwargs["transport"] = transport
        return real_async_client(*args, **kwargs)

    monkeypatch.setattr(client_module.httpx, "AsyncClient", _patched_client)

    c = OpaPolicyClient("http://opa:8181")
    decision = await c.evaluate(
        "verixa.fs.transfer_amount_limit",
        {"agent_identity": {}, "action": {}, "context": {}},
    )

    assert decision.decision == PolicyDecisionKind.PASS
    assert decision.reason == ""
    assert (
        captured["url"]
        == "http://opa:8181/v1/data/verixa/fs/transfer_amount_limit"
    )


@pytest.mark.asyncio
async def test_evaluate_fail_decision_returned(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "result": {
                    "decision": "fail",
                    "reason": "transfer amount 15000 exceeds role limit 10000 for role loan-officer",
                }
            },
        )

    transport = httpx.MockTransport(_handler)
    real_async_client = httpx.AsyncClient
    monkeypatch.setattr(
        client_module.httpx,
        "AsyncClient",
        lambda *a, **kw: real_async_client(*a, transport=transport, **kw),
    )

    c = OpaPolicyClient("http://opa:8181")
    decision = await c.evaluate("verixa.fs.transfer_amount_limit", {})
    assert decision.decision == PolicyDecisionKind.FAIL
    assert "exceeds role limit" in decision.reason


@pytest.mark.asyncio
async def test_evaluate_handles_undefined_path_as_abstain(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """OPA returns 200 with empty body when the data path doesn't exist."""

    def _handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={})

    transport = httpx.MockTransport(_handler)
    real_async_client = httpx.AsyncClient
    monkeypatch.setattr(
        client_module.httpx,
        "AsyncClient",
        lambda *a, **kw: real_async_client(*a, transport=transport, **kw),
    )

    c = OpaPolicyClient("http://opa:8181")
    decision = await c.evaluate("verixa.x.unknown", {})
    assert decision.decision == PolicyDecisionKind.ABSTAIN


@pytest.mark.asyncio
async def test_evaluate_raises_on_http_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    transport = httpx.MockTransport(_handler)
    real_async_client = httpx.AsyncClient
    monkeypatch.setattr(
        client_module.httpx,
        "AsyncClient",
        lambda *a, **kw: real_async_client(*a, transport=transport, **kw),
    )

    c = OpaPolicyClient("http://opa:8181")
    with pytest.raises(PolicyClientError, match="transport error"):
        await c.evaluate("verixa.fs.x", {})


@pytest.mark.asyncio
async def test_evaluate_raises_on_non_200(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": "internal"})

    transport = httpx.MockTransport(_handler)
    real_async_client = httpx.AsyncClient
    monkeypatch.setattr(
        client_module.httpx,
        "AsyncClient",
        lambda *a, **kw: real_async_client(*a, transport=transport, **kw),
    )

    c = OpaPolicyClient("http://opa:8181")
    with pytest.raises(PolicyClientError, match="HTTP 500"):
        await c.evaluate("verixa.fs.x", {})


@pytest.mark.asyncio
async def test_evaluate_raises_on_non_json_body(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="not json")

    transport = httpx.MockTransport(_handler)
    real_async_client = httpx.AsyncClient
    monkeypatch.setattr(
        client_module.httpx,
        "AsyncClient",
        lambda *a, **kw: real_async_client(*a, transport=transport, **kw),
    )

    c = OpaPolicyClient("http://opa:8181")
    with pytest.raises(PolicyClientError, match="non-JSON body"):
        await c.evaluate("verixa.fs.x", {})


# ---------------------------------------------------------------------------
# PolicyDecision frozen + reexports
# ---------------------------------------------------------------------------


def test_policy_decision_is_frozen() -> None:
    d = PolicyDecision(decision=PolicyDecisionKind.PASS, reason="")
    with pytest.raises((AttributeError, Exception)):
        d.reason = "y"  # type: ignore[misc]


def test_policy_decision_default_raw_is_empty_dict() -> None:
    d = PolicyDecision(decision=PolicyDecisionKind.PASS, reason="")
    assert d.raw == {}


def test_policy_package_reexports_client() -> None:
    from verixa_runtime import policy

    for name in (
        "OpaPolicyClient",
        "PolicyClientError",
        "PolicyDecision",
        "PolicyDecisionKind",
    ):
        assert hasattr(policy, name), f"policy package missing {name}"
