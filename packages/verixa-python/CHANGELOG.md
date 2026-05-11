# Changelog

All notable changes to the `verixa` Python SDK are recorded here. Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versioning follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- _(nothing yet -- v0.2.0 will list new items here)_

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

[Unreleased]: https://github.com/v-sen/verixa/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/v-sen/verixa/releases/tag/v0.1.0
