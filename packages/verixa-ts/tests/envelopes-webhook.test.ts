/**
 * CP-68 vitest suite for verixa-ts envelopes (webhook -- COMPLETES surface).
 *
 * Mirrors Python CP-64 test_webhook_envelopes.py. After this commit the
 * typed-response surface is COMPLETE on the TS side too: every
 * server-side response envelope has a TypeScript parser.
 *
 * 4 envelopes covered: WebhookSubscriptionSummary +
 * WebhookSubscriptionListResponse + WebhookDeliverySummary +
 * WebhookDeliveryListResponse.
 */

import { describe, expect, it, test } from 'vitest';

import {
  InvalidEnvelopeError,
  parseWebhookDeliveryListResponse,
  parseWebhookDeliverySummary,
  parseWebhookSubscriptionListResponse,
  parseWebhookSubscriptionSummary,
} from '../src/envelopes.js';

const now = (): string => new Date().toISOString();

function subscriptionPayload(
  overrides: Record<string, unknown> = {},
): Record<string, unknown> {
  return {
    subscription_id: '00000000-0000-0000-0000-000000000060',
    tenant_id: '00000000-0000-0000-0000-000000000061',
    url: 'https://acme.example.com/webhooks/verixa',
    event_types: ['decision.recorded', 'dossier.generated'],
    signing_key_id: 'verixa-sig-prod-acme',
    created_at: now(),
    ...overrides,
  };
}

function deliveryPayload(
  overrides: Record<string, unknown> = {},
): Record<string, unknown> {
  return {
    attempt_id: '00000000-0000-0000-0000-000000000070',
    subscription_id: '00000000-0000-0000-0000-000000000071',
    event_id: '00000000-0000-0000-0000-000000000072',
    url: 'https://acme.example.com/webhooks/verixa',
    status_code: 200,
    latency_ms: 42,
    attempted_at: now(),
    error: null,
    ...overrides,
  };
}

// ---------------------------------------------------------------------------
// parseWebhookSubscriptionSummary
// ---------------------------------------------------------------------------

describe('parseWebhookSubscriptionSummary()', () => {
  it('parses a minimal payload', () => {
    const parsed = parseWebhookSubscriptionSummary(subscriptionPayload());
    expect(parsed.eventTypes).toEqual([
      'decision.recorded',
      'dossier.generated',
    ]);
    expect(parsed.signingKeyId).toBe('verixa-sig-prod-acme');
    expect(parsed.createdAt).toBeInstanceOf(Date);
  });

  it('returns a frozen event_types array', () => {
    const parsed = parseWebhookSubscriptionSummary(subscriptionPayload());
    expect(Object.isFrozen(parsed.eventTypes)).toBe(true);
  });

  it('accepts empty event_types (server validates min_length=1; SDK is forward-compat)', () => {
    const parsed = parseWebhookSubscriptionSummary(
      subscriptionPayload({ event_types: [] }),
    );
    expect(parsed.eventTypes).toEqual([]);
  });

  it('ignores extra fields', () => {
    const parsed = parseWebhookSubscriptionSummary(
      subscriptionPayload({ future_field: 42 }),
    );
    expect(parsed.signingKeyId).toBe('verixa-sig-prod-acme');
  });

  it('rejects non-record input', () => {
    expect(() => parseWebhookSubscriptionSummary('oops')).toThrow(
      InvalidEnvelopeError,
    );
  });

  test.each([
    'subscription_id',
    'tenant_id',
    'url',
    'event_types',
    'signing_key_id',
    'created_at',
  ])('rejects missing required field %s', (missing) => {
    const payload = subscriptionPayload();
    delete payload[missing];
    expect(() => parseWebhookSubscriptionSummary(payload)).toThrow(
      new RegExp(`field ${missing}`),
    );
  });

  it('rejects non-array event_types', () => {
    expect(() =>
      parseWebhookSubscriptionSummary(
        subscriptionPayload({ event_types: 'not-an-array' }),
      ),
    ).toThrow(/expected array of strings/);
  });

  it('rejects non-string element inside event_types with index prefix', () => {
    expect(() =>
      parseWebhookSubscriptionSummary(
        subscriptionPayload({ event_types: ['ok', 42, 'ok2'] }),
      ),
    ).toThrow(/event_types\[1\]: expected string/);
  });
});

// ---------------------------------------------------------------------------
// parseWebhookSubscriptionListResponse
// ---------------------------------------------------------------------------

describe('parseWebhookSubscriptionListResponse()', () => {
  it('parses an empty list', () => {
    const parsed = parseWebhookSubscriptionListResponse({
      subscriptions: [],
      total: 0,
    });
    expect(parsed.subscriptions).toEqual([]);
    expect(parsed.total).toBe(0);
  });

  it('parses multiple subscriptions', () => {
    const items = [
      subscriptionPayload(),
      subscriptionPayload(),
      subscriptionPayload(),
    ];
    const parsed = parseWebhookSubscriptionListResponse({
      subscriptions: items,
      total: 3,
    });
    expect(parsed.subscriptions.length).toBe(3);
    expect(parsed.total).toBe(3);
  });

  it('returns a frozen subscriptions array', () => {
    const parsed = parseWebhookSubscriptionListResponse({
      subscriptions: [],
      total: 0,
    });
    expect(Object.isFrozen(parsed.subscriptions)).toBe(true);
  });

  it('rejects non-record input', () => {
    expect(() => parseWebhookSubscriptionListResponse('oops')).toThrow(
      InvalidEnvelopeError,
    );
  });

  it('rejects missing subscriptions field', () => {
    expect(() =>
      parseWebhookSubscriptionListResponse({ total: 0 }),
    ).toThrow(/field subscriptions/);
  });

  it('rejects non-array subscriptions field', () => {
    expect(() =>
      parseWebhookSubscriptionListResponse({
        subscriptions: 'not-an-array',
        total: 0,
      }),
    ).toThrow(/field subscriptions: expected array/);
  });

  it('bubbles inner error with field name', () => {
    const bad = subscriptionPayload();
    delete bad.url;
    expect(() =>
      parseWebhookSubscriptionListResponse({
        subscriptions: [bad],
        total: 1,
      }),
    ).toThrow(/field url/);
  });
});

// ---------------------------------------------------------------------------
// parseWebhookDeliverySummary
// ---------------------------------------------------------------------------

describe('parseWebhookDeliverySummary()', () => {
  it('parses a successful (2xx) delivery with null error', () => {
    const parsed = parseWebhookDeliverySummary(deliveryPayload());
    expect(parsed.statusCode).toBe(200);
    expect(parsed.latencyMs).toBe(42);
    expect(parsed.error).toBeNull();
  });

  it('parses a failed delivery with error message', () => {
    const parsed = parseWebhookDeliverySummary(
      deliveryPayload({
        status_code: 500,
        latency_ms: 5000,
        error: 'HTTP 500 internal server error',
      }),
    );
    expect(parsed.statusCode).toBe(500);
    expect(parsed.error).toBe('HTTP 500 internal server error');
  });

  it('omitting error key yields null (server may omit vs send null)', () => {
    const payload = deliveryPayload();
    delete payload.error;
    const parsed = parseWebhookDeliverySummary(payload);
    expect(parsed.error).toBeNull();
  });

  it('rejects non-string error when present', () => {
    expect(() =>
      parseWebhookDeliverySummary(deliveryPayload({ error: 42 })),
    ).toThrow(/field error: expected string/);
  });

  it('rejects bool for status_code', () => {
    expect(() =>
      parseWebhookDeliverySummary(deliveryPayload({ status_code: true })),
    ).toThrow(/field status_code: expected int/);
  });

  it('rejects bool for latency_ms', () => {
    expect(() =>
      parseWebhookDeliverySummary(deliveryPayload({ latency_ms: false })),
    ).toThrow(/field latency_ms: expected int/);
  });

  it('ignores extra fields', () => {
    const parsed = parseWebhookDeliverySummary(
      deliveryPayload({ future_field: 42 }),
    );
    expect(parsed.statusCode).toBe(200);
  });

  it('rejects non-record input', () => {
    expect(() => parseWebhookDeliverySummary(42)).toThrow(
      InvalidEnvelopeError,
    );
  });

  test.each([
    'attempt_id',
    'subscription_id',
    'event_id',
    'url',
    'status_code',
    'latency_ms',
    'attempted_at',
  ])('rejects missing required field %s (error is optional)', (missing) => {
    const payload = deliveryPayload();
    delete payload[missing];
    expect(() => parseWebhookDeliverySummary(payload)).toThrow(
      new RegExp(`field ${missing}`),
    );
  });
});

// ---------------------------------------------------------------------------
// parseWebhookDeliveryListResponse
// ---------------------------------------------------------------------------

describe('parseWebhookDeliveryListResponse()', () => {
  it('parses an empty list', () => {
    const parsed = parseWebhookDeliveryListResponse({
      deliveries: [],
      total: 0,
    });
    expect(parsed.deliveries).toEqual([]);
    expect(parsed.total).toBe(0);
  });

  it('parses multiple deliveries', () => {
    const items = [deliveryPayload(), deliveryPayload()];
    const parsed = parseWebhookDeliveryListResponse({
      deliveries: items,
      total: 2,
    });
    expect(parsed.deliveries.length).toBe(2);
  });

  it('returns a frozen deliveries array', () => {
    const parsed = parseWebhookDeliveryListResponse({
      deliveries: [],
      total: 0,
    });
    expect(Object.isFrozen(parsed.deliveries)).toBe(true);
  });

  it('rejects non-record input', () => {
    expect(() => parseWebhookDeliveryListResponse('oops')).toThrow(
      InvalidEnvelopeError,
    );
  });

  it('rejects missing deliveries field', () => {
    expect(() =>
      parseWebhookDeliveryListResponse({ total: 0 }),
    ).toThrow(/field deliveries/);
  });

  it('rejects non-array deliveries field', () => {
    expect(() =>
      parseWebhookDeliveryListResponse({
        deliveries: {},
        total: 0,
      }),
    ).toThrow(/field deliveries: expected array/);
  });

  it('bubbles inner error with field name', () => {
    const bad = deliveryPayload();
    delete bad.url;
    expect(() =>
      parseWebhookDeliveryListResponse({
        deliveries: [bad],
        total: 1,
      }),
    ).toThrow(/field url/);
  });
});

// ---------------------------------------------------------------------------
// Milestone: typed-response surface is COMPLETE on TS side
// ---------------------------------------------------------------------------

describe('TS typed-response surface completeness milestone (CP-68)', () => {
  it('exports all 14 envelope parsers expected for full coverage', async () => {
    const mod = await import('../src/envelopes.js');
    const expectedParsers = [
      // Workflow (3) -- CP-65
      'parseWorkflowRegisterResponse',
      'parseWorkflowSummary',
      'parseWorkflowListResponse',
      // Audit (2) -- CP-65
      'parseAuditEntry',
      'parseAuditQueryResponse',
      // Registry (2) -- CP-66
      'parseAgentRegisterResponse',
      'parseToolRegisterResponse',
      // Replay (1) -- CP-67
      'parseReplayResponse',
      // Dossier (2) -- CP-67
      'parseDossierGenerateResponse',
      'parseDossierGetResponse',
      // Webhook (4) -- CP-68 (completes the set)
      'parseWebhookSubscriptionSummary',
      'parseWebhookSubscriptionListResponse',
      'parseWebhookDeliverySummary',
      'parseWebhookDeliveryListResponse',
    ];
    expect(expectedParsers.length).toBe(14);
    for (const name of expectedParsers) {
      expect(typeof (mod as Record<string, unknown>)[name]).toBe(
        'function',
      );
    }
  });
});
