/**
 * Vitest suite for compliance-language module.
 *
 * Coverage target: 100% line + branch + function on the module under test.
 * Parameterised over each rule with both clean + dirty cases, plus targeted
 * edge cases (empty input, mixed case, multiple violations, ordering,
 * error-path payload).
 */

import { describe, expect, it, test } from 'vitest';

import {
  ComplianceLanguageViolation,
  type Violation,
  assertClean,
  checkText,
  forbiddenPhrases,
  violationToString,
} from '../src/compliance-language.js';

// ---------------------------------------------------------------------------
// forbiddenPhrases() — canonical set non-empty
// ---------------------------------------------------------------------------

describe('forbiddenPhrases()', () => {
  it('returns a non-empty array of regex pattern strings', () => {
    const phrases = forbiddenPhrases();
    expect(Array.isArray(phrases)).toBe(true);
    expect(phrases.length).toBeGreaterThanOrEqual(5);
    for (const p of phrases) {
      expect(typeof p).toBe('string');
      expect(p.length).toBeGreaterThan(0);
    }
  });
});

// ---------------------------------------------------------------------------
// checkText() — clean inputs return empty array
// ---------------------------------------------------------------------------

describe('checkText() with clean inputs', () => {
  test.each([
    [''],
    ['Verixa governs every governed action through a signed policy bundle.'],
    ['The dossier is Annex IV-aligned runtime technical dossier.'],
    ['Verixa creates evidence to demonstrate and support governed actions.'],
    ['Replay is snapshot-based replay, capturing decision context.'],
    ['MI300X serving observed at 80 tokens/sec on Qwen3-72B in our test.'],
    ['We govern every governed action and audit every governed action.'],
    ['The runtime demonstrates compliance via the audit ledger.'],
  ])('returns [] for clean input %#', (clean) => {
    expect(checkText(clean)).toEqual([]);
  });
});

// ---------------------------------------------------------------------------
// Rule 1 — 'every action' (without 'governed')
// ---------------------------------------------------------------------------

describe('checkText() — Rule 1 every action', () => {
  test.each([
    ['Verixa intercepts every action.'],
    ['We log every action that the agent attempts.'],
    ['EVERY ACTION is verified.'],
  ])('flags rule 1 in: %s', (dirty) => {
    const violations = checkText(dirty);
    expect(violations.length).toBeGreaterThanOrEqual(1);
    expect(violations.some((v) => v.rule.startsWith('Rule 1'))).toBe(true);
  });

  it('passes when every action is governed', () => {
    expect(checkText('Verixa intercepts every governed action.')).toEqual([]);
  });
});

// ---------------------------------------------------------------------------
// Rule 2 — 'regulator-ready'
// ---------------------------------------------------------------------------

describe('checkText() — Rule 2 regulator-ready', () => {
  test.each([
    ['Verixa produces a regulator-ready dossier.'],
    ['Regulator-ready output is a key feature.'],
    ['We aim for a regulator ready posture.'],
  ])('flags rule 2 in: %s', (dirty) => {
    const violations = checkText(dirty);
    expect(violations.some((v) => v.rule.startsWith('Rule 2'))).toBe(true);
  });
});

// ---------------------------------------------------------------------------
// Rule 3 — 'proves' / 'proven'
// ---------------------------------------------------------------------------

describe('checkText() — Rule 3 proves/proven', () => {
  test.each([
    ['Verixa proves the action was correct.'],
    ['This system has proven the workflow.'],
    ['Our evidence proves nothing further is needed.'],
    ['PROVEN at scale.'],
  ])('flags rule 3 in: %s', (dirty) => {
    const violations = checkText(dirty);
    expect(violations.some((v) => v.rule.startsWith('Rule 3'))).toBe(true);
  });
});

// ---------------------------------------------------------------------------
// Rule 4 — 'bit-exact replay/regeneration'
// ---------------------------------------------------------------------------

describe('checkText() — Rule 4 bit-exact', () => {
  test.each([
    ['Verixa offers bit-exact replay.'],
    ['Bit exact regeneration of decisions.'],
    ['bitexact replay is supported.'],
  ])('flags rule 4 in: %s', (dirty) => {
    const violations = checkText(dirty);
    expect(violations.some((v) => v.rule.startsWith('Rule 4'))).toBe(true);
  });
});

// ---------------------------------------------------------------------------
// Rule 5 — hedged MI300X claims
// ---------------------------------------------------------------------------

describe('checkText() — Rule 5 hedged MI300X', () => {
  test.each([
    ['Guaranteed MI300X throughput at 1000 tokens/sec.'],
    ['We guarantee throughput on MI300X.'],
    ['Guarantees MI300X latency under 100ms.'],
  ])('flags rule 5 in: %s', (dirty) => {
    const violations = checkText(dirty);
    expect(violations.some((v) => v.rule.startsWith('Rule 5'))).toBe(true);
  });
});

// ---------------------------------------------------------------------------
// Multiple violations + ordering
// ---------------------------------------------------------------------------

describe('checkText() — multiple violations', () => {
  it('returns violations sorted by position', () => {
    const text =
      'Verixa proves every action via a regulator-ready dossier. ' +
      'It guarantees MI300X throughput.';
    const violations = checkText(text);
    expect(violations.length).toBeGreaterThanOrEqual(4);
    const positions = violations.map((v) => v.position);
    const sorted = [...positions].sort((a, b) => a - b);
    expect(positions).toEqual(sorted);
  });

  it('handles a long text with no violations efficiently', () => {
    const text = 'Verixa demonstrates governed AI. '.repeat(100);
    expect(checkText(text)).toEqual([]);
  });
});

// ---------------------------------------------------------------------------
// violationToString
// ---------------------------------------------------------------------------

describe('violationToString()', () => {
  it('renders a violation with position, rule, matched, suggestion', () => {
    const v: Violation = {
      rule: 'Rule X: example',
      matchedText: 'bad phrase',
      position: 42,
      suggestion: 'good phrase',
    };
    const s = violationToString(v);
    expect(s).toContain('pos 42');
    expect(s).toContain('Rule X');
    expect(s).toContain('bad phrase');
    expect(s).toContain('good phrase');
  });
});

// ---------------------------------------------------------------------------
// assertClean() — happy + sad paths
// ---------------------------------------------------------------------------

describe('assertClean()', () => {
  it('does not throw on clean text', () => {
    expect(() =>
      assertClean('Verixa governs every governed action.'),
    ).not.toThrow();
    expect(() => assertClean('')).not.toThrow();
  });

  it('throws ComplianceLanguageViolation on dirty text', () => {
    expect(() => assertClean('Verixa proves every action.')).toThrow(
      ComplianceLanguageViolation,
    );
  });

  it('error carries non-empty violations array', () => {
    try {
      assertClean('regulator-ready dossier proves it.');
      throw new Error('should have thrown');
    } catch (err) {
      expect(err).toBeInstanceOf(ComplianceLanguageViolation);
      const e = err as ComplianceLanguageViolation;
      expect(e.violations.length).toBeGreaterThanOrEqual(2);
      expect(e.message).toContain('Compliance-language violations');
      expect(e.name).toBe('ComplianceLanguageViolation');
    }
  });
});
