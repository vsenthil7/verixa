"""CP-61 -- typed envelope dataclasses for SDK response parsing.

Closes the v0.4.0 roadmap promise from both SDK CHANGELOGs: customers
can opt into typed return values instead of plain ``dict[str, Any]``.

Design notes:

  - Lightweight: ``@dataclass(frozen=True)`` with no runtime dependency
    (Pydantic is intentionally not pulled in; customers who already use
    Pydantic v2 can wrap our dicts themselves).
  - Opt-in: existing SDK methods keep returning ``dict[str, Any]``; new
    helper functions ``parse_workflow_register_response`` etc. take a
    response dict and return the typed object. The next SDK MINOR
    release (v0.2.0) will add ``register(..., return_typed=True)``
    overloads; v1.0.0 will flip the default to ``return_typed=True``.
    This deprecation path is documented in CHANGELOG Unreleased.
  - Conservative: only the THREE most-used response envelopes are
    covered in this commit (Workflow register/list + AuditEntry). Other
    envelopes follow incrementally as customer demand grows -- ship
    less, ship correctly.
  - Defensive: each ``from_dict`` raises ``InvalidEnvelopeError`` with
    a path-prefix ("field {name}: ...") so a server returning an
    unexpected shape gives a debuggable error rather than KeyError.
  - Tolerant of EXTRA fields: server-side may add new optional fields
    (forward-compat); the parser ignores them. MISSING required fields
    are a hard error.

Subset shipped here:

  - WorkflowRegisterResponse
  - WorkflowSummary + WorkflowListResponse
  - AuditEntry + AuditQueryResponse

The remaining envelopes (Agent, Tool, Replay, Dossier, Webhook) get
the same treatment in subsequent commits as the type signatures land.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any


class InvalidEnvelopeError(ValueError):
    """A server response did not match the documented envelope shape.

    Use this to signal a hard parser failure (vs a network/HTTP error
    which is signalled by VerixaHttpError / VerixaConnectionError).
    Subclasses ValueError for backwards-compat with code catching that.
    """


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _require(d: dict[str, Any], key: str, name: str) -> Any:
    """Get d[key] or raise InvalidEnvelopeError(field=name)."""
    if key not in d:
        raise InvalidEnvelopeError(f"field {name}: missing from response")
    return d[key]


def _as_uuid(value: Any, name: str) -> uuid.UUID:
    if isinstance(value, uuid.UUID):
        return value
    if not isinstance(value, str):
        raise InvalidEnvelopeError(
            f"field {name}: expected uuid string, got {type(value).__name__}"
        )
    try:
        return uuid.UUID(value)
    except (ValueError, AttributeError) as e:
        raise InvalidEnvelopeError(
            f"field {name}: {value!r} is not a valid UUID"
        ) from e


def _as_datetime(value: Any, name: str) -> datetime:
    """Parse an ISO-8601 timestamp (with TZ) into datetime.

    The server emits ISO-8601 with a Z suffix or explicit offset; we
    accept both. We do NOT accept naive timestamps -- the server-side
    audit ledger requires every entry have a TZ, and we propagate that
    invariant here so customers cannot silently drop TZ info."""
    if isinstance(value, datetime):
        if value.tzinfo is None:
            raise InvalidEnvelopeError(
                f"field {name}: datetime is naive (no tzinfo); "
                f"Verixa requires TZ-aware timestamps"
            )
        return value
    if not isinstance(value, str):
        raise InvalidEnvelopeError(
            f"field {name}: expected ISO-8601 string, got {type(value).__name__}"
        )
    try:
        # Python 3.11+ accepts 'Z' in fromisoformat
        parsed = datetime.fromisoformat(value)
    except ValueError as e:
        raise InvalidEnvelopeError(
            f"field {name}: {value!r} is not a valid ISO-8601 timestamp"
        ) from e
    if parsed.tzinfo is None:
        raise InvalidEnvelopeError(
            f"field {name}: {value!r} is naive (no tzinfo); "
            f"Verixa requires TZ-aware timestamps"
        )
    return parsed


def _as_str(value: Any, name: str) -> str:
    if not isinstance(value, str):
        raise InvalidEnvelopeError(
            f"field {name}: expected string, got {type(value).__name__}"
        )
    return value


def _as_optional_str(value: Any, name: str) -> str | None:
    if value is None:
        return None
    return _as_str(value, name)


def _as_int(value: Any, name: str) -> int:
    # bool is an int subclass in Python; reject explicitly to avoid
    # silently coercing True/False into 1/0.
    if isinstance(value, bool) or not isinstance(value, int):
        raise InvalidEnvelopeError(
            f"field {name}: expected int, got {type(value).__name__}"
        )
    return value


# ---------------------------------------------------------------------------
# Workflow envelopes
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class WorkflowRegisterResponse:
    """Server response to ``POST /v1/control/workflows``."""

    workflow_id: uuid.UUID
    name: str
    description: str | None
    owner_tenant_id: uuid.UUID
    created_at: datetime

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> WorkflowRegisterResponse:
        if not isinstance(data, dict):
            raise InvalidEnvelopeError(
                f"expected dict for WorkflowRegisterResponse, "
                f"got {type(data).__name__}"
            )
        return cls(
            workflow_id=_as_uuid(_require(data, "workflow_id", "workflow_id"), "workflow_id"),
            name=_as_str(_require(data, "name", "name"), "name"),
            description=_as_optional_str(data.get("description"), "description"),
            owner_tenant_id=_as_uuid(
                _require(data, "owner_tenant_id", "owner_tenant_id"),
                "owner_tenant_id",
            ),
            created_at=_as_datetime(
                _require(data, "created_at", "created_at"), "created_at"
            ),
        )


@dataclass(frozen=True, slots=True)
class WorkflowSummary:
    """One workflow entry in a list response."""

    workflow_id: uuid.UUID
    name: str
    description: str | None
    owner_tenant_id: uuid.UUID
    created_at: datetime

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> WorkflowSummary:
        if not isinstance(data, dict):
            raise InvalidEnvelopeError(
                f"expected dict for WorkflowSummary, got {type(data).__name__}"
            )
        return cls(
            workflow_id=_as_uuid(_require(data, "workflow_id", "workflow_id"), "workflow_id"),
            name=_as_str(_require(data, "name", "name"), "name"),
            description=_as_optional_str(data.get("description"), "description"),
            owner_tenant_id=_as_uuid(
                _require(data, "owner_tenant_id", "owner_tenant_id"),
                "owner_tenant_id",
            ),
            created_at=_as_datetime(
                _require(data, "created_at", "created_at"), "created_at"
            ),
        )


@dataclass(frozen=True, slots=True)
class WorkflowListResponse:
    """Server response to ``GET /v1/control/workflows``."""

    workflows: tuple[WorkflowSummary, ...]
    total: int

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> WorkflowListResponse:
        if not isinstance(data, dict):
            raise InvalidEnvelopeError(
                f"expected dict for WorkflowListResponse, "
                f"got {type(data).__name__}"
            )
        items = _require(data, "workflows", "workflows")
        if not isinstance(items, list):
            raise InvalidEnvelopeError(
                f"field workflows: expected list, got {type(items).__name__}"
            )
        parsed = tuple(
            WorkflowSummary.from_dict(item) for item in items
        )
        return cls(
            workflows=parsed,
            total=_as_int(_require(data, "total", "total"), "total"),
        )


# ---------------------------------------------------------------------------
# Audit envelopes
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class AuditEntry:
    """One entry from the audit ledger."""

    audit_id: uuid.UUID
    workflow_id: uuid.UUID
    timestamp: datetime
    event_type: str
    payload: dict[str, Any]
    signature: str

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AuditEntry:
        if not isinstance(data, dict):
            raise InvalidEnvelopeError(
                f"expected dict for AuditEntry, got {type(data).__name__}"
            )
        payload = _require(data, "payload", "payload")
        if not isinstance(payload, dict):
            raise InvalidEnvelopeError(
                f"field payload: expected dict, got {type(payload).__name__}"
            )
        return cls(
            audit_id=_as_uuid(_require(data, "audit_id", "audit_id"), "audit_id"),
            workflow_id=_as_uuid(
                _require(data, "workflow_id", "workflow_id"), "workflow_id"
            ),
            timestamp=_as_datetime(
                _require(data, "timestamp", "timestamp"), "timestamp"
            ),
            event_type=_as_str(
                _require(data, "event_type", "event_type"), "event_type"
            ),
            payload=payload,
            signature=_as_str(
                _require(data, "signature", "signature"), "signature"
            ),
        )


@dataclass(frozen=True, slots=True)
class AuditQueryResponse:
    """Server response to ``GET /v1/control/audit``."""

    entries: tuple[AuditEntry, ...]
    total: int

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AuditQueryResponse:
        if not isinstance(data, dict):
            raise InvalidEnvelopeError(
                f"expected dict for AuditQueryResponse, "
                f"got {type(data).__name__}"
            )
        items = _require(data, "entries", "entries")
        if not isinstance(items, list):
            raise InvalidEnvelopeError(
                f"field entries: expected list, got {type(items).__name__}"
            )
        parsed = tuple(AuditEntry.from_dict(item) for item in items)
        return cls(
            entries=parsed,
            total=_as_int(_require(data, "total", "total"), "total"),
        )


__all__ = [
    "AuditEntry",
    "AuditQueryResponse",
    "InvalidEnvelopeError",
    "WorkflowListResponse",
    "WorkflowRegisterResponse",
    "WorkflowSummary",
]
