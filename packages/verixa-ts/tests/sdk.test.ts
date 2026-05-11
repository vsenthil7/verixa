/**
 * Vitest suite for the verixa-ts SDK.
 *
 * Coverage target: 100% line + branch + function on src/sdk.ts. Tests
 * use a captured-fetch mock so the SDK is exercised end-to-end without
 * hitting a real server. All 8 resource clients get happy-path coverage;
 * error paths get explicit status + transport-error tests.
 */

import { describe, expect, it } from 'vitest';

import {
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
  type FetchLike,
} from '../src/sdk.js';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

interface CapturedRequest {
  url: string;
  init: RequestInit | undefined;
}

interface MockFetchOptions {
  status?: number;
  body?: unknown;
  bodyBytes?: Uint8Array;
  headers?: Record<string, string>;
  reject?: Error;
}

function makeMockFetch(opts: MockFetchOptions): {
  fetchImpl: FetchLike;
  captured: CapturedRequest[];
} {
  const captured: CapturedRequest[] = [];
  const fetchImpl: FetchLike = async (
    input: RequestInfo | URL,
    init?: RequestInit,
  ): Promise<Response> => {
    const url = typeof input === 'string' ? input : input.toString();
    captured.push({ url, init });
    if (opts.reject) {
      throw opts.reject;
    }
    const status = opts.status ?? 200;
    const headers = new Headers(opts.headers ?? {});
    // Fetch spec: 1xx, 204, 205, 304 MUST have null body.
    const nullBodyStatuses = [101, 103, 204, 205, 304];
    if (nullBodyStatuses.includes(status)) {
      return new Response(null, { status, headers });
    }
    if (opts.bodyBytes !== undefined) {
      return new Response(opts.bodyBytes, { status, headers });
    }
    const body =
      opts.body === undefined
        ? ''
        : typeof opts.body === 'string'
          ? opts.body
          : JSON.stringify(opts.body);
    if (!headers.has('content-type') && body.length > 0) {
      headers.set('content-type', 'application/json');
    }
    return new Response(body, { status, headers });
  };
  return { fetchImpl, captured };
}

function makeClient(opts: MockFetchOptions = {}): {
  client: VerixaClient;
  captured: CapturedRequest[];
} {
  const { fetchImpl, captured } = makeMockFetch(opts);
  const client = new VerixaClient({
    baseUrl: 'https://verixa.test',
    fetchImpl,
  });
  return { client, captured };
}

const TENANT = 'aaaaaaaa-1111-1111-1111-aaaaaaaaaaaa';
const WORKFLOW = '11111111-2222-3333-4444-555555555555';

// ---------------------------------------------------------------------------
// Exceptions
// ---------------------------------------------------------------------------

describe('Exceptions', () => {
  it('VerixaError is an Error subclass', () => {
    const e = new VerixaError('boom');
    expect(e).toBeInstanceOf(Error);
    expect(e.message).toBe('boom');
    expect(e.name).toBe('VerixaError');
  });

  it('VerixaHttpError carries status + body + url', () => {
    const e = new VerixaHttpError(
      404,
      { error: 'not found' },
      'https://verixa.test/foo',
    );
    expect(e.statusCode).toBe(404);
    expect(e.body).toEqual({ error: 'not found' });
    expect(e.url).toBe('https://verixa.test/foo');
    expect(e.message).toContain('404');
    expect(e.message).toContain('https://verixa.test/foo');
    expect(e).toBeInstanceOf(VerixaError);
  });

  it('VerixaConnectionError carries url + cause', () => {
    const cause = new TypeError('dns failed');
    const e = new VerixaConnectionError('https://verixa.test/bar', cause);
    expect(e.url).toBe('https://verixa.test/bar');
    expect(e.cause).toBe(cause);
    expect(e.message).toContain('TypeError');
    expect(e.message).toContain('dns failed');
  });

  it('VerixaConnectionError handles non-Error cause', () => {
    const e = new VerixaConnectionError('https://verixa.test/bar', 'string-cause');
    expect(e.cause).toBe('string-cause');
    expect(e.message).toContain('Error');
    expect(e.message).toContain('string-cause');
  });
});

// ---------------------------------------------------------------------------
// VerixaClient construction
// ---------------------------------------------------------------------------

describe('VerixaClient construction', () => {
  it('rejects ftp:// scheme', () => {
    expect(() => new VerixaClient({ baseUrl: 'ftp://oops.example.com' })).toThrow(
      /must start with http/,
    );
  });

  it('accepts http://', () => {
    const c = new VerixaClient({ baseUrl: 'http://localhost:8000' });
    expect(c.workflows).toBeInstanceOf(WorkflowsClient);
  });

  it('accepts https://', () => {
    const c = new VerixaClient({ baseUrl: 'https://verixa.test' });
    expect(c.workflows).toBeInstanceOf(WorkflowsClient);
  });

  it('exposes all 8 resource clients', () => {
    const c = new VerixaClient({ baseUrl: 'https://verixa.test' });
    expect(c.workflows).toBeInstanceOf(WorkflowsClient);
    expect(c.agents).toBeInstanceOf(AgentsClient);
    expect(c.tools).toBeInstanceOf(ToolsClient);
    expect(c.audit).toBeInstanceOf(AuditClient);
    expect(c.replay).toBeInstanceOf(ReplayClient);
    expect(c.dossier).toBeInstanceOf(DossierClient);
    expect(c.bundles).toBeInstanceOf(BundlesClient);
    expect(c.webhooks).toBeInstanceOf(WebhooksClient);
  });

  it('strips trailing slashes from baseUrl', async () => {
    const { fetchImpl, captured } = makeMockFetch({ body: { ok: true } });
    const c = new VerixaClient({
      baseUrl: 'https://verixa.test///',
      fetchImpl,
    });
    await c.workflows.list();
    expect(captured[0]?.url).toBe('https://verixa.test/v1/control/workflows');
  });

  it('sends User-Agent verixa-ts/0.1.0', async () => {
    const { fetchImpl, captured } = makeMockFetch({ body: {} });
    const c = new VerixaClient({ baseUrl: 'https://verixa.test', fetchImpl });
    await c.workflows.list();
    const headers = captured[0]?.init?.headers as Record<string, string>;
    expect(headers['User-Agent']).toBe('verixa-ts/0.1.0');
  });

  it('sets Authorization header when apiKey provided', async () => {
    const { fetchImpl, captured } = makeMockFetch({ body: {} });
    const c = new VerixaClient({
      baseUrl: 'https://verixa.test',
      apiKey: 'secret-token',
      fetchImpl,
    });
    await c.workflows.list();
    const headers = captured[0]?.init?.headers as Record<string, string>;
    expect(headers['Authorization']).toBe('Bearer secret-token');
  });

  it('omits Authorization when no apiKey', async () => {
    const { fetchImpl, captured } = makeMockFetch({ body: {} });
    const c = new VerixaClient({ baseUrl: 'https://verixa.test', fetchImpl });
    await c.workflows.list();
    const headers = captured[0]?.init?.headers as Record<string, string>;
    expect(headers['Authorization']).toBeUndefined();
  });

  it('uses globalThis.fetch when fetchImpl not provided', () => {
    // Just smoke-test construction; we don't actually call it.
    const c = new VerixaClient({ baseUrl: 'https://verixa.test' });
    expect(c).toBeDefined();
  });
});

// ---------------------------------------------------------------------------
// HTTP error handling
// ---------------------------------------------------------------------------

describe('HTTP error handling', () => {
  it('throws VerixaHttpError on 4xx with JSON body', async () => {
    const { client } = makeClient({
      status: 400,
      body: { error: 'invalid', message: 'bad name' },
    });
    // CP-70: ownerTenantId removed from register signature.
    await expect(
      client.workflows.register({ name: '' }),
    ).rejects.toBeInstanceOf(VerixaHttpError);
  });

  it('throws VerixaHttpError with parsed body on 4xx', async () => {
    const { client } = makeClient({
      status: 422,
      body: { detail: 'validation error' },
    });
    try {
      await client.workflows.list();
      throw new Error('should have thrown');
    } catch (err) {
      expect(err).toBeInstanceOf(VerixaHttpError);
      const httpErr = err as VerixaHttpError;
      expect(httpErr.statusCode).toBe(422);
      expect(httpErr.body).toEqual({ detail: 'validation error' });
    }
  });

  it('throws VerixaHttpError with text body on 5xx without JSON', async () => {
    const { client } = makeClient({
      status: 500,
      body: 'Internal Server Error',
    });
    try {
      await client.workflows.list();
      throw new Error('should have thrown');
    } catch (err) {
      expect(err).toBeInstanceOf(VerixaHttpError);
      expect((err as VerixaHttpError).statusCode).toBe(500);
    }
  });

  it('handles empty body on error', async () => {
    const { client } = makeClient({ status: 404, body: '' });
    try {
      await client.workflows.list();
      throw new Error('should have thrown');
    } catch (err) {
      expect(err).toBeInstanceOf(VerixaHttpError);
      expect((err as VerixaHttpError).body).toBeNull();
    }
  });

  it('wraps transport errors in VerixaConnectionError', async () => {
    const { client } = makeClient({ reject: new TypeError('network down') });
    await expect(client.workflows.list()).rejects.toBeInstanceOf(
      VerixaConnectionError,
    );
  });
});

// ---------------------------------------------------------------------------
// Resource clients -- happy paths
// ---------------------------------------------------------------------------

describe('workflows', () => {
  // CP-70 wire-format correction: the CP-51 SDK sent ownerTenantId
  // which the server's strict extra='forbid' schema rejected.
  // Server WorkflowRegisterRequest accepts name + description
  // (default '') + sector (default 'generic') + risk_threshold_escalate
  // (default 0.50, float [0,1]).
  it('register posts correct body', async () => {
    const { client, captured } = makeClient({
      status: 201,
      body: {
        workflow_id: WORKFLOW,
        name: 'payments',
        sector: 'financial-services',
        created_at: '2026-05-11T22:00:00Z',
      },
    });
    const result = await client.workflows.register({
      name: 'payments',
      description: 'payments workflow',
      sector: 'financial-services',
      riskThresholdEscalate: 0.65,
    });
    expect(captured[0]?.init?.method).toBe('POST');
    expect(captured[0]?.url).toContain('/v1/control/workflows');
    const body = JSON.parse(captured[0]?.init?.body as string);
    expect(body).toEqual({
      name: 'payments',
      description: 'payments workflow',
      sector: 'financial-services',
      risk_threshold_escalate: 0.65,
    });
    // CP-70 bug-fix: owner_tenant_id MUST NOT be sent (server rejects).
    expect(body.owner_tenant_id).toBeUndefined();
    expect((result as { name: string }).name).toBe('payments');
  });

  it('register uses documented defaults when optional kwargs omitted', async () => {
    // Server defaults: description='', sector='generic', risk_threshold=0.50.
    // SDK MUST match so callers omitting kwargs get a deterministic body.
    const { client, captured } = makeClient({
      status: 201,
      body: {
        workflow_id: WORKFLOW,
        name: 'x',
        sector: 'generic',
        created_at: '2026-05-11T22:00:00Z',
      },
    });
    await client.workflows.register({ name: 'x' });
    const body = JSON.parse(captured[0]?.init?.body as string);
    expect(body.description).toBe('');
    expect(body.sector).toBe('generic');
    expect(body.risk_threshold_escalate).toBe(0.5);
  });

  it('register with returnTyped:true returns WorkflowRegisterResponse', async () => {
    // CP-70 opt-in: returnTyped:true returns the parsed envelope.
    const { client } = makeClient({
      status: 201,
      body: {
        workflow_id: WORKFLOW,
        name: 'payments',
        sector: 'financial-services',
        created_at: '2026-05-11T22:00:00Z',
      },
    });
    const result = await client.workflows.register({
      name: 'payments',
      sector: 'financial-services',
      returnTyped: true,
    });
    expect(result.workflowId).toBe(WORKFLOW);
    expect(result.name).toBe('payments');
    expect(result.sector).toBe('financial-services');
    expect(result.createdAt).toBeInstanceOf(Date);
  });

  it('register with returnTyped:false returns unknown (back-compat)', async () => {
    const { client } = makeClient({
      status: 201,
      body: {
        workflow_id: WORKFLOW,
        name: 'payments',
        sector: 'generic',
        created_at: '2026-05-11T22:00:00Z',
      },
    });
    const result = await client.workflows.register({
      name: 'payments',
      returnTyped: false,
    });
    // returnTyped:false path returns the raw JSON (typed as unknown).
    expect((result as { name: string }).name).toBe('payments');
  });

  it('list calls GET', async () => {
    const { client, captured } = makeClient({
      body: { workflows: [], total: 0 },
    });
    const result = await client.workflows.list();
    expect(captured[0]?.init?.method).toBe('GET');
    expect(result).toEqual({ workflows: [], total: 0 });
  });

  it('list with returnTyped:true returns WorkflowListResponse', async () => {
    const { client } = makeClient({
      body: {
        workflows: [
          {
            workflow_id: WORKFLOW,
            name: 'payments',
            sector: 'financial-services',
            risk_threshold_escalate: 0.5,
            agent_count: 3,
            created_at: '2026-05-11T22:00:00Z',
          },
        ],
        total: 1,
      },
    });
    const result = await client.workflows.list({ returnTyped: true });
    expect(result.total).toBe(1);
    expect(result.workflows.length).toBe(1);
    expect(result.workflows[0]?.name).toBe('payments');
    // Frozen immutable array (mirrors Python tuple-not-list).
    expect(Object.isFrozen(result.workflows)).toBe(true);
  });

  it('list with returnTyped:true bubbles InvalidEnvelopeError on bad payload', async () => {
    // Server response missing the required 'total' field. The typed
    // path raises InvalidEnvelopeError with the field name in the
    // message; the untyped path returns the raw dict (no validation).
    const { client } = makeClient({
      body: { workflows: [] }, // missing 'total'
    });
    await expect(
      client.workflows.list({ returnTyped: true }),
    ).rejects.toThrow(/field total/);
    // Untyped path is unchanged: returns raw payload.
    const raw = await client.workflows.list();
    expect(raw).toEqual({ workflows: [] });
  });
});

describe('agents', () => {
  it('register maps camelCase to snake_case in body', async () => {
    const { client, captured } = makeClient({ status: 201, body: {} });
    await client.agents.register({
      workflowId: WORKFLOW,
      name: 'reviewer-1',
      modelProvider: 'amd-mi300x',
      modelName: 'qwen3-0.6b',
    });
    const body = JSON.parse(captured[0]?.init?.body as string);
    expect(body).toEqual({
      workflow_id: WORKFLOW,
      name: 'reviewer-1',
      model_provider: 'amd-mi300x',
      model_name: 'qwen3-0.6b',
    });
  });
});

describe('tools', () => {
  it('register posts schema', async () => {
    const { client, captured } = makeClient({ status: 201, body: {} });
    await client.tools.register({
      workflowId: WORKFLOW,
      name: 'transfer-funds',
      schema: { type: 'object' },
    });
    const body = JSON.parse(captured[0]?.init?.body as string);
    expect(body.name).toBe('transfer-funds');
    expect(body.schema).toEqual({ type: 'object' });
  });
});

describe('audit', () => {
  it('query sends params as query string', async () => {
    const { client, captured } = makeClient({
      body: { entries: [], total: 0 },
    });
    await client.audit.query({
      workflowId: WORKFLOW,
      fromTimestamp: '2026-05-01T00:00:00Z',
      toTimestamp: '2026-05-11T00:00:00Z',
    });
    const url = captured[0]?.url ?? '';
    expect(url).toContain(`workflow_id=${WORKFLOW}`);
    expect(url).toContain('from=2026-05-01');
    expect(url).toContain('to=2026-05-11');
  });
});

describe('replay', () => {
  it('get posts audit_id', async () => {
    const auditId = 'abcd1234-5678-90ab-cdef-1234567890ab';
    const { client, captured } = makeClient({ body: { ok: true } });
    await client.replay.get({ auditId });
    const body = JSON.parse(captured[0]?.init?.body as string);
    expect(body).toEqual({ audit_id: auditId });
  });
});

describe('dossier', () => {
  it('generate posts audit_id + tenant_id', async () => {
    const auditId = '11111111-1111-1111-1111-111111111111';
    const { client, captured } = makeClient({
      status: 201,
      body: { dossier_id: 'x' },
    });
    await client.dossier.generate({ auditId, tenantId: TENANT });
    const body = JSON.parse(captured[0]?.init?.body as string);
    expect(body).toEqual({ audit_id: auditId, tenant_id: TENANT });
  });

  it('get fetches with id in path', async () => {
    const dossierId = '22222222-2222-2222-2222-222222222222';
    const { client, captured } = makeClient({ body: { dossier_id: dossierId } });
    await client.dossier.get(dossierId);
    expect(captured[0]?.url).toContain(`/v1/control/dossier/${dossierId}`);
  });
});

describe('bundles', () => {
  it('list calls GET', async () => {
    const { client, captured } = makeClient({
      body: { bundles: ['core', 'fs-pack'] },
    });
    const result = await client.bundles.list();
    expect(captured[0]?.url).toContain('/v1/control/policy/bundles');
    expect(result).toEqual({ bundles: ['core', 'fs-pack'] });
  });

  it('fetch returns body+etag on 200', async () => {
    const tarball = new Uint8Array([0x1f, 0x8b, 1, 2, 3, 4]);
    const { client } = makeClient({
      status: 200,
      bodyBytes: tarball,
      headers: { etag: '"abc123"', 'content-type': 'application/gzip' },
    });
    const result = await client.bundles.fetch('core');
    expect(result).not.toBeNull();
    expect(result?.body).toEqual(tarball);
    expect(result?.etag).toBe('"abc123"');
  });

  it('fetch returns null on 304', async () => {
    const { client, captured } = makeClient({ status: 304 });
    const result = await client.bundles.fetch('core', {
      ifNoneMatch: '"abc"',
    });
    expect(result).toBeNull();
    const headers = captured[0]?.init?.headers as Record<string, string>;
    expect(headers['If-None-Match']).toBe('"abc"');
  });

  it('fetch sends no If-None-Match when omitted', async () => {
    const { client, captured } = makeClient({
      status: 200,
      bodyBytes: new Uint8Array(),
    });
    await client.bundles.fetch('core');
    const headers = captured[0]?.init?.headers as Record<string, string>;
    expect(headers['If-None-Match']).toBeUndefined();
  });

  it('fetch throws VerixaHttpError on 404', async () => {
    const { client } = makeClient({ status: 404, body: { error: 'not found' } });
    await expect(client.bundles.fetch('missing')).rejects.toBeInstanceOf(
      VerixaHttpError,
    );
  });

  it('fetch wraps transport error', async () => {
    const { client } = makeClient({ reject: new TypeError('network down') });
    await expect(client.bundles.fetch('core')).rejects.toBeInstanceOf(
      VerixaConnectionError,
    );
  });

  it('fetch returns empty-string etag when header absent', async () => {
    const { client } = makeClient({
      status: 200,
      bodyBytes: new Uint8Array([1, 2]),
    });
    const result = await client.bundles.fetch('core');
    expect(result?.etag).toBe('');
  });
});

describe('webhooks', () => {
  it('subscribe maps args to snake_case body', async () => {
    const { client, captured } = makeClient({ status: 201, body: { id: 'x' } });
    await client.webhooks.subscribe({
      tenantId: TENANT,
      url: 'https://customer.example.com/wh',
      eventTypes: ['audit.decision.recorded'],
      signingKeyId: 'verixa-sig-prod',
    });
    const body = JSON.parse(captured[0]?.init?.body as string);
    expect(body).toEqual({
      tenant_id: TENANT,
      url: 'https://customer.example.com/wh',
      event_types: ['audit.decision.recorded'],
      signing_key_id: 'verixa-sig-prod',
    });
  });

  it('listSubscriptions sends tenant_id when provided', async () => {
    const { client, captured } = makeClient({
      body: { subscriptions: [], total: 0 },
    });
    await client.webhooks.listSubscriptions({ tenantId: TENANT });
    expect(captured[0]?.url).toContain(`tenant_id=${TENANT}`);
  });

  it('listSubscriptions omits tenant_id when absent', async () => {
    const { client, captured } = makeClient({
      body: { subscriptions: [], total: 0 },
    });
    await client.webhooks.listSubscriptions();
    expect(captured[0]?.url).not.toContain('tenant_id');
  });

  it('listSubscriptions works with no args', async () => {
    const { client } = makeClient({ body: { subscriptions: [], total: 0 } });
    const result = await client.webhooks.listSubscriptions();
    expect(result).toEqual({ subscriptions: [], total: 0 });
  });

  it('recentDeliveries defaults limit to 50', async () => {
    const { client, captured } = makeClient({
      body: { deliveries: [], total: 0 },
    });
    await client.webhooks.recentDeliveries();
    expect(captured[0]?.url).toContain('limit=50');
  });

  it('recentDeliveries respects custom limit', async () => {
    const { client, captured } = makeClient({
      body: { deliveries: [], total: 0 },
    });
    await client.webhooks.recentDeliveries({ limit: 250 });
    expect(captured[0]?.url).toContain('limit=250');
  });
});
