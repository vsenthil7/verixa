"""CP-50 -- Verixa Python SDK (alpha): async client for Control Plane API.

Closes Phase-1 carry-forward "verixa-python SDK to PyPI". This is the
client-side library customers import to talk to a deployed Verixa
control plane:

    from verixa import VerixaClient
    async with VerixaClient(base_url="https://verixa.acme.com") as client:
        wf = await client.workflows.register(name="payments", ...)
        result = await client.audit.query(workflow_id=..., from_..., to_...)

Phase-0 deliverable (this commit):

  - ``VerixaClient``               top-level async context manager
  - ``VerixaError``                base exception
  - ``VerixaHttpError``            HTTP non-2xx (carries status + body)
  - ``VerixaConnectionError``      transport failures
  - Resource clients (sub-APIs grouped by domain):
      .workflows  -- register, list
      .agents     -- register
      .tools      -- register
      .audit      -- query
      .replay     -- get
      .dossier    -- generate, get
      .bundles    -- list, fetch (returns raw bytes + ETag)
      .webhooks   -- subscribe, list_subscriptions, recent_deliveries

Phase-1+ adds:
  - Synchronous wrapper for non-async code-bases
  - Automatic retry with exponential backoff for 5xx
  - mTLS authentication helper
  - Webhook receiver helper that verifies inbound signatures
  - Built-in pagination iterator for large audit queries

Design choices:

  - **httpx is the underlying client** (already a project dependency)
  - **Async by default** -- modern Python codebases are async; Phase-1+ sync wrapper later
  - **Pydantic models on the wire** -- request/response shapes mirror the
    envelopes module so type checkers + IDE autocomplete work end-to-end
  - **No retry on the alpha SDK** -- explicit caller control; Phase-1+ adds opt-in
  - **Returns plain dicts by default; opt-in typed envelopes** --
    CP-61..CP-64 shipped ``verixa.envelopes`` dataclasses; CP-69
    starts wiring them into the resource clients via
    ``return_typed=True`` overloads (Workflows first; other clients
    follow). v1.0.0 will flip the default to typed.
"""

from __future__ import annotations

import uuid
from contextlib import AbstractAsyncContextManager
from datetime import datetime
from types import TracebackType
from typing import Any, Literal, overload

import httpx

from verixa.envelopes import (
    AgentRegisterResponse,
    ToolRegisterResponse,
    WorkflowListResponse,
    WorkflowRegisterResponse,
)

__all__ = [
    "AgentsClient",
    "AuditClient",
    "BundlesClient",
    "DossierClient",
    "ReplayClient",
    "ToolsClient",
    "VerixaClient",
    "VerixaConnectionError",
    "VerixaError",
    "VerixaHttpError",
    "WebhooksClient",
    "WorkflowsClient",
]


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class VerixaError(Exception):
    """Base class for all SDK errors."""


class VerixaHttpError(VerixaError):
    """A control-plane response was non-2xx.

    Attributes:
      status_code:  HTTP status code
      body:         parsed JSON body if available, raw text otherwise
      url:          request URL (no query string secrets; the SDK
                    does not put secrets in query strings)
    """

    def __init__(
        self,
        *,
        status_code: int,
        body: Any,
        url: str,
    ) -> None:
        self.status_code = status_code
        self.body = body
        self.url = url
        super().__init__(
            f"Verixa HTTP {status_code} at {url}: {body!r}"
        )


class VerixaConnectionError(VerixaError):
    """Transport-level failure (DNS, TCP, TLS, timeout)."""

    def __init__(self, *, url: str, cause: Exception) -> None:
        self.url = url
        self.cause = cause
        super().__init__(
            f"Verixa transport error at {url}: "
            f"{type(cause).__name__}: {cause}"
        )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _check_response(response: httpx.Response) -> None:
    """Raise VerixaHttpError if the status code is not 2xx."""
    if 200 <= response.status_code < 300:
        return
    try:
        body: Any = response.json()
    except ValueError:
        body = response.text
    raise VerixaHttpError(
        status_code=response.status_code,
        body=body,
        url=str(response.request.url),
    )


async def _request_json(
    httpx_client: httpx.AsyncClient,
    method: str,
    path: str,
    *,
    json: Any = None,
    params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Send a JSON request and return the parsed body. Wraps transport
    errors into VerixaConnectionError and HTTP errors into VerixaHttpError."""
    try:
        response = await httpx_client.request(
            method, path, json=json, params=params
        )
    except httpx.RequestError as e:
        raise VerixaConnectionError(
            url=f"{httpx_client.base_url}{path}", cause=e
        ) from e
    _check_response(response)
    return response.json()


# ---------------------------------------------------------------------------
# Resource clients
# ---------------------------------------------------------------------------


class _SubClient:
    """Shared base: holds the httpx.AsyncClient reference."""

    def __init__(self, httpx_client: httpx.AsyncClient) -> None:
        self._http = httpx_client


class WorkflowsClient(_SubClient):
    """Workflow registration + listing.

    CP-69 corrects the CP-50 request-side wire-format bug
    (``owner_tenant_id`` was rejected by the server's
    ``extra='forbid'`` schema; tenant is inferred from auth context)
    and adds opt-in ``return_typed=True`` overloads that return
    typed envelope dataclasses instead of plain dicts. Default
    behaviour is unchanged: ``dict[str, Any]`` is still returned
    when ``return_typed`` is omitted or False. v1.0.0 will flip
    the default per the v0.4.0 deprecation timeline.
    """

    # register() -- two @overload signatures (typed vs dict)
    @overload
    async def register(
        self,
        *,
        name: str,
        description: str = ...,
        sector: str = ...,
        risk_threshold_escalate: float = ...,
        return_typed: Literal[True],
    ) -> WorkflowRegisterResponse: ...

    @overload
    async def register(
        self,
        *,
        name: str,
        description: str = ...,
        sector: str = ...,
        risk_threshold_escalate: float = ...,
        return_typed: Literal[False] = ...,
    ) -> dict[str, Any]: ...

    async def register(
        self,
        *,
        name: str,
        description: str = "",
        sector: str = "generic",
        risk_threshold_escalate: float = 0.50,
        return_typed: bool = False,
    ) -> dict[str, Any] | WorkflowRegisterResponse:
        """Register a new workflow under the calling tenant.

        Args:
            name: 1-200 chars, the human-readable workflow identifier.
            description: free-text describing what the workflow does.
            sector: industry tag (e.g. ``financial-services``,
                ``healthcare``); defaults to ``generic``.
            risk_threshold_escalate: float in [0, 1]; decisions above
                this risk score escalate to triad review. Default 0.50.
            return_typed: if True, returns a ``WorkflowRegisterResponse``
                dataclass instead of a dict.

        Returns:
            ``dict[str, Any]`` by default, or ``WorkflowRegisterResponse``
            if ``return_typed=True``.
        """
        data = await _request_json(
            self._http,
            "POST",
            "/v1/control/workflows",
            json={
                "name": name,
                "description": description,
                "sector": sector,
                "risk_threshold_escalate": risk_threshold_escalate,
            },
        )
        if return_typed:
            return WorkflowRegisterResponse.from_dict(data)
        return data

    # list() -- two @overload signatures (typed vs dict)
    @overload
    async def list(  # noqa: A003
        self, *, return_typed: Literal[True]
    ) -> WorkflowListResponse: ...

    @overload
    async def list(  # noqa: A003
        self, *, return_typed: Literal[False] = ...
    ) -> dict[str, Any]: ...

    async def list(  # noqa: A003
        self, *, return_typed: bool = False
    ) -> dict[str, Any] | WorkflowListResponse:
        """List workflows for the calling tenant.

        Args:
            return_typed: if True, returns ``WorkflowListResponse``
                with a tuple of ``WorkflowSummary`` entries; otherwise
                a plain dict (default).
        """
        data = await _request_json(
            self._http, "GET", "/v1/control/workflows"
        )
        if return_typed:
            return WorkflowListResponse.from_dict(data)
        return data


class AgentsClient(_SubClient):
    """Agent registration.

    CP-71 corrects the CP-50 wire-format bug: server's
    ``AgentRegisterRequest`` accepts ``workflow_id + spiffe_id +
    role + description``; the CP-50 SDK sent ``workflow_id + name +
    model_provider + model_name`` which the strict ``extra='forbid'``
    schema rejects. Adds opt-in ``return_typed=True`` overload that
    returns ``AgentRegisterResponse`` instead of plain dict.
    """

    @overload
    async def register(
        self,
        *,
        workflow_id: uuid.UUID,
        spiffe_id: str,
        role: str,
        description: str = ...,
        return_typed: Literal[True],
    ) -> AgentRegisterResponse: ...

    @overload
    async def register(
        self,
        *,
        workflow_id: uuid.UUID,
        spiffe_id: str,
        role: str,
        description: str = ...,
        return_typed: Literal[False] = ...,
    ) -> dict[str, Any]: ...

    async def register(
        self,
        *,
        workflow_id: uuid.UUID,
        spiffe_id: str,
        role: str,
        description: str = "",
        return_typed: bool = False,
    ) -> dict[str, Any] | AgentRegisterResponse:
        """Register an agent under a workflow.

        Args:
            workflow_id: the workflow under which this agent operates.
            spiffe_id: the agent's SPIFFE identity (1..512 chars).
                Phase-0 bypasses SPIFFE verification but the field is
                recorded for forward compatibility with CP-53 mTLS.
            role: the agent's role (e.g. ``gateway``, ``reviewer``);
                1..128 chars.
            description: free-text description; defaults to empty.
            return_typed: if True, returns ``AgentRegisterResponse``
                dataclass instead of a dict.
        """
        data = await _request_json(
            self._http,
            "POST",
            "/v1/control/agents",
            json={
                "workflow_id": str(workflow_id),
                "spiffe_id": spiffe_id,
                "role": role,
                "description": description,
            },
        )
        if return_typed:
            return AgentRegisterResponse.from_dict(data)
        return data


class ToolsClient(_SubClient):
    """Tool registration.

    CP-73 corrects the CP-50 wire-format bug: server's
    ``ToolRegisterRequest`` accepts ``name + description + is_active +
    allowed_workflow_ids``; the CP-50 SDK sent ``workflow_id + name +
    schema`` which the strict ``extra='forbid'`` schema rejects. Tools
    are NOT workflow-scoped on the server -- they belong to the tenant
    and ``allowed_workflow_ids`` is the per-tool ACL (empty list =
    any-workflow; non-empty = restricted to those workflows). The
    ``schema`` field is not part of the wire format; per-tool JSON
    schema lives on the agent side. Adds opt-in ``return_typed=True``
    overload that returns ``ToolRegisterResponse`` instead of plain dict.
    """

    @overload
    async def register(
        self,
        *,
        name: str,
        description: str = ...,
        is_active: bool = ...,
        allowed_workflow_ids: list[uuid.UUID] | None = ...,
        return_typed: Literal[True],
    ) -> ToolRegisterResponse: ...

    @overload
    async def register(
        self,
        *,
        name: str,
        description: str = ...,
        is_active: bool = ...,
        allowed_workflow_ids: list[uuid.UUID] | None = ...,
        return_typed: Literal[False] = ...,
    ) -> dict[str, Any]: ...

    async def register(
        self,
        *,
        name: str,
        description: str = "",
        is_active: bool = True,
        allowed_workflow_ids: list[uuid.UUID] | None = None,
        return_typed: bool = False,
    ) -> dict[str, Any] | ToolRegisterResponse:
        """Register a tool the agent may invoke (subject to firewall).

        Args:
            name: 1..200 chars, the tool name.
            description: free-text description; defaults to empty.
            is_active: whether the tool is enabled at registration time;
                defaults to True.
            allowed_workflow_ids: per-tool ACL. None or empty list means
                any-workflow; non-empty restricts the tool to the listed
                workflows.
            return_typed: if True, returns ``ToolRegisterResponse``
                dataclass instead of a dict.
        """
        ids = allowed_workflow_ids or []
        data = await _request_json(
            self._http,
            "POST",
            "/v1/control/tools",
            json={
                "name": name,
                "description": description,
                "is_active": is_active,
                "allowed_workflow_ids": [str(i) for i in ids],
            },
        )
        if return_typed:
            return ToolRegisterResponse.from_dict(data)
        return data


class AuditClient(_SubClient):
    """Audit ledger query."""

    async def query(
        self,
        *,
        workflow_id: uuid.UUID,
        from_timestamp: datetime,
        to_timestamp: datetime,
    ) -> dict[str, Any]:
        return await _request_json(
            self._http,
            "GET",
            "/v1/control/audit",
            params={
                "workflow_id": str(workflow_id),
                "from": from_timestamp.isoformat(),
                "to": to_timestamp.isoformat(),
            },
        )


class ReplayClient(_SubClient):
    """Replay reconstruction."""

    async def get(
        self, *, audit_id: uuid.UUID
    ) -> dict[str, Any]:
        return await _request_json(
            self._http,
            "POST",
            "/v1/control/replay",
            json={"audit_id": str(audit_id)},
        )


class DossierClient(_SubClient):
    """Compliance dossier generation + retrieval."""

    async def generate(
        self, *, audit_id: uuid.UUID, tenant_id: uuid.UUID
    ) -> dict[str, Any]:
        return await _request_json(
            self._http,
            "POST",
            "/v1/control/dossier",
            json={
                "audit_id": str(audit_id),
                "tenant_id": str(tenant_id),
            },
        )

    async def get(
        self, dossier_id: uuid.UUID
    ) -> dict[str, Any]:
        return await _request_json(
            self._http,
            "GET",
            f"/v1/control/dossier/{dossier_id}",
        )


class BundlesClient(_SubClient):
    """OPA policy bundle distribution.

    fetch() returns (tarball_bytes, etag) so callers can implement
    If-None-Match caching on their side. Use the bytes with OPA's
    bundle-loading interface.
    """

    async def list(self) -> dict[str, Any]:  # noqa: A003
        return await _request_json(
            self._http, "GET", "/v1/control/policy/bundles"
        )

    async def fetch(
        self,
        name: str,
        *,
        if_none_match: str | None = None,
    ) -> tuple[bytes, str] | None:
        """Fetch a signed bundle.

        Returns (tarball_bytes, etag) on 200, None on 304 cache-hit.
        Raises VerixaHttpError on 400/404/409/503.
        """
        headers: dict[str, str] = {}
        if if_none_match is not None:
            headers["If-None-Match"] = if_none_match
        try:
            response = await self._http.get(
                f"/v1/control/policy/bundles/{name}", headers=headers
            )
        except httpx.RequestError as e:
            raise VerixaConnectionError(
                url=f"{self._http.base_url}/v1/control/policy/bundles/{name}",
                cause=e,
            ) from e
        if response.status_code == 304:
            return None
        _check_response(response)
        return response.content, response.headers.get("etag", "")


class WebhooksClient(_SubClient):
    """Webhook subscription management."""

    async def subscribe(
        self,
        *,
        tenant_id: uuid.UUID,
        url: str,
        event_types: list[str],
        signing_key_id: str,
    ) -> dict[str, Any]:
        return await _request_json(
            self._http,
            "POST",
            "/v1/control/webhooks/subscriptions",
            json={
                "tenant_id": str(tenant_id),
                "url": url,
                "event_types": event_types,
                "signing_key_id": signing_key_id,
            },
        )

    async def list_subscriptions(
        self, *, tenant_id: uuid.UUID | None = None
    ) -> dict[str, Any]:
        params: dict[str, Any] = {}
        if tenant_id is not None:
            params["tenant_id"] = str(tenant_id)
        return await _request_json(
            self._http,
            "GET",
            "/v1/control/webhooks/subscriptions",
            params=params or None,
        )

    async def recent_deliveries(
        self, *, limit: int = 50
    ) -> dict[str, Any]:
        return await _request_json(
            self._http,
            "GET",
            "/v1/control/webhooks/deliveries",
            params={"limit": limit},
        )


# ---------------------------------------------------------------------------
# Top-level VerixaClient
# ---------------------------------------------------------------------------


class VerixaClient(AbstractAsyncContextManager["VerixaClient"]):
    """Top-level async client.

    Usage:

        async with VerixaClient(base_url="https://verixa.acme.com") as c:
            wf = await c.workflows.register(...)

    The context manager guarantees the underlying httpx.AsyncClient is
    closed. For long-lived applications, build the client at startup
    and call ``aclose()`` at shutdown.
    """

    def __init__(
        self,
        *,
        base_url: str,
        timeout: float = 30.0,
        api_key: str | None = None,
        verify: bool | str = True,
    ) -> None:
        if not base_url.startswith(("http://", "https://")):
            raise ValueError(
                f"base_url must start with http:// or https://; got {base_url!r}"
            )
        headers = {
            "User-Agent": "verixa-python/0.1.0",
            "Accept": "application/json",
        }
        if api_key is not None:
            headers["Authorization"] = f"Bearer {api_key}"
        self._http = httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            timeout=timeout,
            headers=headers,
            verify=verify,
        )
        self.workflows = WorkflowsClient(self._http)
        self.agents = AgentsClient(self._http)
        self.tools = ToolsClient(self._http)
        self.audit = AuditClient(self._http)
        self.replay = ReplayClient(self._http)
        self.dossier = DossierClient(self._http)
        self.bundles = BundlesClient(self._http)
        self.webhooks = WebhooksClient(self._http)

    async def aclose(self) -> None:
        """Close the underlying httpx client."""
        await self._http.aclose()

    async def __aenter__(self) -> VerixaClient:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self.aclose()
