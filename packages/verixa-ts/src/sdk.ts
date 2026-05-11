import {
  type AgentRegisterResponse,
  type AuditQueryResponse,
  type DossierGenerateResponse,
  type DossierGetResponse,
  type ReplayResponse,
  type ToolRegisterResponse,
  type WebhookDeliveryListResponse,
  type WebhookSubscriptionListResponse,
  type WebhookSubscriptionSummary,
  type WorkflowListResponse,
  type WorkflowRegisterResponse,
  parseAgentRegisterResponse,
  parseAuditQueryResponse,
  parseDossierGenerateResponse,
  parseDossierGetResponse,
  parseReplayResponse,
  parseToolRegisterResponse,
  parseWebhookDeliveryListResponse,
  parseWebhookSubscriptionListResponse,
  parseWebhookSubscriptionSummary,
  parseWorkflowListResponse,
  parseWorkflowRegisterResponse,
} from './envelopes.js';

/**
 * CP-51 -- Verixa TypeScript SDK (alpha): async client for Control Plane API.
 *
 * Closes Phase-1 carry-forward "verixa-ts SDK to npm". Mirrors the
 * `verixa.sdk` Python SDK from CP-50. Uses Node 20+ built-in `fetch`
 * (no extra dependencies for the SDK itself).
 *
 * Usage:
 *
 *     import { VerixaClient } from '@verixa/ts';
 *     const client = new VerixaClient({ baseUrl: 'https://verixa.acme.com' });
 *     const wf = await client.workflows.register({
 *       name: 'payments',
 *       ownerTenantId: '...uuid...',
 *     });
 *
 * Phase-0 deliverable (this commit):
 *
 *   - `VerixaClient`               top-level client
 *   - `VerixaError`                base exception
 *   - `VerixaHttpError`            HTTP non-2xx (carries status + body)
 *   - `VerixaConnectionError`      transport failures
 *   - Resource clients grouped by domain (workflows, agents, tools,
 *     audit, replay, dossier, bundles, webhooks)
 *
 * Phase-1+ adds: retry-with-exponential-backoff for 5xx, mTLS via
 * Node tls.connect, webhook receiver helper for inbound signatures,
 * pagination iterator, extracted shared envelope types so the SDK
 * returns typed objects instead of `unknown`.
 *
 * Design choices match CP-50 Python: async by default, validates base
 * URL scheme, optional Bearer auth via apiKey, strips trailing slash,
 * never puts secrets in query strings. The TS surface uses camelCase
 * field names; the wire format remains snake_case to match the Python
 * envelopes (mapping happens inside each request method).
 */

// ---------------------------------------------------------------------------
// Exceptions
// ---------------------------------------------------------------------------

export class VerixaError extends Error {
  override name = 'VerixaError';
}

export class VerixaHttpError extends VerixaError {
  override name = 'VerixaHttpError';

  constructor(
    public readonly statusCode: number,
    public readonly body: unknown,
    public readonly url: string,
  ) {
    super(`Verixa HTTP ${statusCode} at ${url}: ${JSON.stringify(body)}`);
  }
}

export class VerixaConnectionError extends VerixaError {
  override name = 'VerixaConnectionError';

  constructor(
    public readonly url: string,
    public readonly cause: unknown,
  ) {
    const causeName = cause instanceof Error ? cause.constructor.name : 'Error';
    const causeMsg = cause instanceof Error ? cause.message : String(cause);
    super(`Verixa transport error at ${url}: ${causeName}: ${causeMsg}`);
  }
}

// ---------------------------------------------------------------------------
// Internal helpers
// ---------------------------------------------------------------------------

/**
 * Build a Fetch implementation. Production uses globalThis.fetch (Node 20+).
 * Tests inject a mock so we never make real network calls.
 */
export type FetchLike = typeof fetch;

interface RequestOptions {
  method: string;
  path: string;
  body?: unknown;
  params?: Record<string, string>;
  headers?: Record<string, string>;
}

interface InternalRequestConfig {
  baseUrl: string;
  defaultHeaders: Record<string, string>;
  fetchImpl: FetchLike;
}

function buildUrl(
  baseUrl: string,
  path: string,
  params?: Record<string, string>,
): string {
  let url = `${baseUrl}${path}`;
  if (params && Object.keys(params).length > 0) {
    const search = new URLSearchParams(params);
    url = `${url}?${search.toString()}`;
  }
  return url;
}

async function parseBody(response: Response): Promise<unknown> {
  const text = await response.text();
  if (text.length === 0) {
    return null;
  }
  try {
    return JSON.parse(text);
  } catch {
    return text;
  }
}

async function checkResponse(response: Response): Promise<void> {
  if (response.status >= 200 && response.status < 300) {
    return;
  }
  const body = await parseBody(response);
  throw new VerixaHttpError(response.status, body, response.url);
}

async function requestJson<T = unknown>(
  config: InternalRequestConfig,
  opts: RequestOptions,
): Promise<T> {
  const url = buildUrl(config.baseUrl, opts.path, opts.params);
  const init: RequestInit = {
    method: opts.method,
    headers: { ...config.defaultHeaders, ...(opts.headers ?? {}) },
  };
  if (opts.body !== undefined) {
    init.body = JSON.stringify(opts.body);
  }
  let response: Response;
  try {
    response = await config.fetchImpl(url, init);
  } catch (cause) {
    throw new VerixaConnectionError(url, cause);
  }
  await checkResponse(response);
  return (await parseBody(response)) as T;
}

// ---------------------------------------------------------------------------
// Resource clients
// ---------------------------------------------------------------------------

/**
 * CP-70: kwargs for WorkflowsClient.register matching the server-side
 * WorkflowRegisterRequest exactly. The CP-51 SDK shipped with
 * `ownerTenantId` which the server's `extra: 'forbid'` schema
 * rejects (tenant is inferred from auth context). Now uses
 * `description` (default empty string), `sector` (default `generic`),
 * `riskThresholdEscalate` (default 0.50; float in [0, 1]).
 */
interface WorkflowRegisterArgs {
  name: string;
  description?: string;
  sector?: string;
  riskThresholdEscalate?: number;
}

export class WorkflowsClient {
  constructor(private readonly config: InternalRequestConfig) {}

  // CP-70: function overloads for opt-in typed return.
  // returnTyped: true -> typed envelope; returnTyped: false | omitted -> unknown.
  async register(
    args: WorkflowRegisterArgs & { returnTyped: true },
  ): Promise<WorkflowRegisterResponse>;
  async register(
    args: WorkflowRegisterArgs & { returnTyped?: false },
  ): Promise<unknown>;
  async register(
    args: WorkflowRegisterArgs & { returnTyped?: boolean },
  ): Promise<unknown | WorkflowRegisterResponse> {
    const data = await requestJson(this.config, {
      method: 'POST',
      path: '/v1/control/workflows',
      body: {
        name: args.name,
        description: args.description ?? '',
        sector: args.sector ?? 'generic',
        risk_threshold_escalate: args.riskThresholdEscalate ?? 0.5,
      },
    });
    if (args.returnTyped === true) {
      return parseWorkflowRegisterResponse(data);
    }
    return data;
  }

  // CP-70: list overloads
  async list(opts: { returnTyped: true }): Promise<WorkflowListResponse>;
  async list(opts?: { returnTyped?: false }): Promise<unknown>;
  async list(
    opts?: { returnTyped?: boolean },
  ): Promise<unknown | WorkflowListResponse> {
    const data = await requestJson(this.config, {
      method: 'GET',
      path: '/v1/control/workflows',
    });
    if (opts?.returnTyped === true) {
      return parseWorkflowListResponse(data);
    }
    return data;
  }
}

/**
 * CP-72: kwargs for AgentsClient.register matching the server-side
 * AgentRegisterRequest exactly. The CP-51 SDK shipped with
 * workflowId + name + modelProvider + modelName which the server's
 * extra='forbid' schema rejects. Server accepts workflowId +
 * spiffeId (1..512 chars, SPIFFE identity; Phase-0 bypasses
 * verification but the field is recorded for CP-53 mTLS forward
 * compatibility) + role (1..128 chars) + description (default '').
 */
interface AgentRegisterArgs {
  workflowId: string;
  spiffeId: string;
  role: string;
  description?: string;
}

export class AgentsClient {
  constructor(private readonly config: InternalRequestConfig) {}

  // CP-72 function overloads for opt-in typed return.
  async register(
    args: AgentRegisterArgs & { returnTyped: true },
  ): Promise<AgentRegisterResponse>;
  async register(
    args: AgentRegisterArgs & { returnTyped?: false },
  ): Promise<unknown>;
  async register(
    args: AgentRegisterArgs & { returnTyped?: boolean },
  ): Promise<unknown | AgentRegisterResponse> {
    const data = await requestJson(this.config, {
      method: 'POST',
      path: '/v1/control/agents',
      body: {
        workflow_id: args.workflowId,
        spiffe_id: args.spiffeId,
        role: args.role,
        description: args.description ?? '',
      },
    });
    if (args.returnTyped === true) {
      return parseAgentRegisterResponse(data);
    }
    return data;
  }
}

/**
 * CP-74: kwargs for ToolsClient.register matching server-side
 * ToolRegisterRequest. The CP-51 SDK shipped workflowId + name +
 * schema which the server's extra='forbid' schema rejects.
 * Tools are NOT workflow-scoped on the server -- they belong to the
 * tenant and allowedWorkflowIds is the per-tool ACL (empty = any
 * workflow; non-empty = restricted to those workflows). The schema
 * field is not part of the wire format; per-tool JSON schema lives
 * on the agent side.
 */
interface ToolRegisterArgs {
  name: string;
  description?: string;
  isActive?: boolean;
  allowedWorkflowIds?: string[];
}

export class ToolsClient {
  constructor(private readonly config: InternalRequestConfig) {}

  // CP-74 function overloads for opt-in typed return.
  async register(
    args: ToolRegisterArgs & { returnTyped: true },
  ): Promise<ToolRegisterResponse>;
  async register(
    args: ToolRegisterArgs & { returnTyped?: false },
  ): Promise<unknown>;
  async register(
    args: ToolRegisterArgs & { returnTyped?: boolean },
  ): Promise<unknown | ToolRegisterResponse> {
    const data = await requestJson(this.config, {
      method: 'POST',
      path: '/v1/control/tools',
      body: {
        name: args.name,
        description: args.description ?? '',
        is_active: args.isActive ?? true,
        allowed_workflow_ids: args.allowedWorkflowIds ?? [],
      },
    });
    if (args.returnTyped === true) {
      return parseToolRegisterResponse(data);
    }
    return data;
  }
}

/**
 * CP-82: kwargs for AuditClient.query. No wire-format fix needed:
 * the CP-51 request shape was already correct -- server route uses
 * Query(..., alias='from') + Query(..., alias='to') so wire keys
 * are literally 'from' and 'to'. Pure addition of typed-return path
 * mirroring Python CP-81.
 */
interface AuditQueryArgs {
  workflowId: string;
  /** ISO-8601 timestamp string. */
  fromTimestamp: string;
  /** ISO-8601 timestamp string. */
  toTimestamp: string;
}

export class AuditClient {
  constructor(private readonly config: InternalRequestConfig) {}

  // CP-82 query() function overloads for opt-in typed return.
  async query(
    args: AuditQueryArgs & { returnTyped: true },
  ): Promise<AuditQueryResponse>;
  async query(
    args: AuditQueryArgs & { returnTyped?: false },
  ): Promise<unknown>;
  async query(
    args: AuditQueryArgs & { returnTyped?: boolean },
  ): Promise<unknown | AuditQueryResponse> {
    const data = await requestJson(this.config, {
      method: 'GET',
      path: '/v1/control/audit',
      params: {
        workflow_id: args.workflowId,
        from: args.fromTimestamp,
        to: args.toTimestamp,
      },
    });
    if (args.returnTyped === true) {
      return parseAuditQueryResponse(data);
    }
    return data;
  }
}

/**
 * CP-78: ReplayClient.get opt-in returnTyped overload. No wire-format
 * fix needed (audit_id was already correct in CP-51). Mirrors Python
 * CP-77.
 */
export class ReplayClient {
  constructor(private readonly config: InternalRequestConfig) {}

  async get(
    args: { auditId: string; returnTyped: true },
  ): Promise<ReplayResponse>;
  async get(
    args: { auditId: string; returnTyped?: false },
  ): Promise<unknown>;
  async get(
    args: { auditId: string; returnTyped?: boolean },
  ): Promise<unknown | ReplayResponse> {
    const data = await requestJson(this.config, {
      method: 'POST',
      path: '/v1/control/replay',
      body: { audit_id: args.auditId },
    });
    if (args.returnTyped === true) {
      return parseReplayResponse(data);
    }
    return data;
  }
}

/**
 * CP-76: kwargs for DossierClient.generate matching server-side
 * DossierGenerateRequest. The CP-51 SDK shipped auditId + tenantId
 * which the server's extra='forbid' schema rejects (tenant is
 * inferred from auth context, same as workflow registration).
 * Server accepts audit_id + action_summary (default '', max 2000
 * chars; auditor-readable summary; empty triggers system-generated).
 */
interface DossierGenerateArgs {
  auditId: string;
  actionSummary?: string;
}

export class DossierClient {
  constructor(private readonly config: InternalRequestConfig) {}

  // CP-76 generate() function overloads for opt-in typed return.
  async generate(
    args: DossierGenerateArgs & { returnTyped: true },
  ): Promise<DossierGenerateResponse>;
  async generate(
    args: DossierGenerateArgs & { returnTyped?: false },
  ): Promise<unknown>;
  async generate(
    args: DossierGenerateArgs & { returnTyped?: boolean },
  ): Promise<unknown | DossierGenerateResponse> {
    const data = await requestJson(this.config, {
      method: 'POST',
      path: '/v1/control/dossier',
      body: {
        audit_id: args.auditId,
        action_summary: args.actionSummary ?? '',
      },
    });
    if (args.returnTyped === true) {
      return parseDossierGenerateResponse(data);
    }
    return data;
  }

  // CP-76 get() function overloads for opt-in typed return.
  async get(
    dossierId: string,
    opts: { returnTyped: true },
  ): Promise<DossierGetResponse>;
  async get(
    dossierId: string,
    opts?: { returnTyped?: false },
  ): Promise<unknown>;
  async get(
    dossierId: string,
    opts?: { returnTyped?: boolean },
  ): Promise<unknown | DossierGetResponse> {
    const data = await requestJson(this.config, {
      method: 'GET',
      path: `/v1/control/dossier/${dossierId}`,
    });
    if (opts?.returnTyped === true) {
      return parseDossierGetResponse(data);
    }
    return data;
  }
}

export class BundlesClient {
  constructor(private readonly config: InternalRequestConfig) {}

  async list(): Promise<unknown> {
    return requestJson(this.config, {
      method: 'GET',
      path: '/v1/control/policy/bundles',
    });
  }

  /**
   * Fetch a signed OPA bundle. Returns `{ body, etag }` on 200, or `null`
   * on 304 cache-hit. Throws VerixaHttpError on 400/404/409/503.
   */
  async fetch(
    name: string,
    options?: { ifNoneMatch?: string },
  ): Promise<{ body: Uint8Array; etag: string } | null> {
    const url = buildUrl(
      this.config.baseUrl,
      `/v1/control/policy/bundles/${name}`,
    );
    const headers: Record<string, string> = { ...this.config.defaultHeaders };
    if (options?.ifNoneMatch !== undefined) {
      headers['If-None-Match'] = options.ifNoneMatch;
    }
    let response: Response;
    try {
      response = await this.config.fetchImpl(url, { method: 'GET', headers });
    } catch (cause) {
      throw new VerixaConnectionError(url, cause);
    }
    if (response.status === 304) {
      return null;
    }
    await checkResponse(response);
    const buf = await response.arrayBuffer();
    return {
      body: new Uint8Array(buf),
      etag: response.headers.get('etag') ?? '',
    };
  }
}

/**
 * CP-80: kwargs for WebhooksClient methods. Request shapes were
 * already correct in CP-51; this CP adds opt-in returnTyped
 * overloads mirroring Python CP-79.
 */
interface WebhookSubscribeArgs {
  tenantId: string;
  url: string;
  eventTypes: string[];
  signingKeyId: string;
}

export class WebhooksClient {
  constructor(private readonly config: InternalRequestConfig) {}

  // CP-80 subscribe() overloads.
  async subscribe(
    args: WebhookSubscribeArgs & { returnTyped: true },
  ): Promise<WebhookSubscriptionSummary>;
  async subscribe(
    args: WebhookSubscribeArgs & { returnTyped?: false },
  ): Promise<unknown>;
  async subscribe(
    args: WebhookSubscribeArgs & { returnTyped?: boolean },
  ): Promise<unknown | WebhookSubscriptionSummary> {
    const data = await requestJson(this.config, {
      method: 'POST',
      path: '/v1/control/webhooks/subscriptions',
      body: {
        tenant_id: args.tenantId,
        url: args.url,
        event_types: args.eventTypes,
        signing_key_id: args.signingKeyId,
      },
    });
    if (args.returnTyped === true) {
      return parseWebhookSubscriptionSummary(data);
    }
    return data;
  }

  // CP-80 listSubscriptions() overloads.
  async listSubscriptions(
    args: { tenantId?: string; returnTyped: true },
  ): Promise<WebhookSubscriptionListResponse>;
  async listSubscriptions(
    args?: { tenantId?: string; returnTyped?: false },
  ): Promise<unknown>;
  async listSubscriptions(
    args?: { tenantId?: string; returnTyped?: boolean },
  ): Promise<unknown | WebhookSubscriptionListResponse> {
    const params: Record<string, string> = {};
    if (args?.tenantId !== undefined) {
      params['tenant_id'] = args.tenantId;
    }
    const data = await requestJson(this.config, {
      method: 'GET',
      path: '/v1/control/webhooks/subscriptions',
      params,
    });
    if (args?.returnTyped === true) {
      return parseWebhookSubscriptionListResponse(data);
    }
    return data;
  }

  // CP-80 recentDeliveries() overloads.
  async recentDeliveries(
    args: { limit?: number; returnTyped: true },
  ): Promise<WebhookDeliveryListResponse>;
  async recentDeliveries(
    args?: { limit?: number; returnTyped?: false },
  ): Promise<unknown>;
  async recentDeliveries(
    args?: { limit?: number; returnTyped?: boolean },
  ): Promise<unknown | WebhookDeliveryListResponse> {
    const limit = args?.limit ?? 50;
    const data = await requestJson(this.config, {
      method: 'GET',
      path: '/v1/control/webhooks/deliveries',
      params: { limit: String(limit) },
    });
    if (args?.returnTyped === true) {
      return parseWebhookDeliveryListResponse(data);
    }
    return data;
  }
}

// ---------------------------------------------------------------------------
// Top-level VerixaClient
// ---------------------------------------------------------------------------

export interface VerixaClientOptions {
  baseUrl: string;
  apiKey?: string;
  /** Inject a custom fetch for testing. Defaults to globalThis.fetch. */
  fetchImpl?: FetchLike;
}

export class VerixaClient {
  readonly workflows: WorkflowsClient;
  readonly agents: AgentsClient;
  readonly tools: ToolsClient;
  readonly audit: AuditClient;
  readonly replay: ReplayClient;
  readonly dossier: DossierClient;
  readonly bundles: BundlesClient;
  readonly webhooks: WebhooksClient;

  constructor(opts: VerixaClientOptions) {
    if (!opts.baseUrl.startsWith('http://') && !opts.baseUrl.startsWith('https://')) {
      throw new Error(
        `baseUrl must start with http:// or https://; got ${opts.baseUrl}`,
      );
    }
    const baseUrl = opts.baseUrl.replace(/\/+$/, '');
    const defaultHeaders: Record<string, string> = {
      'User-Agent': 'verixa-ts/0.2.0',
      Accept: 'application/json',
      'Content-Type': 'application/json',
    };
    if (opts.apiKey !== undefined) {
      defaultHeaders['Authorization'] = `Bearer ${opts.apiKey}`;
    }
    const fetchImpl: FetchLike = opts.fetchImpl ?? globalThis.fetch.bind(globalThis);
    const config: InternalRequestConfig = { baseUrl, defaultHeaders, fetchImpl };
    this.workflows = new WorkflowsClient(config);
    this.agents = new AgentsClient(config);
    this.tools = new ToolsClient(config);
    this.audit = new AuditClient(config);
    this.replay = new ReplayClient(config);
    this.dossier = new DossierClient(config);
    this.bundles = new BundlesClient(config);
    this.webhooks = new WebhooksClient(config);
  }
}
