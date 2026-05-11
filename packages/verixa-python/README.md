# verixa

[![PyPI version](https://img.shields.io/pypi/v/verixa.svg)](https://pypi.org/project/verixa/)
[![Python versions](https://img.shields.io/pypi/pyversions/verixa.svg)](https://pypi.org/project/verixa/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

Async Python SDK for the [Verixa](https://github.com/v-sen/verixa) Control Plane API.

Verixa is the audit + governance layer for AI agent workflows: every model decision is captured, signed, and replayable for regulators. This SDK is the client library you import to talk to a deployed Verixa control plane.

## Install

```bash
pip install verixa
```

Requires Python 3.12+. The SDK depends on `httpx` for async HTTP.

## Quickstart

```python
import asyncio
import uuid
from verixa import VerixaClient

async def main():
    async with VerixaClient(base_url="https://verixa.acme.com") as client:
        # Register a workflow
        wf = await client.workflows.register(
            name="payments",
            owner_tenant_id=uuid.UUID("00000000-0000-0000-0000-000000000001"),
            description="customer payment authorisation",
        )

        # Query the audit ledger
        from datetime import datetime, timedelta, UTC
        result = await client.audit.query(
            workflow_id=uuid.UUID(wf["workflow_id"]),
            from_timestamp=datetime.now(UTC) - timedelta(days=7),
            to_timestamp=datetime.now(UTC),
        )
        print(f"Found {result['total']} audit entries")

asyncio.run(main())
```

## Authentication

Pass an API key (Bearer token) at construction:

```python
client = VerixaClient(
    base_url="https://verixa.acme.com",
    api_key="vx_live_...",
)
```

Phase-1+ adds mTLS authentication via SPIFFE identities; see `verixa_control_plane.mtls` in the server-side codebase.

## Resource clients

The top-level `VerixaClient` exposes eight resource sub-clients, each grouping related endpoints:

| Sub-client      | Methods                                                            | Purpose                                     |
| --------------- | ------------------------------------------------------------------ | ------------------------------------------- |
| `.workflows`    | `register()`, `list()`                                             | AI workflow registration + listing          |
| `.agents`       | `register()`                                                       | Agent definitions per workflow              |
| `.tools`        | `register()`                                                       | Tool definitions per workflow               |
| `.audit`        | `query()`                                                          | Audit ledger query by workflow + time range |
| `.replay`       | `get()`                                                            | Reconstruct a decision from its audit-id    |
| `.dossier`      | `generate()`, `get()`                                              | Compliance dossier generation + retrieval   |
| `.bundles`      | `list()`, `fetch()`                                                | OPA policy bundle distribution              |
| `.webhooks`     | `subscribe()`, `list_subscriptions()`, `recent_deliveries()`       | Outbound webhook management                 |

## Error handling

All SDK errors inherit from `VerixaError`:

- `VerixaHttpError`: HTTP non-2xx response. Carries `status_code`, `body`, `url`.
- `VerixaConnectionError`: transport-level failure (DNS, TCP, TLS, timeout). Carries `url`, `cause`.

```python
from verixa import VerixaClient, VerixaHttpError, VerixaConnectionError

try:
    await client.workflows.register(name="...", owner_tenant_id=...)
except VerixaHttpError as e:
    print(f"HTTP {e.status_code}: {e.body}")
except VerixaConnectionError as e:
    print(f"Network failure: {e.cause}")
```

## OPA bundle pull with caching

The `bundles.fetch()` method supports the OPA pull-model with `If-None-Match` so you don't re-download unchanged bundles:

```python
cached_etag: str | None = None
while True:
    result = await client.bundles.fetch("core", if_none_match=cached_etag)
    if result is None:
        # 304 Not Modified -- keep using the cached bundle
        continue
    tarball, cached_etag = result
    # Hand `tarball` to OPA's bundle loader
    await asyncio.sleep(60)
```

## Webhook receiver verification

Outbound webhooks carry an Ed25519 signature so receivers can verify authenticity offline. See the server-side `verixa_control_plane.webhooks` module docstring for the full verification protocol. A receiver helper that automates this lands in v0.2.0.

## Versioning

Semver. Pre-1.0: minor versions may include breaking changes; pin a tight version range in production:

```toml
verixa = "~0.1.0"
```

See [CHANGELOG.md](CHANGELOG.md) for release notes.

## Roadmap

- v0.2.0: synchronous wrapper for non-async codebases
- v0.2.0: exponential-backoff retry helper for 5xx
- v0.2.0: webhook receiver helper that verifies inbound Ed25519 signatures
- v0.3.0: mTLS authentication helper using cryptography.x509
- v0.3.0: pagination iterator for large audit queries
- v0.4.0: extracted shared envelope Pydantic models so methods return typed objects instead of plain dicts
- v1.0.0: API frozen; Phase-2 capabilities added behind feature-flag namespaces

## License

MIT. See [LICENSE](../../LICENSE) in the monorepo root.

## Contributing

Verixa is open source. Source tree, contributing guide, and issue tracker at <https://github.com/v-sen/verixa>.
