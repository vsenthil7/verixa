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
 * Batch shipped in CP-65 (workflow + audit core; the rest follows in CP-66+):
 *
 *   - WorkflowRegisterResponse + parseWorkflowRegisterResponse
 *   - WorkflowSummary + parseWorkflowSummary
 *   - WorkflowListResponse + parseWorkflowListResponse
 *   - AuditEntry + parseAuditEntry
 *   - AuditQueryResponse + parseAuditQueryResponse
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
