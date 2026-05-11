# Changelog

All notable changes to `@verixa/ts` are recorded here. Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versioning follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Planned

- Automatic retry with exponential backoff on 5xx (v0.3.0 opt-in).
- Webhook receiver helper that verifies inbound `X-Verixa-Signature` Ed25519 signatures (v0.3.0).
- Pagination AsyncIterator for large audit queries (v0.3.0).
- mTLS authentication helper backed by CP-53 Protocol scaffold (v0.4.0).
- v1.0.0 will flip `returnTyped` default from `false` to `true`.

## [0.2.0] -- 2026-05-12

Typed-response surface + corrected request schemas for ALL resource clients. Cross-language symmetry with `verixa@0.2.0` Python SDK. After this release every server-side response envelope has a typed SDK return path available via the new opt-in `returnTyped: true` kwarg. Default behaviour is **unchanged**: every method still returns `Promise<unknown>` by default for full backward compatibility with v0.1.0 callers. v1.0.0 will flip the default per the documented deprecation timeline.

### Added

- New `src/envelopes.ts` module with 14 `readonly` TypeScript interfaces + `parseXxx` parser functions mirroring every server-side response envelope:
  - Workflow: `WorkflowRegisterResponse`, `WorkflowSummary`, `WorkflowListResponse`.
  - Audit: `AuditEntry`, `AuditQueryResponse`.
  - Registry: `AgentRegisterResponse`, `ToolRegisterResponse`.
  - Replay: `ReplayResponse` (10 fields including opaque `requestEnvelope` + 3 frozen readonly array collections + optional `triadReview`).
  - Dossier: `DossierGenerateResponse`, `DossierGetResponse` (with length-validated `signatureHex` 128-char Ed25519 + `publicKeyHex` 64-char Ed25519).
  - Webhook: `WebhookSubscriptionSummary`, `WebhookSubscriptionListResponse`, `WebhookDeliverySummary`, `WebhookDeliveryListResponse`.
- New `InvalidEnvelopeError` exception (extends `Error`) raised by parsers when the server returns a malformed payload. Carries a `field {name}: ...` prefix matching the Python SDK error format for cross-SDK debuggability.
- Opt-in `returnTyped: true` kwarg on every resource-client method that has a typed envelope, implemented via TypeScript function overloads using intersection types so type checkers pick the right return type at call sites:
  - `WorkflowsClient.register({...returnTyped: true}) -> Promise<WorkflowRegisterResponse>`
  - `WorkflowsClient.list({returnTyped: true}) -> Promise<WorkflowListResponse>`
  - `AgentsClient.register({...returnTyped: true}) -> Promise<AgentRegisterResponse>`
  - `ToolsClient.register({...returnTyped: true}) -> Promise<ToolRegisterResponse>`
  - `AuditClient.query({...returnTyped: true}) -> Promise<AuditQueryResponse>`
  - `ReplayClient.get({...returnTyped: true}) -> Promise<ReplayResponse>`
  - `DossierClient.generate({...returnTyped: true}) -> Promise<DossierGenerateResponse>`
  - `DossierClient.get(id, {returnTyped: true}) -> Promise<DossierGetResponse>`
  - `WebhooksClient.subscribe({...returnTyped: true}) -> Promise<WebhookSubscriptionSummary>`
  - `WebhooksClient.listSubscriptions({...returnTyped: true}) -> Promise<WebhookSubscriptionListResponse>`
  - `WebhooksClient.recentDeliveries({...returnTyped: true}) -> Promise<WebhookDeliveryListResponse>`
- All collection-valued envelope fields use `Object.freeze`-d arrays (immutable) so the parsed result cannot be mutated back into SDK state -- mirrors the tuple-not-list invariant from the Python SDK.
- Naive datetime detection: parsers reject ISO-8601 strings without TZ markers because `new Date(str)` silently treats naive strings as local time.
- UUID validation: RFC 4122 case-insensitive regex; lowercases the result for canonical form.

### Fixed

Four wire-format bugs in the v0.1.0 alpha that would cause HTTP 422 from the server's strict `extra='forbid'` Pydantic v2 schemas:

- **`WorkflowsClient.register`**: dropped `ownerTenantId` (tenant is inferred from auth context); added `sector` (default `'generic'`) + `riskThresholdEscalate` (default `0.50`). New signature: `register({name, description?, sector?, riskThresholdEscalate?, returnTyped?})`.
- **`AgentsClient.register`**: dropped `name` + `modelProvider` + `modelName`; added `spiffeId` (1..512 chars; SPIFFE identity, recorded for CP-53 mTLS forward compatibility) + `role` (1..128 chars) + `description` (default `''`). New signature: `register({workflowId, spiffeId, role, description?, returnTyped?})`.
- **`ToolsClient.register`**: tools are NOT workflow-scoped; they belong to the tenant. Dropped `workflowId` + `schema`; added `description` (default `''`) + `isActive` (default `true`) + `allowedWorkflowIds` (per-tool ACL; empty array = any-workflow). New signature: `register({name, description?, isActive?, allowedWorkflowIds?, returnTyped?})`.
- **`DossierClient.generate`**: dropped `tenantId` (inferred from auth context); added `actionSummary` (default `''`, max 2000 chars; auditor-readable summary; empty triggers system-generated). New signature: `generate({auditId, actionSummary?, returnTyped?})`.

### Verified

- `AuditClient.query` request shape (`workflowId` + `fromTimestamp` + `toTimestamp` mapped to `?workflow_id=&from=&to=`) was already correct in v0.1.0. Server route uses `Query(..., alias='from')` + `Query(..., alias='to')`.

### Migration guide from 0.1.0

If any v0.1.0 call site issued requests with the obsolete kwargs above, the calls would have 422'd against the real server. The corrected kwargs match the server-side OpenAPI schema exactly. For typed returns add `returnTyped: true` per-call; otherwise no source change is required.

## [0.1.0] -- 2026-05-11

First public alpha. Async client for the Verixa Control Plane API mirroring the Python `verixa` SDK surface and covering all routes wired through Phase-1 CP-49.

### Added

- `VerixaClient` top-level class with eight resource sub-clients accessible as fields:
  - `.workflows`: `register()`, `list()`.
  - `.agents`: `register()`.
  - `.tools`: `register()`.
  - `.audit`: `query()` by workflow + time range.
  - `.replay`: `get()` by audit-id.
  - `.dossier`: `generate()`, `get()`.
  - `.bundles`: `list()`, `fetch()` with `If-None-Match` ETag caching for the OPA pull model (returns `null` on 304 cache-hit, `{ body, etag }` on 200).
  - `.webhooks`: `subscribe()`, `listSubscriptions()` (with optional `tenantId` filter), `recentDeliveries()` (with `limit`).
- Exception hierarchy: `VerixaError` (extends Error) -> `VerixaHttpError` (carries `statusCode`, `body`, `url`) + `VerixaConnectionError` (carries `url`, `cause`).
- `VerixaClient` configuration:
  - `baseUrl` validation (HTTP/HTTPS only, trailing-slash stripped).
  - Optional `apiKey` for `Bearer` authorization header.
  - `User-Agent: verixa-ts/0.1.0` on every request.
  - Optional `fetchImpl` override for testing or custom transport.
- Built on Node 20+ built-in `fetch`; **zero runtime dependencies**.
- Strict TypeScript: `noUncheckedIndexedAccess` + `exactOptionalPropertyTypes` both enforced.
- camelCase argument names mapped automatically to snake_case wire format matching the server-side OpenAPI schema.

### Limitations (Phase-0 alpha)

- All methods return `unknown` because typed envelope models are still server-side only. v0.4.0 will extract shared types here.
- No automatic retry on 5xx; callers wrap with their own retry policy. v0.2.0 will add an opt-in exponential-backoff helper.
- No webhook receiver helper. v0.2.0 will add one that verifies inbound `X-Verixa-Signature` Ed25519 signatures automatically.
- No pagination helper. v0.3.0 will add an `AsyncIterator` for large audit queries.

### Security

- HTTPS-only base URLs are the recommended production configuration; the SDK accepts `http://` for development convenience but customers should never put production traffic through unencrypted endpoints.
- API keys are sent as `Authorization: Bearer <token>` headers, never as query string parameters.
- The SDK never logs request bodies or response bodies; only call-site code controls what is logged.

[Unreleased]: https://github.com/v-sen/verixa/compare/@verixa/ts@0.2.0...HEAD
[0.2.0]: https://github.com/v-sen/verixa/compare/@verixa/ts@0.1.0...@verixa/ts@0.2.0
[0.1.0]: https://github.com/v-sen/verixa/releases/tag/@verixa/ts@0.1.0
