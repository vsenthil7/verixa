/**
 * Verixa Control Plane API client + types (CP-15.1).
 *
 * Mirrors the FastAPI envelopes from
 * `apps/control-plane-api/verixa_control_plane/envelopes.py`. Pure
 * fetch-based; no runtime deps beyond `fetch` (Next.js 14 polyfills
 * it on the server).
 *
 * The client is a small factory: `createApiClient({ baseUrl })`.
 * Pages call `client.listWorkflows()` etc. Network errors and
 * non-200 responses are wrapped into `ApiError` so call-sites can
 * `try/catch` once. Pure-function design keeps it trivially testable.
 */

// ---------------------------------------------------------------------------
// Types — mirror the Python envelopes exactly
// ---------------------------------------------------------------------------

export interface WorkflowSummary {
  workflow_id: string;
  name: string;
  sector: string;
  risk_threshold_escalate: number;
  agent_count: number;
  created_at: string;
}

export interface WorkflowListResponse {
  workflows: WorkflowSummary[];
  total: number;
}

export interface AuditEntry {
  audit_id: string;
  workflow_id: string;
  decision: 'allow' | 'deny' | 'escalate';
  risk_score: number;
  risk_classification: 'low' | 'medium' | 'high' | 'critical';
  triad_invoked: boolean;
  timestamp: string;
}

export interface AuditQueryResponse {
  entries: AuditEntry[];
  total: number;
  workflow_id: string;
  from_timestamp: string;
  to_timestamp: string;
}

export interface RetrievedDocumentDict {
  doc_id: string;
  content_sha256: string;
}

export interface PolicyEvaluationDict {
  package: string;
  decision: string;
  reason: string;
}

export interface TriadVerdictDict {
  reviewer_id: string;
  decision: string;
  confidence: number;
  reasoning: string;
}

export interface TriadCommitmentDict {
  reviewer_id: string;
  sha256_hex: string;
}

export interface TriadReviewDict {
  consensus_kind: string;
  agreed_decision: string | null;
  verdicts: TriadVerdictDict[];
  commitments: TriadCommitmentDict[];
}

export interface ReplayResponse {
  audit_id: string;
  tenant_id: string;
  decision: 'allow' | 'deny' | 'escalate';
  risk_score: number;
  request_envelope: Record<string, unknown>;
  retrieved_documents: RetrievedDocumentDict[];
  tool_io: Record<string, unknown>[];
  policy_evaluations: PolicyEvaluationDict[];
  triad_review: TriadReviewDict | null;
  timestamp_unix_ns: number;
}

export interface DossierGenerateResponse {
  dossier_id: string;
  audit_id: string;
  signing_key_id: string;
  generated_at: string;
}

export interface DossierManifestDict {
  schema_version: number;
  audit_id: string;
  tenant_id: string;
  generated_at_unix_ns: number;
  decision: string;
  risk_score: number;
  risk_classification: string;
  action_summary: string;
  policy_evaluations: PolicyEvaluationDict[];
  triad_consensus: string | null;
  triad_agreed_decision: string | null;
  triad_dissenters: string[];
  retrieved_documents: RetrievedDocumentDict[];
  replay_storage_key: string;
  signing_key_id: string;
}

export interface DossierGetResponse {
  dossier_id: string;
  audit_id: string;
  manifest: DossierManifestDict;
  signature_hex: string;
  public_key_hex: string;
}

export interface ErrorResponse {
  error: string;
  message: string;
  audit_id?: string | null;
}

// ---------------------------------------------------------------------------
// Client
// ---------------------------------------------------------------------------

export class ApiError extends Error {
  public readonly status: number;
  public readonly body: ErrorResponse | null;

  public constructor(
    status: number,
    message: string,
    body: ErrorResponse | null,
  ) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.body = body;
  }
}

export interface ApiClientConfig {
  /**
   * Base URL of the Verixa Control Plane FastAPI service.
   * For local dev: `http://localhost:8001`. For production: a real URL.
   * Trailing slashes are stripped.
   */
  baseUrl: string;
  /**
   * Optional override for `fetch`. Tests inject a mock fetch
   * implementation; production uses the platform `fetch`.
   */
  fetchImpl?: typeof fetch;
}

export interface ApiClient {
  listWorkflows(): Promise<WorkflowListResponse>;
  queryAudit(params: {
    workflowId: string;
    from: string;
    to: string;
  }): Promise<AuditQueryResponse>;
  replay(auditId: string): Promise<ReplayResponse>;
  generateDossier(params: {
    auditId: string;
    actionSummary?: string;
  }): Promise<DossierGenerateResponse>;
  getDossier(dossierId: string): Promise<DossierGetResponse>;
}

/**
 * Build an ApiClient bound to a given base URL.
 *
 * Errors:
 *   - Non-2xx response with a parseable ErrorResponse body →
 *     ApiError with `body` populated.
 *   - Non-2xx response without a parseable body → ApiError with
 *     body=null and a generic message.
 *   - fetch network failure → re-thrown as-is (Next.js handles it).
 */
export function createApiClient(config: ApiClientConfig): ApiClient {
  const baseUrl = config.baseUrl.replace(/\/+$/, '');
  const doFetch = config.fetchImpl ?? fetch;

  async function request<T>(
    path: string,
    init?: RequestInit,
  ): Promise<T> {
    const url = `${baseUrl}${path}`;
    // ``cache: 'no-store'`` opts every call out of Next.js's
    // patched-fetch cache in Server Components. Without this,
    // GET requests with no Authorization header (which is every
    // call from the Phase-0 UI) are cached by default and a
    // stale empty response from the first render of /
    // (potentially mid-seed) persists for the whole dev session.
    // Caught by the CP-21 Playwright suite as a 2/18 failure
    // on a Windows dev box; the diag scripts in _backup/diag_*
    // confirmed the FastAPI returned 3 entries while the SSR'd
    // dashboard rendered "No decisions in the last 30 days".
    const response = await doFetch(url, {
      cache: 'no-store',
      ...init,
      headers: {
        'Content-Type': 'application/json',
        ...(init?.headers ?? {}),
      },
    });
    if (!response.ok) {
      let body: ErrorResponse | null = null;
      try {
        body = (await response.json()) as ErrorResponse;
      } catch {
        body = null;
      }
      throw new ApiError(
        response.status,
        body?.message ?? `HTTP ${response.status} on ${path}`,
        body,
      );
    }
    return (await response.json()) as T;
  }

  return {
    async listWorkflows() {
      return request<WorkflowListResponse>('/v1/control/workflows');
    },

    async queryAudit({ workflowId, from, to }) {
      const qs = new URLSearchParams({
        workflow_id: workflowId,
        from,
        to,
      }).toString();
      return request<AuditQueryResponse>(`/v1/control/audit?${qs}`);
    },

    async replay(auditId) {
      return request<ReplayResponse>('/v1/control/replay', {
        method: 'POST',
        body: JSON.stringify({ audit_id: auditId }),
      });
    },

    async generateDossier({ auditId, actionSummary }) {
      return request<DossierGenerateResponse>('/v1/control/dossier', {
        method: 'POST',
        body: JSON.stringify({
          audit_id: auditId,
          action_summary: actionSummary ?? '',
        }),
      });
    },

    async getDossier(dossierId) {
      return request<DossierGetResponse>(
        `/v1/control/dossier/${dossierId}`,
      );
    },
  };
}
