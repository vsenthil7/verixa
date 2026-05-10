"""pytest suite for verixa.compliance_language.

Coverage target: 100% line + branch on the module under test.
Approach: parameterised tests for each forbidden rule (clean + dirty cases)
+ targeted edge cases (empty input, mixed case, multiple violations).
"""

from __future__ import annotations

import pytest

from verixa.compliance_language import (
    ComplianceLanguageViolation,
    Violation,
    assert_clean,
    check_text,
    forbidden_phrases,
)

# ---------------------------------------------------------------------------
# forbidden_phrases() — sanity that the canonical set is non-empty + tuple
# ---------------------------------------------------------------------------


def test_forbidden_phrases_is_non_empty_tuple() -> None:
    phrases = forbidden_phrases()
    assert isinstance(phrases, tuple)
    assert len(phrases) >= 5  # at least the five locked rules
    for p in phrases:
        assert isinstance(p, str)
        assert p  # no empty pattern strings


# ---------------------------------------------------------------------------
# check_text() — clean inputs return empty list
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "clean_text",
    [
        "",
        "Verixa governs every governed action through a signed policy bundle.",
        "The dossier is Annex IV-aligned runtime technical dossier.",
        "Verixa creates evidence to demonstrate and support governed actions.",
        "Replay is snapshot-based replay, capturing decision context.",
        "MI300X serving observed at 80 tokens/sec on Qwen3-72B in our test.",
        # Tricky: 'governed' appears mid-sentence
        "We govern every governed action and audit every governed action.",
        # Tricky: 'demonstrate' is the safe verb
        "The runtime demonstrates compliance via the audit ledger.",
    ],
)
def test_check_text_clean_inputs(clean_text: str) -> None:
    assert check_text(clean_text) == []


# ---------------------------------------------------------------------------
# check_text() — Rule 1: 'every action' (without 'governed')
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "dirty_text",
    [
        "Verixa intercepts every action.",
        "We log every action that the agent attempts.",
        "EVERY ACTION is verified.",  # mixed case
    ],
)
def test_check_text_rule1_every_action_violations(dirty_text: str) -> None:
    violations = check_text(dirty_text)
    assert len(violations) >= 1
    assert any("Rule 1" in v.rule for v in violations)


def test_check_text_rule1_every_governed_action_is_clean() -> None:
    assert check_text("Verixa intercepts every governed action.") == []


# ---------------------------------------------------------------------------
# check_text() — Rule 2: 'regulator-ready'
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "dirty_text",
    [
        "Verixa produces a regulator-ready dossier.",
        "Regulator-ready output is a key feature.",  # leading capital
        "We aim for a regulator ready posture.",  # space variant
    ],
)
def test_check_text_rule2_regulator_ready_violations(dirty_text: str) -> None:
    violations = check_text(dirty_text)
    assert any("Rule 2" in v.rule for v in violations)


# ---------------------------------------------------------------------------
# check_text() — Rule 3: 'proves' / 'proven'
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "dirty_text,expected_rule",
    [
        ("Verixa proves the action was correct.", "Rule 3"),
        ("This system has proven the workflow.", "Rule 3"),
        ("Our evidence proves nothing further is needed.", "Rule 3"),
        ("PROVEN at scale.", "Rule 3"),
    ],
)
def test_check_text_rule3_proves_violations(
    dirty_text: str, expected_rule: str
) -> None:
    violations = check_text(dirty_text)
    assert any(expected_rule in v.rule for v in violations)


# ---------------------------------------------------------------------------
# check_text() — Rule 4: 'bit-exact replay/regeneration'
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "dirty_text",
    [
        "Verixa offers bit-exact replay.",
        "Bit exact regeneration of decisions.",
        "bitexact replay is supported.",  # without separator — SHOULD match
    ],
)
def test_check_text_rule4_bit_exact_violations(dirty_text: str) -> None:
    violations = check_text(dirty_text)
    assert any("Rule 4" in v.rule for v in violations)


# ---------------------------------------------------------------------------
# check_text() — Rule 5: hedged MI300X claims
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "dirty_text",
    [
        "Guaranteed MI300X throughput at 1000 tokens/sec.",
        "We guarantee throughput on MI300X.",
        "Guarantees MI300X latency under 100ms.",
    ],
)
def test_check_text_rule5_hedged_mi300x_violations(dirty_text: str) -> None:
    violations = check_text(dirty_text)
    assert any("Rule 5" in v.rule for v in violations)


# ---------------------------------------------------------------------------
# Multiple violations in one text — ordering by position
# ---------------------------------------------------------------------------


def test_check_text_multiple_violations_in_position_order() -> None:
    text = (
        "Verixa proves every action via a regulator-ready dossier. "
        "It guarantees MI300X throughput."
    )
    violations = check_text(text)
    assert len(violations) >= 4  # proves, every action, regulator-ready, guaranteed
    positions = [v.position for v in violations]
    assert positions == sorted(positions), "violations must be position-sorted"


# ---------------------------------------------------------------------------
# Violation dataclass + repr
# ---------------------------------------------------------------------------


def test_violation_str_format() -> None:
    text = "every action is intercepted."
    violations = check_text(text)
    assert len(violations) >= 1
    s = str(violations[0])
    assert "pos 0" in s or "pos " in s
    assert "Rule" in s


def test_violation_is_frozen_dataclass() -> None:
    v = Violation(rule="r", matched_text="m", position=0, suggestion="s")
    with pytest.raises((AttributeError, Exception)):
        v.rule = "changed"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# assert_clean() — happy + sad paths
# ---------------------------------------------------------------------------


def test_assert_clean_passes_on_clean_text() -> None:
    # Should not raise
    assert_clean("Verixa governs every governed action.")
    assert_clean("")


def test_assert_clean_raises_on_dirty_text() -> None:
    with pytest.raises(ComplianceLanguageViolation) as exc_info:
        assert_clean("Verixa proves every action.")
    err = exc_info.value
    assert len(err.violations) >= 2
    msg = str(err)
    assert "Compliance-language violations" in msg
    assert "Rule" in msg


def test_compliance_language_violation_carries_violations() -> None:
    text = "regulator-ready dossier proves it."
    try:
        assert_clean(text)
    except ComplianceLanguageViolation as e:
        assert isinstance(e.violations, list)
        assert all(isinstance(v, Violation) for v in e.violations)
        assert len(e.violations) >= 2
    else:
        pytest.fail("ComplianceLanguageViolation was not raised")
