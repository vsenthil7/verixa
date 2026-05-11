# Changelog

All notable changes to `@verixa/ts` are recorded here. Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versioning follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- _(nothing yet -- v0.2.0 will list new items here)_

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

[Unreleased]: https://github.com/v-sen/verixa/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/v-sen/verixa/releases/tag/v0.1.0
