# Changelog

All notable changes to the `verixa` Python SDK are recorded here. Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versioning follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Planned

- Synchronous wrapper for non-async codebases (v0.3.0).
- Automatic retry with exponential backoff on 5xx (v0.3.0 opt-in).
- Webhook receiver helper that verifies inbound `X-Verixa-Signature` Ed25519 signatures (v0.3.0).
- Pagination iterator for large audit queries (v0.3.0).
- mTLS authentication helper backed by CP-53 Protocol scaffold (v0.4.0).
- v1.0.0 will flip `return_typed` default from `False` to `True`.

## [0.2.0] -- 2026-05-12

Typed-response surface + corrected request schemas for ALL resource clients. After this release every server-side response envelope has a typed SDK return path available via the new opt-in `return_typed=True` kwarg. Default behaviour is **unchanged**: every method still returns `dict[str, Any]` by default for full backward compatibility with v0.1.0 callers. v1.0.0 will flip the default per the documented deprecation timeline.

### Added

- New `verixa.envelopes` module with 15 typed dataclasses mirroring every server-side response envelope. All envelopes use `@dataclass(frozen=True, slots=True)`, accept extra fields for forward compatibility, and reject naive datetimes:
  - Workflow: `WorkflowRegisterResponse`, `WorkflowSummary`, `WorkflowListResponse`.
  - Audit: `AuditEntry`, `AuditQueryResponse`.
  - Registry: `AgentRegisterResponse`, `ToolRegisterResponse`.
  - Replay: `ReplayResponse` (10 fields including opaque `request_envelope` + 3 tuple-of-dict collections + optional `triad_review`).
  - Dossier: `DossierGenerateResponse`, `DossierGetResponse` (with length-validated `signature_hex` 128-char Ed25519 + `public_key_hex` 64-char Ed25519).
  - Webhook: `WebhookSubscriptionSummary`, `WebhookSubscriptionListResponse`, `WebhookDeliverySummary`, `WebhookDeliveryListResponse`.
- New `verixa.envelopes.InvalidEnvelopeError` exception raised by parsers when the server returns a malformed payload. Carries a `field {name}: ...` prefix for debuggability.
- Opt-in `return_typed=True` kwarg on every resource-client method that has a typed envelope. Default is `return_typed=False` returning plain dicts (full backward compatibility):
  - `WorkflowsClient.register(..., return_typed=True) -> WorkflowRegisterResponse`
  - `WorkflowsClient.list(*, return_typed=True) -> WorkflowListResponse`
  - `AgentsClient.register(..., return_typed=True) -> AgentRegisterResponse`
  - `ToolsClient.register(..., return_typed=True) -> ToolRegisterResponse`
  - `AuditClient.query(..., return_typed=True) -> AuditQueryResponse`
  - `ReplayClient.get(..., return_typed=True) -> ReplayResponse`
  - `DossierClient.generate(..., return_typed=True) -> DossierGenerateResponse`
  - `DossierClient.get(..., return_typed=True) -> DossierGetResponse`
  - `WebhooksClient.subscribe(..., return_typed=True) -> WebhookSubscriptionSummary`
  - `WebhooksClient.list_subscriptions(..., return_typed=True) -> WebhookSubscriptionListResponse`
  - `WebhooksClient.recent_deliveries(..., return_typed=True) -> WebhookDeliveryListResponse`
- `@overload` decorators using `typing.Literal[True]` / `Literal[False]` so type checkers pick the right return type at call sites.
- All collection-valued envelope fields use tuples (immutable) instead of lists so the parsed result cannot be mutated back into SDK state.
- Top-level `verixa.__all__` expanded from 12 to 27 symbols re-exporting every envelope class + `InvalidEnvelopeError`.

### Fixed

Four wire-format bugs in the v0.1.0 alpha that would cause HTTP 422 from the server's strict `extra='forbid'` Pydantic v2 schemas:

- **`WorkflowsClient.register`**: dropped `owner_tenant_id` (tenant is inferred from auth context); added `sector` (default `"generic"`) + `risk_threshold_escalate` (default `0.50`). New signature: `register(*, name, description="", sector="generic", risk_threshold_escalate=0.50, return_typed=False)`.
- **`AgentsClient.register`**: dropped `name` + `model_provider` + `model_name`; added `spiffe_id` (1..512 chars; SPIFFE identity, recorded for CP-53 mTLS forward compatibility) + `role` (1..128 chars) + `description` (default `""`). New signature: `register(*, workflow_id, spiffe_id, role, description="", return_typed=False)`.
- **`ToolsClient.register`**: tools are NOT workflow-scoped; they belong to the tenant. Dropped `workflow_id` + `schema`; added `description` (default `""`) + `is_active` (default `True`) + `allowed_workflow_ids` (per-tool ACL; empty list = any-workflow). New signature: `register(*, name, description="", is_active=True, allowed_workflow_ids=None, return_typed=False)`.
- **`DossierClient.generate`**: dropped `tenant_id` (inferred from auth context); added `action_summary` (default `""`, max 2000 chars; auditor-readable summary; empty triggers system-generated). New signature: `generate(*, audit_id, action_summary="", return_typed=False)`.

### Verified

- `AuditClient.query` request shape (`workflow_id` + `from` + `to` query params) was already correct in v0.1.0. Server route uses `Query(..., alias='from')` + `Query(..., alias='to')`; the wire keys really are `from` and `to`.

### Migration guide from 0.1.0

If any v0.1.0 call site issued requests with the obsolete kwargs above, the calls would have 422'd against the real server. The corrected kwargs match the server-side OpenAPI schema exactly. For typed returns add `return_typed=True` per-call; otherwise no source change is required.

## [0.1.0] -- 2026-05-11

First public alpha. Async client for the Verixa Control Plane API covering all routes wired through Phase-1 CP-49.

### Added

- `VerixaClient`: async context manager wrapping `httpx.AsyncClient`.
- Eight resource sub-clients:
  - `workflows`: `register()`, `list()`.
  - `agents`: `register()`.
  - `tools`: `register()`.
  - `audit`: `query()` by workflow + time range.
  - `replay`: `get()` by audit-id.
  - `dossier`: `generate()`, `get()`.
  - `bundles`: `list()`, `fetch()` with `If-None-Match` ETag caching for the OPA pull model (returns `None` on 304 cache-hit, `(bytes, etag)` on 200).
  - `webhooks`: `subscribe()`, `list_subscriptions()` (with optional `tenant_id` filter), `recent_deliveries()` (with `limit`).
- Exception hierarchy: `VerixaError` (base) -> `VerixaHttpError` (carries `status_code`, `body`, `url`) + `VerixaConnectionError` (carries `url`, `cause`).
- `VerixaClient` configuration:
  - `base_url` validation (HTTP/HTTPS only, trailing-slash stripped).
  - Optional `api_key` for `Bearer` authorization header.
  - `User-Agent: verixa-python/0.1.0` on every request.
  - Configurable `timeout` (default 30 seconds).
  - `verify` parameter passthrough to httpx for custom TLS.
- `AbstractAsyncContextManager` integration ensuring the underlying `httpx.AsyncClient` closes on exit; `aclose()` for long-lived applications.
- PEP 561 `py.typed` marker so downstream type checkers see the package as typed.

### Limitations (Phase-0 alpha)

- All methods return plain `dict[str, Any]` because the Pydantic envelope models live in the server-side `apps/control-plane-api` package which customers do not install. v0.4.0 will extract shared envelopes here.
- No automatic retry on 5xx; callers wrap with their own retry policy. v0.2.0 will add an opt-in exponential-backoff helper.
- No synchronous wrapper; callers must use asyncio. v0.2.0 will add a sync entry point.
- No webhook receiver helper. v0.2.0 will add one that verifies inbound `X-Verixa-Signature` Ed25519 signatures automatically.

### Security

- HTTPS-only base URLs are the recommended production configuration; the SDK accepts `http://` for development convenience but customers should never put production traffic through unencrypted endpoints.
- API keys are sent as `Authorization: Bearer <token>` headers, never as query string parameters.
- The SDK never logs request bodies or response bodies; only call-site code controls what is logged.

[Unreleased]: https://github.com/v-sen/verixa/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/v-sen/verixa/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/v-sen/verixa/releases/tag/v0.1.0
