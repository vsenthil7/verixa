/**
 * CP-65 vitest suite for verixa-ts envelopes (workflow + audit core).
 *
 * Mirrors verixa-python tests/test_sdk_envelopes.py for the same 5 types:
 *
 *   - WorkflowRegisterResponse + parser
 *   - WorkflowSummary + parser
 *   - WorkflowListResponse + parser
 *   - AuditEntry + parser
 *   - AuditQueryResponse + parser
 *
 * Coverage target: 100% line + branch on envelopes.ts (matches the
 * vitest gate already enforced for the existing TS modules).
 *
 * Tests cover the same failure modes as the Python suite:
 *
 *   - Positive: valid payloads parse correctly + every field populates
 *   - Type errors: non-string UUID, non-string datetime, wrong types
 *   - Missing required fields: each raises InvalidEnvelopeError with
 *     the field name in the message so customers can debug server-shape
 *     bugs
 *   - Forward-compat: extra fields are IGNORED (server can add fields)
 *   - Datetime invariants: naive datetimes rejected (Verixa requires TZ)
 *   - bool-as-number rejection: true/false cannot silently coerce to 1/0
 *   - List parsing: nested AuditEntry / WorkflowSummary errors bubble up
 *   - Immutable arrays (Object.freeze) on collection fields
 */

import { describe, expect, it, test } from 'vitest';

import {
  type AuditEntry,
  type WorkflowSummary,
  InvalidEnvelopeError,
  parseAuditEntry,
  parseAuditQueryResponse,
  parseWorkflowListResponse,
  parseWorkflowRegisterResponse,
  parseWorkflowSummary,
} from '../src/envelopes.js';

// ---------------------------------------------------------------------------
// Fixtures (match server-side envelopes.py wire format)
// ---------------------------------------------------------------------------

const now = (): string => new Date().toISOString();

function workflowRegisterPayload(
  overrides: Record<string, unknown> = {},
): Record<string, unknown> {
  return {
    workflow_id: '00000000-0000-0000-0000-000000000001',
    name: 'payments-flow',
    sector: 'financial-services',
    created_at: now(),
    ...overrides,
  };
}

function workflowSummaryPayload(
  overrides: Record<string, unknown> = {},
): Record<string, unknown> {
  return {
    workflow_id: '00000000-0000-0000-0000-000000000002',
    name: 'payments-flow',
    sector: 'financial-services',
    risk_threshold_escalate: 0.5,
    agent_count: 3,
    created_at: now(),
    ...overrides,
  };
}

function auditEntryPayload(
  overrides: Record<string, unknown> = {},
): Record<string, unknown> {
  return {
    audit_id: '00000000-0000-0000-0000-000000000003',
    workflow_id: '00000000-0000-0000-0000-000000000004',
    decision: 'allow',
    risk_score: 0.12,
    risk_classification: 'low',
    triad_invoked: false,
    timestamp: now(),
    ...overrides,
  };
}

// ---------------------------------------------------------------------------
// InvalidEnvelopeError shape
// ---------------------------------------------------------------------------

describe('InvalidEnvelopeError', () => {
  it('is an Error subclass with the correct name', () => {
    const err = new InvalidEnvelopeError('test');
    expect(err).toBeInstanceOf(Error);
    expect(err.name).toBe('InvalidEnvelopeError');
    expect(err.message).toBe('test');
  });
});

// ---------------------------------------------------------------------------
// parseWorkflowRegisterResponse -- positive cases
// ---------------------------------------------------------------------------

describe('parseWorkflowRegisterResponse() positive', () => {
  it('parses a minimal payload', () => {
    const parsed = parseWorkflowRegisterResponse(workflowRegisterPayload());
    expect(parsed.name).toBe('payments-flow');
    expect(parsed.sector).toBe('financial-services');
    expect(parsed.workflowId).toBe('00000000-0000-0000-0000-000000000001');
    expect(parsed.createdAt).toBeInstanceOf(Date);
  });

  it('ignores extra fields (forward-compat)', () => {
    const parsed = parseWorkflowRegisterResponse(
      workflowRegisterPayload({ future_field: 42, extra: 'ignored' }),
    );
    expect(parsed.name).toBe('payments-flow');
  });

  it('returns a readonly object (TypeScript level)', () => {
    // readonly is a compile-time guard; we cannot test mutation at
    // runtime without TS. The interface itself is the test contract.
    const parsed = parseWorkflowRegisterResponse(workflowRegisterPayload());
    // Just confirm shape compiles + values present.
    expect(Object.keys(parsed).sort()).toEqual([
      'createdAt',
      'name',
      'sector',
      'workflowId',
    ]);
  });

  it('accepts Z-suffix ISO datetime', () => {
    const parsed = parseWorkflowRegisterResponse(
      workflowRegisterPayload({ created_at: '2026-05-11T17:30:00Z' }),
    );
    expect(parsed.createdAt.toISOString()).toBe(
      '2026-05-11T17:30:00.000Z',
    );
  });

  it('accepts offset ISO datetime (+01:00)', () => {
    const parsed = parseWorkflowRegisterResponse(
      workflowRegisterPayload({ created_at: '2026-05-11T18:30:00+01:00' }),
    );
    // 18:30+01:00 == 17:30 UTC
    expect(parsed.createdAt.toISOString()).toBe(
      '2026-05-11T17:30:00.000Z',
    );
  });

  it('accepts a Date object directly', () => {
    const d = new Date('2026-05-11T17:30:00Z');
    const parsed = parseWorkflowRegisterResponse(
      workflowRegisterPayload({ created_at: d }),
    );
    expect(parsed.createdAt).toBe(d);
  });

  it('lowercases UUID strings for canonical form', () => {
    const parsed = parseWorkflowRegisterResponse(
      workflowRegisterPayload({
        workflow_id: '00000000-0000-0000-0000-00000000000A',
      }),
    );
    expect(parsed.workflowId).toBe('00000000-0000-0000-0000-00000000000a');
  });
});

// ---------------------------------------------------------------------------
// parseWorkflowRegisterResponse -- error cases
// ---------------------------------------------------------------------------

describe('parseWorkflowRegisterResponse() errors', () => {
  test.each([
    [42],
    ['not a dict'],
    [null],
    [[1, 2, 3]],
    [new Date()],
  ])('rejects non-record input: %s', (badInput) => {
    expect(() => parseWorkflowRegisterResponse(badInput)).toThrow(
      InvalidEnvelopeError,
    );
  });

  test.each(['workflow_id', 'name', 'sector', 'created_at'])(
    'rejects missing required field %s',
    (missing) => {
      const payload = workflowRegisterPayload();
      delete payload[missing];
      expect(() => parseWorkflowRegisterResponse(payload)).toThrow(
        new RegExp(`field ${missing}`),
      );
    },
  );

  it('rejects invalid UUID', () => {
    const payload = workflowRegisterPayload({ workflow_id: 'not-a-uuid' });
    expect(() => parseWorkflowRegisterResponse(payload)).toThrow(
      /not a valid UUID/,
    );
  });

  it('rejects non-string UUID', () => {
    const payload = workflowRegisterPayload({ workflow_id: 12345 });
    expect(() => parseWorkflowRegisterResponse(payload)).toThrow(
      /expected uuid string/,
    );
  });

  it('rejects naive datetime string (no tzinfo)', () => {
    const payload = workflowRegisterPayload({
      created_at: '2026-05-11T17:30:00',
    });
    expect(() => parseWorkflowRegisterResponse(payload)).toThrow(/naive/);
  });

  it('rejects invalid datetime string', () => {
    const payload = workflowRegisterPayload({ created_at: 'last TuesdayZ' });
    expect(() => parseWorkflowRegisterResponse(payload)).toThrow(
      /not a valid ISO-8601/,
    );
  });

  it('rejects invalid Date object', () => {
    const bad = new Date('definitely not a date');
    const payload = workflowRegisterPayload({ created_at: bad });
    expect(() => parseWorkflowRegisterResponse(payload)).toThrow(
      /invalid Date object/,
    );
  });

  it('rejects non-string datetime (number)', () => {
    const payload = workflowRegisterPayload({ created_at: 1234567890 });
    expect(() => parseWorkflowRegisterResponse(payload)).toThrow(
      /expected ISO-8601 string/,
    );
  });

  it('rejects non-string name (number)', () => {
    const payload = workflowRegisterPayload({ name: 42 });
    expect(() => parseWorkflowRegisterResponse(payload)).toThrow(
      /field name: expected string/,
    );
  });

  it('rejects non-string sector (number)', () => {
    const payload = workflowRegisterPayload({ sector: 42 });
    expect(() => parseWorkflowRegisterResponse(payload)).toThrow(
      /field sector: expected string/,
    );
  });
});

// ---------------------------------------------------------------------------
// parseWorkflowSummary
// ---------------------------------------------------------------------------

describe('parseWorkflowSummary()', () => {
  it('parses a minimal payload', () => {
    const parsed = parseWorkflowSummary(workflowSummaryPayload());
    expect(parsed.riskThresholdEscalate).toBe(0.5);
    expect(parsed.agentCount).toBe(3);
  });

  it('accepts int for risk_threshold (0/1 float-compatible)', () => {
    const parsed = parseWorkflowSummary(
      workflowSummaryPayload({ risk_threshold_escalate: 1 }),
    );
    expect(parsed.riskThresholdEscalate).toBe(1);
  });

  it('rejects bool for risk_threshold (would silently coerce to 1/0)', () => {
    const payload = workflowSummaryPayload({
      risk_threshold_escalate: true,
    });
    expect(() => parseWorkflowSummary(payload)).toThrow(
      /expected number, got boolean/,
    );
  });

  it('rejects string for risk_threshold', () => {
    const payload = workflowSummaryPayload({
      risk_threshold_escalate: '0.5',
    });
    expect(() => parseWorkflowSummary(payload)).toThrow(/expected number/);
  });

  it('rejects bool for agent_count', () => {
    const payload = workflowSummaryPayload({ agent_count: true });
    expect(() => parseWorkflowSummary(payload)).toThrow(/expected int/);
  });

  it('rejects non-integer agent_count', () => {
    const payload = workflowSummaryPayload({ agent_count: 3.5 });
    expect(() => parseWorkflowSummary(payload)).toThrow(
      /non-integer number/,
    );
  });

  it('rejects string for agent_count (non-number non-boolean branch)', () => {
    const payload = workflowSummaryPayload({ agent_count: '3' });
    expect(() => parseWorkflowSummary(payload)).toThrow(
      /field agent_count: expected int, got string/,
    );
  });

  it('rejects non-record input', () => {
    expect(() => parseWorkflowSummary('oops')).toThrow(InvalidEnvelopeError);
  });

  it('rejects non-finite number (NaN) for risk_threshold', () => {
    const payload = workflowSummaryPayload({
      risk_threshold_escalate: Number.NaN,
    });
    expect(() => parseWorkflowSummary(payload)).toThrow(
      /expected finite number/,
    );
  });
});

// ---------------------------------------------------------------------------
// parseWorkflowListResponse
// ---------------------------------------------------------------------------

describe('parseWorkflowListResponse()', () => {
  it('parses an empty list', () => {
    const parsed = parseWorkflowListResponse({
      workflows: [],
      total: 0,
    });
    expect(parsed.workflows).toEqual([]);
    expect(parsed.total).toBe(0);
  });

  it('parses multiple workflows', () => {
    const items = [
      workflowSummaryPayload(),
      workflowSummaryPayload(),
      workflowSummaryPayload(),
    ];
    const parsed = parseWorkflowListResponse({
      workflows: items,
      total: 3,
    });
    expect(parsed.workflows.length).toBe(3);
    expect(parsed.total).toBe(3);
  });

  it('returns a frozen workflows array', () => {
    const parsed = parseWorkflowListResponse({ workflows: [], total: 0 });
    expect(Object.isFrozen(parsed.workflows)).toBe(true);
  });

  it('rejects non-record input', () => {
    expect(() => parseWorkflowListResponse('x')).toThrow(
      InvalidEnvelopeError,
    );
  });

  it('rejects missing workflows field', () => {
    expect(() => parseWorkflowListResponse({ total: 0 })).toThrow(
      /field workflows/,
    );
  });

  it('rejects non-array workflows field', () => {
    expect(() =>
      parseWorkflowListResponse({ workflows: 'not-array', total: 0 }),
    ).toThrow(/field workflows: expected array/);
  });

  it('rejects missing total', () => {
    expect(() => parseWorkflowListResponse({ workflows: [] })).toThrow(
      /field total/,
    );
  });

  it('rejects bool total', () => {
    expect(() =>
      parseWorkflowListResponse({ workflows: [], total: true }),
    ).toThrow(/field total: expected int/);
  });

  it('bubbles inner parser error with field name', () => {
    const bad = workflowSummaryPayload();
    delete bad.name;
    expect(() =>
      parseWorkflowListResponse({ workflows: [bad], total: 1 }),
    ).toThrow(/field name/);
  });
});

// ---------------------------------------------------------------------------
// parseAuditEntry
// ---------------------------------------------------------------------------

describe('parseAuditEntry()', () => {
  it('parses a minimal payload', () => {
    const parsed = parseAuditEntry(auditEntryPayload());
    expect(parsed.decision).toBe('allow');
    expect(parsed.riskScore).toBe(0.12);
    expect(parsed.riskClassification).toBe('low');
    expect(parsed.triadInvoked).toBe(false);
  });

  it('accepts triad_invoked true', () => {
    const parsed = parseAuditEntry(
      auditEntryPayload({ triad_invoked: true }),
    );
    expect(parsed.triadInvoked).toBe(true);
  });

  it('rejects bool for risk_score', () => {
    expect(() =>
      parseAuditEntry(auditEntryPayload({ risk_score: true })),
    ).toThrow(/expected number, got boolean/);
  });

  test.each(['true', 1, 0])(
    'rejects non-bool %j for triad_invoked',
    (badValue) => {
      expect(() =>
        parseAuditEntry(auditEntryPayload({ triad_invoked: badValue })),
      ).toThrow(/expected bool/);
    },
  );

  it('rejects non-record input', () => {
    expect(() => parseAuditEntry(42)).toThrow(InvalidEnvelopeError);
  });

  test.each([
    'audit_id',
    'workflow_id',
    'decision',
    'risk_score',
    'risk_classification',
    'triad_invoked',
    'timestamp',
  ])('rejects missing required field %s', (missing) => {
    const payload = auditEntryPayload();
    delete payload[missing];
    expect(() => parseAuditEntry(payload)).toThrow(
      new RegExp(`field ${missing}`),
    );
  });
});

// ---------------------------------------------------------------------------
// parseAuditQueryResponse
// ---------------------------------------------------------------------------

describe('parseAuditQueryResponse()', () => {
  function buildQueryPayload(
    overrides: Record<string, unknown> = {},
  ): Record<string, unknown> {
    return {
      entries: [auditEntryPayload(), auditEntryPayload()],
      total: 2,
      workflow_id: '00000000-0000-0000-0000-000000000005',
      from_timestamp: now(),
      to_timestamp: now(),
      ...overrides,
    };
  }

  it('parses a multi-entry response', () => {
    const parsed = parseAuditQueryResponse(buildQueryPayload());
    expect(parsed.entries.length).toBe(2);
    expect(parsed.total).toBe(2);
    expect(parsed.workflowId).toBe(
      '00000000-0000-0000-0000-000000000005',
    );
    expect(parsed.fromTimestamp).toBeInstanceOf(Date);
    expect(parsed.toTimestamp).toBeInstanceOf(Date);
  });

  it('returns a frozen entries array', () => {
    const parsed = parseAuditQueryResponse(buildQueryPayload());
    expect(Object.isFrozen(parsed.entries)).toBe(true);
  });

  it('rejects non-record input', () => {
    expect(() => parseAuditQueryResponse('oops')).toThrow(
      InvalidEnvelopeError,
    );
  });

  it('rejects missing entries field', () => {
    const p = buildQueryPayload();
    delete p.entries;
    expect(() => parseAuditQueryResponse(p)).toThrow(/field entries/);
  });

  it('rejects non-array entries', () => {
    expect(() =>
      parseAuditQueryResponse(buildQueryPayload({ entries: {} })),
    ).toThrow(/field entries: expected array/);
  });

  it('rejects missing workflow_id', () => {
    const p = buildQueryPayload();
    delete p.workflow_id;
    expect(() => parseAuditQueryResponse(p)).toThrow(/field workflow_id/);
  });

  it('bubbles inner error with field name', () => {
    const bad = auditEntryPayload();
    delete bad.timestamp;
    expect(() =>
      parseAuditQueryResponse(buildQueryPayload({ entries: [bad] })),
    ).toThrow(/field timestamp/);
  });
});

// ---------------------------------------------------------------------------
// Type-only sanity (compile-time guard; runtime no-op)
// ---------------------------------------------------------------------------

describe('TypeScript type surface', () => {
  it('AuditEntry interface has expected field types', () => {
    const entry: AuditEntry = parseAuditEntry(auditEntryPayload());
    expect(typeof entry.auditId).toBe('string');
    expect(typeof entry.workflowId).toBe('string');
    expect(typeof entry.decision).toBe('string');
    expect(typeof entry.riskScore).toBe('number');
    expect(typeof entry.triadInvoked).toBe('boolean');
    expect(entry.timestamp).toBeInstanceOf(Date);
  });

  it('WorkflowSummary interface has expected field types', () => {
    const summary: WorkflowSummary = parseWorkflowSummary(
      workflowSummaryPayload(),
    );
    expect(typeof summary.riskThresholdEscalate).toBe('number');
    expect(typeof summary.agentCount).toBe('number');
  });
});
