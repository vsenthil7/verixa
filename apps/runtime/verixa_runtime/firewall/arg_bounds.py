"""Tool Call Firewall -- argument-bounds enforcement (CP-7.2).

Validates ``action.arguments`` against a per-tool JSON-Schema-flavoured
spec. We don't pull in a full JSON Schema validator dependency; the
firewall supports the **subset** Verixa tools actually use:

  - top-level ``type`` (string | integer | number | boolean | array | object)
  - numeric bounds: minimum / maximum / exclusiveMinimum / exclusiveMaximum
                    / multipleOf
  - string bounds: minLength / maxLength / pattern (regex)
                   / format (email | uuid | date-time)
  - array bounds: minItems / maxItems / items (recursive)
  - object bounds: required (list of keys) / properties (key -> sub-schema)
                   / additionalProperties (false rejects extras; default true)
  - enum (any type)

Returns a ``FirewallVerdict``. Adds new error codes:

  - firewall.argument.missing
  - firewall.argument.unknown
  - firewall.argument.type
  - firewall.argument.range
  - firewall.argument.length
  - firewall.argument.pattern
  - firewall.argument.format
  - firewall.argument.enum
  - firewall.argument.array_size
  - firewall.argument.multiple_of

The check is total (always returns a verdict). Schemas with unknown
type strings produce ALLOW with a "schema unknown type, skipped" reason
(forward compatibility -- tomorrow's schemas don't break today's
firewall).
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Final

from verixa_runtime.firewall.allowlist import FirewallDecision, FirewallVerdict
from verixa_runtime.gateway.envelopes import GovernAction

# Error codes -- stable identifiers for log lines / customer messages
CODE_ARG_MISSING: Final[str] = "firewall.argument.missing"
CODE_ARG_UNKNOWN: Final[str] = "firewall.argument.unknown"
CODE_ARG_TYPE: Final[str] = "firewall.argument.type"
CODE_ARG_RANGE: Final[str] = "firewall.argument.range"
CODE_ARG_LENGTH: Final[str] = "firewall.argument.length"
CODE_ARG_PATTERN: Final[str] = "firewall.argument.pattern"
CODE_ARG_FORMAT: Final[str] = "firewall.argument.format"
CODE_ARG_ENUM: Final[str] = "firewall.argument.enum"
CODE_ARG_ARRAY_SIZE: Final[str] = "firewall.argument.array_size"
CODE_ARG_MULTIPLE_OF: Final[str] = "firewall.argument.multiple_of"

_FORMAT_VALIDATORS: dict[str, callable] = {}


def _register_format(name: str):
    def _decorator(fn):
        _FORMAT_VALIDATORS[name] = fn
        return fn

    return _decorator


@_register_format("email")
def _validate_email(value: str) -> bool:
    # Minimal RFC 5322-ish: at least one char, @, at least one char, ., at least one char
    return bool(re.match(r"^[^\s@]+@[^\s@]+\.[^\s@]+$", value))


@_register_format("uuid")
def _validate_uuid(value: str) -> bool:
    try:
        uuid.UUID(value)
    except (ValueError, TypeError, AttributeError):
        return False
    return True


@_register_format("date-time")
def _validate_datetime(value: str) -> bool:
    try:
        datetime.fromisoformat(value)
    except (ValueError, TypeError):
        return False
    return True


@dataclass(frozen=True, slots=True)
class _Failure:
    """Internal: a single argument-bounds failure."""

    path: str
    code: str
    message: str


def _fmt_path(path: list[str | int]) -> str:
    """Render a JSON-pointer-ish path: 'arguments.amount', 'arguments.items[2].sku'."""
    out = "arguments"
    for seg in path:
        if isinstance(seg, int):
            out += f"[{seg}]"
        else:
            out += f".{seg}"
    return out


def _check(value: Any, schema: dict[str, Any], path: list) -> _Failure | None:
    """Recursive validator. Returns first failure or None."""
    # 1. enum (applies to any type)
    if "enum" in schema:
        if value not in schema["enum"]:
            return _Failure(
                path=_fmt_path(path),
                code=CODE_ARG_ENUM,
                message=(
                    f"value not in allowed set: got {value!r}, "
                    f"expected one of {schema['enum']}"
                ),
            )

    # 2. type
    declared = schema.get("type")
    if declared is None:
        return None  # no type, no checks (besides enum above)

    if declared == "boolean":
        if not isinstance(value, bool):
            return _Failure(
                path=_fmt_path(path),
                code=CODE_ARG_TYPE,
                message=f"expected boolean, got {type(value).__name__}",
            )
        return None

    if declared == "integer":
        # bool is subclass of int; reject explicitly
        if isinstance(value, bool) or not isinstance(value, int):
            return _Failure(
                path=_fmt_path(path),
                code=CODE_ARG_TYPE,
                message=f"expected integer, got {type(value).__name__}",
            )
        return _check_numeric_bounds(value, schema, path)

    if declared == "number":
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return _Failure(
                path=_fmt_path(path),
                code=CODE_ARG_TYPE,
                message=f"expected number, got {type(value).__name__}",
            )
        return _check_numeric_bounds(value, schema, path)

    if declared == "string":
        if not isinstance(value, str):
            return _Failure(
                path=_fmt_path(path),
                code=CODE_ARG_TYPE,
                message=f"expected string, got {type(value).__name__}",
            )
        return _check_string_bounds(value, schema, path)

    if declared == "array":
        if not isinstance(value, list):
            return _Failure(
                path=_fmt_path(path),
                code=CODE_ARG_TYPE,
                message=f"expected array, got {type(value).__name__}",
            )
        return _check_array_bounds(value, schema, path)

    if declared == "object":
        if not isinstance(value, dict):
            return _Failure(
                path=_fmt_path(path),
                code=CODE_ARG_TYPE,
                message=f"expected object, got {type(value).__name__}",
            )
        return _check_object_bounds(value, schema, path)

    # Unknown type -- skip (forward compatibility)
    return None


def _check_numeric_bounds(
    value: int | float, schema: dict, path: list
) -> _Failure | None:
    if "minimum" in schema and value < schema["minimum"]:
        return _Failure(
            path=_fmt_path(path),
            code=CODE_ARG_RANGE,
            message=f"value {value} below minimum {schema['minimum']}",
        )
    if "maximum" in schema and value > schema["maximum"]:
        return _Failure(
            path=_fmt_path(path),
            code=CODE_ARG_RANGE,
            message=f"value {value} above maximum {schema['maximum']}",
        )
    if "exclusiveMinimum" in schema and value <= schema["exclusiveMinimum"]:
        return _Failure(
            path=_fmt_path(path),
            code=CODE_ARG_RANGE,
            message=(
                f"value {value} not strictly above "
                f"exclusiveMinimum {schema['exclusiveMinimum']}"
            ),
        )
    if "exclusiveMaximum" in schema and value >= schema["exclusiveMaximum"]:
        return _Failure(
            path=_fmt_path(path),
            code=CODE_ARG_RANGE,
            message=(
                f"value {value} not strictly below "
                f"exclusiveMaximum {schema['exclusiveMaximum']}"
            ),
        )
    if "multipleOf" in schema:
        m = schema["multipleOf"]
        if m == 0 or (value / m) != int(value / m):
            return _Failure(
                path=_fmt_path(path),
                code=CODE_ARG_MULTIPLE_OF,
                message=f"value {value} is not a multiple of {m}",
            )
    return None


def _check_string_bounds(
    value: str, schema: dict, path: list
) -> _Failure | None:
    if "minLength" in schema and len(value) < schema["minLength"]:
        return _Failure(
            path=_fmt_path(path),
            code=CODE_ARG_LENGTH,
            message=(
                f"string length {len(value)} below minLength "
                f"{schema['minLength']}"
            ),
        )
    if "maxLength" in schema and len(value) > schema["maxLength"]:
        return _Failure(
            path=_fmt_path(path),
            code=CODE_ARG_LENGTH,
            message=(
                f"string length {len(value)} above maxLength "
                f"{schema['maxLength']}"
            ),
        )
    if "pattern" in schema:
        if not re.search(schema["pattern"], value):
            return _Failure(
                path=_fmt_path(path),
                code=CODE_ARG_PATTERN,
                message=(
                    f"string does not match pattern {schema['pattern']!r}"
                ),
            )
    if "format" in schema:
        validator = _FORMAT_VALIDATORS.get(schema["format"])
        # Unknown formats are skipped (forward compatibility)
        if validator is not None and not validator(value):
            return _Failure(
                path=_fmt_path(path),
                code=CODE_ARG_FORMAT,
                message=(
                    f"string does not match format {schema['format']!r}"
                ),
            )
    return None


def _check_array_bounds(
    value: list, schema: dict, path: list
) -> _Failure | None:
    if "minItems" in schema and len(value) < schema["minItems"]:
        return _Failure(
            path=_fmt_path(path),
            code=CODE_ARG_ARRAY_SIZE,
            message=(
                f"array length {len(value)} below minItems "
                f"{schema['minItems']}"
            ),
        )
    if "maxItems" in schema and len(value) > schema["maxItems"]:
        return _Failure(
            path=_fmt_path(path),
            code=CODE_ARG_ARRAY_SIZE,
            message=(
                f"array length {len(value)} above maxItems "
                f"{schema['maxItems']}"
            ),
        )
    items_schema = schema.get("items")
    if items_schema is not None:
        for index, element in enumerate(value):
            failure = _check(element, items_schema, path + [index])
            if failure is not None:
                return failure
    return None


def _check_object_bounds(
    value: dict, schema: dict, path: list
) -> _Failure | None:
    properties = schema.get("properties", {})
    required = schema.get("required", [])
    additional = schema.get("additionalProperties", True)

    for req_key in required:
        if req_key not in value:
            return _Failure(
                path=_fmt_path(path + [req_key]),
                code=CODE_ARG_MISSING,
                message=f"required key {req_key!r} missing",
            )

    if additional is False:
        for key in value:
            if key not in properties:
                return _Failure(
                    path=_fmt_path(path + [key]),
                    code=CODE_ARG_UNKNOWN,
                    message=f"unknown argument {key!r}",
                )

    for key, sub_schema in properties.items():
        if key in value:
            failure = _check(value[key], sub_schema, path + [key])
            if failure is not None:
                return failure
    return None


def evaluate_argument_bounds(
    action: GovernAction, schema: dict[str, Any] | None
) -> FirewallVerdict:
    """Validate ``action.arguments`` against the tool's argument schema.

    If ``schema`` is None or empty, the firewall lets the action pass
    (the registry must still allow-list it -- this layer only enforces
    bounds when a schema is supplied).
    """
    if not schema:
        return FirewallVerdict(
            decision=FirewallDecision.ALLOW,
            reason="no argument schema declared; bounds check skipped",
        )
    failure = _check(action.arguments, schema, [])
    if failure is None:
        return FirewallVerdict(
            decision=FirewallDecision.ALLOW,
            reason="argument bounds satisfied",
        )
    return FirewallVerdict(
        decision=FirewallDecision.DENY,
        reason=f"{failure.path}: {failure.message}",
        code=failure.code,
    )
