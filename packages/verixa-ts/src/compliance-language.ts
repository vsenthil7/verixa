/**
 * Compliance-language hardening rules — runtime + test-time validation.
 *
 * The Verixa positioning relies on specific wording. This module makes those
 * rules machine-checkable so they cannot drift in user-facing text (READMEs,
 * demo scripts, dossier templates, error messages).
 *
 * Mirror of `verixa.compliance_language` (Python). Both libraries enforce
 * the same canonical forbidden-phrase set so the hardening is identical
 * across the runtime gateway (Python) and the control plane UI (TypeScript).
 *
 * Rules (locked in AT-Hack0017-002 architecture; see START brief):
 * 1. "every governed action" — never "every action"
 * 2. "Annex IV-aligned runtime technical dossier" — never "regulator-ready"
 * 3. "creates evidence to demonstrate and support" — never "proves"
 * 4. Snapshot-based replay (not bit-exact regeneration)
 * 5. Hedged MI300X claims (no absolute performance guarantees)
 *
 * Invariant on FORBIDDEN_RULES patterns:
 *   Every pattern MUST require at least one literal character to match.
 *   No `*`, `?`, or `{0,N}` quantifiers at the top level. This invariant
 *   keeps `checkText` zero-width-match free; if you add a rule that can
 *   match the empty string you MUST also add a forward-progress guard
 *   (`if (match.index === pattern.lastIndex) pattern.lastIndex += 1`)
 *   AND a test that exercises that branch.
 */

/** A single compliance-language rule violation found in text. */
export interface Violation {
  readonly rule: string;
  readonly matchedText: string;
  readonly position: number;
  readonly suggestion: string;
}

/** Error thrown by {@link assertClean} when forbidden phrases are detected. */
export class ComplianceLanguageViolation extends Error {
  public readonly violations: ReadonlyArray<Violation>;

  constructor(violations: ReadonlyArray<Violation>) {
    const lines = violations.map(violationToString).join('\n  - ');
    super(
      `Compliance-language violations (${violations.length}):\n  - ${lines}`,
    );
    this.name = 'ComplianceLanguageViolation';
    this.violations = violations;
    // Preserve prototype chain through transpilation
    Object.setPrototypeOf(this, ComplianceLanguageViolation.prototype);
  }
}

/** Render a Violation as a single-line string (debugging + error messages). */
export function violationToString(v: Violation): string {
  return (
    `[pos ${v.position}] ${v.rule} ` +
    `(matched: ${JSON.stringify(v.matchedText)}; ` +
    `suggested: ${JSON.stringify(v.suggestion)})`
  );
}

interface ForbiddenRule {
  readonly pattern: RegExp;
  readonly rule: string;
  readonly suggestion: string;
}

// Canonical forbidden-phrase set. Patterns are case-insensitive (`i` flag)
// and use the global flag (`g`) so we can iterate all matches in a string.
// Per the file-level invariant, every pattern requires >= 1 literal char.
const FORBIDDEN_RULES: ReadonlyArray<ForbiddenRule> = [
  {
    pattern: /\bevery\s+action\b(?!\s+(is\s+)?governed)/gi,
    rule: "Rule 1: 'every action' is too broad; use 'every governed action'.",
    suggestion: 'every governed action',
  },
  {
    pattern: /\bregulator[-\s]ready\b/gi,
    rule:
      "Rule 2: 'regulator-ready' overclaims; use 'Annex IV-aligned' or " +
      "'Annex IV-aligned runtime technical dossier'.",
    suggestion: 'Annex IV-aligned',
  },
  {
    pattern: /\bproves?\b/gi,
    rule:
      "Rule 3: Verixa does not 'prove' AI behaviour; use 'creates evidence " +
      "to demonstrate and support' or 'demonstrates'.",
    suggestion: 'creates evidence to demonstrate and support',
  },
  {
    pattern: /\bproven\b/gi,
    rule:
      "Rule 3: Verixa does not 'prove' AI behaviour; use 'demonstrated' " +
      "or 'evidenced'.",
    suggestion: 'demonstrated',
  },
  {
    pattern: /\bbit[-\s]?exact\s+(replay|regeneration)\b/gi,
    rule:
      "Rule 4: Verixa replay is snapshot-based, not bit-exact; use " +
      "'snapshot-based replay'.",
    suggestion: 'snapshot-based replay',
  },
  {
    pattern:
      /\b(guaranteed|guarantee[ds]?)\s+(MI300X|throughput|latency|performance)\b/gi,
    rule:
      "Rule 5: MI300X performance claims must be hedged; remove " +
      "'guaranteed'.",
    suggestion: '(remove or hedge)',
  },
];

/** Return the canonical set of forbidden patterns (regex strings). */
export function forbiddenPhrases(): ReadonlyArray<string> {
  return FORBIDDEN_RULES.map((r) => r.pattern.source);
}

/**
 * Scan text for forbidden phrases. Returns all violations in document order
 * (sorted by `position`). Empty array means clean.
 *
 * Note: the file-level invariant guarantees no zero-width matches, so no
 * forward-progress guard is needed inside the iteration.
 */
export function checkText(text: string): Violation[] {
  if (!text) {
    return [];
  }
  const violations: Violation[] = [];
  for (const { pattern, rule, suggestion } of FORBIDDEN_RULES) {
    // Reset lastIndex because the regex is `g`-flagged and stateful.
    pattern.lastIndex = 0;
    let match: RegExpExecArray | null;
    while ((match = pattern.exec(text)) !== null) {
      violations.push({
        rule,
        matchedText: match[0],
        position: match.index,
        suggestion,
      });
    }
  }
  violations.sort((a, b) => a.position - b.position);
  return violations;
}

/**
 * Throw {@link ComplianceLanguageViolation} if `text` contains forbidden
 * phrases. No-op on clean input.
 */
export function assertClean(text: string): void {
  const violations = checkText(text);
  if (violations.length > 0) {
    throw new ComplianceLanguageViolation(violations);
  }
}
