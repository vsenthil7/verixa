import { describe, expect, it } from 'vitest';

import {
  TOKENS,
  decisionColor,
  formatRiskScore,
  formatTimestamp,
  formatTimestampNs,
  riskColor,
  shortUuid,
} from '../design';

describe('decisionColor', () => {
  it.each([
    ['allow', TOKENS.color.decisionAllow],
    ['deny', TOKENS.color.decisionDeny],
    ['escalate', TOKENS.color.decisionEscalate],
  ])('maps %s to its display color', (decision, expected) => {
    expect(decisionColor(decision)).toBe(expected);
  });

  it('falls back to muted grey for unknown decisions', () => {
    expect(decisionColor('absurd')).toBe(TOKENS.color.inkMuted);
  });
});

describe('riskColor', () => {
  it.each([
    ['low', TOKENS.color.riskLow],
    ['medium', TOKENS.color.riskMedium],
    ['high', TOKENS.color.riskHigh],
    ['critical', TOKENS.color.riskCritical],
  ])('maps %s to its display color', (classification, expected) => {
    expect(riskColor(classification)).toBe(expected);
  });

  it('falls back to muted grey for unknown classifications', () => {
    expect(riskColor('cosmic')).toBe(TOKENS.color.inkMuted);
  });
});

describe('formatTimestamp', () => {
  it('renders ISO-8601 as compact UTC string', () => {
    expect(formatTimestamp('2026-05-10T11:42:00Z')).toBe(
      '2026-05-10 11:42 UTC',
    );
  });

  it('falls back to the original string on unparseable input', () => {
    expect(formatTimestamp('not-a-date')).toBe('not-a-date');
  });
});

describe('formatTimestampNs', () => {
  it('renders unix-nanoseconds as compact UTC string', () => {
    // 2026-05-10 11:42:00 UTC in unix nanoseconds.
    const ns = new Date('2026-05-10T11:42:00Z').getTime() * 1_000_000;
    expect(formatTimestampNs(ns)).toBe('2026-05-10 11:42 UTC');
  });
});

describe('formatRiskScore', () => {
  it.each([
    [0, '0.0%'],
    [0.05, '5.0%'],
    [0.4248, '42.5%'],
    [1, '100.0%'],
  ])('formats %s as %s', (score, expected) => {
    expect(formatRiskScore(score)).toBe(expected);
  });
});

describe('shortUuid', () => {
  it('truncates a long UUID to first8...last4', () => {
    expect(
      shortUuid('aaaa1111-2222-3333-4444-555555555555'),
    ).toBe('aaaa1111…5555');
  });

  it('returns short strings unchanged', () => {
    expect(shortUuid('short')).toBe('short');
  });

  it('returns the boundary 16-char string at full length when over threshold', () => {
    // Exactly 16 chars is below the < 16 cutoff (so 16 is truncated).
    expect(shortUuid('abcd1234efgh5678')).toBe('abcd1234…5678');
  });
});
