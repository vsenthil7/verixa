"""pytest suite for verixa_runtime.gateway.chat_completions (CP-6.3).

The upstream HTTP call goes through `_proxy_to_upstream` which we
monkey-patch in tests so the test suite never hits the live MI300X
droplet. 100% line + branch coverage.

Live droplet integration is exercised separately under the
`live_mi300x` pytest marker (deselected by default).
"""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

import httpx
import pytest
from fastapi.testclient import TestClient

from verixa_runtime.app import create_app
from verixa_runtime.gateway import chat_completions as chat_module


# ---------------------------------------------------------------------------
# Fixtures + helpers
# ---------------------------------------------------------------------------


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app())


def _valid_chat_payload() -> dict[str, Any]:
    return {
        "model": "Qwen/Qwen3-0.6B",
        "messages": [
            {"role": "user", "content": "Hello"},
        ],
        "max_tokens": 16,
    }


def _make_proxy_stub(
    status_code: int = 200, body: dict[str, Any] | None = None
):
    """Build an async stub for `_proxy_to_upstream`."""
    body = body or {
        "id": "chatcmpl-test",
        "object": "chat.completion",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": "Hi there!"},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 1, "completion_tokens": 3, "total_tokens": 4},
    }

    async def _stub(base_url: str, body_in: dict[str, Any], timeout: float):
        return status_code, body

    return _stub


# ---------------------------------------------------------------------------
# Configuration helpers
# ---------------------------------------------------------------------------


def test_default_upstream_base_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("VERIXA_VLLM_BASE_URL", raising=False)
    assert chat_module._upstream_base_url() == chat_module.DEFAULT_VLLM_BASE_URL


def test_upstream_base_url_overridden_by_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("VERIXA_VLLM_BASE_URL", "http://example.com:9999")
    assert chat_module._upstream_base_url() == "http://example.com:9999"


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_endpoint_proxies_and_attaches_verixa_metadata(
    client: TestClient,
) -> None:
    with patch.object(
        chat_module, "_proxy_to_upstream", _make_proxy_stub()
    ):
        r = client.post("/v1/chat/completions", json=_valid_chat_payload())
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["id"] == "chatcmpl-test"
    assert body["choices"][0]["message"]["content"] == "Hi there!"
    # Verixa metadata attached
    assert "_verixa" in body
    assert body["_verixa"]["phase"] == "0"
    assert body["_verixa"]["latency_ms"] >= 0
    assert body["_verixa"]["audit_id"] is None  # CP-12 wires real audit_id


# ---------------------------------------------------------------------------
# Input validation — 400 paths
# ---------------------------------------------------------------------------


def test_endpoint_returns_400_for_invalid_json(client: TestClient) -> None:
    r = client.post(
        "/v1/chat/completions",
        content=b"this is not json",
        headers={"content-type": "application/json"},
    )
    assert r.status_code == 400
    assert "invalid JSON body" in r.text


def test_endpoint_returns_400_for_non_object_body(client: TestClient) -> None:
    r = client.post("/v1/chat/completions", json=[1, 2, 3])
    assert r.status_code == 400
    assert "must be a JSON object" in r.text


def test_endpoint_returns_400_for_missing_messages(client: TestClient) -> None:
    r = client.post("/v1/chat/completions", json={"model": "x"})
    assert r.status_code == 400
    assert "missing required field: messages" in r.text


# ---------------------------------------------------------------------------
# Upstream errors — 502 paths
# ---------------------------------------------------------------------------


def test_endpoint_returns_502_on_upstream_http_error(
    client: TestClient,
) -> None:
    async def _raise_connect_error(
        base_url: str, body: dict, timeout: float
    ):
        raise httpx.ConnectError("connection refused")

    with patch.object(
        chat_module, "_proxy_to_upstream", _raise_connect_error
    ):
        r = client.post("/v1/chat/completions", json=_valid_chat_payload())
    assert r.status_code == 502
    assert "upstream vLLM error" in r.text
    assert "ConnectError" in r.text


def test_endpoint_returns_502_when_upstream_returns_non_200(
    client: TestClient,
) -> None:
    error_body = {"error": {"message": "model not found", "type": "not_found"}}
    with patch.object(
        chat_module,
        "_proxy_to_upstream",
        _make_proxy_stub(status_code=404, body=error_body),
    ):
        r = client.post("/v1/chat/completions", json=_valid_chat_payload())
    assert r.status_code == 502
    assert "upstream returned 404" in r.text


# ---------------------------------------------------------------------------
# OpenAPI schema
# ---------------------------------------------------------------------------


def test_openapi_schema_includes_chat_completions(client: TestClient) -> None:
    schema = client.get("/openapi.json").json()
    paths = schema["paths"]
    assert "/v1/chat/completions" in paths


def test_operational_endpoints_still_work_with_chat_router(
    client: TestClient,
) -> None:
    """CP-2.5 endpoints + CP-6.2 govern must not regress when chat mounts."""
    assert client.get("/healthz").status_code == 200
    assert client.get("/readyz").status_code == 200
    # govern endpoint still reachable
    govern_payload = {
        "agent_identity": {
            "spiffe_id": "spiffe://x",
            "role": "r",
            "workflow_id": "22222222-2222-2222-2222-222222222222",
        },
        "action": {"type": "tool_call", "tool_name": "read_x"},
        "context": {"prompt_hash": "b" * 64, "model_version": "m"},
        "trace_id": "t",
    }
    assert client.post("/v1/runtime/govern", json=govern_payload).status_code == 200


# ---------------------------------------------------------------------------
# _proxy_to_upstream — exercise the real function body via httpx MockTransport
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_proxy_to_upstream_real_call_via_mock_transport(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Exercise the real `_proxy_to_upstream` (lines 59-62) by injecting an
    httpx MockTransport into the AsyncClient construction path.

    We patch `httpx.AsyncClient` at the chat_completions module level so
    that when `_proxy_to_upstream` constructs `httpx.AsyncClient(timeout=...)`,
    it gets back a client backed by our mock transport.
    """
    captured: dict[str, Any] = {}

    def _handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["method"] = request.method
        captured["body"] = request.content
        return httpx.Response(
            200,
            json={
                "id": "real-call",
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": "ok"},
                        "finish_reason": "stop",
                    }
                ],
            },
        )

    transport = httpx.MockTransport(_handler)

    real_async_client = httpx.AsyncClient

    def _async_client_with_transport(*args: Any, **kwargs: Any) -> httpx.AsyncClient:
        kwargs["transport"] = transport
        return real_async_client(*args, **kwargs)

    monkeypatch.setattr(
        chat_module.httpx, "AsyncClient", _async_client_with_transport
    )

    # Now call the REAL `_proxy_to_upstream` — its body (lines 59-62)
    # constructs the AsyncClient (now patched), posts, returns.
    status, body = await chat_module._proxy_to_upstream(
        "http://upstream.test", {"messages": []}, 5.0
    )

    assert status == 200
    assert body["id"] == "real-call"
    assert body["choices"][0]["message"]["content"] == "ok"
    assert captured["url"] == "http://upstream.test/v1/chat/completions"
    assert captured["method"] == "POST"


@pytest.mark.asyncio
async def test_proxy_to_upstream_strips_trailing_slash_in_base_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify the `.rstrip('/')` branch on base_url."""
    captured: dict[str, Any] = {}

    def _handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        return httpx.Response(200, json={"choices": []})

    transport = httpx.MockTransport(_handler)
    real_async_client = httpx.AsyncClient

    def _async_client_with_transport(*args: Any, **kwargs: Any) -> httpx.AsyncClient:
        kwargs["transport"] = transport
        return real_async_client(*args, **kwargs)

    monkeypatch.setattr(
        chat_module.httpx, "AsyncClient", _async_client_with_transport
    )

    # base_url with trailing slash must produce the same URL as without
    await chat_module._proxy_to_upstream(
        "http://upstream.test/", {"messages": []}, 5.0
    )
    assert captured["url"] == "http://upstream.test/v1/chat/completions"
