"""CP-50 tests for verixa.sdk -- Python SDK alpha for the Control Plane API.

Anchored to Phase-1 carry-forward "verixa-python SDK to PyPI". Tests use
httpx's MockTransport so the SDK is exercised end-to-end against a fake
ASGI app surface without needing a real server. All 9 resource-client
methods get at least happy-path coverage; the exception paths get
explicit error-status + transport-error tests.

Coverage approach:
  - Exceptions (VerixaError / VerixaHttpError / VerixaConnectionError)
  - _check_response + _request_json helpers
  - Every resource client method (workflows/agents/tools/audit/replay/
    dossier/bundles/webhooks)
  - VerixaClient context manager + base_url validation + api_key header
  - bundles.fetch returns (bytes, etag) on 200 + None on 304
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import Any

import httpx
import pytest
from verixa.sdk import (
    AgentsClient,
    AuditClient,
    BundlesClient,
    DossierClient,
    ReplayClient,
    ToolsClient,
    VerixaClient,
    VerixaConnectionError,
    VerixaError,
    VerixaHttpError,
    WebhooksClient,
    WorkflowsClient,
    _check_response,
    _request_json,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


_TENANT = uuid.UUID("aaaaaaaa-1111-1111-1111-aaaaaaaaaaaa")
_WORKFLOW = uuid.UUID("11111111-2222-3333-4444-555555555555")


def _make_client_with_handler(
    handler,
    *,
    base_url: str = "https://verixa.test",
) -> VerixaClient:
    """Build a VerixaClient whose underlying httpx uses a MockTransport.

    The handler receives an httpx.Request and returns an httpx.Response.
    """
    transport = httpx.MockTransport(handler)
    client = VerixaClient(base_url=base_url)
    # Swap the underlying http client for one with MockTransport
    client._http = httpx.AsyncClient(
        base_url=client._http.base_url,
        timeout=client._http.timeout,
        headers=client._http.headers,
        transport=transport,
    )
    # Re-wire resource clients to use the new http client
    client.workflows = WorkflowsClient(client._http)
    client.agents = AgentsClient(client._http)
    client.tools = ToolsClient(client._http)
    client.audit = AuditClient(client._http)
    client.replay = ReplayClient(client._http)
    client.dossier = DossierClient(client._http)
    client.bundles = BundlesClient(client._http)
    client.webhooks = WebhooksClient(client._http)
    return client


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


def test_verixa_error_is_exception() -> None:
    e = VerixaError("boom")
    assert isinstance(e, Exception)
    assert str(e) == "boom"


def test_verixa_http_error_carries_status_body_url() -> None:
    e = VerixaHttpError(
        status_code=404,
        body={"error": "not found"},
        url="https://verixa.test/foo",
    )
    assert e.status_code == 404
    assert e.body == {"error": "not found"}
    assert e.url == "https://verixa.test/foo"
    assert "404" in str(e)
    assert "https://verixa.test/foo" in str(e)


def test_verixa_connection_error_carries_url_and_cause() -> None:
    cause = ConnectionError("dns failed")
    e = VerixaConnectionError(url="https://verixa.test/bar", cause=cause)
    assert e.url == "https://verixa.test/bar"
    assert e.cause is cause
    assert "ConnectionError" in str(e)
    assert "dns failed" in str(e)


# ---------------------------------------------------------------------------
# _check_response helper
# ---------------------------------------------------------------------------


def test_check_response_passes_on_2xx() -> None:
    request = httpx.Request("GET", "https://verixa.test/foo")
    response = httpx.Response(200, request=request, json={"ok": True})
    # No raise
    _check_response(response)


def test_check_response_passes_on_201() -> None:
    request = httpx.Request("POST", "https://verixa.test/foo")
    response = httpx.Response(201, request=request, json={"id": "x"})
    _check_response(response)


def test_check_response_raises_on_4xx_with_json_body() -> None:
    request = httpx.Request("GET", "https://verixa.test/foo")
    response = httpx.Response(
        404, request=request, json={"error": "not found"}
    )
    with pytest.raises(VerixaHttpError) as exc_info:
        _check_response(response)
    assert exc_info.value.status_code == 404
    assert exc_info.value.body == {"error": "not found"}


def test_check_response_raises_on_5xx_with_text_body() -> None:
    request = httpx.Request("GET", "https://verixa.test/foo")
    response = httpx.Response(
        500, request=request, content=b"Internal Server Error"
    )
    with pytest.raises(VerixaHttpError) as exc_info:
        _check_response(response)
    assert exc_info.value.status_code == 500
    assert exc_info.value.body == "Internal Server Error"


# ---------------------------------------------------------------------------
# _request_json helper
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_request_json_wraps_transport_errors() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("dns failed", request=request)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(
        base_url="https://verixa.test", transport=transport
    ) as http_client:
        with pytest.raises(VerixaConnectionError) as exc_info:
            await _request_json(http_client, "GET", "/foo")
        assert "/foo" in exc_info.value.url


# ---------------------------------------------------------------------------
# VerixaClient construction
# ---------------------------------------------------------------------------


def test_verixa_client_rejects_bad_base_url() -> None:
    with pytest.raises(ValueError, match="base_url must start with"):
        VerixaClient(base_url="ftp://oops.example.com")


def test_verixa_client_accepts_http_base_url() -> None:
    """http:// is allowed for dev/test; production hardening recommended via mTLS."""
    c = VerixaClient(base_url="http://localhost:8000")
    assert str(c._http.base_url) == "http://localhost:8000"


def test_verixa_client_strips_trailing_slash() -> None:
    c = VerixaClient(base_url="https://verixa.test/")
    assert str(c._http.base_url) == "https://verixa.test"


def test_verixa_client_sends_user_agent() -> None:
    c = VerixaClient(base_url="https://verixa.test")
    assert "verixa-python/0.1.0" in c._http.headers["User-Agent"]


def test_verixa_client_with_api_key_sets_authorization_header() -> None:
    c = VerixaClient(
        base_url="https://verixa.test", api_key="secret-token"
    )
    assert c._http.headers["Authorization"] == "Bearer secret-token"


def test_verixa_client_no_api_key_no_auth_header() -> None:
    c = VerixaClient(base_url="https://verixa.test")
    assert "Authorization" not in c._http.headers


def test_verixa_client_has_all_resource_clients() -> None:
    c = VerixaClient(base_url="https://verixa.test")
    assert isinstance(c.workflows, WorkflowsClient)
    assert isinstance(c.agents, AgentsClient)
    assert isinstance(c.tools, ToolsClient)
    assert isinstance(c.audit, AuditClient)
    assert isinstance(c.replay, ReplayClient)
    assert isinstance(c.dossier, DossierClient)
    assert isinstance(c.bundles, BundlesClient)
    assert isinstance(c.webhooks, WebhooksClient)


# ---------------------------------------------------------------------------
# Context manager
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_context_manager_closes_underlying_client() -> None:
    async with VerixaClient(base_url="https://verixa.test") as client:
        assert not client._http.is_closed
    assert client._http.is_closed


@pytest.mark.asyncio
async def test_aclose_closes_underlying_client() -> None:
    client = VerixaClient(base_url="https://verixa.test")
    await client.aclose()
    assert client._http.is_closed


# ---------------------------------------------------------------------------
# workflows.register + workflows.list
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_workflows_register_posts_correct_body() -> None:
    """CP-69 corrects the CP-50 wire-format bug: server's strict
    ``extra='forbid'`` schema rejected ``owner_tenant_id`` (tenant is
    inferred from auth context). Server accepts name + description +
    sector + risk_threshold_escalate."""
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["method"] = request.method
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            201,
            request=request,
            json={
                "workflow_id": str(uuid.uuid4()),
                "name": captured["body"]["name"],
                "sector": captured["body"]["sector"],
                "created_at": "2026-05-11T22:00:00Z",
            },
        )

    async with _make_client_with_handler(handler) as c:
        result = await c.workflows.register(
            name="payments",
            description="payments workflow",
            sector="financial-services",
            risk_threshold_escalate=0.65,
        )
    assert captured["method"] == "POST"
    assert captured["url"].endswith("/v1/control/workflows")
    assert captured["body"]["name"] == "payments"
    assert captured["body"]["description"] == "payments workflow"
    assert captured["body"]["sector"] == "financial-services"
    assert captured["body"]["risk_threshold_escalate"] == 0.65
    # CP-69 bug-fix: owner_tenant_id MUST NOT be sent (server rejects)
    assert "owner_tenant_id" not in captured["body"]
    assert result["name"] == "payments"


@pytest.mark.asyncio
async def test_workflows_register_uses_documented_defaults() -> None:
    """Server defaults are ``description=""``, ``sector="generic"``,
    ``risk_threshold_escalate=0.50``; the SDK MUST match those so
    customers omitting the kwargs get a deterministic body."""
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            201,
            request=request,
            json={
                "workflow_id": str(uuid.uuid4()),
                "name": "x",
                "sector": "generic",
                "created_at": "2026-05-11T22:00:00Z",
            },
        )

    async with _make_client_with_handler(handler) as c:
        await c.workflows.register(name="x")
    assert captured["body"]["description"] == ""
    assert captured["body"]["sector"] == "generic"
    assert captured["body"]["risk_threshold_escalate"] == 0.50


@pytest.mark.asyncio
async def test_workflows_register_return_typed_true_returns_dataclass() -> None:
    """CP-69 opt-in: ``return_typed=True`` returns
    ``WorkflowRegisterResponse`` dataclass (frozen, slots, typed)."""
    from verixa.envelopes import WorkflowRegisterResponse

    workflow_id = uuid.uuid4()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            201,
            request=request,
            json={
                "workflow_id": str(workflow_id),
                "name": "payments",
                "sector": "financial-services",
                "created_at": "2026-05-11T22:00:00Z",
            },
        )

    async with _make_client_with_handler(handler) as c:
        result = await c.workflows.register(
            name="payments",
            sector="financial-services",
            return_typed=True,
        )
    assert isinstance(result, WorkflowRegisterResponse)
    assert result.workflow_id == workflow_id
    assert result.name == "payments"
    assert result.sector == "financial-services"


@pytest.mark.asyncio
async def test_workflows_register_return_typed_false_returns_dict() -> None:
    """Explicit ``return_typed=False`` returns ``dict[str, Any]``
    (same as omitting the kwarg). Backwards-compatibility."""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            201,
            request=request,
            json={
                "workflow_id": str(uuid.uuid4()),
                "name": "payments",
                "sector": "generic",
                "created_at": "2026-05-11T22:00:00Z",
            },
        )

    async with _make_client_with_handler(handler) as c:
        result = await c.workflows.register(
            name="payments",
            return_typed=False,
        )
    assert isinstance(result, dict)
    assert result["name"] == "payments"


@pytest.mark.asyncio
async def test_workflows_list_calls_get() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        return httpx.Response(
            200, request=request, json={"workflows": [], "total": 0}
        )

    async with _make_client_with_handler(handler) as c:
        result = await c.workflows.list()
    assert result == {"workflows": [], "total": 0}


@pytest.mark.asyncio
async def test_workflows_list_return_typed_true_returns_dataclass() -> None:
    """CP-69 opt-in: ``return_typed=True`` returns
    ``WorkflowListResponse`` with a tuple-of-``WorkflowSummary``."""
    from verixa.envelopes import WorkflowListResponse, WorkflowSummary

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            request=request,
            json={
                "workflows": [
                    {
                        "workflow_id": str(uuid.uuid4()),
                        "name": "payments",
                        "sector": "financial-services",
                        "risk_threshold_escalate": 0.5,
                        "agent_count": 3,
                        "created_at": "2026-05-11T22:00:00Z",
                    }
                ],
                "total": 1,
            },
        )

    async with _make_client_with_handler(handler) as c:
        result = await c.workflows.list(return_typed=True)
    assert isinstance(result, WorkflowListResponse)
    assert result.total == 1
    assert len(result.workflows) == 1
    assert isinstance(result.workflows[0], WorkflowSummary)
    assert result.workflows[0].name == "payments"
    # Tuple-not-list immutability
    assert isinstance(result.workflows, tuple)


@pytest.mark.asyncio
async def test_workflows_list_return_typed_bubbles_envelope_error() -> None:
    """If the server returns a malformed payload, the typed path
    raises ``InvalidEnvelopeError`` instead of silently corrupting
    state. The dict-path returns the raw dict."""
    from verixa.envelopes import InvalidEnvelopeError

    def handler(request: httpx.Request) -> httpx.Response:
        # Missing the "total" field
        return httpx.Response(
            200, request=request, json={"workflows": []}
        )

    async with _make_client_with_handler(handler) as c:
        # Dict path: returns raw payload (no validation)
        raw = await c.workflows.list()
        assert raw == {"workflows": []}
        # Typed path: raises with field name in message
        with pytest.raises(InvalidEnvelopeError, match="field total"):
            await c.workflows.list(return_typed=True)


# ---------------------------------------------------------------------------
# agents + tools + audit + replay + dossier (one happy path each)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_agents_register_posts_correct_body() -> None:
    """CP-71 corrects the CP-50 wire-format bug: server's
    ``AgentRegisterRequest`` accepts ``workflow_id + spiffe_id +
    role + description``; the CP-50 SDK sent ``workflow_id + name +
    model_provider + model_name`` which the strict ``extra='forbid'``
    schema rejects."""
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            201,
            request=request,
            json={
                "agent_id": str(uuid.uuid4()),
                "workflow_id": str(_WORKFLOW),
                "spiffe_id": "spiffe://verixa.local/prod/gw/1",
                "role": "gateway",
                "created_at": "2026-05-11T22:00:00Z",
            },
        )

    async with _make_client_with_handler(handler) as c:
        await c.agents.register(
            workflow_id=_WORKFLOW,
            spiffe_id="spiffe://verixa.local/prod/gw/1",
            role="gateway",
            description="payments gateway",
        )
    assert captured["body"]["workflow_id"] == str(_WORKFLOW)
    assert captured["body"]["spiffe_id"] == "spiffe://verixa.local/prod/gw/1"
    assert captured["body"]["role"] == "gateway"
    assert captured["body"]["description"] == "payments gateway"
    # CP-71 bug-fix: legacy fields MUST NOT be sent (server rejects)
    assert "name" not in captured["body"]
    assert "model_provider" not in captured["body"]
    assert "model_name" not in captured["body"]


@pytest.mark.asyncio
async def test_agents_register_description_defaults_to_empty_string() -> None:
    """Server default for description is empty string."""
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            201,
            request=request,
            json={
                "agent_id": str(uuid.uuid4()),
                "workflow_id": str(_WORKFLOW),
                "spiffe_id": "x",
                "role": "y",
                "created_at": "2026-05-11T22:00:00Z",
            },
        )

    async with _make_client_with_handler(handler) as c:
        await c.agents.register(
            workflow_id=_WORKFLOW,
            spiffe_id="spiffe://x",
            role="gateway",
        )
    assert captured["body"]["description"] == ""


@pytest.mark.asyncio
async def test_agents_register_return_typed_true_returns_dataclass() -> None:
    """CP-71 opt-in: ``return_typed=True`` returns
    ``AgentRegisterResponse`` dataclass."""
    from verixa.envelopes import AgentRegisterResponse

    agent_id = uuid.uuid4()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            201,
            request=request,
            json={
                "agent_id": str(agent_id),
                "workflow_id": str(_WORKFLOW),
                "spiffe_id": "spiffe://verixa.local/prod/gw/1",
                "role": "gateway",
                "created_at": "2026-05-11T22:00:00Z",
            },
        )

    async with _make_client_with_handler(handler) as c:
        result = await c.agents.register(
            workflow_id=_WORKFLOW,
            spiffe_id="spiffe://verixa.local/prod/gw/1",
            role="gateway",
            return_typed=True,
        )
    assert isinstance(result, AgentRegisterResponse)
    assert result.agent_id == agent_id
    assert result.workflow_id == _WORKFLOW
    assert result.role == "gateway"


@pytest.mark.asyncio
async def test_tools_register_posts_correct_body() -> None:
    """CP-73 corrects the CP-50 wire-format bug: server's
    ``ToolRegisterRequest`` accepts ``name + description + is_active +
    allowed_workflow_ids``; the CP-50 SDK sent ``workflow_id + name +
    schema`` which the strict ``extra='forbid'`` schema rejects.
    Tools are NOT workflow-scoped on the server -- they belong to the
    tenant and allowed_workflow_ids is the per-tool ACL."""
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            201,
            request=request,
            json={
                "tool_id": str(uuid.uuid4()),
                "name": "transfer-funds",
                "is_active": True,
                "allowed_workflow_ids": [str(_WORKFLOW)],
                "created_at": "2026-05-11T22:00:00Z",
            },
        )

    async with _make_client_with_handler(handler) as c:
        await c.tools.register(
            name="transfer-funds",
            description="moves money between accounts",
            is_active=True,
            allowed_workflow_ids=[_WORKFLOW],
        )
    assert captured["body"]["name"] == "transfer-funds"
    assert captured["body"]["description"] == "moves money between accounts"
    assert captured["body"]["is_active"] is True
    assert captured["body"]["allowed_workflow_ids"] == [str(_WORKFLOW)]
    # CP-73 bug-fix: legacy fields MUST NOT be sent (server rejects)
    assert "workflow_id" not in captured["body"]
    assert "schema" not in captured["body"]


@pytest.mark.asyncio
async def test_tools_register_uses_documented_defaults() -> None:
    """Server defaults: description='', is_active=True,
    allowed_workflow_ids=[] (any-workflow). SDK MUST match."""
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            201,
            request=request,
            json={
                "tool_id": str(uuid.uuid4()),
                "name": "x",
                "is_active": True,
                "allowed_workflow_ids": [],
                "created_at": "2026-05-11T22:00:00Z",
            },
        )

    async with _make_client_with_handler(handler) as c:
        await c.tools.register(name="x")
    assert captured["body"]["description"] == ""
    assert captured["body"]["is_active"] is True
    assert captured["body"]["allowed_workflow_ids"] == []


@pytest.mark.asyncio
async def test_tools_register_allowed_workflow_ids_none_treated_as_empty() -> None:
    """None -> [] (any-workflow) per the docstring."""
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            201,
            request=request,
            json={
                "tool_id": str(uuid.uuid4()),
                "name": "x",
                "is_active": True,
                "allowed_workflow_ids": [],
                "created_at": "2026-05-11T22:00:00Z",
            },
        )

    async with _make_client_with_handler(handler) as c:
        await c.tools.register(name="x", allowed_workflow_ids=None)
    assert captured["body"]["allowed_workflow_ids"] == []


@pytest.mark.asyncio
async def test_tools_register_return_typed_true_returns_dataclass() -> None:
    """CP-73 opt-in: ``return_typed=True`` returns
    ``ToolRegisterResponse`` dataclass with tuple-of-UUID
    allowed_workflow_ids (immutable)."""
    from verixa.envelopes import ToolRegisterResponse

    tool_id = uuid.uuid4()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            201,
            request=request,
            json={
                "tool_id": str(tool_id),
                "name": "transfer-funds",
                "is_active": True,
                "allowed_workflow_ids": [str(_WORKFLOW)],
                "created_at": "2026-05-11T22:00:00Z",
            },
        )

    async with _make_client_with_handler(handler) as c:
        result = await c.tools.register(
            name="transfer-funds",
            allowed_workflow_ids=[_WORKFLOW],
            return_typed=True,
        )
    assert isinstance(result, ToolRegisterResponse)
    assert result.tool_id == tool_id
    assert result.name == "transfer-funds"
    assert result.is_active is True
    assert result.allowed_workflow_ids == (_WORKFLOW,)
    assert isinstance(result.allowed_workflow_ids, tuple)


@pytest.mark.asyncio
async def test_audit_query_sends_correct_query_params() -> None:
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["params"] = dict(request.url.params)
        return httpx.Response(
            200, request=request, json={"entries": [], "total": 0}
        )

    async with _make_client_with_handler(handler) as c:
        await c.audit.query(
            workflow_id=_WORKFLOW,
            from_timestamp=datetime(2026, 5, 1, 0, 0, 0, tzinfo=UTC),
            to_timestamp=datetime(2026, 5, 11, 0, 0, 0, tzinfo=UTC),
        )
    assert captured["params"]["workflow_id"] == str(_WORKFLOW)
    assert "2026-05-01" in captured["params"]["from"]
    assert "2026-05-11" in captured["params"]["to"]


@pytest.mark.asyncio
async def test_replay_get_posts_audit_id() -> None:
    audit_id = uuid.uuid4()
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            200, request=request, json={"audit_id": str(audit_id)}
        )

    async with _make_client_with_handler(handler) as c:
        await c.replay.get(audit_id=audit_id)
    assert captured["body"]["audit_id"] == str(audit_id)


@pytest.mark.asyncio
async def test_replay_get_return_typed_true_returns_dataclass() -> None:
    """CP-77 opt-in: ``return_typed=True`` returns ``ReplayResponse``
    with all collections as tuples (immutable) and opaque
    request_envelope/triad_review."""
    from verixa.envelopes import ReplayResponse

    audit_id = uuid.uuid4()
    tenant_id = uuid.uuid4()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            request=request,
            json={
                "audit_id": str(audit_id),
                "tenant_id": str(tenant_id),
                "decision": "allow",
                "risk_score": 0.12,
                "request_envelope": {"prompt": "approve $5000 payment"},
                "retrieved_documents": [
                    {"doc_id": "d1", "content_sha256": "abc"},
                ],
                "tool_io": [],
                "policy_evaluations": [
                    {"package": "fs.pii", "decision": "allow", "reason": "no pii"},
                ],
                "triad_review": None,
                "timestamp_unix_ns": 1747000000000000000,
            },
        )

    async with _make_client_with_handler(handler) as c:
        result = await c.replay.get(audit_id=audit_id, return_typed=True)
    assert isinstance(result, ReplayResponse)
    assert result.audit_id == audit_id
    assert result.tenant_id == tenant_id
    assert result.decision == "allow"
    assert result.risk_score == 0.12
    assert result.triad_review is None
    # Collections are tuple-not-list (immutable)
    assert isinstance(result.retrieved_documents, tuple)
    assert isinstance(result.tool_io, tuple)
    assert isinstance(result.policy_evaluations, tuple)
    assert len(result.retrieved_documents) == 1
    assert result.retrieved_documents[0]["doc_id"] == "d1"


@pytest.mark.asyncio
async def test_replay_get_return_typed_with_triad_review() -> None:
    """Parses triad_review dict when present (triad-invoked decision)."""
    from verixa.envelopes import ReplayResponse

    audit_id = uuid.uuid4()
    tenant_id = uuid.uuid4()
    triad = {"agreement": True, "votes": [{"model": "qwen3", "vote": "approve"}]}

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            request=request,
            json={
                "audit_id": str(audit_id),
                "tenant_id": str(tenant_id),
                "decision": "escalate",
                "risk_score": 0.75,
                "request_envelope": {},
                "retrieved_documents": [],
                "tool_io": [],
                "policy_evaluations": [],
                "triad_review": triad,
                "timestamp_unix_ns": 1747000000000000000,
            },
        )

    async with _make_client_with_handler(handler) as c:
        result = await c.replay.get(audit_id=audit_id, return_typed=True)
    assert isinstance(result, ReplayResponse)
    assert result.triad_review == triad


@pytest.mark.asyncio
async def test_dossier_generate_posts_correct_body() -> None:
    """CP-75 corrects the CP-50 wire-format bug: server's
    ``DossierGenerateRequest`` accepts ``audit_id + action_summary``;
    the CP-50 SDK sent ``audit_id + tenant_id`` which the strict
    ``extra='forbid'`` schema rejects (tenant inferred from auth)."""
    audit_id = uuid.uuid4()
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            201,
            request=request,
            json={
                "dossier_id": str(uuid.uuid4()),
                "audit_id": str(audit_id),
                "signing_key_id": "verixa-sig-dev",
                "generated_at": "2026-05-11T22:00:00Z",
            },
        )

    async with _make_client_with_handler(handler) as c:
        await c.dossier.generate(
            audit_id=audit_id,
            action_summary="customer approved payment of $5000",
        )
    assert captured["body"]["audit_id"] == str(audit_id)
    assert captured["body"]["action_summary"] == "customer approved payment of $5000"
    # CP-75 bug-fix: tenant_id MUST NOT be sent (server rejects)
    assert "tenant_id" not in captured["body"]


@pytest.mark.asyncio
async def test_dossier_generate_defaults_action_summary_empty() -> None:
    """Server default for action_summary is empty string (triggers
    system-generated summary). SDK MUST match."""
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            201,
            request=request,
            json={
                "dossier_id": str(uuid.uuid4()),
                "audit_id": str(uuid.uuid4()),
                "signing_key_id": "verixa-sig-dev",
                "generated_at": "2026-05-11T22:00:00Z",
            },
        )

    async with _make_client_with_handler(handler) as c:
        await c.dossier.generate(audit_id=uuid.uuid4())
    assert captured["body"]["action_summary"] == ""


@pytest.mark.asyncio
async def test_dossier_generate_return_typed_true_returns_dataclass() -> None:
    """CP-75 opt-in: ``return_typed=True`` returns
    ``DossierGenerateResponse`` dataclass."""
    from verixa.envelopes import DossierGenerateResponse

    dossier_id = uuid.uuid4()
    audit_id = uuid.uuid4()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            201,
            request=request,
            json={
                "dossier_id": str(dossier_id),
                "audit_id": str(audit_id),
                "signing_key_id": "verixa-sig-prod-acme",
                "generated_at": "2026-05-11T22:00:00Z",
            },
        )

    async with _make_client_with_handler(handler) as c:
        result = await c.dossier.generate(
            audit_id=audit_id,
            return_typed=True,
        )
    assert isinstance(result, DossierGenerateResponse)
    assert result.dossier_id == dossier_id
    assert result.audit_id == audit_id
    assert result.signing_key_id == "verixa-sig-prod-acme"


@pytest.mark.asyncio
async def test_dossier_get_calls_with_id_in_path() -> None:
    dossier_id = uuid.uuid4()
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        return httpx.Response(
            200,
            request=request,
            json={"dossier_id": str(dossier_id)},
        )

    async with _make_client_with_handler(handler) as c:
        await c.dossier.get(dossier_id)
    assert captured["path"] == f"/v1/control/dossier/{dossier_id}"


@pytest.mark.asyncio
async def test_dossier_get_return_typed_true_returns_dataclass() -> None:
    """CP-75 opt-in: ``return_typed=True`` returns
    ``DossierGetResponse`` with length-validated signature_hex (128 hex
    = 64 bytes Ed25519 sig) + public_key_hex (64 hex = 32 bytes Ed25519
    public key)."""
    from verixa.envelopes import DossierGetResponse

    dossier_id = uuid.uuid4()
    audit_id = uuid.uuid4()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            request=request,
            json={
                "dossier_id": str(dossier_id),
                "audit_id": str(audit_id),
                "manifest": {"summary": "approved payment"},
                "signature_hex": "a" * 128,
                "public_key_hex": "b" * 64,
            },
        )

    async with _make_client_with_handler(handler) as c:
        result = await c.dossier.get(dossier_id, return_typed=True)
    assert isinstance(result, DossierGetResponse)
    assert result.dossier_id == dossier_id
    assert result.audit_id == audit_id
    assert result.manifest == {"summary": "approved payment"}
    assert len(result.signature_hex) == 128
    assert len(result.public_key_hex) == 64


# ---------------------------------------------------------------------------
# bundles.list + bundles.fetch
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_bundles_list_returns_json() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, request=request, json={"bundles": ["core", "fs-pack"]}
        )

    async with _make_client_with_handler(handler) as c:
        result = await c.bundles.list()
    assert result == {"bundles": ["core", "fs-pack"]}


@pytest.mark.asyncio
async def test_bundles_fetch_returns_bytes_and_etag_on_200() -> None:
    tarball = b"\x1f\x8b" + b"fake-gzip-bytes" * 10
    etag = '"abc123"'

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            request=request,
            content=tarball,
            headers={"etag": etag, "content-type": "application/gzip"},
        )

    async with _make_client_with_handler(handler) as c:
        result = await c.bundles.fetch("core")
    assert result is not None
    body, returned_etag = result
    assert body == tarball
    assert returned_etag == etag


@pytest.mark.asyncio
async def test_bundles_fetch_returns_none_on_304() -> None:
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["if_none_match"] = request.headers.get("if-none-match")
        return httpx.Response(304, request=request)

    async with _make_client_with_handler(handler) as c:
        result = await c.bundles.fetch("core", if_none_match='"abc"')
    assert result is None
    assert captured["if_none_match"] == '"abc"'


@pytest.mark.asyncio
async def test_bundles_fetch_raises_on_404() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            404, request=request, json={"error": "not found"}
        )

    async with _make_client_with_handler(handler) as c:
        with pytest.raises(VerixaHttpError) as exc_info:
            await c.bundles.fetch("missing")
    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_bundles_fetch_wraps_transport_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("network down", request=request)

    async with _make_client_with_handler(handler) as c:
        with pytest.raises(VerixaConnectionError):
            await c.bundles.fetch("core")


# ---------------------------------------------------------------------------
# webhooks
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_webhooks_subscribe_posts_correct_body() -> None:
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            201,
            request=request,
            json={"subscription_id": str(uuid.uuid4())},
        )

    async with _make_client_with_handler(handler) as c:
        await c.webhooks.subscribe(
            tenant_id=_TENANT,
            url="https://customer.example.com/wh",
            event_types=["audit.decision.recorded"],
            signing_key_id="verixa-sig-prod",
        )
    assert captured["body"]["tenant_id"] == str(_TENANT)
    assert captured["body"]["url"] == "https://customer.example.com/wh"
    assert captured["body"]["event_types"] == [
        "audit.decision.recorded"
    ]
    assert captured["body"]["signing_key_id"] == "verixa-sig-prod"


@pytest.mark.asyncio
async def test_webhooks_list_subscriptions_with_tenant_filter() -> None:
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["params"] = dict(request.url.params)
        return httpx.Response(
            200,
            request=request,
            json={"subscriptions": [], "total": 0},
        )

    async with _make_client_with_handler(handler) as c:
        await c.webhooks.list_subscriptions(tenant_id=_TENANT)
    assert captured["params"]["tenant_id"] == str(_TENANT)


@pytest.mark.asyncio
async def test_webhooks_list_subscriptions_without_filter() -> None:
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["params"] = dict(request.url.params)
        return httpx.Response(
            200,
            request=request,
            json={"subscriptions": [], "total": 0},
        )

    async with _make_client_with_handler(handler) as c:
        await c.webhooks.list_subscriptions()
    assert captured["params"] == {}


@pytest.mark.asyncio
async def test_webhooks_recent_deliveries_passes_limit() -> None:
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["params"] = dict(request.url.params)
        return httpx.Response(
            200, request=request, json={"deliveries": [], "total": 0}
        )

    async with _make_client_with_handler(handler) as c:
        await c.webhooks.recent_deliveries(limit=100)
    assert captured["params"]["limit"] == "100"


# ---------------------------------------------------------------------------
# Cross-cutting: SDK propagates VerixaHttpError on non-2xx
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sdk_raises_http_error_on_400_with_typed_body() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            400,
            request=request,
            json={"error": "invalid_request", "message": "name required"},
        )

    async with _make_client_with_handler(handler) as c:
        with pytest.raises(VerixaHttpError) as exc_info:
            await c.workflows.register(name="")
    assert exc_info.value.status_code == 400
    assert exc_info.value.body["error"] == "invalid_request"
