/**
 * CP-67 vitest suite for verixa-ts envelopes (replay + dossier).
 *
 * Mirrors Python CP-63 test_replay_dossier_envelopes.py. Covers:
 *   - ReplayResponse (most complex; 10 fields + 3 list-of-record
 *     collections + optional triadReview)
 *   - DossierGenerateResponse
 *   - DossierGetResponse (with signatureHex 128-char + publicKeyHex
 *     64-char length validation)
 */

import { describe, expect, it, test } from 'vitest';

import {
  InvalidEnvelopeError,
  parseDossierGenerateResponse,
  parseDossierGetResponse,
  parseReplayResponse,
} from '../src/envelopes.js';

const now = (): string => new Date().toISOString();

function replayPayload(
  overrides: Record<string, unknown> = {},
): Record<string, unknown> {
  return {
    audit_id: '00000000-0000-0000-0000-000000000030',
    tenant_id: '00000000-0000-0000-0000-000000000031',
    decision: 'allow',
    risk_score: 0.12,
    request_envelope: { prompt: 'approve this payment' },
    retrieved_documents: [
      { doc_id: 'd1', content_sha256: 'abc' },
      { doc_id: 'd2', content_sha256: 'def' },
    ],
    tool_io: [{ name: 'lookup', input: {}, output: 'ok' }],
    policy_evaluations: [
      { package: 'fs.pii', decision: 'allow', reason: 'no pii' },
    ],
    triad_review: null,
    timestamp_unix_ns: 1747000000000000000,
    ...overrides,
  };
}

function dossierGeneratePayload(
  overrides: Record<string, unknown> = {},
): Record<string, unknown> {
  return {
    dossier_id: '00000000-0000-0000-0000-000000000040',
    audit_id: '00000000-0000-0000-0000-000000000041',
    signing_key_id: 'verixa-sig-dev',
    generated_at: now(),
    ...overrides,
  };
}

function dossierGetPayload(
  overrides: Record<string, unknown> = {},
): Record<string, unknown> {
  return {
    dossier_id: '00000000-0000-0000-0000-000000000050',
    audit_id: '00000000-0000-0000-0000-000000000051',
    manifest: { summary: 'ok' },
    signature_hex: 'a'.repeat(128),
    public_key_hex: 'b'.repeat(64),
    ...overrides,
  };
}

// ---------------------------------------------------------------------------
// parseReplayResponse -- positive
// ---------------------------------------------------------------------------

describe('parseReplayResponse() positive', () => {
  it('parses with no triad review (null)', () => {
    const parsed = parseReplayResponse(replayPayload());
    expect(parsed.decision).toBe('allow');
    expect(parsed.riskScore).toBe(0.12);
    expect(parsed.triadReview).toBeNull();
    expect(parsed.timestampUnixNs).toBe(1747000000000000000);
  });

  it('parses with triad review record', () => {
    const triad = {
      agreement: true,
      votes: [{ model: 'qwen3', vote: 'approve' }],
    };
    const parsed = parseReplayResponse(replayPayload({ triad_review: triad }));
    expect(parsed.triadReview).toEqual(triad);
  });

  it('collections are frozen readonly arrays', () => {
    const parsed = parseReplayResponse(replayPayload());
    expect(Object.isFrozen(parsed.retrievedDocuments)).toBe(true);
    expect(Object.isFrozen(parsed.toolIo)).toBe(true);
    expect(Object.isFrozen(parsed.policyEvaluations)).toBe(true);
  });

  it('inner records pass through opaquely', () => {
    const req = { nested: { deeper: { value: 42 } } };
    const parsed = parseReplayResponse(replayPayload({ request_envelope: req }));
    expect(parsed.requestEnvelope).toEqual(req);
    const re = parsed.requestEnvelope['nested'] as Record<string, unknown>;
    const inner = re['deeper'] as Record<string, unknown>;
    expect(inner['value']).toBe(42);
  });

  it('accepts empty collections', () => {
    const parsed = parseReplayResponse(
      replayPayload({
        retrieved_documents: [],
        tool_io: [],
        policy_evaluations: [],
      }),
    );
    expect(parsed.retrievedDocuments).toEqual([]);
    expect(parsed.toolIo).toEqual([]);
    expect(parsed.policyEvaluations).toEqual([]);
  });

  it('omitting triad_review key yields null', () => {
    const payload = replayPayload();
    delete payload.triad_review;
    const parsed = parseReplayResponse(payload);
    expect(parsed.triadReview).toBeNull();
  });

  it('ignores extra fields', () => {
    const parsed = parseReplayResponse(
      replayPayload({ future_field: 42 }),
    );
    expect(parsed.decision).toBe('allow');
  });
});

// ---------------------------------------------------------------------------
// parseReplayResponse -- errors
// ---------------------------------------------------------------------------

describe('parseReplayResponse() errors', () => {
  it('rejects non-record input', () => {
    expect(() => parseReplayResponse(42)).toThrow(InvalidEnvelopeError);
  });

  test.each([
    'audit_id',
    'tenant_id',
    'decision',
    'risk_score',
    'request_envelope',
    'retrieved_documents',
    'tool_io',
    'policy_evaluations',
    'timestamp_unix_ns',
  ])('rejects missing required field %s (triad_review is optional)', (missing) => {
    const payload = replayPayload();
    delete payload[missing];
    expect(() => parseReplayResponse(payload)).toThrow(
      new RegExp(`field ${missing}`),
    );
  });

  it('rejects non-record request_envelope', () => {
    expect(() =>
      parseReplayResponse(replayPayload({ request_envelope: 'not-a-record' })),
    ).toThrow(/field request_envelope: expected dict/);
  });

  it('rejects non-array retrieved_documents', () => {
    expect(() =>
      parseReplayResponse(replayPayload({ retrieved_documents: {} })),
    ).toThrow(/field retrieved_documents: expected array/);
  });

  it('rejects non-record entry inside retrieved_documents with index prefix', () => {
    expect(() =>
      parseReplayResponse(
        replayPayload({
          retrieved_documents: [{ ok: 1 }, 'not-a-record', { ok: 2 }],
        }),
      ),
    ).toThrow(/retrieved_documents\[1\]: expected dict/);
  });

  it('rejects non-record triad_review when present', () => {
    expect(() =>
      parseReplayResponse(replayPayload({ triad_review: 'not-a-record' })),
    ).toThrow(/field triad_review: expected dict/);
  });

  it('rejects bool for timestamp_unix_ns', () => {
    expect(() =>
      parseReplayResponse(replayPayload({ timestamp_unix_ns: true })),
    ).toThrow(/field timestamp_unix_ns: expected int/);
  });

  it('rejects invalid UUID for audit_id', () => {
    expect(() =>
      parseReplayResponse(replayPayload({ audit_id: 'not-a-uuid' })),
    ).toThrow(/not a valid UUID/);
  });
});

// ---------------------------------------------------------------------------
// parseDossierGenerateResponse
// ---------------------------------------------------------------------------

describe('parseDossierGenerateResponse()', () => {
  it('parses a minimal payload', () => {
    const parsed = parseDossierGenerateResponse(dossierGeneratePayload());
    expect(parsed.signingKeyId).toBe('verixa-sig-dev');
    expect(parsed.generatedAt).toBeInstanceOf(Date);
  });

  it('ignores extra fields', () => {
    const parsed = parseDossierGenerateResponse(
      dossierGeneratePayload({ future_field: 42 }),
    );
    expect(parsed.signingKeyId).toBe('verixa-sig-dev');
  });

  it('rejects non-record input', () => {
    expect(() => parseDossierGenerateResponse([])).toThrow(
      InvalidEnvelopeError,
    );
  });

  test.each(['dossier_id', 'audit_id', 'signing_key_id', 'generated_at'])(
    'rejects missing required field %s',
    (missing) => {
      const payload = dossierGeneratePayload();
      delete payload[missing];
      expect(() => parseDossierGenerateResponse(payload)).toThrow(
        new RegExp(`field ${missing}`),
      );
    },
  );

  it('rejects non-string signing_key_id', () => {
    expect(() =>
      parseDossierGenerateResponse(
        dossierGeneratePayload({ signing_key_id: 42 }),
      ),
    ).toThrow(/field signing_key_id/);
  });
});

// ---------------------------------------------------------------------------
// parseDossierGetResponse (signature + public key length pinning)
// ---------------------------------------------------------------------------

describe('parseDossierGetResponse()', () => {
  it('parses a minimal payload', () => {
    const parsed = parseDossierGetResponse(dossierGetPayload());
    expect(parsed.manifest).toEqual({ summary: 'ok' });
    expect(parsed.signatureHex.length).toBe(128);
    expect(parsed.publicKeyHex.length).toBe(64);
  });

  test.each([127, 129, 0, 64])(
    'rejects signature_hex of wrong length: %d',
    (badLen) => {
      expect(() =>
        parseDossierGetResponse(
          dossierGetPayload({ signature_hex: 'a'.repeat(badLen) }),
        ),
      ).toThrow(/signature_hex: expected 128 hex/);
    },
  );

  test.each([63, 65, 0, 128])(
    'rejects public_key_hex of wrong length: %d',
    (badLen) => {
      expect(() =>
        parseDossierGetResponse(
          dossierGetPayload({ public_key_hex: 'b'.repeat(badLen) }),
        ),
      ).toThrow(/public_key_hex: expected 64 hex/);
    },
  );

  it('rejects non-record manifest', () => {
    expect(() =>
      parseDossierGetResponse(
        dossierGetPayload({ manifest: 'not-a-record' }),
      ),
    ).toThrow(/field manifest: expected dict/);
  });

  it('ignores extra fields', () => {
    const parsed = parseDossierGetResponse(
      dossierGetPayload({ future_field: 42 }),
    );
    expect(parsed.manifest).toEqual({ summary: 'ok' });
  });

  it('rejects non-record input', () => {
    expect(() => parseDossierGetResponse('oops')).toThrow(
      InvalidEnvelopeError,
    );
  });

  test.each([
    'dossier_id',
    'audit_id',
    'manifest',
    'signature_hex',
    'public_key_hex',
  ])('rejects missing required field %s', (missing) => {
    const payload = dossierGetPayload();
    delete payload[missing];
    expect(() => parseDossierGetResponse(payload)).toThrow(
      new RegExp(`field ${missing}`),
    );
  });
});
