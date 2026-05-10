"""Compliance-language hardening rules — runtime + test-time validation.

The Verixa positioning relies on specific wording. This module makes those
rules machine-checkable so they cannot drift in user-facing text (READMEs,
demo scripts, dossier templates, error messages).

Rules carried from the START brief and AT-Hack0017-002 architecture lock:

1. "every governed action" — never "every action"
2. "Annex IV-aligned runtime technical dossier" — never "regulator-ready Annex IV dossier"
3. "creates evidence to demonstrate and support" — never "proves"
4. Snapshot-based replay (not bit-exact regeneration)
5. Hedged MI300X claims (no absolute performance guarantees)

Functions:
    check_text(text)        -> list of violations (empty = clean)
    assert_clean(text)      -> raises ComplianceLanguageViolation if dirty
    forbidden_phrases()     -> the canonical forbidden-phrase set

This module has no I/O, no network, no DB. It is pure-function and trivial
to unit-test.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Final

# ---------------------------------------------------------------------------
# Canonical forbidden phrases (case-insensitive, word-boundary aware)
# ---------------------------------------------------------------------------

# Each entry: (regex pattern, human-readable rule, suggested replacement)
_FORBIDDEN: Final[tuple[tuple[str, str, str], ...]] = (
    (
        r"\bevery\s+action\b(?!\s+(is\s+)?governed)",
        "Rule 1: 'every action' is too broad; use 'every governed action'.",
        "every governed action",
    ),
    (
        r"\bregulator[-\s]ready\b",
        "Rule 2: 'regulator-ready' overclaims; use 'Annex IV-aligned' or "
        "'Annex IV-aligned runtime technical dossier'.",
        "Annex IV-aligned",
    ),
    (
        r"\bproves?\b",
        "Rule 3: Verixa does not 'prove' AI behaviour; use 'creates evidence "
        "to demonstrate and support' or 'demonstrates'.",
        "creates evidence to demonstrate and support",
    ),
    (
        r"\bproven\b",
        "Rule 3: Verixa does not 'prove' AI behaviour; use 'demonstrated' "
        "or 'evidenced'.",
        "demonstrated",
    ),
    (
        r"\bbit[-\s]?exact\s+(replay|regeneration)\b",
        "Rule 4: Verixa replay is snapshot-based, not bit-exact; use "
        "'snapshot-based replay'.",
        "snapshot-based replay",
    ),
    (
        r"\b(guaranteed|guarantee[ds]?)\s+(MI300X|throughput|latency|performance)\b",
        "Rule 5: MI300X performance claims must be hedged; remove "
        "'guaranteed'.",
        "(remove or hedge)",
    ),
)


@dataclass(frozen=True, slots=True)
class Violation:
    """A single compliance-language rule violation found in text."""

    rule: str
    matched_text: str
    position: int
    suggestion: str

    def __str__(self) -> str:
        return (
            f"[pos {self.position}] {self.rule} "
            f"(matched: {self.matched_text!r}; suggested: {self.suggestion!r})"
        )


class ComplianceLanguageViolation(ValueError):
    """Raised by assert_clean() when forbidden phrases are detected."""

    def __init__(self, violations: list[Violation]) -> None:
        self.violations = violations
        joined = "\n  - ".join(str(v) for v in violations)
        super().__init__(
            f"Compliance-language violations ({len(violations)}):\n  - {joined}"
        )


def forbidden_phrases() -> tuple[str, ...]:
    """Return the canonical set of forbidden patterns (regex strings).

    Useful for documentation, doc-build linters, and CI checks.
    """
    return tuple(pattern for pattern, _rule, _sugg in _FORBIDDEN)


def check_text(text: str) -> list[Violation]:
    """Scan text for forbidden phrases. Empty list = clean.

    Case-insensitive. Returns all violations in document order.
    """
    if not text:
        return []
    violations: list[Violation] = []
    for pattern, rule, suggestion in _FORBIDDEN:
        for match in re.finditer(pattern, text, flags=re.IGNORECASE):
            violations.append(
                Violation(
                    rule=rule,
                    matched_text=match.group(0),
                    position=match.start(),
                    suggestion=suggestion,
                )
            )
    violations.sort(key=lambda v: v.position)
    return violations


def assert_clean(text: str) -> None:
    """Raise ComplianceLanguageViolation if text contains forbidden phrases."""
    violations = check_text(text)
    if violations:
        raise ComplianceLanguageViolation(violations)
