"""pytest suite for verixa_runtime.firewall.arg_bounds (CP-7.2).

Comprehensive unit tests + Hypothesis property tests covering every
branch in the bounds evaluator.
"""

from __future__ import annotations

from typing import Any

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from verixa_runtime.firewall import (
    CODE_ARG_ARRAY_SIZE,
    CODE_ARG_ENUM,
    CODE_ARG_FORMAT,
    CODE_ARG_LENGTH,
    CODE_ARG_MISSING,
    CODE_ARG_MULTIPLE_OF,
    CODE_ARG_PATTERN,
    CODE_ARG_RANGE,
    CODE_ARG_TYPE,
    CODE_ARG_UNKNOWN,
    FirewallDecision,
    evaluate_argument_bounds,
)
from verixa_runtime.gateway.envelopes import GovernAction


def _action(arguments: dict[str, Any]) -> GovernAction:
    return GovernAction.model_validate(
        {
            "type": "tool_call",
            "tool_name": "transfer_funds",
            "arguments": arguments,
        }
    )


# ---------------------------------------------------------------------------
# Empty / missing schema
# ---------------------------------------------------------------------------


def test_no_schema_passes() -> None:
    verdict = evaluate_argument_bounds(_action({"x": 1}), None)
    assert verdict.decision == FirewallDecision.ALLOW


def test_empty_schema_passes() -> None:
    verdict = evaluate_argument_bounds(_action({"x": 1}), {})
    assert verdict.decision == FirewallDecision.ALLOW


# ---------------------------------------------------------------------------
# enum
# ---------------------------------------------------------------------------


def test_enum_match_passes() -> None:
    schema = {
        "type": "object",
        "properties": {"currency": {"enum": ["GBP", "USD"]}},
    }
    verdict = evaluate_argument_bounds(_action({"currency": "GBP"}), schema)
    assert verdict.decision == FirewallDecision.ALLOW


def test_enum_mismatch_denied() -> None:
    schema = {
        "type": "object",
        "properties": {"currency": {"enum": ["GBP", "USD"]}},
    }
    verdict = evaluate_argument_bounds(_action({"currency": "JPY"}), schema)
    assert verdict.decision == FirewallDecision.DENY
    assert verdict.code == CODE_ARG_ENUM


def test_enum_at_top_level_with_no_type() -> None:
    """enum without type still applies."""
    schema = {"enum": [{"a": 1}, {"a": 2}]}
    # Args dict not in enum -> deny
    verdict = evaluate_argument_bounds(_action({"a": 3}), schema)
    assert verdict.decision == FirewallDecision.DENY


# ---------------------------------------------------------------------------
# Type checks
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "type_,value,expected_pass",
    [
        ("integer", 5, True),
        ("integer", 5.5, False),
        ("integer", True, False),  # bool rejected
        ("integer", "5", False),
        ("number", 5, True),
        ("number", 5.5, True),
        ("number", True, False),
        ("number", "5", False),
        ("string", "hi", True),
        ("string", 5, False),
        ("boolean", True, True),
        ("boolean", 1, False),
        ("array", [1, 2], True),
        ("array", "abc", False),
        ("object", {"x": 1}, True),
        ("object", [1, 2], False),
    ],
)
def test_type_check(
    type_: str, value: Any, expected_pass: bool
) -> None:
    schema = {"type": "object", "properties": {"x": {"type": type_}}}
    verdict = evaluate_argument_bounds(_action({"x": value}), schema)
    if expected_pass:
        assert verdict.decision == FirewallDecision.ALLOW
    else:
        assert verdict.decision == FirewallDecision.DENY
        assert verdict.code == CODE_ARG_TYPE


def test_unknown_top_level_type_skips() -> None:
    """Forward compatibility: unknown type strings produce no failure."""
    schema = {"type": "futureType"}
    verdict = evaluate_argument_bounds(_action({"x": 1}), schema)
    assert verdict.decision == FirewallDecision.ALLOW


# ---------------------------------------------------------------------------
# Numeric bounds
# ---------------------------------------------------------------------------


def test_minimum() -> None:
    schema = {"type": "object", "properties": {"n": {"type": "integer", "minimum": 1}}}
    assert (
        evaluate_argument_bounds(_action({"n": 1}), schema).decision
        == FirewallDecision.ALLOW
    )
    v = evaluate_argument_bounds(_action({"n": 0}), schema)
    assert v.decision == FirewallDecision.DENY
    assert v.code == CODE_ARG_RANGE


def test_maximum() -> None:
    schema = {"type": "object", "properties": {"n": {"type": "integer", "maximum": 10}}}
    assert (
        evaluate_argument_bounds(_action({"n": 10}), schema).decision
        == FirewallDecision.ALLOW
    )
    v = evaluate_argument_bounds(_action({"n": 11}), schema)
    assert v.decision == FirewallDecision.DENY
    assert v.code == CODE_ARG_RANGE


def test_exclusive_minimum() -> None:
    schema = {
        "type": "object",
        "properties": {"n": {"type": "number", "exclusiveMinimum": 0}},
    }
    assert (
        evaluate_argument_bounds(_action({"n": 0.001}), schema).decision
        == FirewallDecision.ALLOW
    )
    v = evaluate_argument_bounds(_action({"n": 0}), schema)
    assert v.decision == FirewallDecision.DENY
    assert v.code == CODE_ARG_RANGE


def test_exclusive_maximum() -> None:
    schema = {
        "type": "object",
        "properties": {"n": {"type": "number", "exclusiveMaximum": 1.0}},
    }
    assert (
        evaluate_argument_bounds(_action({"n": 0.999}), schema).decision
        == FirewallDecision.ALLOW
    )
    v = evaluate_argument_bounds(_action({"n": 1.0}), schema)
    assert v.decision == FirewallDecision.DENY
    assert v.code == CODE_ARG_RANGE


def test_multiple_of() -> None:
    schema = {"type": "object", "properties": {"n": {"type": "integer", "multipleOf": 5}}}
    assert (
        evaluate_argument_bounds(_action({"n": 25}), schema).decision
        == FirewallDecision.ALLOW
    )
    v = evaluate_argument_bounds(_action({"n": 26}), schema)
    assert v.decision == FirewallDecision.DENY
    assert v.code == CODE_ARG_MULTIPLE_OF


def test_multiple_of_zero_rejects() -> None:
    """Defensive: multipleOf=0 should not divide-by-zero."""
    schema = {"type": "object", "properties": {"n": {"type": "integer", "multipleOf": 0}}}
    v = evaluate_argument_bounds(_action({"n": 5}), schema)
    assert v.decision == FirewallDecision.DENY
    assert v.code == CODE_ARG_MULTIPLE_OF


# ---------------------------------------------------------------------------
# String bounds
# ---------------------------------------------------------------------------


def test_min_length() -> None:
    schema = {"type": "object", "properties": {"s": {"type": "string", "minLength": 3}}}
    assert (
        evaluate_argument_bounds(_action({"s": "abc"}), schema).decision
        == FirewallDecision.ALLOW
    )
    v = evaluate_argument_bounds(_action({"s": "ab"}), schema)
    assert v.decision == FirewallDecision.DENY
    assert v.code == CODE_ARG_LENGTH


def test_max_length() -> None:
    schema = {"type": "object", "properties": {"s": {"type": "string", "maxLength": 3}}}
    assert (
        evaluate_argument_bounds(_action({"s": "abc"}), schema).decision
        == FirewallDecision.ALLOW
    )
    v = evaluate_argument_bounds(_action({"s": "abcd"}), schema)
    assert v.decision == FirewallDecision.DENY
    assert v.code == CODE_ARG_LENGTH


def test_pattern() -> None:
    schema = {
        "type": "object",
        "properties": {"acc": {"type": "string", "pattern": r"^ACC-\d+$"}},
    }
    assert (
        evaluate_argument_bounds(_action({"acc": "ACC-12345"}), schema).decision
        == FirewallDecision.ALLOW
    )
    v = evaluate_argument_bounds(_action({"acc": "X-12345"}), schema)
    assert v.decision == FirewallDecision.DENY
    assert v.code == CODE_ARG_PATTERN


@pytest.mark.parametrize(
    "fmt,good,bad",
    [
        ("email", "alice@example.com", "not-an-email"),
        ("uuid", "11111111-1111-1111-1111-111111111111", "not-a-uuid"),
        ("date-time", "2026-05-10T12:00:00+00:00", "not-a-date"),
    ],
)
def test_format_validators(fmt: str, good: str, bad: str) -> None:
    schema = {
        "type": "object",
        "properties": {"v": {"type": "string", "format": fmt}},
    }
    assert (
        evaluate_argument_bounds(_action({"v": good}), schema).decision
        == FirewallDecision.ALLOW
    )
    v = evaluate_argument_bounds(_action({"v": bad}), schema)
    assert v.decision == FirewallDecision.DENY
    assert v.code == CODE_ARG_FORMAT


def test_unknown_format_skipped() -> None:
    """Forward compatibility: unknown format strings don't fail."""
    schema = {
        "type": "object",
        "properties": {"v": {"type": "string", "format": "ipv6-address"}},
    }
    verdict = evaluate_argument_bounds(_action({"v": "anything"}), schema)
    assert verdict.decision == FirewallDecision.ALLOW


# ---------------------------------------------------------------------------
# Array bounds + recursion
# ---------------------------------------------------------------------------


def test_min_items() -> None:
    schema = {
        "type": "object",
        "properties": {"xs": {"type": "array", "minItems": 2}},
    }
    assert (
        evaluate_argument_bounds(_action({"xs": [1, 2]}), schema).decision
        == FirewallDecision.ALLOW
    )
    v = evaluate_argument_bounds(_action({"xs": [1]}), schema)
    assert v.decision == FirewallDecision.DENY
    assert v.code == CODE_ARG_ARRAY_SIZE


def test_max_items() -> None:
    schema = {
        "type": "object",
        "properties": {"xs": {"type": "array", "maxItems": 2}},
    }
    assert (
        evaluate_argument_bounds(_action({"xs": [1, 2]}), schema).decision
        == FirewallDecision.ALLOW
    )
    v = evaluate_argument_bounds(_action({"xs": [1, 2, 3]}), schema)
    assert v.decision == FirewallDecision.DENY


def test_array_items_recursion() -> None:
    """items schema applies recursively to each element."""
    schema = {
        "type": "object",
        "properties": {
            "xs": {
                "type": "array",
                "items": {"type": "integer", "minimum": 0, "maximum": 100},
            }
        },
    }
    assert (
        evaluate_argument_bounds(
            _action({"xs": [10, 20, 30]}), schema
        ).decision
        == FirewallDecision.ALLOW
    )
    # One bad element trips the firewall
    v = evaluate_argument_bounds(_action({"xs": [10, 200]}), schema)
    assert v.decision == FirewallDecision.DENY
    assert v.code == CODE_ARG_RANGE
    # Path includes index
    assert "[1]" in v.reason


# ---------------------------------------------------------------------------
# Object bounds: required, additionalProperties, recursion
# ---------------------------------------------------------------------------


def test_required_missing() -> None:
    schema = {
        "type": "object",
        "required": ["amount"],
        "properties": {"amount": {"type": "integer"}},
    }
    v = evaluate_argument_bounds(_action({}), schema)
    assert v.decision == FirewallDecision.DENY
    assert v.code == CODE_ARG_MISSING


def test_required_present() -> None:
    schema = {
        "type": "object",
        "required": ["amount"],
        "properties": {"amount": {"type": "integer"}},
    }
    v = evaluate_argument_bounds(_action({"amount": 100}), schema)
    assert v.decision == FirewallDecision.ALLOW


def test_additional_properties_false_rejects_extras() -> None:
    schema = {
        "type": "object",
        "additionalProperties": False,
        "properties": {"amount": {"type": "integer"}},
    }
    v = evaluate_argument_bounds(
        _action({"amount": 100, "stowaway": "bad"}), schema
    )
    assert v.decision == FirewallDecision.DENY
    assert v.code == CODE_ARG_UNKNOWN


def test_additional_properties_default_true_allows_extras() -> None:
    schema = {
        "type": "object",
        "properties": {"amount": {"type": "integer"}},
    }
    v = evaluate_argument_bounds(
        _action({"amount": 100, "extra": "ok"}), schema
    )
    assert v.decision == FirewallDecision.ALLOW


def test_nested_object_validation() -> None:
    schema = {
        "type": "object",
        "properties": {
            "destination": {
                "type": "object",
                "required": ["account"],
                "properties": {
                    "account": {
                        "type": "string",
                        "pattern": r"^ACC-\d+$",
                    }
                },
            }
        },
    }
    good = {"destination": {"account": "ACC-12345"}}
    bad = {"destination": {"account": "X"}}
    assert evaluate_argument_bounds(_action(good), schema).decision == FirewallDecision.ALLOW
    v = evaluate_argument_bounds(_action(bad), schema)
    assert v.decision == FirewallDecision.DENY
    assert v.code == CODE_ARG_PATTERN
    assert "destination.account" in v.reason


# ---------------------------------------------------------------------------
# Realistic transfer_funds schema
# ---------------------------------------------------------------------------


_TRANSFER_FUNDS_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["from_account", "to_account", "amount", "currency"],
    "properties": {
        "from_account": {"type": "string", "pattern": r"^ACC-\d+$"},
        "to_account": {"type": "string", "pattern": r"^ACC-\d+$"},
        "amount": {
            "type": "number",
            "exclusiveMinimum": 0,
            "maximum": 10000,
        },
        "currency": {"enum": ["GBP", "USD", "EUR"]},
        "memo": {"type": "string", "maxLength": 200},
    },
}


def test_transfer_funds_happy_path() -> None:
    args = {
        "from_account": "ACC-12345",
        "to_account": "ACC-67890",
        "amount": 5000,
        "currency": "GBP",
    }
    v = evaluate_argument_bounds(_action(args), _TRANSFER_FUNDS_SCHEMA)
    assert v.decision == FirewallDecision.ALLOW


def test_transfer_funds_amount_above_limit() -> None:
    args = {
        "from_account": "ACC-12345",
        "to_account": "ACC-67890",
        "amount": 15000,  # > 10000
        "currency": "GBP",
    }
    v = evaluate_argument_bounds(_action(args), _TRANSFER_FUNDS_SCHEMA)
    assert v.decision == FirewallDecision.DENY
    assert v.code == CODE_ARG_RANGE


# ---------------------------------------------------------------------------
# Hypothesis property tests
# ---------------------------------------------------------------------------


@given(
    n=st.integers(min_value=-1000, max_value=1000),
    minimum=st.integers(min_value=-500, max_value=500),
    maximum=st.integers(min_value=-500, max_value=500),
)
@settings(max_examples=80, deadline=None)
def test_property_integer_min_max(n: int, minimum: int, maximum: int) -> None:
    """For any (n, min, max): the firewall verdict matches the predicate
    `min <= n <= max` (when min <= max)."""
    if minimum > maximum:
        return  # skip nonsensical schemas
    schema = {
        "type": "object",
        "properties": {
            "n": {"type": "integer", "minimum": minimum, "maximum": maximum}
        },
    }
    v = evaluate_argument_bounds(_action({"n": n}), schema)
    expected_allow = minimum <= n <= maximum
    if expected_allow:
        assert v.decision == FirewallDecision.ALLOW, (n, minimum, maximum)
    else:
        assert v.decision == FirewallDecision.DENY, (n, minimum, maximum)


@given(
    s=st.text(max_size=20),
    min_len=st.integers(min_value=0, max_value=10),
    max_len=st.integers(min_value=0, max_value=20),
)
@settings(max_examples=60, deadline=None)
def test_property_string_length(s: str, min_len: int, max_len: int) -> None:
    if min_len > max_len:
        return
    schema = {
        "type": "object",
        "properties": {
            "s": {"type": "string", "minLength": min_len, "maxLength": max_len}
        },
    }
    v = evaluate_argument_bounds(_action({"s": s}), schema)
    expected_allow = min_len <= len(s) <= max_len
    if expected_allow:
        assert v.decision == FirewallDecision.ALLOW
    else:
        assert v.decision == FirewallDecision.DENY


@given(
    items=st.lists(st.integers(min_value=0, max_value=100), max_size=10),
    min_items=st.integers(min_value=0, max_value=5),
    max_items=st.integers(min_value=0, max_value=10),
)
@settings(max_examples=50, deadline=None)
def test_property_array_size(
    items: list[int], min_items: int, max_items: int
) -> None:
    if min_items > max_items:
        return
    schema = {
        "type": "object",
        "properties": {
            "xs": {
                "type": "array",
                "minItems": min_items,
                "maxItems": max_items,
                "items": {"type": "integer", "minimum": 0, "maximum": 100},
            }
        },
    }
    v = evaluate_argument_bounds(_action({"xs": items}), schema)
    expected_allow = min_items <= len(items) <= max_items
    if expected_allow:
        assert v.decision == FirewallDecision.ALLOW
    else:
        assert v.decision == FirewallDecision.DENY


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def test_firewall_package_exports_arg_bounds() -> None:
    from verixa_runtime import firewall

    for name in (
        "CODE_ARG_ARRAY_SIZE",
        "CODE_ARG_ENUM",
        "CODE_ARG_FORMAT",
        "CODE_ARG_LENGTH",
        "CODE_ARG_MISSING",
        "CODE_ARG_MULTIPLE_OF",
        "CODE_ARG_PATTERN",
        "CODE_ARG_RANGE",
        "CODE_ARG_TYPE",
        "CODE_ARG_UNKNOWN",
        "evaluate_argument_bounds",
    ):
        assert hasattr(firewall, name), f"firewall package missing {name}"
