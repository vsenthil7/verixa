import { describe, expect, it } from 'vitest';

import {
  ApiError,
  createApiClient,
  type ApiClient,
  type AuditQueryResponse,
  type DossierGenerateResponse,
  type DossierGetResponse,
  type ReplayResponse,
  type WorkflowListResponse,
} from '../api-client';

interface RecordedCall {
  url: string;
  init: RequestInit | undefined;
}

function makeMockFetch(
  responses: Array<{ status: number; body: unknown }>,
): {
  fetchImpl: typeof fetch;
  calls: RecordedCall[];
} {
  let i = 0;
  const calls: RecordedCall[] = [];
  const fetchImpl = (async (
    url: string | URL | Request,
    init?: RequestInit,
  ) => {
    calls.push({ url: String(url), init });
    const response = responses[i++];
    if (response === undefined) {
      throw new Error('mock fetch exhausted');
    }
    return new Response(
      typeof response.body === 'string'
        ? response.body
        : JSON.stringify(response.body),
      { status: response.status, headers: { 'Content-Type': 'application/json' } },
    );
  }) as unknown as typeof fetch;
  return { fetchImpl, calls };
}

function makeClient(
  responses: Array<{ status: number; body: unknown }>,
): {
  client: ApiClient;
  calls: RecordedCall[];
} {
  const { fetchImpl, calls } = makeMockFetch(responses);
  const client = createApiClient({
    baseUrl: 'http://api.example.com',
    fetchImpl,
  });
  return { client, calls };
}

function firstCall(calls: RecordedCall[]): RecordedCall {
  const c = calls[0];
  if (c === undefined) {
    throw new Error('expected at least one fetch call');
  }
  return c;
}

describe('createApiClient', () => {
  it('strips trailing slashes from the base URL', async () => {
    const { fetchImpl, calls } = makeMockFetch([
      { status: 200, body: { workflows: [], total: 0 } },
    ]);
    const client = createApiClient({
      baseUrl: 'http://api.example.com///',
      fetchImpl,
    });
    await client.listWorkflows();
    expect(firstCall(calls).url).toBe(
      'http://api.example.com/v1/control/workflows',
    );
  });

  it('uses the global fetch when no fetchImpl is supplied', () => {
    const client = createApiClient({ baseUrl: 'http://x' });
    expect(client).toBeDefined();
  });

  it('attaches Content-Type: application/json on every request', async () => {
    const { client, calls } = makeClient([
      { status: 200, body: { workflows: [], total: 0 } },
    ]);
    await client.listWorkflows();
    const headers = (firstCall(calls).init?.headers ?? {}) as Record<
      string,
      string
    >;
    expect(headers['Content-Type']).toBe('application/json');
  });

  it('preserves caller-supplied headers alongside defaults', async () => {
    const { fetchImpl, calls } = makeMockFetch([
      { status: 200, body: { workflows: [], total: 0 } },
    ]);
    const client = createApiClient({
      baseUrl: 'http://api.example.com',
      fetchImpl,
    });
    await client.listWorkflows();
    const headers = (firstCall(calls).init?.headers ?? {}) as Record<
      string,
      string
    >;
    expect(headers['Content-Type']).toBe('application/json');
  });
});

describe('ApiClient.listWorkflows', () => {
  it('returns the parsed WorkflowListResponse', async () => {
    const body: WorkflowListResponse = {
      workflows: [
        {
          workflow_id: '11111111-1111-1111-1111-111111111111',
          name: 'Loan Approval',
          sector: 'financial-services',
          risk_threshold_escalate: 0.4,
          agent_count: 1,
          created_at: '2026-05-10T09:15:00Z',
        },
      ],
      total: 1,
    };
    const { client } = makeClient([{ status: 200, body }]);
    const result = await client.listWorkflows();
    expect(result.total).toBe(1);
    expect(result.workflows[0]?.name).toBe('Loan Approval');
  });
});

describe('ApiClient.queryAudit', () => {
  it('builds the query string from the three params', async () => {
    const body: AuditQueryResponse = {
      entries: [],
      total: 0,
      workflow_id: '11111111-1111-1111-1111-111111111111',
      from_timestamp: '2026-05-10T00:00:00Z',
      to_timestamp: '2026-05-11T00:00:00Z',
    };
    const { client, calls } = makeClient([{ status: 200, body }]);
    await client.queryAudit({
      workflowId: '11111111-1111-1111-1111-111111111111',
      from: '2026-05-10T00:00:00Z',
      to: '2026-05-11T00:00:00Z',
    });
    const url = firstCall(calls).url;
    expect(url).toContain('workflow_id=');
    expect(url).toContain('from=');
    expect(url).toContain('to=');
  });
});

describe('ApiClient.replay', () => {
  it('POSTs JSON with the audit_id', async () => {
    const body: ReplayResponse = {
      audit_id: 'aaaa1111-2222-3333-4444-555555555555',
      tenant_id: 'bbbb1111-2222-3333-4444-555555555555',
      decision: 'allow',
      risk_score: 0.1,
      request_envelope: { k: 'v' },
      retrieved_documents: [],
      tool_io: [],
      policy_evaluations: [],
      triad_review: null,
      timestamp_unix_ns: 1_700_000_000_000_000_000,
    };
    const { client, calls } = makeClient([{ status: 200, body }]);
    const result = await client.replay(
      'aaaa1111-2222-3333-4444-555555555555',
    );
    expect(result.decision).toBe('allow');
    const init = firstCall(calls).init;
    expect(init?.method).toBe('POST');
    expect(init?.body).toContain('aaaa1111-2222-3333-4444-555555555555');
  });
});

describe('ApiClient.generateDossier', () => {
  it('defaults action_summary to empty string when omitted', async () => {
    const body: DossierGenerateResponse = {
      dossier_id: 'dddd1111-2222-3333-4444-555555555555',
      audit_id: 'aaaa1111-2222-3333-4444-555555555555',
      signing_key_id: 'verixa-sig',
      generated_at: '2026-05-10T11:43:00Z',
    };
    const { client, calls } = makeClient([{ status: 200, body }]);
    await client.generateDossier({
      auditId: 'aaaa1111-2222-3333-4444-555555555555',
    });
    const sent = JSON.parse(firstCall(calls).init?.body as string) as {
      action_summary: string;
    };
    expect(sent.action_summary).toBe('');
  });

  it('passes through action_summary when supplied', async () => {
    const body: DossierGenerateResponse = {
      dossier_id: 'dddd1111-2222-3333-4444-555555555555',
      audit_id: 'aaaa1111-2222-3333-4444-555555555555',
      signing_key_id: 'verixa-sig',
      generated_at: '2026-05-10T11:43:00Z',
    };
    const { client, calls } = makeClient([{ status: 200, body }]);
    await client.generateDossier({
      auditId: 'aaaa1111-2222-3333-4444-555555555555',
      actionSummary: 'loan officer approved transfer',
    });
    const sent = JSON.parse(firstCall(calls).init?.body as string) as {
      action_summary: string;
    };
    expect(sent.action_summary).toBe('loan officer approved transfer');
  });
});

describe('ApiClient.getDossier', () => {
  it('embeds dossier_id in the URL path', async () => {
    const body: DossierGetResponse = {
      dossier_id: 'dddd1111-2222-3333-4444-555555555555',
      audit_id: 'aaaa1111-2222-3333-4444-555555555555',
      manifest: {} as DossierGetResponse['manifest'],
      signature_hex: 'a'.repeat(128),
      public_key_hex: 'b'.repeat(64),
    };
    const { client, calls } = makeClient([{ status: 200, body }]);
    await client.getDossier('dddd1111-2222-3333-4444-555555555555');
    expect(firstCall(calls).url).toContain(
      '/v1/control/dossier/dddd1111-2222-3333-4444-555555555555',
    );
  });
});

describe('ApiError handling', () => {
  it('throws ApiError with parsed body on non-2xx + JSON error body', async () => {
    const { client } = makeClient([
      {
        status: 404,
        body: { error: 'audit_not_found', message: 'no such audit_id' },
      },
    ]);
    await expect(client.replay('not-a-real-uuid')).rejects.toMatchObject({
      name: 'ApiError',
      status: 404,
      message: 'no such audit_id',
    });
  });

  it('throws ApiError with body=null when response is not JSON', async () => {
    const { client } = makeClient([
      { status: 500, body: 'plaintext gateway error not JSON' },
    ]);
    try {
      await client.listWorkflows();
      expect.fail('should have thrown');
    } catch (e) {
      expect(e).toBeInstanceOf(ApiError);
      const err = e as ApiError;
      expect(err.status).toBe(500);
      expect(err.body).toBeNull();
      expect(err.message).toContain('HTTP 500');
    }
  });

  it('uses generic message when error body has no message field', async () => {
    const { client } = makeClient([
      { status: 400, body: { error: 'invalid' } },
    ]);
    try {
      await client.listWorkflows();
      expect.fail('should have thrown');
    } catch (e) {
      const err = e as ApiError;
      expect(err.message).toContain('HTTP 400');
    }
  });
});
