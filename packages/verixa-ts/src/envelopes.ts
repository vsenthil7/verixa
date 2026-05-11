/**
 * CP-65 -- typed envelope types + parsers for TypeScript SDK response handling.
 *
 * Closes the v0.4.0 roadmap promise from `@verixa/ts` CHANGELOG: customers
 * can opt into typed return values instead of plain `unknown`. Mirrors the
 * Python SDK's verixa.envelopes module (CP-61..CP-64) for cross-language
 * symmetry of the typed-response surface.
 *
 * Design notes:
 *
 *   - Lightweight: plain `readonly` interfaces (no Zod / Pydantic runtime
 *     dep -- customers who use those libs can wrap our unknown responses
 *     themselves).
 *   - Opt-in: existing SDK methods still return `unknown`; new exported
 *     parser functions `parseWorkflowRegisterResponse(data: unknown)` etc.
 *     take an opaque response and return the typed object. The next SDK
 *     MINOR release (v0.2.0) will add `register(..., returnTyped: true)`
 *     overloads; v1.0.0 will flip the default.
 *   - Pinned to wire format: every field name + type here mirrors the
 *     Python SDK envelopes which mirror the server-side envelopes.py
 *     exactly. Property names are camelCase (TS convention); the parser
 *     reads the snake_case wire fields and maps to camelCase output.
 *   - Defensive: each parser throws `InvalidEnvelopeError` with a
 *     `field {name}: ...` prefix so a server returning an unexpected
 *     shape gives a debuggable error rather than `undefined` access.
 *   - Tolerant of EXTRA fields: server-side may add new optional fields
 *     (forward-compat); the parsers ignore them. MISSING required fields
 *     are a hard error.
 *   - Strict invariants: naive datetimes rejected (Verixa requires
 *     TZ-aware everywhere); typeof !== 'boolean' rejected on bool fields
 *     so 0/1/string cannot silently coerce; UUID-like string validation
 *     uses canonical RFC 4122 regex.
 *
 * Subsets shipped:
 *
 *   CP-65 (workflow + audit core; mirrors Python CP-61):
 *     - WorkflowRegisterResponse + parseWorkflowRegisterResponse
 *     - WorkflowSummary + parseWorkflowSummary
 *     - WorkflowListResponse + parseWorkflowListResponse
 *     - AuditEntry + parseAuditEntry
 *     - AuditQueryResponse + parseAuditQueryResponse
 *
 *   CP-66 (registry: agent + tool; mirrors Python CP-62):
 *     - AgentRegisterResponse + parseAgentRegisterResponse
 *     - ToolRegisterResponse + parseToolRegisterResponse
 *
 *   CP-67 (replay + dossier; mirrors Python CP-63):
 *     - ReplayResponse + parseReplayResponse
 *     - DossierGenerateResponse + parseDossierGenerateResponse
 *     - DossierGetResponse + parseDossierGetResponse
 *
 *   CP-68 (webhook -- COMPLETES the typed-response surface;
 *   mirrors Python CP-64):
 *     - WebhookSubscriptionSummary + parser
 *     - WebhookSubscriptionListResponse + parser
 *     - WebhookDeliverySummary + parser
 *     - WebhookDeliveryListResponse + parser
 *
 * The full server-side response envelope set is now mirrored on
 * both Python AND TypeScript SDKs. Next round (Phase-1+) wires
 * opt-in returnTyped:true overloads on resource client methods
 * across both SDKs per the v0.2.0 deprecation timeline.
 */

// ---------------------------------------------------------------------------
// Exception
// ---------------------------------------------------------------------------

export class InvalidEnvelopeError extends Error {
  override readonly name = 'InvalidEnvelopeError';
}

// ---------------------------------------------------------------------------
// Helpers (mirror verixa.envelopes._require / _as_* in Python)
// ---------------------------------------------------------------------------

/** A JSON object (after JSON.parse). */
type JsonRecord = Record<string, unknown>;

function isRecord(value: unknown): value is JsonRecord {
  return (
    typeof value === 'object' &&
    value !== null &&
    !Array.isArray(value) &&
    !(value instanceof Date)
  );
}

function requireField(d: JsonRecord, key: string, name: string): unknown {
  if (!Object.prototype.hasOwnProperty.call(d, key)) {
    throw new InvalidEnvelopeError(
      `field ${name}: missing from response`,
    );
  }
  return d[key];
}

/**
 * Canonical RFC 4122 UUID regex (case-insensitive). Used to validate
 * string-form UUIDs without taking a runtime dependency on a uuid
 * library. The SDK returns UUIDs as strings (not Buffer / no `uuid`
 * package) so customer code can pass them straight back to the server.
 */
const UUID_RE =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

function asUuid(value: unknown, name: string): string {
  if (typeof value !== 'string') {
    throw new InvalidEnvelopeError(
      `field ${name}: expected uuid string, got ${typeof value}`,
    );
  }
  if (!UUID_RE.test(value)) {
    throw new InvalidEnvelopeError(
      `field ${name}: ${JSON.stringify(value)} is not a valid UUID`,
    );
  }
  return value.toLowerCase();
}

/**
 * Parse an ISO-8601 timestamp into a Date. Server emits ISO-8601 with
 * Z suffix or explicit offset; both are accepted by Date(string). We
 * do NOT accept naive timestamps (no TZ); the server-side audit ledger
 * requires every entry have a TZ + we propagate that invariant.
 *
 * Naive detection: Date(s) silently treats naive strings as LOCAL time;
 * we detect by checking the original string for a TZ marker (Z or +/-HH:MM).
 */
function asDateTime(value: unknown, name: string): Date {
  if (value instanceof Date) {
    if (Number.isNaN(value.getTime())) {
      throw new InvalidEnvelopeError(
        `field ${name}: invalid Date object`,
      );
    }
    // Date objects in JS are always TZ-aware (Unix epoch); accept.
    return value;
  }
  if (typeof value !== 'string') {
    throw new InvalidEnvelopeError(
      `field ${name}: expected ISO-8601 string, got ${typeof value}`,
    );
  }
  // Detect naive timestamps: no 'Z', no '+HH:MM', no '-HH:MM' at end.
  const hasTz = /([Zz]|[+-]\d{2}:?\d{2})$/.test(value);
  if (!hasTz) {
    throw new InvalidEnvelopeError(
      `field ${name}: ${JSON.stringify(value)} is naive (no tzinfo); ` +
        `Verixa requires TZ-aware timestamps`,
    );
  }
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    throw new InvalidEnvelopeError(
      `field ${name}: ${JSON.stringify(value)} is not a valid ISO-8601 timestamp`,
    );
  }
  return parsed;
}

function asString(value: unknown, name: string): string {
  if (typeof value !== 'string') {
    throw new InvalidEnvelopeError(
      `field ${name}: expected string, got ${typeof value}`,
    );
  }
  return value;
}

function asInt(value: unknown, name: string): number {
  // boolean is excluded explicitly even though typeof is 'boolean' not
  // 'number'; we also reject non-integer floats so 0.5 doesn't silently
  // become a count.
  if (typeof value === 'boolean') {
    throw new InvalidEnvelopeError(
      `field ${name}: expected int, got boolean`,
    );
  }
  if (typeof value !== 'number') {
    throw new InvalidEnvelopeError(
      `field ${name}: expected int, got ${typeof value}`,
    );
  }
  if (!Number.isInteger(value)) {
    throw new InvalidEnvelopeError(
      `field ${name}: expected int, got non-integer number`,
    );
  }
  return value;
}

function asFloat(value: unknown, name: string): number {
  if (typeof value === 'boolean') {
    throw new InvalidEnvelopeError(
      `field ${name}: expected number, got boolean`,
    );
  }
  if (typeof value !== 'number') {
    throw new InvalidEnvelopeError(
      `field ${name}: expected number, got ${typeof value}`,
    );
  }
  if (!Number.isFinite(value)) {
    throw new InvalidEnvelopeError(
      `field ${name}: expected finite number, got ${value}`,
    );
  }
  return value;
}

function asBool(value: unknown, name: string): boolean {
  if (typeof value !== 'boolean') {
    throw new InvalidEnvelopeError(
      `field ${name}: expected bool, got ${typeof value}`,
    );
  }
  return value;
}

/**
 * Parse an array of UUID strings into an immutable frozen array.
 * Per-element validation with index-prefixed field name (e.g.
 * `allowed_workflow_ids[1]`) for debuggability. Mirrors Python
 * verixa.envelopes._as_uuid_list.
 */
function asUuidList(value: unknown, name: string): readonly string[] {
  if (!Array.isArray(value)) {
    throw new InvalidEnvelopeError(
      `field ${name}: expected array of uuids, got ${typeof value}`,
    );
  }
  const out: string[] = value.map((v, i) => asUuid(v, `${name}[${i}]`));
  return Object.freeze(out);
}

/**
 * Strict record/object check; rejects null, array, Date, primitives.
 * Used for nested envelope dicts the SDK passes through opaquely
 * (the customer can drill into them or wrap with their own model).
 * Mirrors Python verixa.envelopes._as_dict.
 */
function asUnknownRecord(
  value: unknown,
  name: string,
): Record<string, unknown> {
  if (!isRecord(value)) {
    throw new InvalidEnvelopeError(
      `field ${name}: expected dict, got ${typeof value}`,
    );
  }
  return value;
}

/** Like asUnknownRecord but accepts null (for optional nested envelopes). */
function asOptionalRecord(
  value: unknown,
  name: string,
): Record<string, unknown> | null {
  if (value === null || value === undefined) {
    return null;
  }
  return asUnknownRecord(value, name);
}

/**
 * Parse an array-of-dicts into an immutable frozen array of plain
 * record objects. Inner records pass through unparsed (each is opaque
 * to the SDK surface; e.g. retrieved_documents is an array of
 * {doc_id, content_sha256} items but ReplayResponse exposes them as
 * plain records). Index-prefixed field name on per-element failure
 * (e.g. `retrieved_documents[1]`) for debuggability. Mirrors Python
 * verixa.envelopes._as_list_of_dict.
 */
function asListOfRecord(
  value: unknown,
  name: string,
): readonly Record<string, unknown>[] {
  if (!Array.isArray(value)) {
    throw new InvalidEnvelopeError(
      `field ${name}: expected array of dicts, got ${typeof value}`,
    );
  }
  const out: Record<string, unknown>[] = value.map((v, i) => {
    if (!isRecord(v)) {
      throw new InvalidEnvelopeError(
        `field ${name}[${i}]: expected dict, got ${typeof v}`,
      );
    }
    return v;
  });
  return Object.freeze(out);
}

// ---------------------------------------------------------------------------
// Workflow envelopes (CP-65 batch 1; mirrors Python CP-61)
// ---------------------------------------------------------------------------

/**
 * Server response to `POST /v1/control/workflows`.
 * Matches apps/control-plane-api/.../envelopes.py:WorkflowRegisterResponse.
 */
export interface WorkflowRegisterResponse {
  readonly workflowId: string;
  readonly name: string;
  readonly sector: string;
  readonly createdAt: Date;
}

export function parseWorkflowRegisterResponse(
  data: unknown,
): WorkflowRegisterResponse {
  if (!isRecord(data)) {
    throw new InvalidEnvelopeError(
      `expected dict for WorkflowRegisterResponse, got ${typeof data}`,
    );
  }
  return {
    workflowId: asUuid(
      requireField(data, 'workflow_id', 'workflow_id'),
      'workflow_id',
    ),
    name: asString(requireField(data, 'name', 'name'), 'name'),
    sector: asString(requireField(data, 'sector', 'sector'), 'sector'),
    createdAt: asDateTime(
      requireField(data, 'created_at', 'created_at'),
      'created_at',
    ),
  };
}

/**
 * One workflow entry in a list response.
 * Matches server-side WorkflowSummary: + risk_threshold_escalate + agent_count.
 */
export interface WorkflowSummary {
  readonly workflowId: string;
  readonly name: string;
  readonly sector: string;
  readonly riskThresholdEscalate: number;
  readonly agentCount: number;
  readonly createdAt: Date;
}

export function parseWorkflowSummary(data: unknown): WorkflowSummary {
  if (!isRecord(data)) {
    throw new InvalidEnvelopeError(
      `expected dict for WorkflowSummary, got ${typeof data}`,
    );
  }
  return {
    workflowId: asUuid(
      requireField(data, 'workflow_id', 'workflow_id'),
      'workflow_id',
    ),
    name: asString(requireField(data, 'name', 'name'), 'name'),
    sector: asString(requireField(data, 'sector', 'sector'), 'sector'),
    riskThresholdEscalate: asFloat(
      requireField(
        data,
        'risk_threshold_escalate',
        'risk_threshold_escalate',
      ),
      'risk_threshold_escalate',
    ),
    agentCount: asInt(
      requireField(data, 'agent_count', 'agent_count'),
      'agent_count',
    ),
    createdAt: asDateTime(
      requireField(data, 'created_at', 'created_at'),
      'created_at',
    ),
  };
}

/** Server response to `GET /v1/control/workflows`. */
export interface WorkflowListResponse {
  readonly workflows: readonly WorkflowSummary[];
  readonly total: number;
}

export function parseWorkflowListResponse(
  data: unknown,
): WorkflowListResponse {
  if (!isRecord(data)) {
    throw new InvalidEnvelopeError(
      `expected dict for WorkflowListResponse, got ${typeof data}`,
    );
  }
  const items = requireField(data, 'workflows', 'workflows');
  if (!Array.isArray(items)) {
    throw new InvalidEnvelopeError(
      `field workflows: expected array, got ${typeof items}`,
    );
  }
  const parsed: WorkflowSummary[] = items.map((item) =>
    parseWorkflowSummary(item),
  );
  return {
    workflows: Object.freeze(parsed),
    total: asInt(requireField(data, 'total', 'total'), 'total'),
  };
}

// ---------------------------------------------------------------------------
// Audit envelopes (CP-65 batch 1; mirrors Python CP-61)
// ---------------------------------------------------------------------------

/**
 * One entry from the audit ledger as exposed by the Control Plane API.
 * Redacted view; not the full ledger row (which carries hash chain
 * links + Ed25519 signatures; those are in ReplayResponse).
 */
export interface AuditEntry {
  readonly auditId: string;
  readonly workflowId: string;
  readonly decision: string;
  readonly riskScore: number;
  readonly riskClassification: string;
  readonly triadInvoked: boolean;
  readonly timestamp: Date;
}

export function parseAuditEntry(data: unknown): AuditEntry {
  if (!isRecord(data)) {
    throw new InvalidEnvelopeError(
      `expected dict for AuditEntry, got ${typeof data}`,
    );
  }
  return {
    auditId: asUuid(
      requireField(data, 'audit_id', 'audit_id'),
      'audit_id',
    ),
    workflowId: asUuid(
      requireField(data, 'workflow_id', 'workflow_id'),
      'workflow_id',
    ),
    decision: asString(
      requireField(data, 'decision', 'decision'),
      'decision',
    ),
    riskScore: asFloat(
      requireField(data, 'risk_score', 'risk_score'),
      'risk_score',
    ),
    riskClassification: asString(
      requireField(data, 'risk_classification', 'risk_classification'),
      'risk_classification',
    ),
    triadInvoked: asBool(
      requireField(data, 'triad_invoked', 'triad_invoked'),
      'triad_invoked',
    ),
    timestamp: asDateTime(
      requireField(data, 'timestamp', 'timestamp'),
      'timestamp',
    ),
  };
}

/** Server response to `GET /v1/control/audit`. */
export interface AuditQueryResponse {
  readonly entries: readonly AuditEntry[];
  readonly total: number;
  readonly workflowId: string;
  readonly fromTimestamp: Date;
  readonly toTimestamp: Date;
}

export function parseAuditQueryResponse(
  data: unknown,
): AuditQueryResponse {
  if (!isRecord(data)) {
    throw new InvalidEnvelopeError(
      `expected dict for AuditQueryResponse, got ${typeof data}`,
    );
  }
  const items = requireField(data, 'entries', 'entries');
  if (!Array.isArray(items)) {
    throw new InvalidEnvelopeError(
      `field entries: expected array, got ${typeof items}`,
    );
  }
  const parsed: AuditEntry[] = items.map((item) => parseAuditEntry(item));
  return {
    entries: Object.freeze(parsed),
    total: asInt(requireField(data, 'total', 'total'), 'total'),
    workflowId: asUuid(
      requireField(data, 'workflow_id', 'workflow_id'),
      'workflow_id',
    ),
    fromTimestamp: asDateTime(
      requireField(data, 'from_timestamp', 'from_timestamp'),
      'from_timestamp',
    ),
    toTimestamp: asDateTime(
      requireField(data, 'to_timestamp', 'to_timestamp'),
      'to_timestamp',
    ),
  };
}

// ---------------------------------------------------------------------------
// Registry envelopes (CP-66; mirrors Python CP-62 -- agent + tool)
// ---------------------------------------------------------------------------

/**
 * Server response to `POST /v1/control/agents`.
 *
 * Matches server-side AgentRegisterResponse: agent_id + workflow_id +
 * spiffe_id + role + created_at. The agent is an operational entity
 * acting under the workflow; spiffe_id is the SPIFFE identity
 * (Phase-0 bypasses SPIFFE verification; the field is recorded for
 * forward compatibility with the CP-53 mTLS Protocol surface).
 */
export interface AgentRegisterResponse {
  readonly agentId: string;
  readonly workflowId: string;
  readonly spiffeId: string;
  readonly role: string;
  readonly createdAt: Date;
}

export function parseAgentRegisterResponse(
  data: unknown,
): AgentRegisterResponse {
  if (!isRecord(data)) {
    throw new InvalidEnvelopeError(
      `expected dict for AgentRegisterResponse, got ${typeof data}`,
    );
  }
  return {
    agentId: asUuid(
      requireField(data, 'agent_id', 'agent_id'),
      'agent_id',
    ),
    workflowId: asUuid(
      requireField(data, 'workflow_id', 'workflow_id'),
      'workflow_id',
    ),
    spiffeId: asString(
      requireField(data, 'spiffe_id', 'spiffe_id'),
      'spiffe_id',
    ),
    role: asString(requireField(data, 'role', 'role'), 'role'),
    createdAt: asDateTime(
      requireField(data, 'created_at', 'created_at'),
      'created_at',
    ),
  };
}

/**
 * Server response to `POST /v1/control/tools`.
 *
 * Matches server-side ToolRegisterResponse: tool_id + name + is_active
 * + allowed_workflow_ids (empty array = any workflow; non-empty =
 * restricted to those workflows) + created_at. The tool is something
 * the agent may invoke subject to firewall + per-tenant ACL.
 *
 * allowedWorkflowIds is a frozen readonly array (immutable) so
 * customers cannot mutate the parsed result.
 */
export interface ToolRegisterResponse {
  readonly toolId: string;
  readonly name: string;
  readonly isActive: boolean;
  readonly allowedWorkflowIds: readonly string[];
  readonly createdAt: Date;
}

export function parseToolRegisterResponse(
  data: unknown,
): ToolRegisterResponse {
  if (!isRecord(data)) {
    throw new InvalidEnvelopeError(
      `expected dict for ToolRegisterResponse, got ${typeof data}`,
    );
  }
  return {
    toolId: asUuid(requireField(data, 'tool_id', 'tool_id'), 'tool_id'),
    name: asString(requireField(data, 'name', 'name'), 'name'),
    isActive: asBool(
      requireField(data, 'is_active', 'is_active'),
      'is_active',
    ),
    allowedWorkflowIds: asUuidList(
      requireField(
        data,
        'allowed_workflow_ids',
        'allowed_workflow_ids',
      ),
      'allowed_workflow_ids',
    ),
    createdAt: asDateTime(
      requireField(data, 'created_at', 'created_at'),
      'created_at',
    ),
  };
}

// ---------------------------------------------------------------------------
// Replay envelopes (CP-67; mirrors Python CP-63)
// ---------------------------------------------------------------------------

/**
 * Server response to `GET /v1/control/replay`.
 *
 * Reconstructed decision context for an audit_id. Mirrors the
 * server-side ReplayResponse: full request envelope + retrieved
 * documents + tool I/O + policy evaluations + optional triad review
 * + nanosecond-precision timestamp.
 *
 * Nested records pass through opaquely (requestEnvelope is the
 * original decision payload; retrievedDocuments are
 * {doc_id, content_sha256} pairs; toolIo captures every tool call
 * request+response; policyEvaluations is one entry per Rego package
 * evaluated). Customers can drill into them or wrap with their own
 * model. All collections are frozen readonly arrays.
 *
 * triadReview is `null` when the decision did NOT go through triad
 * review (i.e. AuditEntry.triadInvoked was false).
 */
export interface ReplayResponse {
  readonly auditId: string;
  readonly tenantId: string;
  readonly decision: string;
  readonly riskScore: number;
  readonly requestEnvelope: Record<string, unknown>;
  readonly retrievedDocuments: readonly Record<string, unknown>[];
  readonly toolIo: readonly Record<string, unknown>[];
  readonly policyEvaluations: readonly Record<string, unknown>[];
  readonly triadReview: Record<string, unknown> | null;
  readonly timestampUnixNs: number;
}

export function parseReplayResponse(data: unknown): ReplayResponse {
  if (!isRecord(data)) {
    throw new InvalidEnvelopeError(
      `expected dict for ReplayResponse, got ${typeof data}`,
    );
  }
  return {
    auditId: asUuid(
      requireField(data, 'audit_id', 'audit_id'),
      'audit_id',
    ),
    tenantId: asUuid(
      requireField(data, 'tenant_id', 'tenant_id'),
      'tenant_id',
    ),
    decision: asString(
      requireField(data, 'decision', 'decision'),
      'decision',
    ),
    riskScore: asFloat(
      requireField(data, 'risk_score', 'risk_score'),
      'risk_score',
    ),
    requestEnvelope: asUnknownRecord(
      requireField(data, 'request_envelope', 'request_envelope'),
      'request_envelope',
    ),
    retrievedDocuments: asListOfRecord(
      requireField(data, 'retrieved_documents', 'retrieved_documents'),
      'retrieved_documents',
    ),
    toolIo: asListOfRecord(
      requireField(data, 'tool_io', 'tool_io'),
      'tool_io',
    ),
    policyEvaluations: asListOfRecord(
      requireField(data, 'policy_evaluations', 'policy_evaluations'),
      'policy_evaluations',
    ),
    triadReview: asOptionalRecord(
      data['triad_review'],
      'triad_review',
    ),
    timestampUnixNs: asInt(
      requireField(data, 'timestamp_unix_ns', 'timestamp_unix_ns'),
      'timestamp_unix_ns',
    ),
  };
}

// ---------------------------------------------------------------------------
// Dossier envelopes (CP-67; mirrors Python CP-63)
// ---------------------------------------------------------------------------

/**
 * Server response to `POST /v1/control/dossier`.
 *
 * Carries enough to fetch the full signed JSON via the follow-up
 * GET /v1/control/dossier/{id} call.
 */
export interface DossierGenerateResponse {
  readonly dossierId: string;
  readonly auditId: string;
  readonly signingKeyId: string;
  readonly generatedAt: Date;
}

export function parseDossierGenerateResponse(
  data: unknown,
): DossierGenerateResponse {
  if (!isRecord(data)) {
    throw new InvalidEnvelopeError(
      `expected dict for DossierGenerateResponse, got ${typeof data}`,
    );
  }
  return {
    dossierId: asUuid(
      requireField(data, 'dossier_id', 'dossier_id'),
      'dossier_id',
    ),
    auditId: asUuid(
      requireField(data, 'audit_id', 'audit_id'),
      'audit_id',
    ),
    signingKeyId: asString(
      requireField(data, 'signing_key_id', 'signing_key_id'),
      'signing_key_id',
    ),
    generatedAt: asDateTime(
      requireField(data, 'generated_at', 'generated_at'),
      'generated_at',
    ),
  };
}

/**
 * Server response to `GET /v1/control/dossier/{id}`.
 *
 * Carries the full SignedDossier inline so the caller can verify it
 * offline without further round-trips. signatureHex is exactly 128
 * hex chars (Ed25519 sig = 64 bytes); publicKeyHex is exactly 64 hex
 * chars (Ed25519 public key = 32 bytes). manifest is opaque to the
 * SDK -- the caller verifies it via the verixa_runtime crypto
 * primitives. Lengths are validated by the parser.
 */
export interface DossierGetResponse {
  readonly dossierId: string;
  readonly auditId: string;
  readonly manifest: Record<string, unknown>;
  readonly signatureHex: string;
  readonly publicKeyHex: string;
}

export function parseDossierGetResponse(data: unknown): DossierGetResponse {
  if (!isRecord(data)) {
    throw new InvalidEnvelopeError(
      `expected dict for DossierGetResponse, got ${typeof data}`,
    );
  }
  const sig = asString(
    requireField(data, 'signature_hex', 'signature_hex'),
    'signature_hex',
  );
  if (sig.length !== 128) {
    throw new InvalidEnvelopeError(
      `field signature_hex: expected 128 hex chars, got ${sig.length}`,
    );
  }
  const pub = asString(
    requireField(data, 'public_key_hex', 'public_key_hex'),
    'public_key_hex',
  );
  if (pub.length !== 64) {
    throw new InvalidEnvelopeError(
      `field public_key_hex: expected 64 hex chars, got ${pub.length}`,
    );
  }
  return {
    dossierId: asUuid(
      requireField(data, 'dossier_id', 'dossier_id'),
      'dossier_id',
    ),
    auditId: asUuid(
      requireField(data, 'audit_id', 'audit_id'),
      'audit_id',
    ),
    manifest: asUnknownRecord(
      requireField(data, 'manifest', 'manifest'),
      'manifest',
    ),
    signatureHex: sig,
    publicKeyHex: pub,
  };
}

// ---------------------------------------------------------------------------
// Webhook envelopes (CP-68; mirrors Python CP-64)
// --
// COMPLETES the typed-response surface on the TS side. After this commit
// every server-side response envelope has a TypeScript SDK parser, matching
// the Python SDK's CP-64 milestone.
// ---------------------------------------------------------------------------

/**
 * Parse an array of strings into an immutable frozen array.
 * Per-element validation with index-prefixed field name (e.g.
 * `event_types[1]`) for debuggability. Mirrors Python
 * verixa.envelopes._as_str_list.
 */
function asStringList(value: unknown, name: string): readonly string[] {
  if (!Array.isArray(value)) {
    throw new InvalidEnvelopeError(
      `field ${name}: expected array of strings, got ${typeof value}`,
    );
  }
  const out: string[] = value.map((v, i) => {
    if (typeof v !== 'string') {
      throw new InvalidEnvelopeError(
        `field ${name}[${i}]: expected string, got ${typeof v}`,
      );
    }
    return v;
  });
  return Object.freeze(out);
}

/** Optional string field (null-or-string); mirrors Python _as_optional_str. */
function asOptionalString(value: unknown, name: string): string | null {
  if (value === null || value === undefined) {
    return null;
  }
  return asString(value, name);
}

/**
 * One subscription as returned by `GET /v1/control/webhooks/subscriptions`.
 *
 * Matches server-side WebhookSubscriptionSummary: subscription_id +
 * tenant_id + url + event_types + signing_key_id + created_at.
 * eventTypes is a frozen readonly array of strings (e.g.
 * decision.recorded, dossier.generated, replay.requested).
 * signingKeyId is the Vault-tracked key the dispatcher uses to
 * Ed25519-sign deliveries (per webhook receiver verification
 * protocol).
 */
export interface WebhookSubscriptionSummary {
  readonly subscriptionId: string;
  readonly tenantId: string;
  readonly url: string;
  readonly eventTypes: readonly string[];
  readonly signingKeyId: string;
  readonly createdAt: Date;
}

export function parseWebhookSubscriptionSummary(
  data: unknown,
): WebhookSubscriptionSummary {
  if (!isRecord(data)) {
    throw new InvalidEnvelopeError(
      `expected dict for WebhookSubscriptionSummary, got ${typeof data}`,
    );
  }
  return {
    subscriptionId: asUuid(
      requireField(data, 'subscription_id', 'subscription_id'),
      'subscription_id',
    ),
    tenantId: asUuid(
      requireField(data, 'tenant_id', 'tenant_id'),
      'tenant_id',
    ),
    url: asString(requireField(data, 'url', 'url'), 'url'),
    eventTypes: asStringList(
      requireField(data, 'event_types', 'event_types'),
      'event_types',
    ),
    signingKeyId: asString(
      requireField(data, 'signing_key_id', 'signing_key_id'),
      'signing_key_id',
    ),
    createdAt: asDateTime(
      requireField(data, 'created_at', 'created_at'),
      'created_at',
    ),
  };
}

/** Server response to `GET /v1/control/webhooks/subscriptions`. */
export interface WebhookSubscriptionListResponse {
  readonly subscriptions: readonly WebhookSubscriptionSummary[];
  readonly total: number;
}

export function parseWebhookSubscriptionListResponse(
  data: unknown,
): WebhookSubscriptionListResponse {
  if (!isRecord(data)) {
    throw new InvalidEnvelopeError(
      `expected dict for WebhookSubscriptionListResponse, ` +
        `got ${typeof data}`,
    );
  }
  const items = requireField(data, 'subscriptions', 'subscriptions');
  if (!Array.isArray(items)) {
    throw new InvalidEnvelopeError(
      `field subscriptions: expected array, got ${typeof items}`,
    );
  }
  const parsed: WebhookSubscriptionSummary[] = items.map((item) =>
    parseWebhookSubscriptionSummary(item),
  );
  return {
    subscriptions: Object.freeze(parsed),
    total: asInt(requireField(data, 'total', 'total'), 'total'),
  };
}

/**
 * One forensic delivery record from `GET /v1/control/webhooks/deliveries`.
 *
 * Matches server-side WebhookDeliverySummary: attempt_id +
 * subscription_id + event_id + url + status_code + latency_ms +
 * attempted_at + optional error. error is `null` on successful
 * delivery (2xx response); on failure carries the exception
 * description (e.g. "connection refused", "timeout after 5s",
 * "HTTP 500 internal server error").
 */
export interface WebhookDeliverySummary {
  readonly attemptId: string;
  readonly subscriptionId: string;
  readonly eventId: string;
  readonly url: string;
  readonly statusCode: number;
  readonly latencyMs: number;
  readonly attemptedAt: Date;
  readonly error: string | null;
}

export function parseWebhookDeliverySummary(
  data: unknown,
): WebhookDeliverySummary {
  if (!isRecord(data)) {
    throw new InvalidEnvelopeError(
      `expected dict for WebhookDeliverySummary, got ${typeof data}`,
    );
  }
  return {
    attemptId: asUuid(
      requireField(data, 'attempt_id', 'attempt_id'),
      'attempt_id',
    ),
    subscriptionId: asUuid(
      requireField(data, 'subscription_id', 'subscription_id'),
      'subscription_id',
    ),
    eventId: asUuid(
      requireField(data, 'event_id', 'event_id'),
      'event_id',
    ),
    url: asString(requireField(data, 'url', 'url'), 'url'),
    statusCode: asInt(
      requireField(data, 'status_code', 'status_code'),
      'status_code',
    ),
    latencyMs: asInt(
      requireField(data, 'latency_ms', 'latency_ms'),
      'latency_ms',
    ),
    attemptedAt: asDateTime(
      requireField(data, 'attempted_at', 'attempted_at'),
      'attempted_at',
    ),
    error: asOptionalString(data['error'], 'error'),
  };
}

/** Server response to `GET /v1/control/webhooks/deliveries`. */
export interface WebhookDeliveryListResponse {
  readonly deliveries: readonly WebhookDeliverySummary[];
  readonly total: number;
}

export function parseWebhookDeliveryListResponse(
  data: unknown,
): WebhookDeliveryListResponse {
  if (!isRecord(data)) {
    throw new InvalidEnvelopeError(
      `expected dict for WebhookDeliveryListResponse, got ${typeof data}`,
    );
  }
  const items = requireField(data, 'deliveries', 'deliveries');
  if (!Array.isArray(items)) {
    throw new InvalidEnvelopeError(
      `field deliveries: expected array, got ${typeof items}`,
    );
  }
  const parsed: WebhookDeliverySummary[] = items.map((item) =>
    parseWebhookDeliverySummary(item),
  );
  return {
    deliveries: Object.freeze(parsed),
    total: asInt(requireField(data, 'total', 'total'), 'total'),
  };
}
