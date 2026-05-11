# @verixa/ts

[![npm version](https://img.shields.io/npm/v/@verixa/ts.svg)](https://www.npmjs.com/package/@verixa/ts)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

Async TypeScript SDK for the [Verixa](https://github.com/v-sen/verixa) Control Plane API.

Verixa is the audit + governance layer for AI agent workflows: every model decision is captured, signed, and replayable for regulators. This SDK is the client library you import to talk to a deployed Verixa control plane from Node 20+ or modern browsers with fetch.

Mirrors the Python [`verixa`](https://pypi.org/project/verixa/) SDK API surface; choose either based on your stack.

## Install

```bash
npm install @verixa/ts
```

Requires Node 20+ (uses built-in `fetch`). No runtime dependencies. TypeScript 5.7+ for development.

## Quickstart

```typescript
import { VerixaClient } from '@verixa/ts';

const client = new VerixaClient({ baseUrl: 'https://verixa.acme.com' });

const wf = await client.workflows.register({
  name: 'payments',
  ownerTenantId: '00000000-0000-0000-0000-000000000001',
  description: 'customer payment authorisation',
});

const audit = await client.audit.query({
  workflowId: (wf as { workflow_id: string }).workflow_id,
  fromTimestamp: new Date(Date.now() - 7 * 24 * 60 * 60 * 1000).toISOString(),
  toTimestamp: new Date().toISOString(),
});
```

## Authentication

Pass an API key (Bearer token) at construction:

```typescript
const client = new VerixaClient({
  baseUrl: 'https://verixa.acme.com',
  apiKey: 'vx_live_...',
});
```

Phase-1+ adds mTLS via SPIFFE identities on the server side.

## Resource clients

The top-level `VerixaClient` exposes eight resource sub-clients:

| Sub-client      | Methods                                                                | Purpose                                     |
| --------------- | ---------------------------------------------------------------------- | ------------------------------------------- |
| `.workflows`    | `register()`, `list()`                                                 | AI workflow registration + listing          |
| `.agents`       | `register()`                                                           | Agent definitions per workflow              |
| `.tools`        | `register()`                                                           | Tool definitions per workflow               |
| `.audit`        | `query()`                                                              | Audit ledger query by workflow + time range |
| `.replay`       | `get()`                                                                | Reconstruct a decision from its audit-id    |
| `.dossier`      | `generate()`, `get()`                                                  | Compliance dossier generation + retrieval   |
| `.bundles`      | `list()`, `fetch()`                                                    | OPA policy bundle distribution              |
| `.webhooks`     | `subscribe()`, `listSubscriptions()`, `recentDeliveries()`             | Outbound webhook management                 |

All method arguments are camelCase TypeScript objects; the SDK maps them to snake_case wire format automatically so the JSON sent to the server matches the documented [OpenAPI schema](https://github.com/v-sen/verixa/blob/main/docs/openapi.json).

## Error handling

All SDK errors inherit from `VerixaError`:

- `VerixaHttpError`: HTTP non-2xx response. Carries `statusCode`, `body`, `url`.
- `VerixaConnectionError`: transport-level failure (DNS, TCP, TLS, timeout). Carries `url`, `cause`.

```typescript
import { VerixaClient, VerixaHttpError, VerixaConnectionError } from '@verixa/ts';

try {
  await client.workflows.register({ name: 'x', ownerTenantId: '...' });
} catch (err) {
  if (err instanceof VerixaHttpError) {
    console.error(`HTTP ${err.statusCode}: ${JSON.stringify(err.body)}`);
  } else if (err instanceof VerixaConnectionError) {
    console.error(`Network failure: ${err.cause}`);
  } else {
    throw err;
  }
}
```

## OPA bundle pull with caching

The `bundles.fetch()` method supports the OPA pull-model with `If-None-Match` so you don't re-download unchanged bundles:

```typescript
let cachedEtag: string | undefined;
while (true) {
  const result = await client.bundles.fetch('core', { ifNoneMatch: cachedEtag });
  if (result === null) {
    // 304 Not Modified -- keep using the cached bundle
  } else {
    cachedEtag = result.etag;
    // Hand `result.body` (Uint8Array) to OPA's bundle loader
  }
  await new Promise((r) => setTimeout(r, 60_000));
}
```

## Custom fetch

For testing or special transport needs, inject a custom fetch implementation:

```typescript
import { VerixaClient, type FetchLike } from '@verixa/ts';

const myFetch: FetchLike = async (url, init) => {
  // Custom logic, e.g. mTLS via undici
  return fetch(url, init);
};

const client = new VerixaClient({
  baseUrl: 'https://verixa.acme.com',
  fetchImpl: myFetch,
});
```

## Versioning

Semver. Pre-1.0: minor versions may include breaking changes; pin a tight version range in production:

```json
{ "dependencies": { "@verixa/ts": "~0.1.0" } }
```

See [CHANGELOG.md](CHANGELOG.md) for release notes.

## Roadmap

- v0.2.0: retry-with-exponential-backoff for 5xx
- v0.2.0: webhook receiver helper that verifies inbound Ed25519 signatures
- v0.3.0: mTLS authentication helper using undici Agent + client certs
- v0.3.0: AsyncIterator pagination helper for large audit queries
- v0.4.0: extracted shared envelope TypeScript types so methods return typed objects instead of `unknown`
- v1.0.0: API frozen; Phase-2 capabilities added behind feature-flag namespaces

## License

MIT. See [LICENSE](../../LICENSE) in the monorepo root.

## Contributing

Verixa is open source. Source tree, contributing guide, and issue tracker at <https://github.com/v-sen/verixa>.
